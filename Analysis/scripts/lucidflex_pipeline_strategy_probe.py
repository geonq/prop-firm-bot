"""Probe ORB-like distributions through the full LucidFlex pipeline.

This is synthetic. It uses the same i.i.d. trade distribution in eval and
funded, so it is a path-geometry probe rather than a historical strategy test.

Run:
    python3 Analysis/scripts/lucidflex_pipeline_strategy_probe.py
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult, simulate_lucidflex_pipeline
from src.strategies.parametric import BernoulliTradeStrategy


N_SIMS = 10_000
MAX_EVAL_DAYS = 90
MAX_FUNDED_DAYS = 180


def pct(value: float) -> str:
    return f"{value * 100:6.2f}%"


def mean(values: Iterable[float]) -> float:
    rows = list(values)
    return statistics.fmean(rows) if rows else 0.0


def summarize(results: Iterable[LucidFlexPipelineResult]) -> dict[str, float | int]:
    rows = list(results)
    n = len(rows)
    passed = [r for r in rows if r.eval_passed]
    funded_breaches = [r for r in rows if r.funded_breached]
    max_payouts = [r for r in rows if r.completed_max_payouts]
    return {
        "n": n,
        "eval_pass_rate": len(passed) / n,
        "funded_breach_rate": len(funded_breaches) / n,
        "max_payout_rate": len(max_payouts) / n,
        "mean_payouts": mean(r.payout_count for r in rows),
        "mean_trader_payouts": mean(r.trader_payouts for r in rows),
        "mean_net_ev": mean(r.net_ev for r in rows),
        "median_net_ev": statistics.median(r.net_ev for r in rows),
    }


def run_cell(win_rate: float, rr_ratio: float, loss_size: float, cost_per_trade: float) -> dict[str, float | int]:
    strategy = BernoulliTradeStrategy(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        loss_size=loss_size,
        trades_per_day=1,
        cost_per_trade=cost_per_trade,
    )
    results = (
        simulate_lucidflex_pipeline(
            strategy,
            seed=50_000 + i,
            max_eval_days=MAX_EVAL_DAYS,
            max_funded_days=MAX_FUNDED_DAYS,
        )
        for i in range(N_SIMS)
    )
    summary = summarize(results)
    summary["ev_per_trade"] = strategy.expected_value_per_trade
    return summary


def main() -> None:
    print("LucidFlex 50K full-pipeline probe: synthetic ORB-like one-trade/day distributions")
    print(
        f"Simulations/cell: {N_SIMS:,} | Eval days: {MAX_EVAL_DAYS} | "
        f"Funded days: {MAX_FUNDED_DAYS} | Eval fee: $175"
    )
    print("Funded model: request payout whenever eligible; max 5 simulated payouts; same distribution in eval/funded.")
    print()

    scenarios = [
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
        f"{'WR':>5} {'RR':>5} {'risk':>6} {'EV/tr':>8} {'eval pass':>10} "
        f"{'fund br':>8} {'max po':>8} {'avg po':>7} {'avg paid':>9} "
        f"{'mean EV':>9} {'med EV':>8}"
    )
    print(header)
    print("-" * len(header))

    for win_rate, rr_ratio, loss_size, cost_per_trade in scenarios:
        summary = run_cell(win_rate, rr_ratio, loss_size, cost_per_trade)
        print(
            f"{win_rate:5.2f} {rr_ratio:5.2f} {loss_size:6.0f} "
            f"{summary['ev_per_trade']:8.1f} "
            f"{pct(summary['eval_pass_rate'])} "
            f"{pct(summary['funded_breach_rate'])} "
            f"{pct(summary['max_payout_rate'])} "
            f"{summary['mean_payouts']:7.2f} "
            f"{summary['mean_trader_payouts']:9.0f} "
            f"{summary['mean_net_ev']:9.0f} "
            f"{summary['median_net_ev']:8.0f}"
        )

    print()
    print("Interpretation guardrails:")
    print("  - Positive mean EV here does not prove ORB is profitable; the trade distribution is assumed.")
    print("  - Median EV can remain negative even when mean EV is positive because most attempts lose the fee.")
    print("  - The next required upgrade is phase-aware sizing and real trade exports.")


if __name__ == "__main__":
    main()
