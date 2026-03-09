import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

data_dir = Path("data")
charts_dir = Path("charts")
reports_dir = Path("reports")

charts_dir.mkdir(exist_ok=True)
reports_dir.mkdir(exist_ok=True)

def load_csv(name):
    path = data_dir / name
    if path.exists():
        df = pd.read_csv(path)
        df["source"] = name
        return df
    return None

dayahead = load_csv("dayahead_prices.csv")
ida1 = load_csv("ida1_prices.csv")
ida2 = load_csv("ida2_prices.csv")
ida3 = load_csv("ida3_prices.csv")
intraday = load_csv("intraday_continuous_vwap_qh.csv")

all_dfs = [df for df in [dayahead, ida1, ida2, ida3, intraday] if df is not None]
if not all_dfs:
    raise ValueError("No CSV files found in data/")

combined = pd.concat(all_dfs, ignore_index=True)

def find_price_col(df):
    candidates = [c for c in df.columns if "price" in c.lower() or "vwap" in c.lower()]
    if not candidates:
        raise ValueError(f"No price-like column found in columns: {list(df.columns)}")
    return candidates[0]

def normalize_dataset(df, market_name):
    if df is None:
        return None
    price_col = find_price_col(df)
    out = df.copy()
    out["market"] = market_name
    out["price_value"] = pd.to_numeric(out[price_col], errors="coerce")
    if "date_cet" in out.columns:
        out["date_cet"] = pd.to_datetime(out["date_cet"], errors="coerce")
    else:
        out["date_cet"] = pd.NaT
    return out

datasets = {
    "DayAhead": normalize_dataset(dayahead, "DayAhead"),
    "IDA1": normalize_dataset(ida1, "IDA1"),
    "IDA2": normalize_dataset(ida2, "IDA2"),
    "IDA3": normalize_dataset(ida3, "IDA3"),
    "IntradayVWAP": normalize_dataset(intraday, "IntradayVWAP"),
}

available = [df for df in datasets.values() if df is not None]
all_prices = pd.concat(available, ignore_index=True)

# -------------------------
# 1. Summary by dataset
# -------------------------
summary = (
    all_prices.groupby("market")["price_value"]
    .agg(["mean", "min", "max", "std"])
    .reset_index()
    .sort_values("mean", ascending=False)
)
summary["spread_max_min"] = summary["max"] - summary["min"]
summary.to_csv(reports_dir / "summary.csv", index=False)

# -------------------------
# 2. Price trend chart
# -------------------------
plt.figure(figsize=(10, 6))
for name, group in all_prices.groupby("market"):
    plt.plot(group["price_value"].reset_index(drop=True), label=name)

plt.legend()
plt.title("Electricity Market Price Comparison")
plt.ylabel("€/MWh")
plt.xlabel("Observation")
plt.tight_layout()
plt.savefig(charts_dir / "price_trends.png")
plt.close()

# -------------------------
# 3. Max-min spread chart
# -------------------------
plt.figure(figsize=(10, 6))
plt.bar(summary["market"], summary["spread_max_min"])
plt.title("Max-Min Spread by Dataset")
plt.ylabel("Spread €/MWh")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(charts_dir / "spreads.png")
plt.close()

# -------------------------
# 4. Daily averages
# -------------------------
daily = (
    all_prices.dropna(subset=["date_cet"])
    .groupby(["date_cet", "market"])["price_value"]
    .mean()
    .reset_index()
    .sort_values(["market", "date_cet"])
)

if not daily.empty:
    daily.to_csv(reports_dir / "daily_market_averages.csv", index=False)

# -------------------------
# 5. Yesterday vs today change
# -------------------------
daily_changes = []
for market, group in daily.groupby("market"):
    group = group.sort_values("date_cet").copy()
    if len(group) >= 2:
        today_row = group.iloc[-1]
        yday_row = group.iloc[-2]
        change_abs = today_row["price_value"] - yday_row["price_value"]
        change_pct = (change_abs / yday_row["price_value"] * 100) if yday_row["price_value"] != 0 else None
        daily_changes.append({
            "market": market,
            "yesterday": yday_row["date_cet"].date(),
            "today": today_row["date_cet"].date(),
            "yesterday_avg": yday_row["price_value"],
            "today_avg": today_row["price_value"],
            "change_abs": change_abs,
            "change_pct": change_pct,
        })

daily_changes_df = pd.DataFrame(daily_changes)
if not daily_changes_df.empty:
    daily_changes_df.to_csv(reports_dir / "yesterday_vs_today.csv", index=False)

    plt.figure(figsize=(10, 6))
    plt.bar(daily_changes_df["market"], daily_changes_df["change_abs"])
    plt.title("Yesterday vs Today Average Price Change")
    plt.ylabel("Change €/MWh")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(charts_dir / "yesterday_vs_today.png")
    plt.close()

