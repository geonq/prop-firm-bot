"""AdaptiveSizing sweep for the frozen ORB winner — PRE-HOLDOUT DATA ONLY.

Strategy params frozen (2026-07-17 verdict). Sweeps AdaptiveSizing knobs via
the replay MC (sizing_fn support reviewer-approved 2026-07-17). Evidence level:
pooled pre-holdout for the full grid, then per-fold check on the top cells.
Risk search space bounded to realistic per-trade dollar risk (reviewer note:
unbounded sizers produce unrealizable EV cells).

Baseline comparison: fixed $250-$400 from risk_sweep.json.
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path
from statistics import median

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import HOLDOUT_START, _fold_replay_days, make_folds
from src.pipeline.apex_replay import simulate_apex_trade_replay
from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.monte_carlo import summarize_pipeline_results
from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.sizing.dynamic import AdaptiveSizing

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
OUT = ROOT / "Analysis" / "output" / "orb"
TRADING_DAYS_PER_MONTH = 21
FIRMS = ["lucidflex", "topstep", "apex_eod", "apex_intraday"]

FROZEN = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
)

GRID = list(itertools.product(
    [200.0, 300.0, 400.0],      # eval_base
    [200.0, 300.0, 400.0],      # funded_base
    [0.02, 0.04],               # buffer_full_frac
    [0.25, 0.5],                # buffer_floor
    [0.6, 1.0],                 # post_payout_shrink
))


def _simulate(firm: str, sampled, fn):
    if firm == "lucidflex":
        return simulate_lucidflex_trade_replay(sampled, sizing_fn=fn)
    if firm == "topstep":
        return simulate_topstep_trade_replay(sampled, sizing_fn=fn)
    variant = "eod" if firm == "apex_eod" else "intraday"
    return simulate_apex_trade_replay(sampled, sizing_fn=fn, drawdown_variant=variant)


def _score(replay_days, fn, firm, n_sims, seed=0):
    rng = random.Random(seed)
    results = []
    for _ in range(n_sims):
        sampled = block_bootstrap_replay_days(
            replay_days, target_length=len(replay_days), block_size=5, rng=rng
        )
        results.append(_simulate(firm, sampled, fn))
    s = summarize_pipeline_results(results, firm="apex" if firm.startswith("apex") else firm)
    mean_days = sum(r.eval_days + r.funded_days for r in results) / len(results)
    return s, mean_days


def main() -> None:
    bars = pd.read_parquet(PARQUET)
    _, pooled = _fold_replay_days(
        bars, FROZEN,
        warmup_start=pd.Timestamp("2020-01-01"),
        window_start=pd.Timestamp("2020-04-01"),
        window_end=pd.Timestamp(HOLDOUT_START),
    )
    print(f"pooled pre-holdout days: {len(pooled)}  grid cells: {len(GRID)}")

    rows = []
    for eb, fb, bff, bf, pps in GRID:
        fn = AdaptiveSizing(eval_base=eb, funded_base=fb,
                            buffer_full_frac=bff, buffer_floor=bf, post_payout_shrink=pps)
        row = {"eval_base": eb, "funded_base": fb, "buffer_full_frac": bff,
               "buffer_floor": bf, "post_payout_shrink": pps}
        for firm in FIRMS:
            s, days = _score(pooled, fn, firm, n_sims=1_000)
            row[f"{firm}_ev_month"] = round(s.mean_net_ev / days * TRADING_DAYS_PER_MONTH, 1)
            row[f"{firm}_pass"] = round(s.eval_pass_rate, 3)
        row["best_ev_month"] = max(row[f"{f}_ev_month"] for f in FIRMS)
        rows.append(row)
        print(row)

    rows.sort(key=lambda r: -r["best_ev_month"])
    top = rows[:5]

    # Fold-level check on the top cells (worst-fold discipline).
    folds = make_folds(pd.Timestamp("2020-01-01"), pd.Timestamp(HOLDOUT_START))
    fold_days = []
    for f in folds:
        _, rd = _fold_replay_days(
            bars, FROZEN,
            warmup_start=f.oos_start - pd.DateOffset(months=3),
            window_start=f.oos_start, window_end=f.oos_end,
        )
        fold_days.append(rd)

    for row in top:
        fn = AdaptiveSizing(eval_base=row["eval_base"], funded_base=row["funded_base"],
                            buffer_full_frac=row["buffer_full_frac"],
                            buffer_floor=row["buffer_floor"],
                            post_payout_shrink=row["post_payout_shrink"])
        for firm in FIRMS:
            evs = []
            for rd in fold_days:
                s, _ = _score(list(rd), fn, firm, n_sims=1_000)
                evs.append(s.mean_net_ev)
            row[f"{firm}_fold_median"] = round(median(evs), 1)
            row[f"{firm}_fold_worst"] = round(min(evs), 1)
        print("FOLDS", {k: v for k, v in row.items() if "fold" in k or k in
                        ("eval_base", "funded_base", "buffer_full_frac", "buffer_floor", "post_payout_shrink")})

    (OUT / "sizing_sweep.json").write_text(json.dumps({"grid_rows": rows, "top5_with_folds": top}, indent=2))
    print(f"\nwrote {OUT / 'sizing_sweep.json'}")


if __name__ == "__main__":
    main()
