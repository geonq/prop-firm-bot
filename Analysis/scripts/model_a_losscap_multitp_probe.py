"""Probe Model A loss-capping and MNQ-style partial exits.

Inputs come from the clean post-bug M15 TradingView CSV. This script first
applies the high-vol entry block proxy from `model_a_highvol_block_proxy.py`,
then transforms each trade's R outcome under simple execution assumptions:

- loss cap: floor losses at a chosen negative R multiple
- partial TP + BE runner: if MFE reaches a target, take `fraction` off there
  and let the rest exit at max(realized R, 0)

This is intentionally approximate. TV exports MFE/MAE, not intratrade path
order, so it can answer "is the geometry worth implementing/exporting?" but
cannot replace a fresh Pine backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from Analysis.scripts.model_a_highvol_block_proxy import (
    RISK_AMOUNT,
    is_highvol_block,
    load_trades,
)
from src.pipeline.replay_monte_carlo import run_replay_monte_carlo
from src.pipeline.replay_validation import compute_replay_distribution_stats
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing
from src.strategies.replay import ReplayDay


RECENT_START = "2023-05-11"
MNQ10_COST_PER_TRADE = 15.0


@dataclass(frozen=True)
class Scenario:
    name: str
    loss_cap_r: float | None = None
    tp_r: float | None = None
    tp_fraction: float = 0.5
    runner_be: bool = True


SCENARIOS = (
    Scenario("raw_proxy"),
    Scenario("cap_1p50R", loss_cap_r=1.5),
    Scenario("cap_1p25R", loss_cap_r=1.25),
    Scenario("cap_1p00R", loss_cap_r=1.0),
    Scenario("cap_1p50R_tp2_50be", loss_cap_r=1.5, tp_r=2.0, tp_fraction=0.5),
    Scenario("cap_1p50R_tp3_50be", loss_cap_r=1.5, tp_r=3.0, tp_fraction=0.5),
    Scenario("cap_1p25R_tp2_50be", loss_cap_r=1.25, tp_r=2.0, tp_fraction=0.5),
    Scenario("cap_1p25R_tp3_50be", loss_cap_r=1.25, tp_r=3.0, tp_fraction=0.5),
    Scenario("cap_1p25R_tp2_30be", loss_cap_r=1.25, tp_r=2.0, tp_fraction=0.3),
)


def transform_r(trades: pd.DataFrame, scenario: Scenario) -> pd.Series:
    pnl_r = trades["pnl"].astype(float) / RISK_AMOUNT
    mfe_r = trades["Positive Exkursion USD"].astype(float) / RISK_AMOUNT
    out = pnl_r.copy()

    if scenario.loss_cap_r is not None:
        out = out.clip(lower=-scenario.loss_cap_r)

    if scenario.tp_r is not None:
        hit = mfe_r >= scenario.tp_r
        runner = out.clip(lower=0.0) if scenario.runner_be else out
        partial = scenario.tp_fraction * scenario.tp_r
        out.loc[hit] = partial + (1.0 - scenario.tp_fraction) * runner.loc[hit]

    return out


def to_replay_days(
    trades: pd.DataFrame,
    r_values: pd.Series,
    *,
    start: str = RECENT_START,
) -> list[ReplayDay]:
    scoped = trades.copy()
    scoped["r"] = r_values
    scoped = scoped[scoped["entry_ts"] >= pd.Timestamp(start)].copy()
    first = scoped["entry_ts"].dt.date.min()
    last = scoped["entry_ts"].dt.date.max()
    grouped = scoped.groupby(scoped["entry_ts"].dt.date)["r"].apply(tuple).to_dict()
    return [
        ReplayDay(day.date(), grouped.get(day.date(), ()))
        for day in pd.bdate_range(first, last)
    ]


def topstep_once(
    days: list[ReplayDay],
    *,
    risk: float,
    cost_per_trade: float = MNQ10_COST_PER_TRADE,
) -> str:
    result = simulate_topstep_trade_replay(
        days,
        sizing_fn=FixedSizing(eval_size=risk, funded_size=risk),
        payout_path=TopStepPayoutPath.CONSISTENCY,
        max_back2funded_reactivations=3,
        payout_cap=5,
        eval_cost_per_trade=cost_per_trade,
        funded_cost_per_trade=cost_per_trade,
    )
    return (
        f"{result.terminal_reason}:pass={result.eval_passed}:"
        f"d={result.combine_days}/{result.xfa_days}:"
        f"payouts={result.payout_count}:ev={result.net_ev:.0f}"
    )


def mc_summary(
    days: list[ReplayDay],
    *,
    risk: float,
    n: int,
    cost_per_trade: float = MNQ10_COST_PER_TRADE,
) -> tuple[float, float, float, float]:
    result = run_replay_monte_carlo(
        days,
        firm="topstep",
        n_simulations=n,
        seed=11,
        block_size=5,
        topstep_eval_risk=risk,
        topstep_funded_risk=risk,
        topstep_payout_path=TopStepPayoutPath.CONSISTENCY,
        topstep_max_back2funded_reactivations=3,
        payout_cap=5,
        eval_cost_per_trade=cost_per_trade,
        funded_cost_per_trade=cost_per_trade,
    )
    return (
        result.eval_pass_rate,
        result.max_payout_rate,
        result.mean_net_ev,
        result.ev_ci.low,
    )


def main() -> None:
    trades = load_trades()
    trades = trades[~is_highvol_block(trades)].copy()
    trades = trades[trades["entry_ts"] >= pd.Timestamp(RECENT_START)].copy()

    print(
        "Model A recent high-vol-block proxy "
        f"({RECENT_START}+), MNQx10 cost assumption=${MNQ10_COST_PER_TRADE:.0f}/trade"
    )
    print(
        f"{'scenario':<24} {'trades':>6} {'WR':>7} {'R':>5} {'freq':>6} "
        f"{'EV_R':>7} {'worstR':>7} {'p95MFE':>7} "
        f"{'once r200':<34} {'MC r150':>31} {'MC r200':>31} {'MC r250':>31}"
    )
    for scenario in SCENARIOS:
        r_values = transform_r(trades, scenario)
        days = to_replay_days(trades, r_values)
        dist = compute_replay_distribution_stats(tuple(days))
        flat = [r for day in days for r in day.r_multiples]
        r_series = pd.Series(flat)
        mfe_r = trades["Positive Exkursion USD"].astype(float) / RISK_AMOUNT
        once = topstep_once(days, risk=200)
        mc_parts = []
        for risk in (150.0, 200.0, 250.0):
            pass_rate, max_payout, mean_ev, ci_low = mc_summary(days, risk=risk, n=1_000)
            mc_parts.append(
                f"p={pass_rate:.2f} max={max_payout:.2f} ev={mean_ev:.0f} lo={ci_low:.0f}"
            )
        print(
            f"{scenario.name:<24} {dist.trades:>6} {dist.win_rate:>6.1%} "
            f"{dist.avg_win_loss_ratio:>5.2f} {dist.trades_per_replay_day:>6.2f} "
            f"{r_series.mean():>+7.3f} {r_series.min():>7.2f} "
            f"{mfe_r.quantile(0.95):>7.2f} {once:<34} "
            f"{mc_parts[0]:>31} {mc_parts[1]:>31} {mc_parts[2]:>31}"
        )


if __name__ == "__main__":
    main()
