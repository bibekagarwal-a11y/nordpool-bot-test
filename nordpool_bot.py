import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import requests
import pandas as pd

TZ = ZoneInfo("Europe/Paris")

PRICES_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
INTRADAY_STATS_URL = "https://dataportal-api.nordpoolgroup.com/api/IntradayMarketStatistics"

AREAS = os.environ.get("AREAS", "FR,GER")
CURRENCY = os.environ.get("CURRENCY", "EUR")
START_DATE = os.environ.get("START_DATE", "2026-03-01")

OUT_DIR = "artifacts"


def paris_now() -> datetime:
    return datetime.now(tz=TZ)


def is_noon_paris() -> bool:
    return paris_now().hour == 12


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
    if not iso_utc:
        return None
    s = iso_utc
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt.astimezone(TZ).isoformat()


def fetch_prices(d: date, market: str) -> object:
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
    target_areas = [a.strip().upper() for a in AREAS.split(",")]

    delivery_date_cet = payload.get("deliveryDateCET")
    currency = payload.get("currency")
    market = payload.get("market")

    rows: List[Dict[str, Any]] = []

    for e in payload.get("multiAreaEntries", []):
        start_utc = e.get("deliveryStart")
        end_utc = e.get("deliveryEnd")
        per_area = e.get("entryPerArea", {})

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
    r = requests.get(
        INTRADAY_STATS_URL,
        params={
            "date": d.isoformat(),
            "deliveryArea": area,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def extract_vwap_qh_rows(payload: Any, area: str) -> List[Dict[str, Any]]:
    """
    Extract ONLY quarter-hour contracts (QH) VWAP
    """

    rows: List[Dict[str, Any]] = []

    delivery_date_cet = payload.get("deliveryDateCET")

    for c in payload.get("contracts", []):

        contract_name = c.get("contractName")

        # keep ONLY quarter hour contracts
        if not contract_name or not contract_name.startswith("QH-"):
            continue

        start_utc = c.get("deliveryStart")
        end_utc = c.get("deliveryEnd")

        rows.append(
            {
                "market": "IntradayContinuousVWAP",
                "date_cet": delivery_date_cet,
                "area": area,
                "contractName": contract_name,
                "deliveryStartUTC": start_utc,
                "deliveryEndUTC": end_utc,
                "deliveryStartCET": parse_utc_iso_to_paris(start_utc),
                "deliveryEndCET": parse_utc_iso_to_paris(end_utc),
                "vwap": c.get("averagePrice"),
                "volume": c.get("volume"),
            }
        )

    return rows


def write_csv(rows: List[Dict[str, Any]], filename: str):

    if not rows:
        return

    df = pd.DataFrame(rows).drop_duplicates()

    if "deliveryStartCET" in df.columns:
        df = df.sort_values(["date_cet", "area", "deliveryStartCET"])

    df.to_csv(os.path.join(OUT_DIR, "tidy", filename), index=False)


def run(backfill: bool):

    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)

    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    all_dayahead = []
    all_ida1 = []
    all_ida2 = []
    all_ida3 = []
    all_vwap = []

    auction_markets = [
        ("DayAhead", all_dayahead),
        ("SIDC_IntradayAuction1", all_ida1),
        ("SIDC_IntradayAuction2", all_ida2),
        ("SIDC_IntradayAuction3", all_ida3),
    ]

    areas = [a.strip().upper() for a in AREAS.split(",")]

    for d in dates:

        # auctions
        for market, bucket in auction_markets:

            payload = fetch_prices(d, market)

            write_raw("prices", market, d, payload)

            bucket.extend(extract_auction_rows(payload))

        # intraday continuous VWAP
        for area in areas:

            stats = fetch_intraday_stats(d, area)

            write_raw("intraday_stats", area, d, stats)

            all_vwap.extend(extract_vwap_qh_rows(stats, area))

    write_csv(all_dayahead, "dayahead_prices.csv")
    write_csv(all_ida1, "ida1_prices.csv")
    write_csv(all_ida2, "ida2_prices.csv")
    write_csv(all_ida3, "ida3_prices.csv")
    write_csv(all_vwap, "intraday_continuous_vwap_qh.csv")


def main():

    enforce_noon = os.environ.get("ENFORCE_NOON_PARIS", "1") == "1"
    backfill = os.environ.get("BACKFILL", "0") == "1"

    if enforce_noon and not backfill and not is_noon_paris():
        print("Not 12:00 Paris time — exiting")
        return

    run(backfill=backfill)

    print("Done")


if __name__ == "__main__":
    main()
