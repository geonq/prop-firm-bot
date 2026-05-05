"""Generic Monte Carlo aggregation over prop-firm pipelines."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult, simulate_lucidflex_pipeline
from src.pipeline.topstep_pipeline import TopStepPipelineResult, simulate_topstep_pipeline
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.strategies.parametric import (
    AutocorrelatedPhaseAwareBernoulliStrategy,
    BernoulliTradeStrategy,
    PhaseAwareBernoulliStrategy,
    RegimeSwitchingPhaseAwareBernoulliStrategy,
    StateAwareBernoulliStrategy,
)


FirmName = Literal["lucidflex", "topstep"]
Strategy = (
    BernoulliTradeStrategy
    | PhaseAwareBernoulliStrategy
    | StateAwareBernoulliStrategy
    | AutocorrelatedPhaseAwareBernoulliStrategy
    | RegimeSwitchingPhaseAwareBernoulliStrategy
)
PipelineResult = LucidFlexPipelineResult | TopStepPipelineResult


@dataclass(frozen=True)
class ConfidenceInterval:
    low: float
    high: float


@dataclass(frozen=True)
class MonteCarloResult:
    firm: FirmName
    n_simulations: int
    eval_pass_count: int
    funded_breach_count: int
    max_payout_count: int
    eval_pass_rate: float
    eval_pass_ci: ConfidenceInterval
    funded_breach_rate: float
    funded_breach_ci: ConfidenceInterval
    funded_breach_after_pass_rate: float
    funded_breach_after_pass_ci: ConfidenceInterval
    max_payout_rate: float
    max_payout_ci: ConfidenceInterval
    mean_payouts: float
    mean_trader_payouts: float
    mean_net_ev: float
    median_net_ev: float
    ev_stddev: float
    ev_stderr: float
    ev_ci: ConfidenceInterval


@dataclass(frozen=True)
class ParametricGridResult:
    firm: FirmName
    win_rate: float
    rr_ratio: float
    eval_risk: float
    funded_risk: float
    n_simulations: int
    eval_pass_rate: float
    eval_pass_ci: ConfidenceInterval
    funded_breach_rate: float
    funded_breach_ci: ConfidenceInterval
    funded_breach_after_pass_rate: float
    funded_breach_after_pass_ci: ConfidenceInterval
    max_payout_rate: float
    max_payout_ci: ConfidenceInterval
    mean_payouts: float
    mean_trader_payouts: float
    mean_net_ev: float
    median_net_ev: float
    ev_stderr: float
    ev_ci: ConfidenceInterval


def run_monte_carlo(
    strategy: Strategy,
    *,
    firm: FirmName,
    n_simulations: int = 10_000,
    seed: int = 0,
    lucidflex_ruleset: LucidFlex50K | None = None,
    topstep_ruleset: TopStepNoFee50K | None = None,
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    topstep_use_daily_loss_limit: bool = False,
    topstep_max_back2funded_reactivations: int = 0,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    payout_cap: int | None = None,
) -> MonteCarloResult:
    """Run one strategy through one firm pipeline many times and aggregate."""
    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive")

    results: list[PipelineResult] = []
    for i in range(n_simulations):
        sim_seed = seed + i
        if firm == "lucidflex":
            results.append(
                simulate_lucidflex_pipeline(
                    strategy,
                    ruleset=lucidflex_ruleset,
                    seed=sim_seed,
                    max_eval_days=max_eval_days,
                    max_funded_days=max_funded_days,
                )
            )
        elif firm == "topstep":
            results.append(
                simulate_topstep_pipeline(
                    strategy,
                    ruleset=topstep_ruleset,
                    payout_path=topstep_payout_path,
                    use_daily_loss_limit=topstep_use_daily_loss_limit,
                    seed=sim_seed,
                    max_combine_days=max_eval_days,
                    max_xfa_days=max_funded_days,
                    payout_cap=payout_cap,
                    max_back2funded_reactivations=topstep_max_back2funded_reactivations,
                )
            )
        else:
            raise ValueError(f"unknown firm: {firm}")

    return summarize_pipeline_results(results, firm=firm)


def summarize_pipeline_results(
    results: Sequence[PipelineResult],
    *,
    firm: FirmName,
) -> MonteCarloResult:
    if not results:
        raise ValueError("results must not be empty")

    n = len(results)
    eval_pass_count = sum(1 for r in results if r.eval_passed)
    funded_breach_count = sum(1 for r in results if r.funded_breached)
    max_payout_count = sum(1 for r in results if r.completed_max_payouts)
    evs = [r.net_ev for r in results]

    ev_stddev = statistics.stdev(evs) if n > 1 else 0.0
    ev_stderr = ev_stddev / math.sqrt(n) if n > 1 else 0.0
    mean_net_ev = statistics.fmean(evs)
    return MonteCarloResult(
        firm=firm,
        n_simulations=n,
        eval_pass_count=eval_pass_count,
        funded_breach_count=funded_breach_count,
        max_payout_count=max_payout_count,
        eval_pass_rate=eval_pass_count / n,
        eval_pass_ci=_wilson_ci(eval_pass_count, n),
        funded_breach_rate=funded_breach_count / n,
        funded_breach_ci=_wilson_ci(funded_breach_count, n),
        funded_breach_after_pass_rate=(
            funded_breach_count / eval_pass_count if eval_pass_count else 0.0
        ),
        funded_breach_after_pass_ci=_wilson_ci(funded_breach_count, eval_pass_count),
        max_payout_rate=max_payout_count / n,
        max_payout_ci=_wilson_ci(max_payout_count, n),
        mean_payouts=statistics.fmean(r.payout_count for r in results),
        mean_trader_payouts=statistics.fmean(r.trader_payouts for r in results),
        mean_net_ev=mean_net_ev,
        median_net_ev=statistics.median(evs),
        ev_stddev=ev_stddev,
        ev_stderr=ev_stderr,
        ev_ci=ConfidenceInterval(
            low=mean_net_ev - 1.96 * ev_stderr,
            high=mean_net_ev + 1.96 * ev_stderr,
        ),
    )


def run_parametric_grid(
    *,
    firm: FirmName,
    profiles: Sequence[tuple[float, float]],
    eval_risks: Sequence[float],
    funded_risks: Sequence[float],
    n_simulations: int = 1_000,
    seed: int = 0,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    eval_cost_per_trade: float = 5.0,
    funded_cost_per_trade: float = 5.0,
    payout_cap: int | None = None,
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    topstep_use_daily_loss_limit: bool = False,
    topstep_max_back2funded_reactivations: int = 0,
) -> list[ParametricGridResult]:
    rows: list[ParametricGridResult] = []
    for win_rate, rr_ratio in profiles:
        for eval_risk in eval_risks:
            for funded_risk in funded_risks:
                strategy = PhaseAwareBernoulliStrategy(
                    win_rate=win_rate,
                    rr_ratio=rr_ratio,
                    eval_loss_size=eval_risk,
                    funded_loss_size=funded_risk,
                    trades_per_day=1,
                    eval_cost_per_trade=eval_cost_per_trade,
                    funded_cost_per_trade=funded_cost_per_trade,
                )
                cell_seed = _cell_seed(seed, firm, win_rate, rr_ratio, eval_risk, funded_risk)
                result = run_monte_carlo(
                    strategy,
                    firm=firm,
                    n_simulations=n_simulations,
                    seed=cell_seed,
                    max_eval_days=max_eval_days,
                    max_funded_days=max_funded_days,
                    payout_cap=payout_cap,
                    topstep_payout_path=topstep_payout_path,
                    topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
                    topstep_max_back2funded_reactivations=topstep_max_back2funded_reactivations,
                )
                rows.append(
                    ParametricGridResult(
                        firm=firm,
                        win_rate=win_rate,
                        rr_ratio=rr_ratio,
                        eval_risk=eval_risk,
                        funded_risk=funded_risk,
                        n_simulations=n_simulations,
                        eval_pass_rate=result.eval_pass_rate,
                        eval_pass_ci=result.eval_pass_ci,
                        funded_breach_rate=result.funded_breach_rate,
                        funded_breach_ci=result.funded_breach_ci,
                        funded_breach_after_pass_rate=result.funded_breach_after_pass_rate,
                        funded_breach_after_pass_ci=result.funded_breach_after_pass_ci,
                        max_payout_rate=result.max_payout_rate,
                        max_payout_ci=result.max_payout_ci,
                        mean_payouts=result.mean_payouts,
                        mean_trader_payouts=result.mean_trader_payouts,
                        mean_net_ev=result.mean_net_ev,
                        median_net_ev=result.median_net_ev,
                        ev_stderr=result.ev_stderr,
                        ev_ci=result.ev_ci,
                    )
                )
    return rows


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> ConfidenceInterval:
    if n <= 0:
        return ConfidenceInterval(0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half_width = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return ConfidenceInterval(max(0.0, center - half_width), min(1.0, center + half_width))


def _cell_seed(
    seed: int,
    firm: FirmName,
    win_rate: float,
    rr_ratio: float,
    eval_risk: float,
    funded_risk: float,
) -> int:
    firm_offset = 100_000_000 if firm == "topstep" else 0
    return int(
        seed
        + firm_offset
        + win_rate * 10_000
        + rr_ratio * 1_000
        + eval_risk * 10
        + funded_risk
    )
