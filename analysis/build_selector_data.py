"""
Script to build selector data for nordpool-bot-test.

This script reads various Nord Pool CSV price files, normalises their
schema, expands hourly records to quarter‑hour resolution, and then
computes price differentials across market pairs.  The resulting
datasets are written to the docs/data folder for consumption by the
frontend.  It has been updated to robustly handle daylight saving
transitions (e.g. 2026‑03‑29 in Europe/Paris) by parsing UTC
timestamps and converting them to the local timezone.  Without this
change, pandas would mark some delivery start/end times around the
DST change as ``NaT``, causing those rows to be dropped and the
dashboard to stop at 2026‑03‑28.

To regenerate the selector data after updating your raw CSV files, run
this script from the repository root:

    python analysis/build_selector_data.py

"""

import pandas as pd
from pathlib import Path
from itertools import combinations

# Directory containing the raw CSV files downloaded from Nord Pool
DATA_DIR = Path("data")

# Directory where processed selector data will be saved (committed to docs)
OUT_DIR = Path("docs/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name: str) -> pd.DataFrame | None:
    """Load a CSV from ``DATA_DIR`` if it exists.

    Parameters
    ----------
    name : str
        File name relative to ``DATA_DIR``.

    Returns
    -------
    pandas.DataFrame | None
        DataFrame containing the CSV contents, or ``None`` if the file
        does not exist.
    """
    path = DATA_DIR / name
    if not path.exists():
        print(f"Missing file: {path}")
        return None
    print(f"Loading: {path}")
    return pd.read_csv(path)


def find_first(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column in ``df`` matching any of ``candidates`` (case-insensitive).

    If none of the candidate names are present, ``None`` is returned.
    """
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def find_price_col(df: pd.DataFrame) -> str:
    """Return the name of the price column in ``df``.

    The function looks for a column whose lower‑case name contains
    ``price`` or ``vwap``.  If none is found, a ``ValueError`` is raised.
    """
    for c in df.columns:
        lc = c.lower()
        if "price" in lc or "vwap" in lc:
            return c
    raise ValueError(f"No price/vwap column found in columns: {list(df.columns)}")


def normalize(df: pd.DataFrame | None, market_name: str) -> pd.DataFrame | None:
    """Normalise a raw price DataFrame.

    This helper renames/derives a common set of columns across all market
    files (date, area, market, price_value, start, end, contract,
    contract_sort) and handles daylight saving changes correctly.  It
    takes the first available start/end columns in the order ``deliveryStartUTC``,
    ``delivery_start_utc``, ``deliveryStartCET``, ``delivery_start_cet``, etc.
    If UTC timestamps are present they are parsed as UTC and converted
    to Europe/Paris.  CET timestamps (with offset information) are
    parsed as timezone‑aware and converted to Europe/Paris.  Failing
    that, rows will have ``NaT`` start/end and are processed later by
    ``expand_to_quarters``.

    Parameters
    ----------
    df : pandas.DataFrame | None
        Raw CSV data frame.  ``None`` is returned if ``df`` is ``None``.
    market_name : str
        Market code (e.g. ``DA``, ``IDA1``, ``IDA2``, ``IDA3``, ``VWAP``).

    Returns
    -------
    pandas.DataFrame | None
        Normalised frame with unified columns, or ``None`` if ``df`` was ``None``.
    """
    if df is None:
        return None

    out = df.copy()
    out["market"] = market_name

    # Standardise price column to numeric
    price_col = find_price_col(out)
    out["price_value"] = pd.to_numeric(out[price_col], errors="coerce")

    # Standardise area column; default to "ALL" if none is found
    area_col = find_first(out, ["area", "country", "market_area", "bidding_zone"])
    out["area"] = out[area_col].astype(str) if area_col else "ALL"

    # Prefer UTC delivery timestamps when available, fall back to CET timestamps
    utc_start_col = find_first(out, ["deliveryStartUTC", "delivery_start_utc"])
    utc_end_col = find_first(out, ["deliveryEndUTC", "delivery_end_utc"])
    cet_start_col = find_first(out, ["deliveryStartCET", "delivery_start_cet", "start_cet"])
    cet_end_col = find_first(out, ["deliveryEndCET", "delivery_end_cet", "end_cet"])
    date_col = find_first(out, ["date_cet"])

    if utc_start_col:
        # Parse UTC timestamps and convert to Europe/Paris (handles DST)
        out["start"] = (
            pd.to_datetime(out[utc_start_col], errors="coerce", utc=True)
            .dt.tz_convert("Europe/Paris")
            .dt.tz_localize(None)
        )
    elif cet_start_col:
        # Parse CET timestamps (they include offset such as +01:00/+02:00)
        out["start"] = pd.to_datetime(out[cet_start_col], errors="coerce", utc=True)
        out["start"] = out["start"].dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    else:
        out["start"] = pd.NaT

    if utc_end_col:
        out["end"] = (
            pd.to_datetime(out[utc_end_col], errors="coerce", utc=True)
            .dt.tz_convert("Europe/Paris")
            .dt.tz_localize(None)
        )
    elif cet_end_col:
        out["end"] = pd.to_datetime(out[cet_end_col], errors="coerce", utc=True)
        out["end"] = out["end"].dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    elif utc_start_col:
        # If end is missing but start is present, assume 15‑minute interval
        out["end"] = out["start"] + pd.Timedelta(minutes=15)
    elif cet_start_col:
        out["end"] = out["start"] + pd.Timedelta(minutes=15)
    else:
        out["end"] = pd.NaT

    # Derive date string; prefer explicit date_cet column if present
    if date_col:
        out["date"] = pd.to_datetime(out[date_col], errors="coerce").dt.date.astype(str)
    elif not out["start"].isna().all():
        out["date"] = out["start"].dt.date.astype(str)
    else:
        out["date"] = "unknown"

    # Build contract label and sort key
    if not out["start"].isna().all():
        out["contract"] = out["start"].dt.strftime("%H:%M") + "-" + out["end"].dt.strftime("%H:%M")
        out["contract_sort"] = out["start"].dt.hour * 60 + out["start"].dt.minute
    else:
        # Fallback when no timestamp is available; create sequential quarter labels
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


def expand_to_quarters(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Expand any multi‑quarter records into quarter‑hour granularity.

    For datasets like DA, a single hourly record is provided; we split
    those into four quarter‑hour rows so they align with intraday markets.
    If ``df`` is ``None`` or empty it is returned unchanged.
    """
    if df is None or df.empty:
        return df
    rows: list[dict] = []
    for _, row in df.iterrows():
        start = row["start"]
        end = row["end"]
        # Preserve rows without valid timestamps as‑is
        if pd.isna(start) or pd.isna(end):
            rows.append(row.to_dict())
            continue
        duration_mins = (end - start).total_seconds() / 60
        # Already quarter‑hour resolution or shorter
        if duration_mins <= 15:
            rows.append(row.to_dict())
            continue
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


def main() -> None:
    """Entry point to build selector data across all available markets."""
    # Load raw datasets and normalise them
    market_frames: dict[str, pd.DataFrame | None] = {
        "DA": normalize(load_csv("dayahead_prices.csv"), "DA"),
        "IDA1": normalize(load_csv("ida1_prices.csv"), "IDA1"),
        "IDA2": normalize(load_csv("ida2_prices.csv"), "IDA2"),
        "IDA3": normalize(load_csv("ida3_prices.csv"), "IDA3"),
        "VWAP": normalize(load_csv("intraday_continuous_vwap_qh.csv"), "VWAP"),
    }

    # Expand any non‑quarter data into quarters
    for key in list(market_frames.keys()):
        market_frames[key] = expand_to_quarters(market_frames[key])

    # Only keep markets that actually loaded data
    available_markets = [k for k, v in market_frames.items() if v is not None and not v.empty]
    if not available_markets:
        raise ValueError("No datasets loaded from data/")

    # Concatenate all markets for merging
    base = pd.concat([market_frames[k] for k in available_markets], ignore_index=True)

    # Build every unordered pair once; the UI handles reverse direction
    pairs = list(combinations(available_markets, 2))
    profit_rows: list[pd.DataFrame] = []
    for left_market, right_market in pairs:
        left_df = base[base["market"] == left_market].copy().rename(columns={"price_value": "left_price"})
        right_df = base[base["market"] == right_market].copy().rename(columns={"price_value": "right_price"})
        merged = left_df.merge(
            right_df,
            on=["date", "area", "contract"],
            how="inner",
            suffixes=("_left", "_right"),
        )
        if merged.empty:
            print(f"No matches for pair: {left_market}_{right_market}")
            continue
        merged["rule"] = f"{left_market}_{right_market}"
        merged["buy_price"] = merged["left_price"]
        merged["sell_price"] = merged["right_price"]
        merged["profit"] = merged["sell_price"] - merged["buy_price"]
        # Carry forward the contract_sort from whichever side exists
        if "contract_sort_left" in merged.columns:
            merged["contract_sort"] = merged["contract_sort_left"]
        elif "contract_sort_right" in merged.columns:
            merged["contract_sort"] = merged["contract_sort_right"]
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
        raise ValueError("No matched rows were created. Check date/area/contract alignment across files.")

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
    print(f"Rules generated: {sorted(result['rule'].unique().tolist())}")


if __name__ == "__main__":
    main()
