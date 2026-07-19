"""Fetch NQ continuous front-month 1-min OHLCV from Databento into DataLocal/.

Cost was quoted at $8.42 for 2020-01-01..2026-07-16 (metadata.get_cost, 2026-07-17).
Output is gitignored — Databento data must not be committed/redistributed.
"""

from __future__ import annotations

import os
from pathlib import Path

import databento as db
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "DataLocal"
START = "2020-01-01"
END = "2026-07-16"
OUT_PATH = OUT_DIR / f"nq_ohlcv_1m_{START}_{END}.parquet"


def main() -> None:
    load_dotenv(ROOT / ".env")
    client = db.Historical(os.environ["DATABENTO_API_KEY"])
    OUT_DIR.mkdir(exist_ok=True)

    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=["NQ.v.0"],
        stype_in="continuous",
        schema="ohlcv-1m",
        start=START,
        end=END,
    )
    df = data.to_df()
    print(f"rows={len(df)} cols={list(df.columns)}")
    print(df.head(3))
    print(df.tail(3))
    print(f"index range: {df.index.min()} .. {df.index.max()}")
    print(f"NaNs:\n{df.isna().sum()}")
    df.to_parquet(OUT_PATH)
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
