"""Risk-level sweep for the frozen ORB winner — PRE-HOLDOUT DATA ONLY.

The strategy params are frozen (2026-07-17 verdict); only the per-trade dollar
risk fed to the replay MC varies. Evidence level: walk-forward folds
(2020→2025-06). The holdout is burned and is NOT consulted — results here are
fold-level evidence, to be validated on H2-2026 data once it accumulates.

Stage 2 (per-month conversion with day counts) runs pooled over the pre-holdout
window for the top risk levels.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    HOLDOUT_START,
    REPLAY_FIRMS,
    _fold_replay_days,
    make_folds,
    run_walk_forward,
)
from src.pipeline.apex_replay import simulate_apex_trade_replay
from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.monte_carlo import summarize_pipeline_results
from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
from src.pipeline.topstep_replay import simulate_topstep_trade_replay

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
OUT = ROOT / "Analysis" / "output" / "orb"
RISK_LEVELS = [100.0, 150.0, 200.0, 250.0, 300.0, 400.0]
TRADING_DAYS_PER_MONTH = 21

FROZEN = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
)


def _simulate(firm: str, sampled, risk: float):
    if firm == "lucidflex":
        return simulate_lucidflex_trade_replay(sampled, eval_risk=risk, funded_risk=risk)
    if firm == "topstep":
        return simulate_topstep_trade_replay(sampled, eval_risk=risk, funded_risk=risk)
    variant = "eod" if firm == "apex_eod" else "intraday"
    return simulate_apex_trade_replay(sampled, eval_risk=risk, funded_risk=risk, drawdown_variant=variant)


def main() -> None:
    bars = pd.read_parquet(PARQUET)
    folds = make_folds(pd.Timestamp("2020-01-01"), pd.Timestamp(HOLDOUT_START))
    print(f"folds: {len(folds)}  risk levels: {RISK_LEVELS}")

    # Stage 1: fold-level sweep computed directly (run_walk_forward returns
    # admissible-only ranked candidates, which crashes the sweep at risk levels
    # where the config fails a clause — here we want the numbers regardless).
    # Trades are independent of risk: backtest each fold's OOS window ONCE,
    # then rescore the replay MC per risk level.
    from statistics import median

    from src.optimizer.walk_forward import _replay_mc_summary

    fold_days = []
    for f in folds:
        _, rd = _fold_replay_days(
            bars, FROZEN,
            warmup_start=f.oos_start - pd.DateOffset(months=3),
            window_start=f.oos_start, window_end=f.oos_end,
        )
        fold_days.append(rd)

    rows = []
    for risk in RISK_LEVELS:
        row = {"risk": risk}
        for firm in REPLAY_FIRMS:
            per_fold = []
            for rd in fold_days:
                s = _replay_mc_summary(
                    list(rd), firm=firm, n_simulations=2_000, seed=0,
                    block_size=5, eval_risk=risk, funded_risk=risk,
                )
                if s is not None:
                    per_fold.append(s)
            row[f"{firm}_median_low"] = round(median(s.net_ev_ci_low for s in per_fold), 1)
            row[f"{firm}_worst_mean"] = round(min(s.net_ev_mean for s in per_fold), 1)
        rows.append(row)
        print(row)

    # Stage 2: pooled pre-holdout replay MC with day counts -> EV/month.
    warmup_start = pd.Timestamp("2020-01-01")
    window_end = pd.Timestamp(HOLDOUT_START)
    _, replay_days = _fold_replay_days(
        bars, FROZEN, warmup_start=warmup_start,
        window_start=pd.Timestamp("2020-04-01"), window_end=window_end,
    )
    monthly = []
    for risk in RISK_LEVELS:
        rec = {"risk": risk}
        for firm in REPLAY_FIRMS:
            rng = random.Random(0)
            results = []
            for _ in range(3_000):
                sampled = block_bootstrap_replay_days(
                    replay_days, target_length=len(replay_days), block_size=5, rng=rng
                )
                results.append(_simulate(firm, sampled, risk))
            s = summarize_pipeline_results(results, firm="apex" if firm.startswith("apex") else firm)
            mean_days = sum(r.eval_days + r.funded_days for r in results) / len(results)
            rec[f"{firm}_ev_attempt"] = round(s.mean_net_ev, 1)
            rec[f"{firm}_pass"] = round(s.eval_pass_rate, 3)
            rec[f"{firm}_days"] = round(mean_days, 1)
            rec[f"{firm}_ev_month"] = round(s.mean_net_ev / mean_days * TRADING_DAYS_PER_MONTH, 1)
        monthly.append(rec)
        print(rec)

    out = {"frozen_params_hash_note": "risk is scoring-side; strategy params frozen",
           "fold_sweep": rows, "pooled_preholdout_monthly": monthly}
    (OUT / "risk_sweep.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT / 'risk_sweep.json'}")


if __name__ == "__main__":
    main()
