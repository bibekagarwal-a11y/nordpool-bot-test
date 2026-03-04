import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests
import pandas as pd

TZ = ZoneInfo("Europe/Paris")

# Public day-ahead endpoint (no auth)
DAYAHEAD_PUBLIC_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"

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


def write_raw(prefix: str, d: date, payload: object):
    p = os.path.join(OUT_DIR, "raw", f"{prefix}_{d.isoformat()}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_utc_iso_to_paris(iso_utc: Optional[str]) -> Optional[str]:
    """
    Convert '2026-03-01T00:00:00Z' -> '2026-03-01T01:00:00+01:00' (CET)
    Handles DST automatically (CEST).
    """
    if not iso_utc or not isinstance(iso_utc, str):
        return None
    s = iso_utc.strip()
    if not s:
        return None
    # Support "Z"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # If it ever comes without tz, assume UTC (defensive)
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ).isoformat()


def fetch_dayahead(d: date) -> object:
    r = requests.get(
        DAYAHEAD_PUBLIC_URL,
        params={
            "date": d.isoformat(),
            "market": "DayAhead",
            "deliveryArea": AREAS,   # "FR,GER"
            "currency": CURRENCY,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def extract_dayahead_rows(payload: Any) -> List[Dict[str, Any]]:
    """
    Payload shape (confirmed from your sample):
      deliveryDateCET
      multiAreaEntries[]: { deliveryStart, deliveryEnd, entryPerArea{FR:.., GER:..}}
    Produces 1 row per (time-slice, area), with both UTC and CET/CEST timestamps.
    """
    target_areas = [a.strip().upper() for a in AREAS.split(",") if a.strip()]

    delivery_date_cet = payload.get("deliveryDateCET")
    currency = payload.get("currency", CURRENCY)
    market = payload.get("market", "DayAhead")

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


# --------------------------
# Optional (paid) additions
# --------------------------
def try_fetch_ida_and_vwap(_d: date) -> List[Dict[str, Any]]:
    """
    IDA1/IDA2/IDA3 and continuous VWAP are typically behind paid APIs/subscriptions.
    We intentionally do nothing unless you configure a working endpoint + auth.

    When you have credentials, we can implement:
    - IDA1/IDA2/IDA3 prices (auction results)
    - Intraday continuous VWAP (often from hourly statistics or trade feeds)

    Return extra rows to append to CSV(s).
    """
    return []


def run(backfill: bool):
    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    dayahead_rows: List[Dict[str, Any]] = []
    extra_rows: List[Dict[str, Any]] = []

    for d in dates:
        payload = fetch_dayahead(d)
        write_raw("dayahead", d, payload)
        dayahead_rows.extend(extract_dayahead_rows(payload))

        # Optional (won't error)
        extra_rows.extend(try_fetch_ida_and_vwap(d))

    # Write tidy outputs
    if dayahead_rows:
        df = pd.DataFrame(dayahead_rows).drop_duplicates()
        df = df.sort_values(["date_cet", "area", "deliveryStartCET"])
        df.to_csv(os.path.join(OUT_DIR, "tidy", "dayahead_prices.csv"), index=False)
        df.to_json(
            os.path.join(OUT_DIR, "tidy", "dayahead_prices.json"),
            orient="records",
            force_ascii=False,
            indent=2,
        )

    if extra_rows:
        df2 = pd.DataFrame(extra_rows).drop_duplicates()
        df2.to_csv(os.path.join(OUT_DIR, "tidy", "extra_markets.csv"), index=False)


def main():
    enforce_noon = os.environ.get("ENFORCE_NOON_PARIS", "1") == "1"
    backfill = os.environ.get("BACKFILL", "0") == "1"

    # For scheduled runs: only run at noon Paris time
    if enforce_noon and not backfill and not is_noon_paris():
        print("Not 12:00 Europe/Paris; exiting.")
        return

    run(backfill=backfill)
    print("Done.")


if __name__ == "__main__":
    main()
