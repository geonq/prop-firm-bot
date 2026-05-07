"""Sequential Monte Carlo with adaptive stopping.

Runs `replay_monte_carlo` in batches, stopping early when the 95% CIs on both
``eval_pass_rate`` and ``mean_net_ev`` are clearly on one side of their decision
thresholds. Clear winners and clear losers stop early; only borderline cases
run to ``n_max``. Uses Wilson + Normal CIs as already returned by
``summarize_pipeline_results`` to keep the stopping rule consistent with what
the dashboard renders.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.monte_carlo import MonteCarloResult, summarize_pipeline_results
from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.sizing.dynamic import SizingFunction
from src.strategies.replay import ReplayDay


FirmName = Literal["lucidflex", "topstep"]


@dataclass(frozen=True)
class StoppingConfig:
    """Decision boundaries the CI must exclude before stopping early."""

    p_pass_threshold: float = 0.20
    ev_threshold_usd: float = 0.0


@dataclass(frozen=True)
class SequentialMCResult:
    mc_result: MonteCarloResult
    n_run: int
    n_max: int
    n_init: int
    n_step: int
    iterations: int
    stopped_reason: str  # "decision_clear" | "n_max"
    p_pass_threshold: float
    ev_threshold_usd: float


def _decision_clear(summary: MonteCarloResult, stopping: StoppingConfig) -> tuple[bool, dict]:
    """True iff both p_pass and EV CIs are entirely above OR entirely below thresholds."""
    p = summary.eval_pass_ci
    p_clear = p.high < stopping.p_pass_threshold or p.low > stopping.p_pass_threshold

    e = summary.ev_ci
    e_clear = e.high < stopping.ev_threshold_usd or e.low > stopping.ev_threshold_usd

    detail = {
        "p_pass_clear": p_clear,
        "p_pass_ci": (p.low, p.high),
        "ev_clear": e_clear,
        "ev_ci": (e.low, e.high),
    }
    return (p_clear and e_clear), detail


def sequential_replay_mc(
    replay_days: Sequence[ReplayDay],
    *,
    firm: FirmName,
    n_init: int = 2_000,
    n_step: int = 2_000,
    n_max: int = 50_000,
    block_size: int = 5,
    seed: int = 0,
    target_length: int | None = None,
    stopping: StoppingConfig = StoppingConfig(),
    # TopStep wiring (mirror replay_monte_carlo.run_replay_monte_carlo)
    sizing_fn: SizingFunction | None = None,
    topstep_eval_risk: float | None = None,
    topstep_funded_risk: float | None = None,
    topstep_ruleset: TopStepNoFee50K | None = None,
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.CONSISTENCY,
    topstep_use_daily_loss_limit: bool = False,
    topstep_max_back2funded_reactivations: int = 3,
    payout_cap: int | None = 5,
    eval_cost_per_trade: float = 5.0,
    funded_cost_per_trade: float = 5.0,
    max_combine_days: int = 90,
    max_xfa_days: int = 180,
    # LucidFlex wiring
    lucidflex_ruleset: LucidFlex50K | None = None,
    lucidflex_eval_risk: float | None = None,
    lucidflex_funded_risk: float | None = None,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
) -> SequentialMCResult:
    """Block-bootstrap with adaptive stopping. See module docstring for the rule."""
    if n_init <= 0 or n_step <= 0 or n_max <= 0:
        raise ValueError("n_init, n_step, n_max must all be positive")
    if n_init > n_max:
        raise ValueError("n_init must be <= n_max")
    if firm == "lucidflex":
        if lucidflex_eval_risk is None or lucidflex_funded_risk is None:
            raise ValueError(
                "lucidflex_eval_risk and lucidflex_funded_risk are required for firm='lucidflex'"
            )
    if firm == "topstep":
        if sizing_fn is None and (topstep_eval_risk is None or topstep_funded_risk is None):
            raise ValueError(
                "for firm='topstep', pass either sizing_fn or both topstep_eval_risk and topstep_funded_risk"
            )

    sample_length = target_length if target_length is not None else len(replay_days)
    rng = random.Random(seed)
    accumulated: list = []

    def run_batch(target_total: int) -> None:
        while len(accumulated) < target_total:
            sampled = block_bootstrap_replay_days(
                replay_days,
                target_length=sample_length,
                block_size=block_size,
                rng=rng,
            )
            if firm == "topstep":
                accumulated.append(
                    simulate_topstep_trade_replay(
                        sampled,
                        sizing_fn=sizing_fn,
                        eval_risk=topstep_eval_risk if sizing_fn is None else None,
                        funded_risk=topstep_funded_risk if sizing_fn is None else None,
                        ruleset=topstep_ruleset,
                        payout_path=topstep_payout_path,
                        use_daily_loss_limit=topstep_use_daily_loss_limit,
                        eval_cost_per_trade=eval_cost_per_trade,
                        funded_cost_per_trade=funded_cost_per_trade,
                        max_combine_days=max_combine_days,
                        max_xfa_days=max_xfa_days,
                        payout_cap=payout_cap,
                        max_back2funded_reactivations=topstep_max_back2funded_reactivations,
                    )
                )
            else:
                accumulated.append(
                    simulate_lucidflex_trade_replay(
                        sampled,
                        eval_risk=lucidflex_eval_risk,
                        funded_risk=lucidflex_funded_risk,
                        ruleset=lucidflex_ruleset,
                        eval_cost_per_trade=eval_cost_per_trade,
                        funded_cost_per_trade=funded_cost_per_trade,
                        max_eval_days=max_eval_days,
                        max_funded_days=max_funded_days,
                    )
                )

    iterations = 0
    target = n_init
    while True:
        iterations += 1
        run_batch(target)
        summary = summarize_pipeline_results(accumulated, firm=firm)
        clear, _ = _decision_clear(summary, stopping)
        if clear:
            return SequentialMCResult(
                mc_result=summary,
                n_run=len(accumulated),
                n_max=n_max,
                n_init=n_init,
                n_step=n_step,
                iterations=iterations,
                stopped_reason="decision_clear",
                p_pass_threshold=stopping.p_pass_threshold,
                ev_threshold_usd=stopping.ev_threshold_usd,
            )
        if target >= n_max:
            return SequentialMCResult(
                mc_result=summary,
                n_run=len(accumulated),
                n_max=n_max,
                n_init=n_init,
                n_step=n_step,
                iterations=iterations,
                stopped_reason="n_max",
                p_pass_threshold=stopping.p_pass_threshold,
                ev_threshold_usd=stopping.ev_threshold_usd,
            )
        target = min(target + n_step, n_max)
