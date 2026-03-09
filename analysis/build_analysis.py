import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

data_dir = Path("data")
charts_dir = Path("charts")
charts_dir.mkdir(exist_ok=True)

files = list(data_dir.glob("*.csv"))

dfs = []

for f in files:
    df = pd.read_csv(f)
    df["source"] = f.name
    dfs.append(df)

df = pd.concat(dfs)

price_col = [c for c in df.columns if "price" in c.lower()][0]

plt.figure(figsize=(10,6))

for name, group in df.groupby("source"):
    plt.plot(group[price_col].values, label=name)

plt.legend()
plt.title("Electricity Market Price Comparison")
plt.ylabel("€/MWh")

plt.savefig("charts/price_trends.png")
