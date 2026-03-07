import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests
import pandas as pd

# Timezone used throughout the script (Europe/Paris)
TZ = ZoneInfo("Europe/Paris")

# Public Nord Pool data portal APIs (no authentication required)
PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
INTRADAY_STATS_URL = "https://dataportal-api.nordpoolgroup.com/api/IntradayMarketStatistics"

# Areas (delivery zones) to query; default to France and Germany
AREAS = os.environ.get("AREAS", "FR,GER")
# Currency for all prices
CURRENCY = os.environ.get("CURRENCY", "EUR")
# Start date (inclusive) for historical backfills
START_DATE = os.environ.get("START_DATE", "2026-03-01")

# Permanent datasets are written into this directory
DATA_DIR = "data"

# Raw JSON (debugging) will be stored as GitHub Actions artifacts
ARTIFACTS_RAW_DIR = os.path.join("artifacts", "raw")

def paris_now() -> datetime:
    """Return current datetime in Europe/Paris timezone."""
    return datetime.now(tz=TZ)

def is_noon_paris() -> bool:
    """Return True if the current hour in Paris is 12 (noon)."""
    return paris_now().hour == 12

def daterange(d0: date, d1: date):
    """Generate a sequence of dates from d0 to d1 inclusive."""
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)

def ensure_dirs() -> None:
    """Ensure DATA_DIR and ARTIFACTS_RAW_DIR exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ARTIFACTS_RAW_DIR, exist_ok=True)

def write_raw(prefix: str, market: str, d: date, payload: object) -> None:
    """
    Save raw JSON payloads for debugging.
    These files will be saved in artifacts/raw but not committed.
    """
    ensure_dirs()
    path = os.path.join(ARTIFACTS_RAW_DIR, f"{prefix}_{market}_{d.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def parse_utc_iso_to_paris(iso_utc: Optional[str]) -> Optional[str]:
    """
    Convert an ISO 8601 string in UTC (with 'Z') to an ISO string in Europe/Paris timezone.
    Returns None if input is None.
    """
    if not iso_utc:
        return None
    s = iso_utc
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    return d.astimezone(TZ).isoformat()

def fetch_prices(d: date, market: str) -> object:
    """
    Fetch day‑ahead or SIDC intraday auction prices for a given date and market.
    """
    r = requests.get(
        PRICES_URL,
        params={
            "date": d.isoformat(),
            "market": market,
            "deliveryArea": AREAS,
            "currency": CURRENCY,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()

def extract_auction_rows(payload: Any) -> List[Dict[str, Any]]:
    """
    Parse auction price payload into a list of rows keyed by area.
    Each row includes delivery dates/times in UTC and CET and the price.
    """
    target_areas = [a.strip().upper() for a in AREAS.split(",") if a.strip()]

    delivery_date_cet = payload.get("deliveryDateCET")
    currency = payload.get("currency", CURRENCY)
    market = payload.get("market", "Unknown")

    rows: List[Dict[str, Any]] = []

    for entry in payload.get("multiAreaEntries", []) or []:
        start_utc = entry.get("deliveryStart")
        end_utc = entry.get("deliveryEnd")
        per_area = entry.get("entryPerArea", {}) or {}

        start_cet = parse_utc_iso_to_paris(start_utc)
        end_cet = parse_utc_iso_to_paris(end_utc)

        for area in target_areas:
            if area in per_area:
                rows.append(
                    {
                        "market": market,
                        "date_cet": delivery_date_cet,
                        "area": area,
                        "deliveryStartUTC": start_utc,
                        "deliveryEndUTC": end_utc,
                        "deliveryStartCET": start_cet,
                        "deliveryEndCET": end_cet,
                        "price": per_area[area],
                        "currency": currency,
                    }
                )
    return rows

def fetch_intraday_stats(d: date, area: str) -> object:
    """
    Fetch continuous intraday market statistics (VWAP and volumes) for a given date and delivery area.
    """
    r = requests.get(
        INTRADAY_STATS_URL,
        params={"date": d.isoformat(), "deliveryArea": area},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()

def extract_vwap_qh_rows(payload: Any, area: str) -> List[Dict[str, Any]]:
    """
    Extract quarter‑hour continuous intraday VWAP data.  Only contracts whose name starts
    with 'QH-' are included.  Times returned by the API are in UTC.
    """
    rows: List[Dict[str, Any]] = []
    delivery_date_cet = payload.get("deliveryDateCET", None)
    area_payload = (payload.get("deliveryArea") or area).strip().upper()

    for c in payload.get("contracts", []) or []:
        name = c.get("contractName")
        if not name or not name.startswith("QH-"):
            continue
        start_utc = c.get("deliveryStart")
        end_utc = c.get("deliveryEnd")
        vwap = c.get("averagePrice")
        # Skip rows missing times or invalid VWAP values
        if not (start_utc and end_utc) or not isinstance(vwap, (int, float)):
            continue

        rows.append(
            {
                "market": "IntradayContinuousVWAP",
                "date_cet": delivery_date_cet,
                "area": area_payload,
                "contractName": name,
                "contractId": c.get("contractId"),
                "deliveryStartUTC": start_utc,
                "deliveryEndUTC": end_utc,
                "deliveryStartCET": parse_utc_iso_to_paris(start_utc),
                "deliveryEndCET": parse_utc_iso_to_paris(end_utc),
                "vwap": float(vwap),
                "volume": c.get("volume"),
                "priceUnit": payload.get("priceUnit"),
                "volumeUnit": payload.get("volumeUnit"),
            }
        )
    return rows

def upsert_csv(rows: List[Dict[str, Any]], filename: str, sort_cols: List[str]) -> None:
    """
    Merge new rows into data/<filename>, drop duplicates, sort, and write back.
    """
    if not rows:
        return

    ensure_dirs()
    path = os.path.join(DATA_DIR, filename)
    new_df = pd.DataFrame(rows)

    if os.path.exists(path):
        old_df = pd.read_csv(path)
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    df = df.drop_duplicates()

    # Only sort on columns that actually exist in the DataFrame
    existing_sort_cols = [c for c in sort_cols if c in df.columns]
    if existing_sort_cols:
        df = df.sort_values(existing_sort_cols)

    df.to_csv(path, index=False)

def run(backfill: bool) -> None:
    """
    Execute the data collection for either a single day (yesterday) or a range
    of dates if backfilling.
    """
    ensure_dirs()
    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    all_dayahead: List[Dict[str, Any]] = []
    all_ida1: List[Dict[str, Any]] = []
    all_ida2: List[Dict[str, Any]] = []
    all_ida3: List[Dict[str, Any]] = []
    all_vwap_qh: List[Dict[str, Any]] = []

    auction_markets = [
        ("DayAhead", all_dayahead),
        ("SIDC IntradayAuction1", all_ida1),
        ("SIDC IntradayAuction2", all_ida2),
        ("SIDC IntradayAuction3", all_ida3),
    ]

    areas = [a.strip().upper() for a in AREAS.split(",") if a.strip()]

    for d in dates:
        # Auction markets (day‑ahead and SIDC intraday auctions)
        for market, bucket in auction_markets:
            payload = fetch_prices(d, market)
            write_raw("prices", market, d, payload)
            bucket.extend(extract_auction_rows(payload))

        # Continuous intraday VWAP (quarter‑hour only)
        for area in areas:
            stats = fetch_intraday_stats(d, area)
            write_raw("intraday_stats", area, d, stats)
            all_vwap_qh.extend(extract_vwap_qh_rows(stats, area))

    # Merge new data into the CSV files in the data directory
    upsert_csv(all_dayahead, "dayahead_prices.csv", ["date_cet", "area", "deliveryStartCET"])
    upsert_csv(all_ida1, "ida1_prices.csv", ["date_cet", "area", "deliveryStartCET"])
    upsert_csv(all_ida2, "ida2_prices.csv", ["date_cet", "area", "deliveryStartCET"])
    upsert_csv(all_ida3, "ida3_prices.csv", ["date_cet", "area", "deliveryStartCET"])
    upsert_csv(all_vwap_qh, "intraday_continuous_vwap_qh.csv", ["date_cet", "area", "deliveryStartCET"])

def main() -> None:
    """
    Entry point.  Optionally enforce running only at noon Paris time, and handle backfill.
    """
    enforce_noon = os.environ.get("ENFORCE_NOON_PARIS", "1") == "1"
    backfill = os.environ.get("BACKFILL", "0") == "1"

    # Scheduled runs: only run at 12:00 Paris time if enforced
    if enforce_noon and not backfill and not is_noon_paris():
        print("Not 12:00 Paris time – exiting")
        return

    run(backfill=backfill)
    print("Done")

if __name__ == "__main__":
    main()
