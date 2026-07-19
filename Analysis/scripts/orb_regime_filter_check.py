"""Empirical test: does gating on vol_percentile_min rescue worst-fold robustness
across the full 2015-2025, 18-fold dataset?

Motivated by Georg's regime-persistence hypothesis (2026-07-18) and a
complication found while checking it: the existing vol_percentile_min metric
(20-day rolling std of daily returns, expanding-rank) does NOT cleanly
separate the profitable 2021-2025 folds from the losing 2016-2019 ones --
fold 15 (2024 H1, one of the best 6mo periods) reads LOWER than the losing
regime's own average. This script tests empirically, not theoretically,
whether gating trades on this metric still helps despite that complication.

Tests both the original round-2/3 winner shape (or=15+vwap_trail+time_stop)
and the Stage-B alternative (or=5+target_r=4+time_stop) at several
vol_percentile_min thresholds, across all 18 folds, all 4 firms, at $400
risk (round-3's better-than-$200 finding). Holdout untouched.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Analysis" / "scripts"))

import pandas as pd

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    HOLDOUT_START,
    REPLAY_FIRMS,
    _evaluate_candidate_oos,
    make_folds,
)

import orb_full_scope_run as fsr

OUT = ROOT / "Analysis" / "output" / "orb" / "full_scope"
RISK = 400.0
N_SIM = 2000

ORIGINAL_BASE = ORBParams(
    or_minutes=15, entry_mode="first_candle", stop_mode="or_opposite", target_r=4.0,
    slippage_ticks=2.0, vwap_trail_after_r=2.0, time_stop_minutes=120,
)
ALT_BASE = ORBParams(
    or_minutes=5, entry_mode="first_candle", stop_mode="or_opposite", target_r=4.0,
    slippage_ticks=1.0, time_stop_minutes=120,
)

VOL_THRESHOLDS = [None, 0.3, 0.4, 0.5, 0.6, 0.7]


def main() -> None:
    bars = pd.read_parquet(ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet")
    folds = make_folds("2015-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)

    grid = []
    for base_name, base in [("original", ORIGINAL_BASE), ("alt", ALT_BASE)]:
        for vp in VOL_THRESHOLDS:
            grid.append((base_name, replace(base, vol_percentile_min=vp)))

    print(f"testing {len(grid)} configs across {len(folds)} folds at risk={RISK}")
    t0 = time.monotonic()
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(_evaluate_candidate_oos, bars, params, folds, firms=REPLAY_FIRMS,
                        n_simulations=N_SIM, block_size=5, risk_per_trade_usd=RISK, seed=0)
            for _, params in grid
        ]
        for i, fut in enumerate(futures):
            results.append(fut.result())
            print(f"{i+1}/{len(grid)} done ({time.monotonic()-t0:.0f}s elapsed)", flush=True)

    rows = []
    for (base_name, _), result in zip(grid, results, strict=True):
        row = fsr._candidate_row(result)
        row["base"] = base_name
        # per-fold min/count to see if the filter actually suppresses losing-regime trades
        pre2020_trades = sum(f.trade_count for f in result.fold_results if f.fold_index <= 9)
        post2021_trades = sum(f.trade_count for f in result.fold_results if f.fold_index >= 10)
        row["pre2020_trades"] = pre2020_trades
        row["post2021_trades"] = post2021_trades
        rows.append(row)
        print(row)

    pd.DataFrame(rows).to_csv(OUT / "regime_filter_check.csv", index=False)
    print(f"\nwrote {OUT / 'regime_filter_check.csv'}")
    print("\nREGIME FILTER CHECK COMPLETE")


if __name__ == "__main__":
    main()
