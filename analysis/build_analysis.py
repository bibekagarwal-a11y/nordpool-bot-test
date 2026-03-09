import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

data_dir = Path("data")
charts_dir = Path("charts")
reports_dir = Path("reports")

charts_dir.mkdir(exist_ok=True)
reports_dir.mkdir(exist_ok=True)

files = list(data_dir.glob("*.csv"))
dfs = []

for f in files:
    df = pd.read_csv(f)
    df["source"] = f.name
    dfs.append(df)

if not dfs:
    raise ValueError("No CSV files found in data/")

df = pd.concat(dfs, ignore_index=True)

price_candidates = [c for c in df.columns if "price" in c.lower() or "vwap" in c.lower()]
if not price_candidates:
    raise ValueError("No price-like column found")

price_col = price_candidates[0]

summary = (
    df.groupby("source")[price_col]
    .agg(["mean", "min", "max", "std"])
    .reset_index()
    .sort_values("mean", ascending=False)
)

summary["spread_max_min"] = summary["max"] - summary["min"]
summary.to_csv(reports_dir / "summary.csv", index=False)

plt.figure(figsize=(10, 6))
for name, group in df.groupby("source"):
    plt.plot(group[price_col].reset_index(drop=True), label=name)

plt.legend()
plt.title("Electricity Market Price Comparison")
plt.ylabel("€/MWh")
plt.xlabel("Observation")
plt.tight_layout()
plt.savefig(charts_dir / "price_trends.png")
plt.close()

plt.figure(figsize=(10, 6))
plt.bar(summary["source"], summary["spread_max_min"])
plt.title("Max-Min Spread by Dataset")
plt.ylabel("Spread €/MWh")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(charts_dir / "spreads.png")
plt.close()

report_md = f"""# Daily Electricity Market Analysis

## Datasets analysed
{len(summary)}

## Highest average price
{summary.iloc[0]['source']} — {summary.iloc[0]['mean']:.2f} €/MWh

## Largest spread
{summary.sort_values('spread_max_min', ascending=False).iloc[0]['source']} — {summary.sort_values('spread_max_min', ascending=False).iloc[0]['spread_max_min']:.2f} €/MWh
"""

(reports_dir / "daily_report.md").write_text(report_md)
