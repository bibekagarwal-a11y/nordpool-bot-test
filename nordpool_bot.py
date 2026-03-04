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
    os.makedirs(os.path.join(OUT_DIR, "tidy"), exist_ok=True)

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

def walk_json(x: Any):
    """Yield every dict found in a nested JSON structure."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk_json(v)
    elif isinstance(x, list):
        for it in x:
            yield from walk_json(it)

def normalize_area_code(area: str) -> str:
    area = area.strip()
    if area.upper() in ("FR", "GER"):
        return area.upper()
    return area

def extract_rows_from_payload(payload: Any, delivery_date: date) -> List[Dict[str, Any]]:
    """
    Robust extraction: find dicts that look like price points containing:
      - area (deliveryArea/area)
      - timestamp (deliveryStart/startTime/time/dateTime)
      - price (price/value)
    """
    target_areas = {a.strip().upper() for a in AREAS.split(",") if a.strip()}

    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()

    for d in walk_json(payload):
        area = d.get("deliveryArea") or d.get("area") or d.get("delivery_area")
        if not isinstance(area, str):
            continue
        area_norm = normalize_area_code(area)
        if area_norm.upper() not in target_areas:
            continue

        # price
        price = d.get("price")
        if price is None:
            price = d.get("value")
        if price is None:
            continue

        # time (string)
        t = d.get("deliveryStart") or d.get("startTime") or d.get("time") or d.get("dateTime")
        if not isinstance(t, str) or not t.strip():
            continue

        # end time is optional
        t_end = d.get("deliveryEnd") or d.get("endTime")

        key = (area_norm.upper(), t, str(price))
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "market": "DayAhead",
            "date_cet": delivery_date.isoformat(),
            "area": area_norm.upper(),
            "deliveryStart": t,
            "deliveryEnd": t_end if isinstance(t_end, str) else None,
            "price": price,
            "currency": CURRENCY,
        })

    return rows

def run(backfill: bool):
    ensure_dirs()

    start = date.fromisoformat(START_DATE)
    yesterday = paris_now().date() - timedelta(days=1)
    dates = list(daterange(start, yesterday)) if backfill else [yesterday]

    all_rows: List[Dict[str, Any]] = []

    for d in dates:
        payload = fetch_dayahead(d)
        write_raw("dayahead", d, payload)

        rows = extract_rows_from_payload(payload, d)
        all_rows.extend(rows)

    # Write tidy outputs
    if all_rows:
        df = pd.DataFrame(all_rows).drop_duplicates()

        # Sort for readability if possible
        for col in ["date_cet", "area", "deliveryStart"]:
            if col not in df.columns:
                break
        else:
            df = df.sort_values(["date_cet", "area", "deliveryStart"])

        df.to_csv(os.path.join(OUT_DIR, "tidy", "dayahead_prices.csv"), index=False)
        df.to_json(os.path.join(OUT_DIR, "tidy", "dayahead_prices.json"),
                   orient="records", force_ascii=False, indent=2)

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
