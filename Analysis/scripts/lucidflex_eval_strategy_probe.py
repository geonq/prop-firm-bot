"""Probe ORB-like trade distributions against LucidFlex 50K eval rules.

This is a synthetic strategy-distribution test, not a historical ORB backtest.
It answers: if ORB-like trades produced a given win rate, R:R, and risk size,
would that path shape work inside LucidFlex's evaluation barrier mechanics?

Run:
    python3 Analysis/scripts/lucidflex_eval_strategy_probe.py
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.eval_simulator import EvalAttemptResult, simulate_lucidflex_eval
from src.rules.lucidflex import LucidFlex50K
from src.strategies.parametric import BernoulliTradeStrategy


N_SIMS = 10_000
MAX_DAYS = 90


def pct(value: float) -> str:
    return f"{value * 100:6.2f}%"


def summarize(results: Iterable[EvalAttemptResult]) -> dict[str, float | int | None]:
    rows = list(results)
    passed = [r for r in rows if r.passed]
    breached = [r for r in rows if r.breached]
    timed_out = [r for r in rows if r.timed_out]
    consistency_delayed = [r for r in rows if r.target_touches_before_consistency > 0]

    return {
        "n": len(rows),
        "pass_rate": len(passed) / len(rows),
        "breach_rate": len(breached) / len(rows),
        "timeout_rate": len(timed_out) / len(rows),
        "consistency_delay_rate": len(consistency_delayed) / len(rows),
        "median_days_to_pass": statistics.median([r.days_used for r in passed]) if passed else None,
        "median_total_profit": statistics.median([r.total_profit for r in rows]),
    }


def run_cell(win_rate: float, rr_ratio: float, loss_size: float, cost_per_trade: float) -> dict[str, float | int | None]:
    strategy = BernoulliTradeStrategy(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        loss_size=loss_size,
        trades_per_day=1,
        cost_per_trade=cost_per_trade,
    )
    results = (
        simulate_lucidflex_eval(strategy, ruleset=LucidFlex50K(), seed=10_000 + i, max_days=MAX_DAYS)
        for i in range(N_SIMS)
    )
    summary = summarize(results)
    summary["ev_per_trade"] = strategy.expected_value_per_trade
    return summary


def main() -> None:
    print("LucidFlex 50K eval probe: synthetic ORB-like one-trade/day distributions")
    print(f"Simulations/cell: {N_SIMS:,} | Max days: {MAX_DAYS} | Rules: EOD MLL + 52% eval consistency cushion")
    print("Cost model: $5/trade placeholder. Replace after TradingView/commission model is fixed.")
    print()

    scenarios = [
        # win_rate, rr_ratio, loss_size, cost_per_trade
        (0.35, 2.00, 150.0, 5.0),
        (0.40, 1.50, 150.0, 5.0),
        (0.45, 1.25, 150.0, 5.0),
        (0.50, 1.00, 150.0, 5.0),
        (0.45, 1.50, 150.0, 5.0),
        (0.50, 1.25, 150.0, 5.0),
        (0.55, 1.00, 150.0, 5.0),
        (0.45, 1.50, 250.0, 5.0),
        (0.50, 1.25, 250.0, 5.0),
        (0.55, 1.00, 250.0, 5.0),
    ]

    header = (
        f"{'WR':>6} {'RR':>5} {'risk':>7} {'EV/tr':>8} {'pass':>8} "
        f"{'breach':>8} {'timeout':>8} {'cons-dly':>9} {'med pass d':>10} {'med PnL':>9}"
    )
    print(header)
    print("-" * len(header))

    for win_rate, rr_ratio, loss_size, cost_per_trade in scenarios:
        summary = run_cell(win_rate, rr_ratio, loss_size, cost_per_trade)
        median_days = summary["median_days_to_pass"]
        median_days_text = f"{median_days:10.1f}" if median_days is not None else f"{'--':>10}"
        print(
            f"{win_rate:6.2f} {rr_ratio:5.2f} {loss_size:7.0f} "
            f"{summary['ev_per_trade']:8.1f} "
            f"{pct(summary['pass_rate'])} "
            f"{pct(summary['breach_rate'])} "
            f"{pct(summary['timeout_rate'])} "
            f"{pct(summary['consistency_delay_rate'])} "
            f"{median_days_text} "
            f"{summary['median_total_profit']:9.0f}"
        )

    print()
    print("Interpretation guardrails:")
    print("  - This is not historical ORB performance.")
    print("  - It tests whether ORB-like WR/RR/risk profiles are compatible with LucidFlex eval mechanics.")
    print("  - Any profile that only works at high risk may still fail after real slippage, clustering, and bad fills.")


if __name__ == "__main__":
    main()
