import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests
import pandas as pd

TZ = ZoneInfo("Europe/Paris")

# Public endpoint (no auth) used by the Data Portal for day-ahead (and sometimes other auctions)
PUBLIC_PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"

# Authenticated Market Data API v2 (often subscription-gated for intraday statistics like VWAP)
V2_API_BASE = "https://data-api.nordpoolgroup.com"

AREAS = os.environ.get("AREAS", "FR,GER")          # comma-separated
CURRENCY = os.environ.get("CURRENCY", "EUR")
START_DATE = os.environ.get("START_DATE", "2026-03-01")

OUT_DIR = "artifacts"

# Optional: for VWAP (and possibly IDA if your access requires it)
# Put this in GitHub Secrets: NORDPOOL_API_KEY
NORDPOOL_API_KEY = os.environ.get("NORDPOOL_API_KEY", "").strip()

# How to send the key: "bearer" or "x-api-key"
# If you don't know, try bearer first; if still 401, try x-api-key.
NORDPOOL_AUTH_MODE = os.environ.get("NORDPOOL_AUTH_MODE", "bearer").strip().lower()


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
    """
    Convert '2026-03-01T00:00:00Z' -> Europe/Paris ISO string (+01:00 or +02:00).
    DST handled automatically.
    """
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
    Fetch prices via public endpoint. Returns None if market unsupported (400/404).
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

    if r.status_code in (400, 404):
        print(f"[INFO] Market {market} not available via public endpoint (status {r.status_code}); skipping.")
        return None

    r.raise_for_status()
    return r.json()


def extract_price_rows(payload: Any) -> List[Dict[str, Any]]:
    """
    Works with the JSON shape you shared:
      deliveryDateCET
      market
      multiAreaEntries[]: { deliveryStart, deliveryEnd, entryPerArea{FR:.., GER:..}}
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


def v2_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NordPoolBot/1.0)",
        "Accept": "application/json",
    })
    if NORDPOOL_API_KEY:
        if NORDPOOL_AUTH_MODE == "x-api-key":
            s.headers.update({"x-api-key": NORDPOOL_API_KEY})
        else:
            s.headers.update({"Authorization": f"Bearer {NORDPOOL_API_KEY}"})
    return s


def fetch_v2_intraday_hourly_vwap(d: date) -> Optional[object]:
    """
    Intraday VWAP typically comes from Intraday statistics endpoints (subscription-gated).
    We try Market Data API v2:
      /api/v2/Intraday/HourlyStatistics/ByAreas
    If unauthorized, we skip (do not fail the run).
    """
    if not NORDPOOL_API_KEY:
        print("[INFO] No NORDPOOL_API_KEY set; skipping continuous VWAP.")
        return None

    s = v2_session()
    url = f"{V2_API_BASE}/api/v2/Intraday/HourlyStatistics/ByAreas"
    r = s.get(url, params={"areas": AREAS, "date": d.isoformat()}, timeout=60)

    if r.status_code in (401, 403):
        print(f"[WARN] VWAP endpoint unauthorized ({r.status_code}). Skipping VWAP. "
              f"Try setting NORDPOOL_AUTH_MODE to 'x-api-key' or ensure subscription.")
        return None

    # Some accounts may get 400 if params differ; skip rather than fail.
    if r.status_code in (400, 404):
        print(f"[WARN] VWAP endpoint not available ({r.status_code}). Skipping VWAP.")
        return None

    r.raise_for_status()
    return r.json()


def extract_vwap_rows(payload: Any) -> List[Dict[str, Any]]:
    """
    Expected v2 shape (approx):
      [ { deliveryArea, hourlyStatistics: [ { deliveryStart, deliveryEnd, averagePrice, volume, ...}, ...] }, ... ]
    We store VWAP in column vwap.
    """
    rows: List[Dict[str, Any]] = []
    if not isinstance(payload, list):
        return rows

    for area_obj in payload:
        area = (area_obj.get("deliveryArea") or area_obj.get("area") or "").strip().upper()
        stats = area_obj.get("hourlyStatistics") or area_obj.get("statistics") or []
        for h in stats:
            start_utc = h.get("deliveryStart")
            end_utc = h.get("deliveryEnd")
            rows.append({
                "market": "IntradayContinuousVWAP",
                "area": area,
                "deliveryStartUTC": start_utc,
                "deliveryEndUTC": end_utc,
                "deliveryStartCET": parse_utc_iso_to_paris(start_utc),
                "deliveryEndCET": parse_utc_iso_to_paris(end_utc),
                "vwap": h.get("averagePrice"),
                "volume": h.get("volume"),
            })

    return rows


def write_csv(rows: List[Dict[str, Any]], filename: str):
    if not rows:
        return
    df = pd.DataFrame(rows).drop_duplicates()
    sort_cols = [c for c in ["date_cet", "area", "deliveryStartCET"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    df.to_csv(os.path.join(OUT_DIR, "tidy", filename), index=False)


def run(backfill: bool):
    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    # Auction outputs
    all_dayahead: List[Dict[str, Any]] = []
    all_ida1: List[Dict[str, Any]] = []
    all_ida2: List[Dict[str, Any]] = []
    all_ida3: List[Dict[str, Any]] = []

    # Continuous VWAP output
    all_vwap: List[Dict[str, Any]] = []

    auction_markets = [
        ("DayAhead", all_dayahead),
        ("IntradayAuction1", all_ida1),
        ("IntradayAuction2", all_ida2),
        ("IntradayAuction3", all_ida3),
    ]

    for d in dates:
        # Auctions (public if available)
        for market, bucket in auction_markets:
            payload = fetch_public_prices(d, market)
            if payload is None:
                continue
            write_raw("prices", market, d, payload)
            bucket.extend(extract_price_rows(payload))

        # Continuous VWAP (v2, likely subscription)
        vwap_payload = fetch_v2_intraday_hourly_vwap(d)
        if vwap_payload is not None:
            write_raw("intraday_vwap", "HourlyStatisticsByAreas", d, vwap_payload)
            all_vwap.extend(extract_vwap_rows(vwap_payload))

    write_csv(all_dayahead, "dayahead_prices.csv")
    write_csv(all_ida1, "ida1_prices.csv")
    write_csv(all_ida2, "ida2_prices.csv")
    write_csv(all_ida3, "ida3_prices.csv")
    write_csv(all_vwap, "intraday_continuous_vwap.csv")


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
