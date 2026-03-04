import os
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

TZ = ZoneInfo("Europe/Paris")

API_BASE = os.environ.get("NORDPOOL_API_BASE", "https://data-api.nordpoolgroup.com")
API_KEY = os.environ.get("NORDPOOL_API_KEY", "")  # optional

AREAS = os.environ.get("AREAS", "FR,GER")
CURRENCY = os.environ.get("CURRENCY", "EUR")
START_DATE = os.environ.get("START_DATE", "2026-03-01")

# Default markets (names are per the API enum; if you get 400, adjust here)
AUCTION_MARKETS = os.environ.get(
    "AUCTION_MARKETS",
    "DayAhead,IntradayAuction1,IntradayAuction2,IntradayAuction3"
)

OUT_DIR = "artifacts"

def paris_now() -> datetime:
    return datetime.now(tz=TZ)

def is_noon_paris() -> bool:
    now = paris_now()
    return now.hour == 12  # run only during the 12:xx hour

def daterange(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)

def session() -> requests.Session:
    s = requests.Session()
    # A normal browser-ish UA helps some gateways
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; NordPoolBot/1.0)",
        "Accept": "application/json",
    })
    if API_KEY:
        # API uses standard auth patterns; if your account uses another header name,
        # change it here.
        s.headers.update({"Authorization": f"Bearer {API_KEY}"})
    return s

def fetch_json(s: requests.Session, path: str, params: dict) -> object:
    url = f"{API_BASE}{path}"
    r = s.get(url, params=params, timeout=60)
    # Make debugging easier:
    if r.status_code in (401, 403):
        raise RuntimeError(
            f"Auth/permission error {r.status_code} for {r.url}. "
            f"If you have a subscription/API key, set secret NORDPOOL_API_KEY."
        )
    r.raise_for_status()
    return r.json()

def ensure_dirs():
    os.makedirs(os.path.join(OUT_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "tidy"), exist_ok=True)

def write_raw(kind: str, market: str, d: date, payload: object):
    p = os.path.join(OUT_DIR, "raw", f"{kind}_{market}_{d.isoformat()}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def normalize_auction_prices(payload, market: str, d: date) -> list[dict]:
    """
    payload is an array of ApiAuctionPrice objects (per swagger).
    We'll try to be robust to minor schema differences.
    """
    rows = []
    if not isinstance(payload, list):
        return rows

    for area_obj in payload:
        area = area_obj.get("deliveryArea") or area_obj.get("area")
        if not area:
            continue

        prices = area_obj.get("prices") or []
        for p in prices:
            rows.append({
                "market": market,
                "date_cet": d.isoformat(),
                "area": area,
                "deliveryStart": p.get("deliveryStart") or p.get("startTime"),
                "deliveryEnd": p.get("deliveryEnd") or p.get("endTime"),
                "price": p.get("price"),
                "currency": CURRENCY,
                "status": area_obj.get("status"),
            })
    return rows

def normalize_intraday_vwap(payload, d: date) -> list[dict]:
    """
    payload is an array of ApiDeliveryAreaMarketHourlyStatistic.
    We only keep VWAP == averagePrice.
    """
    rows = []
    if not isinstance(payload, list):
        return rows

    for area_obj in payload:
        area = area_obj.get("deliveryArea") or area_obj.get("area")
        stats = area_obj.get("hourlyStatistics") or area_obj.get("statistics") or []

        for h in stats:
            rows.append({
                "market": "IntradayContinuousVWAP",
                "date_cet": d.isoformat(),
                "area": area,
                "deliveryStart": h.get("deliveryStart"),
                "deliveryEnd": h.get("deliveryEnd"),
                "vwap": h.get("averagePrice"),  # volume-weighted average price
                "priceUnit": area_obj.get("priceUnit"),
                "volume": h.get("volume"),
            })
    return rows

def run(backfill: bool):
    ensure_dirs()
    s = session()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)

    # If not backfilling, do only yesterday
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    markets = [m.strip() for m in AUCTION_MARKETS.split(",") if m.strip()]
    areas = AREAS

    auction_rows = []
    vwap_rows = []

    for d in dates:
        # Auction prices: DayAhead + IDA1/2/3
        for market in markets:
            payload = fetch_json(
                s,
                "/api/v2/Auction/Prices/ByAreas",
                {"market": market, "areas": areas, "currency": CURRENCY, "date": d.isoformat()},
            )
            write_raw("auction_prices", market, d, payload)
            auction_rows.extend(normalize_auction_prices(payload, market, d))

        # Intraday VWAP (continuous proxy): hourly statistics
        payload = fetch_json(
            s,
            "/api/v2/Intraday/HourlyStatistics/ByAreas",
            {"areas": areas, "date": d.isoformat()},
        )
        write_raw("intraday_hourly_stats", "ByAreas", d, payload)
        vwap_rows.extend(normalize_intraday_vwap(payload, d))

    if auction_rows:
        pd.DataFrame(auction_rows).drop_duplicates().to_csv(
            os.path.join(OUT_DIR, "tidy", "auction_prices.csv"), index=False
        )

    if vwap_rows:
        pd.DataFrame(vwap_rows).drop_duplicates().to_csv(
            os.path.join(OUT_DIR, "tidy", "intraday_vwap.csv"), index=False
        )

def main():
    # Hourly workflow → run only at 12:00 Europe/Paris
    enforce_noon = os.environ.get("ENFORCE_NOON_PARIS", "1") == "1"
    backfill = os.environ.get("BACKFILL", "0") == "1"

    if enforce_noon and not backfill and not is_noon_paris():
        print("Not 12:00 Europe/Paris; exiting.")
        return

    run(backfill=backfill)
    print("Done.")

if __name__ == "__main__":
    main()
