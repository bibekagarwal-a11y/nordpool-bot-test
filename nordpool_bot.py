import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import requests
import pandas as pd

TZ = ZoneInfo("Europe/Paris")

# Public Nord Pool dataportal APIs (no auth)
PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
INTRADAY_STATS_URL = "https://dataportal-api.nordpoolgroup.com/api/IntradayMarketStatistics"

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
    """
    Convert '...Z' (UTC) to Europe/Paris ISO string (+01:00 or +02:00).
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


def walk_json(x: Any):
    """Yield every dict found in a nested JSON structure."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk_json(v)
    elif isinstance(x, list):
        for it in x:
            yield from walk_json(it)


def fetch_prices(d: date, market: str) -> object:
    """
    Fetch auction prices via DayAheadPrices endpoint, using market codes discovered from the portal.
    Examples discovered:
      market=SIDC_IntradayAuction1/2/3
      market=DayAhead (works for you already)
    """
    r = requests.get(
        PRICES_URL,
        params={
            "date": d.isoformat(),
            "market": market,
            "deliveryArea": AREAS,   # "FR,GER"
            "currency": CURRENCY,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def extract_auction_rows(payload: Any) -> List[Dict[str, Any]]:
    """
    Expected shape (matches your DayAhead payload):
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


def fetch_intraday_market_statistics(d: date, area: str) -> object:
    """
    Fetch continuous intraday market statistics for one area.
    Discovered endpoints:
      /api/IntradayMarketStatistics?date=YYYY-MM-DD&deliveryArea=FR|GER
    """
    r = requests.get(
        INTRADAY_STATS_URL,
        params={"date": d.isoformat(), "deliveryArea": area},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def extract_vwap_rows(stats_payload: Any, area: str, d: date) -> List[Dict[str, Any]]:
    """
    The portal's IntradayMarketStatistics JSON schema can vary, so we extract VWAP robustly.

    Strategy:
    - Traverse all dicts
    - Find dicts that contain a time interval (deliveryStart/deliveryEnd OR start/end)
    - And contain a numeric VWAP-like field (key contains 'vwap' case-insensitive)

    This produces rows:
      area, deliveryStartUTC/CET, deliveryEndUTC/CET, vwap
    """
    def pick_time(obj: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        start = obj.get("deliveryStart") or obj.get("startTime") or obj.get("start")
        end = obj.get("deliveryEnd") or obj.get("endTime") or obj.get("end")
        if isinstance(start, str) and isinstance(end, str):
            return start, end
        return None, None

    def find_vwap_value(obj: Dict[str, Any]) -> Optional[float]:
        # Prefer exact-ish keys first
        preferred_keys = ["vwap", "VWAP", "vwapPrice", "vwap_price", "volumeWeightedAveragePrice"]
        for k in preferred_keys:
            if k in obj and isinstance(obj[k], (int, float)):
                return float(obj[k])

        # Then any key containing 'vwap'
        for k, v in obj.items():
            if isinstance(k, str) and "vwap" in k.lower() and isinstance(v, (int, float)):
                return float(v)

        return None

    rows: List[Dict[str, Any]] = []
    seen = set()

    for obj in walk_json(stats_payload):
        start_utc, end_utc = pick_time(obj)
        if not start_utc or not end_utc:
            continue

        vwap = find_vwap_value(obj)
        if vwap is None:
            continue

        key = (area, start_utc, end_utc, vwap)
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "market": "IntradayContinuousVWAP",
            "date_cet": d.isoformat(),
            "area": area,
            "deliveryStartUTC": start_utc,
            "deliveryEndUTC": end_utc,
            "deliveryStartCET": parse_utc_iso_to_paris(start_utc),
            "deliveryEndCET": parse_utc_iso_to_paris(end_utc),
            "vwap": vwap,
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

    # Auctions
    all_dayahead: List[Dict[str, Any]] = []
    all_ida1: List[Dict[str, Any]] = []
    all_ida2: List[Dict[str, Any]] = []
    all_ida3: List[Dict[str, Any]] = []

    # Continuous VWAP
    all_vwap: List[Dict[str, Any]] = []

    auction_markets = [
        ("DayAhead", all_dayahead),
        ("SIDC_IntradayAuction1", all_ida1),
        ("SIDC_IntradayAuction2", all_ida2),
        ("SIDC_IntradayAuction3", all_ida3),
    ]

    target_areas = [a.strip().upper() for a in AREAS.split(",") if a.strip()]

    for d in dates:
        # Auction prices
        for market, bucket in auction_markets:
            payload = fetch_prices(d, market)
            write_raw("prices", market, d, payload)
            bucket.extend(extract_auction_rows(payload))

        # Continuous VWAP (per area)
        for area in target_areas:
            stats = fetch_intraday_market_statistics(d, area)
            write_raw("intraday_stats", f"{area}", d, stats)
            all_vwap.extend(extract_vwap_rows(stats, area, d))

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
