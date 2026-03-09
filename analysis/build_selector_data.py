import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
OUT_DIR = Path("docs/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name):
    path = DATA_DIR / name
    if not path.exists():
        return None
    return pd.read_csv(path)


def find_price_col(df):
    for c in df.columns:
        if "price" in c.lower() or "vwap" in c.lower():
            return c
    raise ValueError("Price column not found")


def normalize(df, market_name):
    if df is None:
        return None

    out = df.copy()
    out["market"] = market_name

    price_col = find_price_col(df)
    out["price_value"] = pd.to_numeric(out[price_col], errors="coerce")

    # detect area column
    area_col = None
    for c in df.columns:
        if c.lower() in ["area", "country", "market_area", "bidding_zone"]:
            area_col = c

    if area_col:
        out["area"] = out[area_col]
    else:
        out["area"] = "ALL"

    # detect contract timestamps
    start_col = None
    end_col = None

    for c in df.columns:
        if "deliverystart" in c.lower():
            start_col = c
        if "deliveryend" in c.lower():
            end_col = c

    if start_col:
        out["start"] = pd.to_datetime(out[start_col])
        if end_col:
            out["end"] = pd.to_datetime(out[end_col])
        else:
            out["end"] = out["start"] + pd.Timedelta(minutes=15)

        out["contract"] = out["start"].dt.strftime("%H:%M") + "-" + out["end"].dt.strftime("%H:%M")
        out["contract_sort"] = out["start"].dt.hour * 60 + out["start"].dt.minute
    else:
        out["contract"] = "unknown"
        out["contract_sort"] = 0

    # detect date
    if "date_cet" in df.columns:
        out["date"] = pd.to_datetime(df["date_cet"]).dt.date.astype(str)
    else:
        out["date"] = "unknown"

    return out[
        [
            "date",
            "area",
            "contract",
            "contract_sort",
            "market",
            "price_value",
        ]
    ]


da = normalize(load_csv("dayahead_prices.csv"), "DayAhead")
ida1 = normalize(load_csv("ida1_prices.csv"), "IDA1")
ida2 = normalize(load_csv("ida2_prices.csv"), "IDA2")
ida3 = normalize(load_csv("ida3_prices.csv"), "IDA3")
vwap = normalize(load_csv("intraday_continuous_vwap_qh.csv"), "IntradayVWAP")

datasets = [x for x in [da, ida1, ida2, ida3, vwap] if x is not None]

base = pd.concat(datasets)

rules = [
    ("DA_IDA1", "DayAhead", "IDA1"),
    ("DA_IDA2", "DayAhead", "IDA2"),
    ("DA_IDA3", "DayAhead", "IDA3"),
    ("DA_VWAP", "DayAhead", "IntradayVWAP"),
]

profit_rows = []

for rule_name, buy_market, sell_market in rules:

    buy = base[base.market == buy_market].rename(columns={"price_value": "buy_price"})
    sell = base[base.market == sell_market].rename(columns={"price_value": "sell_price"})

merged = buy.merge(
    sell,
    on=["date", "area", "contract"],
    how="inner",
    suffixes=("_buy", "_sell"),
)

merged["rule"] = rule_name
merged["profit"] = merged["sell_price"] - merged["buy_price"]

# recover contract_sort
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

result = pd.concat(profit_rows).sort_values(
    ["date", "area", "rule", "contract_sort"]
)

result.to_csv(OUT_DIR / "contract_profits.csv", index=False)
(result).to_json(OUT_DIR / "contract_profits.json", orient="records")

print("Selector dataset built")
