"""CLI: walk-forward finetune the ORB strategy on real NQ 1-min data.

Builds a literature-anchored coarse grid, runs rolling IS/OOS folds via
`src.optimizer.walk_forward.run_walk_forward`, scores candidates by
prop-firm net EV (replay Monte Carlo, not raw PnL), and writes ranked
results to `Analysis/output/orb/`.

This script NEVER touches the holdout window (>= 2025-07-01). It only runs
`run_walk_forward` over rolling folds that end strictly before the holdout.

Usage:
    .venv/bin/python3 Analysis/scripts/orb_walk_forward.py
    .venv/bin/python3 Analysis/scripts/orb_walk_forward.py --smoke
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    DEFAULT_RISK_PER_TRADE_USD,
    HOLDOUT_START,
    REPLAY_FIRMS,
    CandidateResult,
    make_folds,
    params_hash,
    run_walk_forward,
)

DATA_PATH = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
OUTPUT_DIR = ROOT / "Analysis" / "output" / "orb"

DATA_START = "2020-01-01"


def build_coarse_grid() -> list[ORBParams]:
    """~200-300 config literature-anchored grid (Phase 4B spec).

    or_minutes {5,15,30} x entry_mode {breakout, first_candle} x
    stop {or_opposite} x target_r {None,4,10} x
    vol_percentile_min {None,50,75} x rel_volume_min {None,1.2} x
    slippage_ticks {1,2}
    = 3*2*1*3*3*2*2 = 216 configs.
    """
    or_minutes_opts = [5, 15, 30]
    entry_mode_opts = ["breakout", "first_candle"]
    stop_mode_opts = ["or_opposite"]
    target_r_opts = [None, 4.0, 10.0]
    vol_percentile_opts = [None, 50.0, 75.0]
    rel_volume_opts = [None, 1.2]
    slippage_opts = [1, 2]

    grid: list[ORBParams] = []
    for or_minutes, entry_mode, stop_mode, target_r, vol_pct, rel_vol, slip in itertools.product(
        or_minutes_opts,
        entry_mode_opts,
        stop_mode_opts,
        target_r_opts,
        vol_percentile_opts,
        rel_volume_opts,
        slippage_opts,
    ):
        vol_percentile_min = (vol_pct / 100.0) if vol_pct is not None else None
        grid.append(
            ORBParams(
                or_minutes=or_minutes,
                entry_mode=entry_mode,
                stop_mode=stop_mode,
                target_r=target_r,
                vol_percentile_min=vol_percentile_min,
                rel_volume_min=rel_vol,
                slippage_ticks=float(slip),
            )
        )
    return grid


def _candidate_row(c: CandidateResult) -> dict:
    row: dict = {
        "params_hash": None,
        "or_minutes": c.params.or_minutes,
        "entry_mode": c.params.entry_mode,
        "stop_mode": c.params.stop_mode,
        "target_r": c.params.target_r,
        "vol_percentile_min": c.params.vol_percentile_min,
        "rel_volume_min": c.params.rel_volume_min,
        "slippage_ticks": c.params.slippage_ticks,
        "risk_per_trade_usd": c.risk_per_trade_usd,
        "total_oos_trades": c.total_oos_trades,
        "is_admissible": c.is_admissible(),
        "admissible_firms": ",".join(c.admissible_firms()),
    }
    for firm in REPLAY_FIRMS:
        row[f"{firm}_median_ev_ci_low"] = c.median_ev_ci_low(firm)
        row[f"{firm}_worst_fold_ev_mean"] = c.worst_fold_ev_mean(firm)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Run 5 configs on 2 folds to verify plumbing fast.")
    parser.add_argument("--top-k-is", type=int, default=40, help="Grid survivors after IS pruning.")
    parser.add_argument("--n-simulations", type=int, default=2_000, help="Replay MC sims per candidate per fold per firm.")
    parser.add_argument("--max-workers", type=int, default=None, help="Process pool workers (None = sequential).")
    parser.add_argument(
        "--risk",
        type=float,
        default=DEFAULT_RISK_PER_TRADE_USD,
        help="Fixed per-trade dollar risk fed to the replay MC's eval_risk/funded_risk sizing (default $200).",
    )
    args = parser.parse_args()

    bars = pd.read_parquet(DATA_PATH)

    folds = make_folds(DATA_START, HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    if not folds:
        raise RuntimeError("no folds produced before holdout — check DATA_START/HOLDOUT_START")

    grid = build_coarse_grid()

    if args.smoke:
        grid = grid[:5]
        folds = folds[:2]
        n_simulations = 200
        top_k_is = 5
        print(f"[smoke] {len(grid)} configs x {len(folds)} folds, n_simulations={n_simulations}")
    else:
        n_simulations = args.n_simulations
        top_k_is = args.top_k_is
        print(f"[full] {len(grid)} configs x {len(folds)} folds, top_k_is={top_k_is}, n_simulations={n_simulations}")

    for f in folds:
        print(
            f"  fold {f.fold_index}: warmup={f.warmup_start.date()} IS=[{f.is_start.date()},{f.is_end.date()}) "
            f"OOS=[{f.oos_start.date()},{f.oos_end.date()})"
        )

    print(f"  risk_per_trade_usd={args.risk}")

    t0 = time.monotonic()
    results = run_walk_forward(
        bars,
        grid,
        folds,
        top_k_is=top_k_is,
        n_simulations=n_simulations,
        max_workers=args.max_workers,
        risk_per_trade_usd=args.risk,
    )
    elapsed = time.monotonic() - t0
    print(f"\nwalk-forward run complete in {elapsed:.1f}s, {len(results)} admissible candidates")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [_candidate_row(c) for c in results]
    for row, c in zip(rows, results, strict=True):
        row["params_hash"] = params_hash(c.params)

    csv_path = OUTPUT_DIR / ("smoke_results.csv" if args.smoke else "walk_forward_results.csv")
    json_path = OUTPUT_DIR / ("smoke_summary.json" if args.smoke else "walk_forward_summary.json")

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)

    summary = {
        "elapsed_seconds": elapsed,
        "grid_size": len(grid),
        "fold_count": len(folds),
        "risk_per_trade_usd": args.risk,
        "admissible_count": len(results),
        "apex_skipped_reason": results[0].apex_skipped_reason if results else None,
        "top10": rows[:10],
    }
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")

    print("\ntop 10 candidates:")
    if not rows:
        print("  (none admissible)")
    for row in rows[:10]:
        firm_bits = " ".join(
            f"{firm}: median_ev_low={row.get(f'{firm}_median_ev_ci_low')} worst_mean={row.get(f'{firm}_worst_fold_ev_mean')}"
            for firm in REPLAY_FIRMS
        )
        print(
            f"  or={row['or_minutes']} entry={row['entry_mode']} target_r={row['target_r']} "
            f"vol_pct_min={row['vol_percentile_min']} rel_vol_min={row['rel_volume_min']} "
            f"slip={row['slippage_ticks']} trades={row['total_oos_trades']} | {firm_bits}"
        )


if __name__ == "__main__":
    main()
