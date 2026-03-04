import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests
import pandas as pd

TZ = ZoneInfo("Europe/Paris")

# Public endpoint you are already using
PUBLIC_PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"

AREAS = os.environ.get("AREAS", "FR,GER")   # comma-separated
CURRENCY = os.environ.get("CURRENCY", "EUR")
START_DATE = os.environ.get("START_DATE", "2026-03-01")

OUT_DIR = "artifacts"


def paris_now() -> datetime:
    return datetime.now(tz=TZ)


def is_noon_paris() -> bool:
    return paris_now().hour == 12  # run during 12:xx Europe/Paris hour


def daterange(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def ensure_dirs():
    os.makedirs(os.path.join(OUT_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "tidy"), exist_ok=True)


def write_raw(prefix: str, market: str, d: date, payload: object):
    p = os.path.join(OUT_DIR, "raw", f"{prefix}_{market}_{d.isoformat()}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_utc_iso_to_paris(iso_utc: Optional[str]) -> Optional[str]:
    """Convert '...Z' (UTC) to Europe/Paris ISO string (+01/+02)."""
    if not iso_utc or not isinstance(iso_utc, str):
        return None
    s = iso_utc.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ).isoformat()


def fetch_public_prices(d: date, market: str) -> Optional[object]:
    """
    Fetch prices via public endpoint.
    Returns None if the market isn't supported publicly (4xx other than rate limits).
    """
    r = requests.get(
        PUBLIC_PRICES_URL,
        params={
            "date": d.isoformat(),
            "market": market,
            "deliveryArea": AREAS,   # "FR,GER"
            "currency": CURRENCY,
        },
        timeout=60,
    )

    # If Nord Pool doesn't support this market on the public endpoint, don't fail the job.
    if r.status_code in (400, 404):
        print(f"Market {market} not available via public endpoint (status {r.status_code}); skipping.")
        return None

    r.raise_for_status()
    return r.json()


def extract_rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    """
    Parse payload of the form:
      deliveryDateCET
      multiAreaEntries[]: { deliveryStart, deliveryEnd, entryPerArea{FR:.., GER:..}}
    Produces 1 row per (time-slice, area), with both UTC and CET/CEST timestamps.
    """
    target_areas = [a.strip().upper() for a in AREAS.split(",") if a.strip()]

    delivery_date_cet = payload.get("deliveryDateCET")
    currency = payload.get("currency", CURRENCY)
    market = payload.get("market", "Unknown")

    rows: List[Dict[str, Any]] = []
    for e in payload.get("multiAreaEntries", []) or []:
        start_utc = e.get("deliveryStart")
        end_utc = e.get("deliveryEnd")
        per_area = e.get("entryPerArea", {}) or {}

        start_paris = parse_utc_iso_to_paris(start_utc)
        end_paris = parse_utc_iso_to_paris(end_utc)

        for area in target_areas:
            if area in per_area:
                rows.append({
                    "market": market,
                    "date_cet": delivery_date_cet,
                    "area": area,
                    "deliveryStartUTC": start_utc,
                    "deliveryEndUTC": end_utc,
                    "deliveryStartCET": start_paris,
                    "deliveryEndCET": end_paris,
                    "price": per_area.get(area),
                    "currency": currency,
                })

    return rows


def write_csv(rows: List[Dict[str, Any]], filename: str):
    if not rows:
        return
    df = pd.DataFrame(rows).drop_duplicates()

    # Prefer CET ordering if present
    sort_cols = [c for c in ["date_cet", "area", "deliveryStartCET"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    df.to_csv(os.path.join(OUT_DIR, "tidy", filename), index=False)


def run(backfill: bool):
    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    all_dayahead: List[Dict[str, Any]] = []
    all_ida1: List[Dict[str, Any]] = []
    all_ida2: List[Dict[str, Any]] = []
    all_ida3: List[Dict[str, Any]] = []

    markets = [
        ("DayAhead", all_dayahead),
        ("IntradayAuction1", all_ida1),
        ("IntradayAuction2", all_ida2),
        ("IntradayAuction3", all_ida3),
    ]

    for d in dates:
        for market, bucket in markets:
            payload = fetch_public_prices(d, market)
            if payload is None:
                continue
            write_raw("prices", market, d, payload)
            bucket.extend(extract_rows_from_payload(payload))

    write_csv(all_dayahead, "dayahead_prices.csv")
    write_csv(all_ida1, "ida1_prices.csv")
    write_csv(all_ida2, "ida2_prices.csv")
    write_csv(all_ida3, "ida3_prices.csv")


def main():
    enforce_noon = os.environ.get("ENFORCE_NOON_PARIS", "1") == "1"
    backfill = os.environ.get("BACKFILL", "0") == "1"

    if enforce_noon and not backfill and not is_noon_paris():
        print("Not 12:00 Europe/Paris; exiting.")
        return

    run(backfill=backfill)
    print("Done.")


if __name__ == "__main__":
    main()
