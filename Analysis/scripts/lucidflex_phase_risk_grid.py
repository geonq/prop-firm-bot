"""Grid search eval/funded risk for LucidFlex synthetic profiles.

This is still a synthetic distribution search. It ranks risk geometry under
assumed WR/R:R cells; it does not validate that a market strategy can produce
those cells.

Run:
    .venv/bin/python Analysis/scripts/lucidflex_phase_risk_grid.py
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult, simulate_lucidflex_pipeline
from src.strategies.parametric import PhaseAwareBernoulliStrategy


N_SIMS = 5_000
MAX_EVAL_DAYS = 90
MAX_FUNDED_DAYS = 180
EVAL_RISKS = (100.0, 150.0, 200.0, 250.0, 300.0)
FUNDED_RISKS = (100.0, 125.0, 150.0, 200.0, 250.0, 300.0)
PROFILES = (
    (0.45, 1.50),
    (0.50, 1.25),
    (0.55, 1.00),
)


@dataclass(frozen=True)
class GridResult:
    win_rate: float
    rr_ratio: float
    eval_risk: float
    funded_risk: float
    eval_pass_rate: float
    funded_breach_rate: float
    funded_breach_after_pass_rate: float
    max_payout_rate: float
    mean_payouts: float
    mean_trader_payouts: float
    mean_net_ev: float
    median_net_ev: float


def pct(value: float) -> str:
    return f"{value * 100:6.2f}%"


def mean(values: Iterable[float]) -> float:
    rows = list(values)
    return statistics.fmean(rows) if rows else 0.0


def summarize(
    win_rate: float,
    rr_ratio: float,
    eval_risk: float,
    funded_risk: float,
    results: Iterable[LucidFlexPipelineResult],
) -> GridResult:
    rows = list(results)
    n = len(rows)
    passed = [r for r in rows if r.eval_passed]
    funded_breaches = [r for r in rows if r.funded_breached]
    max_payouts = [r for r in rows if r.completed_max_payouts]
    return GridResult(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        eval_risk=eval_risk,
        funded_risk=funded_risk,
        eval_pass_rate=len(passed) / n,
        funded_breach_rate=len(funded_breaches) / n,
        funded_breach_after_pass_rate=len(funded_breaches) / len(passed) if passed else 0.0,
        max_payout_rate=len(max_payouts) / n,
        mean_payouts=mean(r.payout_count for r in rows),
        mean_trader_payouts=mean(r.trader_payouts for r in rows),
        mean_net_ev=mean(r.net_ev for r in rows),
        median_net_ev=statistics.median(r.net_ev for r in rows),
    )


def run_cell(
    win_rate: float,
    rr_ratio: float,
    eval_risk: float,
    funded_risk: float,
    n_sims: int = N_SIMS,
    max_eval_days: int = MAX_EVAL_DAYS,
    max_funded_days: int = MAX_FUNDED_DAYS,
) -> GridResult:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        eval_loss_size=eval_risk,
        funded_loss_size=funded_risk,
        trades_per_day=1,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )
    seed_base = int(win_rate * 10_000 + rr_ratio * 1_000 + eval_risk * 10 + funded_risk)
    results = (
        simulate_lucidflex_pipeline(
            strategy,
            seed=seed_base + i,
            max_eval_days=max_eval_days,
            max_funded_days=max_funded_days,
        )
        for i in range(n_sims)
    )
    return summarize(win_rate, rr_ratio, eval_risk, funded_risk, results)


def run_grid(
    profiles: Iterable[tuple[float, float]],
    eval_risks: Iterable[float],
    funded_risks: Iterable[float],
    n_sims: int = N_SIMS,
    max_eval_days: int = MAX_EVAL_DAYS,
    max_funded_days: int = MAX_FUNDED_DAYS,
) -> list[GridResult]:
    rows: list[GridResult] = []
    for win_rate, rr_ratio in profiles:
        for eval_risk in eval_risks:
            for funded_risk in funded_risks:
                rows.append(
                    run_cell(
                        win_rate,
                        rr_ratio,
                        eval_risk,
                        funded_risk,
                        n_sims=n_sims,
                        max_eval_days=max_eval_days,
                        max_funded_days=max_funded_days,
                    )
                )
    return rows


def print_table(title: str, rows: list[GridResult], limit: int = 12) -> None:
    print(title)
    header = (
        f"{'WR':>5} {'RR':>5} {'evalR':>7} {'fundR':>7} {'eval pass':>10} "
        f"{'fund br/a':>9} {'fund br/p':>9} {'max po':>8} {'avg po':>7} {'avg paid':>9} "
        f"{'mean EV':>9} {'med EV':>8}"
    )
    print(header)
    print("-" * len(header))
    for row in rows[:limit]:
        print(
            f"{row.win_rate:5.2f} {row.rr_ratio:5.2f} "
            f"{row.eval_risk:7.0f} {row.funded_risk:7.0f} "
            f"{pct(row.eval_pass_rate)} "
            f"{pct(row.funded_breach_rate)} "
            f"{pct(row.funded_breach_after_pass_rate)} "
            f"{pct(row.max_payout_rate)} "
            f"{row.mean_payouts:7.2f} "
            f"{row.mean_trader_payouts:9.0f} "
            f"{row.mean_net_ev:9.0f} "
            f"{row.median_net_ev:8.0f}"
        )
    print()


def main() -> None:
    print("LucidFlex 50K phase-risk grid search")
    print(
        f"Profiles: {PROFILES} | Eval risks: {EVAL_RISKS} | "
        f"Funded risks: {FUNDED_RISKS} | Sims/cell: {N_SIMS:,}"
    )
    print("Synthetic WR/RR only; this does not validate a market edge.")
    print()

    rows = run_grid(PROFILES, EVAL_RISKS, FUNDED_RISKS)

    by_mean_ev = sorted(rows, key=lambda row: row.mean_net_ev, reverse=True)
    by_profile_best = []
    for profile in PROFILES:
        profile_rows = [row for row in rows if (row.win_rate, row.rr_ratio) == profile]
        by_profile_best.extend(sorted(profile_rows, key=lambda row: row.mean_net_ev, reverse=True)[:5])

    print_table("Top cells by mean net EV", by_mean_ev, limit=15)
    print_table("Top 5 cells per WR/RR profile", by_profile_best, limit=len(by_profile_best))

    viable = [
        row
        for row in rows
        if row.mean_net_ev > 0
        and row.funded_breach_after_pass_rate < 0.85
        and row.max_payout_rate > 0.01
    ]
    print_table(
        "Lower-risk cells: mean EV > 0, conditional funded breach < 85%, max-payout > 1%",
        sorted(viable, key=lambda row: row.mean_net_ev, reverse=True),
        limit=20,
    )

    print("Guardrail:")
    print("  fund br/a = funded breach across all eval attempts.")
    print("  fund br/p = funded breach conditional on passing eval.")
    print("  Positive mean EV here is still conditional on assumed WR/R:R. Real NQ/MNQ trade exports must reproduce the distribution.")


if __name__ == "__main__":
    main()
