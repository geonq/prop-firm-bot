"""Round-3 ladder search — laddered partial exit on top of the round-2 winner.

PRE-HOLDOUT FOLD EVIDENCE ONLY (holdout burned 2026-07-17). Base params =
round-2 winner (or=15, first_candle, or_opposite, 4R, slip=2, vwap_trail_after_r=2.0,
time_stop_minutes=120), friction-corrected ladder overlay (reviewer fix
2026-07-17). Grid: partial_exit_r x partial_exit_fraction (Maroy 2025's exact
values unavailable -- SSRN blocked; placeholder grid, well-motivated: levels
below/at the vwap_trail arm point, moderate fractions), plus a no-ladder
control row for direct comparison. Evaluated at $400 risk (comparison
baseline) across all 8 folds / 4 firms.
"""

from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path
from statistics import median

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    HOLDOUT_START,
    REPLAY_FIRMS,
    _fold_replay_days,
    _replay_mc_summary,
    make_folds,
)

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
OUT = ROOT / "Analysis" / "output" / "orb"
RISK = 400.0
N_SIMS = 2_000

ROUND2_BASE = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
    vwap_trail_after_r=2.0,
    time_stop_minutes=120,
)

LADDER_GRID = list(itertools.product([None, 1.5, 2.0, 3.0], [0.33, 0.5, 0.67]))
# (None, x) collapses to the same no-ladder config regardless of fraction; dedupe.
LADDER_GRID = sorted(
    set((r, f) if r is not None else (None, None) for r, f in LADDER_GRID),
    key=lambda rf: (rf[0] is not None, rf[0] or 0.0, rf[1] or 0.0),
)


def main() -> None:
    bars = pd.read_parquet(PARQUET)
    folds = make_folds(pd.Timestamp("2020-01-01"), pd.Timestamp(HOLDOUT_START))
    print(f"folds={len(folds)} ladder_configs={len(LADDER_GRID)} risk={RISK}")

    rows = []
    for partial_r, partial_frac in LADDER_GRID:
        if partial_r is None:
            params = ROUND2_BASE
        else:
            params = replace(ROUND2_BASE, partial_exit_r=partial_r, partial_exit_fraction=partial_frac)

        per_fold: dict[str, list[float]] = {f: [] for f in REPLAY_FIRMS}
        total_trades = 0
        for f in folds:
            trades, rd = _fold_replay_days(
                bars, params,
                warmup_start=f.oos_start - pd.DateOffset(months=3),
                window_start=f.oos_start, window_end=f.oos_end,
            )
            total_trades += len(trades)
            for firm in REPLAY_FIRMS:
                s = _replay_mc_summary(list(rd), firm=firm, n_simulations=N_SIMS, seed=0,
                                       block_size=5, eval_risk=RISK, funded_risk=RISK)
                if s is not None:
                    per_fold[firm].append(s.net_ev_mean)

        row = {"partial_exit_r": partial_r, "partial_exit_fraction": partial_frac, "oos_trades": total_trades}
        for firm in REPLAY_FIRMS:
            row[f"{firm}_fold_median"] = round(median(per_fold[firm]), 1)
            row[f"{firm}_fold_worst"] = round(min(per_fold[firm]), 1)
        row["best_median"] = max(row[f"{f}_fold_median"] for f in REPLAY_FIRMS)
        rows.append(row)
        print(row)

    baseline = next(r for r in rows if r["partial_exit_r"] is None)
    print(f"\nBASELINE (no ladder): {baseline}")
    rows.sort(key=lambda r: -r["best_median"])
    print("\nTOP 5 ladder configs:")
    for r in rows[:5]:
        print(r)

    (OUT / "round3_ladder_search.json").write_text(
        json.dumps({"baseline_no_ladder": baseline, "all_rows": rows}, indent=2)
    )
    print(f"\nwrote {OUT / 'round3_ladder_search.json'}")


if __name__ == "__main__":
    main()
