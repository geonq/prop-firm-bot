"""Smoke test for src/backtest/orb.py against real NQ 1-min data.

Runs ONE literature-anchored config (5-min OR, first-candle direction entry,
opposite-OR-extreme stop, 10R-or-EoD target, no filters). This is a smoke
test proving the pipeline runs end-to-end on real data — NOT the Phase 4B
research result (no walk-forward, no friction sweep, no filter search).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest.orb import ORBParams, run_orb_backtest

DATA_PATH = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"


def main() -> None:
    bars = pd.read_parquet(DATA_PATH)

    params = ORBParams(
        or_minutes=5,
        entry_mode="first_candle",
        stop_mode="or_opposite",
        target_r=10.0,
        slippage_ticks=1,
        commission_usd_per_side=4.5,
    )

    trades = run_orb_backtest(bars, params)

    n = len(trades)
    wins = [t for t in trades if t.r_multiple > 0]
    wr = len(wins) / n if n else float("nan")
    mean_r = sum(t.r_multiple for t in trades) / n if n else float("nan")
    total_pnl_points = sum(t.pnl_points for t in trades)

    print(f"config: or_minutes={params.or_minutes} entry_mode={params.entry_mode} "
          f"stop_mode={params.stop_mode} target_r={params.target_r} "
          f"slippage_ticks={params.slippage_ticks} commission_usd_per_side={params.commission_usd_per_side}")
    print(f"trade count: {n}")
    print(f"win rate: {wr:.4f}")
    print(f"mean R: {mean_r:.4f}")
    print(f"total PnL points (after friction): {total_pnl_points:.2f}")

    print("\nfirst 3 trades:")
    for t in trades[:3]:
        print(t)

    print("\nlast 3 trades:")
    for t in trades[-3:]:
        print(t)


if __name__ == "__main__":
    main()
