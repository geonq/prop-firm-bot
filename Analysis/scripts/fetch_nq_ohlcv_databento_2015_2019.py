"""Extend NQ continuous front-month 1-min OHLCV back to 2015-01-01.

Cost quoted at $6.23 for 2015-01-01..2020-01-01 (metadata.get_cost, 2026-07-18).
Output is gitignored — Databento data must not be committed/redistributed.
Merges with the existing 2020-01-01..2026-07-16 parquet into one combined file.
"""

from __future__ import annotations

import os
from pathlib import Path

import databento as db
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "DataLocal"
NEW_START = "2015-01-01"
NEW_END = "2020-01-01"
NEW_PATH = OUT_DIR / f"nq_ohlcv_1m_{NEW_START}_{NEW_END}.parquet"
EXISTING_PATH = OUT_DIR / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
COMBINED_PATH = OUT_DIR / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"


def main() -> None:
    load_dotenv(ROOT / ".env")
    client = db.Historical(os.environ["DATABENTO_API_KEY"])
    OUT_DIR.mkdir(exist_ok=True)

    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=["NQ.v.0"],
        stype_in="continuous",
        schema="ohlcv-1m",
        start=NEW_START,
        end=NEW_END,
    )
    new_df = data.to_df()
    print(f"new rows={len(new_df)} cols={list(new_df.columns)}")
    print(f"new index range: {new_df.index.min()} .. {new_df.index.max()}")
    print(f"new NaNs:\n{new_df.isna().sum()}")
    new_df.to_parquet(NEW_PATH)
    print(f"wrote {NEW_PATH} ({NEW_PATH.stat().st_size / 1e6:.1f} MB)")

    existing_df = pd.read_parquet(EXISTING_PATH)
    print(f"\nexisting rows={len(existing_df)} range: {existing_df.index.min()} .. {existing_df.index.max()}")

    combined = pd.concat([new_df, existing_df]).sort_index()
    dupe_count = combined.index.duplicated().sum()
    print(f"combined rows={len(combined)} duplicated index entries={dupe_count}")
    if dupe_count:
        combined = combined[~combined.index.duplicated(keep="last")]
        print(f"after de-dup: {len(combined)} rows")

    gap = combined.index.to_series().diff()
    print(f"max single gap between consecutive bars: {gap.max()}")
    print(f"combined index monotonic increasing: {combined.index.is_monotonic_increasing}")
    print(f"combined NaNs:\n{combined.isna().sum()}")

    combined.to_parquet(COMBINED_PATH)
    print(f"\nwrote {COMBINED_PATH} ({COMBINED_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"final combined range: {combined.index.min()} .. {combined.index.max()}, {len(combined)} rows")


if __name__ == "__main__":
    main()