# -------------------------
# 6. 7-day anomaly detection
# -------------------------
anomaly_rows = []
for market, group in daily.groupby("market"):
    group = group.sort_values("date_cet").copy()
    group["rolling_7d_avg"] = group["price_value"].rolling(7, min_periods=2).mean()
    group["rolling_7d_std"] = group["price_value"].rolling(7, min_periods=2).std()
    group["zscore_like"] = (group["price_value"] - group["rolling_7d_avg"]) / group["rolling_7d_std"]
    latest = group.iloc[-1]
    anomaly_rows.append({
        "market": market,
        "date": latest["date_cet"],
        "price": latest["price_value"],
        "rolling_7d_avg": latest["rolling_7d_avg"],
        "rolling_7d_std": latest["rolling_7d_std"],
        "zscore_like": latest["zscore_like"],
        "is_anomaly_gt_2std": pd.notna(latest["zscore_like"]) and abs(latest["zscore_like"]) > 2,
    })

anomaly_df = pd.DataFrame(anomaly_rows)
if not anomaly_df.empty:
    anomaly_df.to_csv(reports_dir / "anomaly_detection.csv", index=False)

# -------------------------
# 7. DayAhead vs intraday arbitrage
# -------------------------
arbitrage_rows = []
dayahead_daily = daily[daily["market"] == "DayAhead"][["date_cet", "price_value"]].rename(columns={"price_value": "dayahead_avg"})

for intraday_market in ["IDA1", "IDA2", "IDA3", "IntradayVWAP"]:
    intraday_daily = daily[daily["market"] == intraday_market][["date_cet", "price_value"]].rename(columns={"price_value": "intraday_avg"})
    merged = dayahead_daily.merge(intraday_daily, on="date_cet", how="inner")
    if not merged.empty:
        merged["market_pair"] = f"DayAhead_to_{intraday_market}"
        merged["profit_if_buy_DA_sell_intraday"] = merged["intraday_avg"] - merged["dayahead_avg"]
        arbitrage_rows.append(merged)

if arbitrage_rows:
    arbitrage_df = pd.concat(arbitrage_rows, ignore_index=True)
    arbitrage_df.to_csv(reports_dir / "arbitrage_opportunities.csv", index=False)

    arb_summary = (
        arbitrage_df.groupby("market_pair")["profit_if_buy_DA_sell_intraday"]
        .agg(["mean", "min", "max"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )
    arb_summary.to_csv(reports_dir / "arbitrage_summary.csv", index=False)

    plt.figure(figsize=(10, 6))
    plt.bar(arb_summary["market_pair"], arb_summary["mean"])
    plt.title("Average Arbitrage Opportunity: Buy DayAhead, Sell Intraday")
    plt.ylabel("Average Profit €/MWh")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(charts_dir / "arbitrage_summary.png")
    plt.close()
else:
    arbitrage_df = pd.DataFrame()
    arb_summary = pd.DataFrame()

# -------------------------
# 8. Markdown report
# -------------------------
top_market = summary.iloc[0]["market"]
top_market_avg = summary.iloc[0]["mean"]

largest_spread_row = summary.sort_values("spread_max_min", ascending=False).iloc[0]
largest_spread_market = largest_spread_row["market"]
largest_spread_val = largest_spread_row["spread_max_min"]

report_lines = [
    "# Daily Electricity Market Analysis",
    "",
    f"## Datasets analysed",
    f"{len(summary)}",
    "",
    "## Highest average price",
    f"{top_market} — {top_market_avg:.2f} €/MWh",
    "",
    "## Largest spread",
    f"{largest_spread_market} — {largest_spread_val:.2f} €/MWh",
    "",
]

if not daily_changes_df.empty:
    biggest_move = daily_changes_df.iloc[daily_changes_df["change_abs"].abs().idxmax()]
    report_lines += [
        "## Biggest yesterday-vs-today move",
        f"{biggest_move['market']} — {biggest_move['change_abs']:.2f} €/MWh ({biggest_move['change_pct']:.2f}%)",
        "",
    ]

if not anomaly_df.empty:
    flagged = anomaly_df[anomaly_df["is_anomaly_gt_2std"] == True]
    report_lines += ["## 7-day anomalies"]
    if flagged.empty:
        report_lines += ["No strong anomalies detected (> 2 rolling std).", ""]
    else:
        for _, row in flagged.iterrows():
            report_lines.append(f"{row['market']} on {row['date'].date()} flagged as anomaly.")
        report_lines.append("")

if not arb_summary.empty:
    best_arb = arb_summary.iloc[0]
    report_lines += [
        "## Best arbitrage setup",
        f"{best_arb['market_pair']} — average profit {best_arb['mean']:.2f} €/MWh",
        "",
    ]

(report_dir := reports_dir / "daily_report.md").write_text("\n".join(report_lines))
print(f"Saved report to {report_dir}")
