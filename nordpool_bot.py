import os
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

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
    now = paris_now()
    return now.hour == 12  # run during 12:xx Europe/Paris hour

def daterange(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)

def ensure_dirs():
    os.makedirs(os.path.join(OUT_DIR, "raw"), exist_ok=True)

def write_raw(kind: str, d: date, payload: object):
    p = os.path.join(OUT_DIR, "raw", f"{kind}_{d.isoformat()}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

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

def run(backfill: bool):
    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)

    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    for d in dates:
        payload = fetch_dayahead(d)
        write_raw("dayahead", d, payload)

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
