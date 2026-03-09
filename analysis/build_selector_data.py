import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
OUT_DIR = Path("docs/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name):
    path = DATA_DIR / name
    if not path.exists():
        print(f"Missing file: {path}")
        return None
    print(f"Loading: {path}")
    return pd.read_csv(path)


def find_first(df, candidates):
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def find_price_col(df):
    for c in df.columns:
        lc = c.lower()
        if "price" in lc or "vwap" in lc:
            return c
    raise ValueError(f"No price/vwap column found in columns: {list(df.columns)}")


def normalize(df, market_name):
    if df is None:
        return None

    out = df.copy()
    out["market"] = market_name

    price_col = find_price_col(out)
    out["price_value"] = pd.to_numeric(out[price_col], errors="coerce")

    area_col = find_first(out, ["area", "country", "market_area", "bidding_zone"])
    out["area"] = out[area_col].astype(str) if area_col else "ALL"

    start_col = find_first(out, ["deliveryStartCET", "delivery_start_cet", "start_cet"])
    end_col = find_first(out, ["deliveryEndCET", "delivery_end_cet", "end_cet"])
    date_col = find_first(out, ["date_cet"])

    if start_col:
        out["start"] = pd.to_datetime(out[start_col], errors="coerce")
    else:
        out["start"] = pd.NaT

    if end_col:
        out["end"] = pd.to_datetime(out[end_col], errors="coerce")
    elif start_col:
        out["end"] = out["start"] + pd.Timedelta(minutes=15)
    else:
        out["end"] = pd.NaT

    if start_col:
        out["date"] = out["start"].dt.date.astype(str)
        out["contract"] = out["start"].dt.strftime("%H:%M") + "-" + out["end"].dt.strftime("%H:%M")
        out["contract_sort"] = out["start"].dt.hour * 60 + out["start"].dt.minute
    else:
        if date_col:
            out["date"] = pd.to_datetime(out[date_col], errors="coerce").dt.date.astype(str)
        else:
            out["date"] = "unknown"
        out["row_num"] = out.groupby(["date", "area"]).cumcount() + 1
        out["contract"] = out["row_num"].apply(lambda x: f"Q{x:02d}")
        out["contract_sort"] = out["row_num"]

    return out[
        ["date", "area", "market", "price_value", "start", "end", "contract", "contract_sort"]
    ]


def expand_hourly_to_quarters(df):
    """Expand hourly products into quarter-hour rows if needed."""
    if df is None or df.empty:
        return df

    rows = []

    for _, row in df.iterrows():
        start = row["start"]
        end = row["end"]

        if pd.isna(start) or pd.isna(end):
            rows.append(row.to_dict())
            continue

        duration_mins = (end - start).total_seconds() / 60

        # if already quarter-hourly, keep as-is
        if duration_mins <= 15:
            rows.append(row.to_dict())
            continue

        # split longer contracts into 15-minute blocks
        current = start
        while current < end:
            next_q = min(current + pd.Timedelta(minutes=15), end)
            new_row = row.to_dict()
            new_row["start"] = current
            new_row["end"] = next_q
            new_row["contract"] = current.strftime("%H:%M") + "-" + next_q.strftime("%H:%M")
            new_row["contract_sort"] = current.hour * 60 + current.minute
            new_row["date"] = str(current.date())
            rows.append(new_row)
            current = next_q

    return pd.DataFrame(rows)


dayahead = normalize(load_csv("dayahead_prices.csv"), "DayAhead")
ida1 = normalize(load_csv("ida1_prices.csv"), "IDA1")
ida2 = normalize(load_csv("ida2_prices.csv"), "IDA2")
ida3 = normalize(load_csv("ida3_prices.csv"), "IDA3")
vwap = normalize(load_csv("intraday_continuous_vwap_qh.csv"), "IntradayVWAP")

# expand day-ahead hourly contracts to quarter-hours
dayahead = expand_hourly_to_quarters(dayahead)

datasets = [x for x in [dayahead, ida1, ida2, ida3, vwap] if x is not None and not x.empty]

if not datasets:
    raise ValueError("No datasets loaded from data/")

base = pd.concat(datasets, ignore_index=True)

rules = [
    ("DA_IDA1", "DayAhead", "IDA1"),
    ("DA_IDA2", "DayAhead", "IDA2"),
    ("DA_IDA3", "DayAhead", "IDA3"),
    ("DA_VWAP", "DayAhead", "IntradayVWAP"),
]

profit_rows = []

for rule_name, buy_market, sell_market in rules:
    buy = base[base["market"] == buy_market].copy()
    sell = base[base["market"] == sell_market].copy()

    buy = buy.rename(columns={"price_value": "buy_price"})
    sell = sell.rename(columns={"price_value": "sell_price"})

    merged = buy.merge(
        sell,
        on=["date", "area", "contract"],
        how="inner",
        suffixes=("_buy", "_sell"),
    )

    if merged.empty:
        print(f"No matches for rule: {rule_name}")
        continue

    merged["rule"] = rule_name
    merged["profit"] = merged["sell_price"] - merged["buy_price"]

    if "contract_sort_buy" in merged.columns:
        merged["contract_sort"] = merged["contract_sort_buy"]
    elif "contract_sort_sell" in merged.columns:
        merged["contract_sort"] = merged["contract_sort_sell"]
    else:
        merged["contract_sort"] = 0

    profit_rows.append(
        merged[
            [
                "date",
                "area",
                "contract",
                "contract_sort",
                "rule",
                "buy_price",
                "sell_price",
                "profit",
            ]
        ]
    )

if not profit_rows:
    raise ValueError(
        "No arbitrage rows were created. This means the datasets still do not align on date/area/contract."
    )

result = pd.concat(profit_rows, ignore_index=True).sort_values(
    ["date", "area", "rule", "contract_sort", "contract"]
)

csv_path = OUT_DIR / "contract_profits.csv"
json_path = OUT_DIR / "contract_profits.json"

result.to_csv(csv_path, index=False)
json_path.write_text(result.to_json(orient="records"))

print(f"Wrote CSV: {csv_path}")
print(f"Wrote JSON: {json_path}")
print(f"Rows written: {len(result)}")
