"""ONE-SHOT holdout evaluation of the frozen ORB winner across all four firm-variants.

Protocol note (documented deviation): `evaluate_holdout` in walk_forward.py guards
one (params, firm) pair per hash. The verdict needs the SAME frozen trade list
scored under all four firms' account rules — identical trades, no re-tuning, so
this script performs the single holdout pass computing all four firms at once,
then writes the immutable record and creates the sentinel via the same paths.
Any second invocation refuses. The frozen params were selected 2026-07-17 from
the walk-forward plateau (or=15, first_candle, or_opposite, 4R, no filters) at
the conservative 2-tick slippage; risk $200/trade.

This mirrors run_replay_monte_carlo's loop verbatim (same seed/bootstrap) while
also collecting per-pipeline day counts for EV-per-month conversion.
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
    _fold_replay_days,
    params_hash,
)
from src.pipeline.apex_replay import simulate_apex_trade_replay
from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.monte_carlo import summarize_pipeline_results
from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
from src.pipeline.topstep_replay import simulate_topstep_trade_replay

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
OUT_DIR = ROOT / "Analysis" / "output" / "orb"
N_SIMULATIONS = 10_000
SEED = 0
BLOCK_SIZE = 5
RISK = 200.0
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

FIRMS = ["lucidflex", "topstep", "apex_eod", "apex_intraday"]


def _simulate(firm: str, sampled) -> object:
    if firm == "lucidflex":
        return simulate_lucidflex_trade_replay(sampled, eval_risk=RISK, funded_risk=RISK)
    if firm == "topstep":
        return simulate_topstep_trade_replay(sampled, eval_risk=RISK, funded_risk=RISK)
    variant = "eod" if firm == "apex_eod" else "intraday"
    return simulate_apex_trade_replay(
        sampled, eval_risk=RISK, funded_risk=RISK, drawdown_variant=variant
    )


def main() -> None:
    params_h = params_hash(FROZEN)
    sentinel_dir = OUT_DIR / "HOLDOUT_UNLOCKED"
    sentinel = sentinel_dir / f"{params_h}.lock"
    if sentinel.exists():
        raise PermissionError(f"holdout already evaluated for {params_h}; refusing second run")

    bars = pd.read_parquet(PARQUET)
    holdout_start = pd.Timestamp(HOLDOUT_START)
    holdout_end = bars.index.max().tz_convert("UTC")
    warmup_start = holdout_start - pd.DateOffset(months=3)

    trades, replay_days = _fold_replay_days(
        bars, FROZEN, warmup_start=warmup_start, window_start=holdout_start, window_end=holdout_end
    )
    n = len(trades)
    wins = sum(1 for t in trades if t.r_multiple > 0)
    mean_r = sum(t.r_multiple for t in trades) / n if n else 0.0
    print(f"HOLDOUT {holdout_start.date()}..{holdout_end.date()}  trades={n}  "
          f"WR={wins / n:.4f}  meanR={mean_r:.4f}")

    firm_records = {}
    for firm in FIRMS:
        rng = random.Random(SEED)
        results = []
        for _ in range(N_SIMULATIONS):
            sampled = block_bootstrap_replay_days(
                replay_days, target_length=len(replay_days), block_size=BLOCK_SIZE, rng=rng
            )
            results.append(_simulate(firm, sampled))
        summary_firm = "apex" if firm.startswith("apex") else firm
        s = summarize_pipeline_results(results, firm=summary_firm)
        total_days = [r.eval_days + r.funded_days for r in results]
        mean_days = sum(total_days) / len(total_days)
        ev_per_month = s.mean_net_ev / mean_days * TRADING_DAYS_PER_MONTH
        ev_low_per_month = s.ev_ci.low / mean_days * TRADING_DAYS_PER_MONTH
        firm_records[firm] = {
            "net_ev_mean": s.mean_net_ev,
            "net_ev_ci_low": s.ev_ci.low,
            "net_ev_ci_high": s.ev_ci.high,
            "median_net_ev": s.median_net_ev,
            "eval_pass_rate": s.eval_pass_rate,
            "funded_breach_after_pass_rate": s.funded_breach_after_pass_rate,
            "mean_payouts": s.mean_payouts,
            "mean_trader_payouts": s.mean_trader_payouts,
            "mean_pipeline_days": mean_days,
            "ev_per_month_mean": ev_per_month,
            "ev_per_month_ci_low": ev_low_per_month,
        }
        print(f"{firm:14s} net_ev={s.mean_net_ev:9.2f} [{s.ev_ci.low:8.2f},{s.ev_ci.high:8.2f}] "
              f"P(pass)={s.eval_pass_rate:.3f} payouts={s.mean_payouts:.2f} "
              f"days={mean_days:6.1f} EV/mo={ev_per_month:8.2f} (lowCI {ev_low_per_month:8.2f})")

    record = {
        "params_hash": params_h,
        "params": {
            "or_minutes": FROZEN.or_minutes,
            "entry_mode": FROZEN.entry_mode,
            "stop_mode": FROZEN.stop_mode,
            "target_r": FROZEN.target_r,
            "vol_percentile_min": FROZEN.vol_percentile_min,
            "rel_volume_min": FROZEN.rel_volume_min,
            "slippage_ticks": FROZEN.slippage_ticks,
        },
        "protocol_note": "single holdout pass, all four firm-variants on identical frozen trade list",
        "timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "holdout_start": str(holdout_start.date()),
        "holdout_end": str(holdout_end.date()),
        "risk_per_trade_usd": RISK,
        "n_simulations": N_SIMULATIONS,
        "seed": SEED,
        "block_size": BLOCK_SIZE,
        "trade_count": n,
        "win_rate": wins / n if n else 0.0,
        "mean_r": mean_r,
        "firms": firm_records,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    record_path = OUT_DIR / f"holdout_{params_h}.json"
    record_path.write_text(json.dumps(record, indent=2))
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(record["timestamp_utc"])
    print(f"\nwrote {record_path}\nsentinel {sentinel} — holdout is now permanently locked")


if __name__ == "__main__":
    main()
