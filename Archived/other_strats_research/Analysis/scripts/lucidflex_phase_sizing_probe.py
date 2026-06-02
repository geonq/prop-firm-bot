"""Probe phase-aware sizing through the LucidFlex pipeline.

This keeps the same synthetic WR/R:R assumptions but changes risk between eval
and funded phases.

Run:
    .venv/bin/python Analysis/scripts/lucidflex_phase_sizing_probe.py
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult, simulate_lucidflex_pipeline
from src.strategies.parametric import PhaseAwareBernoulliStrategy


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
        "eval_pass_rate": len(passed) / n,
        "funded_breach_rate": len(funded_breaches) / n,
        "max_payout_rate": len(max_payouts) / n,
        "mean_payouts": mean(r.payout_count for r in rows),
        "mean_trader_payouts": mean(r.trader_payouts for r in rows),
        "mean_net_ev": mean(r.net_ev for r in rows),
        "median_net_ev": statistics.median(r.net_ev for r in rows),
    }


def run_cell(
    win_rate: float,
    rr_ratio: float,
    eval_loss_size: float,
    funded_loss_size: float,
    eval_cost_per_trade: float,
    funded_cost_per_trade: float,
) -> dict[str, float | int]:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        eval_loss_size=eval_loss_size,
        funded_loss_size=funded_loss_size,
        trades_per_day=1,
        eval_cost_per_trade=eval_cost_per_trade,
        funded_cost_per_trade=funded_cost_per_trade,
    )
    results = (
        simulate_lucidflex_pipeline(
            strategy,
            seed=70_000 + i,
            max_eval_days=MAX_EVAL_DAYS,
            max_funded_days=MAX_FUNDED_DAYS,
        )
        for i in range(N_SIMS)
    )
    summary = summarize(results)
    summary["eval_ev_per_trade"] = strategy.expected_value_per_trade("eval")
    summary["funded_ev_per_trade"] = strategy.expected_value_per_trade("funded")
    return summary


def main() -> None:
    print("LucidFlex 50K phase-sizing probe: same WR/RR, different eval/funded risk")
    print(f"Simulations/cell: {N_SIMS:,} | Eval days: {MAX_EVAL_DAYS} | Funded days: {MAX_FUNDED_DAYS}")
    print("Cost model: $5/trade in both phases. Synthetic distribution only.")
    print()

    scenarios = [
        # label, win_rate, rr_ratio, eval_risk, funded_risk
        ("base", 0.45, 1.50, 250.0, 250.0),
        ("funded_half", 0.45, 1.50, 250.0, 125.0),
        ("funded_150", 0.45, 1.50, 250.0, 150.0),
        ("base", 0.50, 1.25, 250.0, 250.0),
        ("funded_half", 0.50, 1.25, 250.0, 125.0),
        ("funded_150", 0.50, 1.25, 250.0, 150.0),
        ("base", 0.55, 1.00, 250.0, 250.0),
        ("funded_half", 0.55, 1.00, 250.0, 125.0),
        ("funded_150", 0.55, 1.00, 250.0, 150.0),
    ]

    header = (
        f"{'case':>12} {'WR':>5} {'RR':>5} {'evalR':>7} {'fundR':>7} "
        f"{'eval pass':>10} {'fund br':>8} {'max po':>8} {'avg po':>7} "
        f"{'avg paid':>9} {'mean EV':>9} {'med EV':>8}"
    )
    print(header)
    print("-" * len(header))

    for label, win_rate, rr_ratio, eval_loss_size, funded_loss_size in scenarios:
        summary = run_cell(
            win_rate,
            rr_ratio,
            eval_loss_size,
            funded_loss_size,
            eval_cost_per_trade=5.0,
            funded_cost_per_trade=5.0,
        )
        print(
            f"{label:>12} {win_rate:5.2f} {rr_ratio:5.2f} "
            f"{eval_loss_size:7.0f} {funded_loss_size:7.0f} "
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
    print("  - This isolates sizing only; WR/RR are still assumed, not backtested.")
    print("  - Lower funded risk can reduce funded breaches but may also slow payout collection.")


if __name__ == "__main__":
    main()
