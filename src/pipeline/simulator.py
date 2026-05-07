"""Generic prop-firm simulation facade.

This module is the stable Phase 3 entry point for callers that should not
know which per-firm pipeline implements the account lifecycle underneath.
It intentionally stays thin: firm-specific state machines remain the source
of truth, while this facade validates option boundaries and routes the call.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult, simulate_lucidflex_pipeline
from src.pipeline.monte_carlo import FirmName, MonteCarloResult, Strategy, run_monte_carlo
from src.pipeline.topstep_pipeline import TopStepPipelineResult, simulate_topstep_pipeline
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath


@dataclass(frozen=True)
class SimulationConfig:
    firm: FirmName
    lucidflex_ruleset: LucidFlex50K | None = None
    topstep_ruleset: TopStepNoFee50K | None = None
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD
    topstep_use_daily_loss_limit: bool = False
    topstep_max_back2funded_reactivations: int = 0
    max_eval_days: int = 90
    max_funded_days: int = 180
    payout_cap: int | None = None


PipelineResult = LucidFlexPipelineResult | TopStepPipelineResult


def simulate_one(
    strategy: Strategy,
    config: SimulationConfig,
    *,
    seed: int | None = None,
) -> PipelineResult:
    """Run one pipeline attempt using a firm-agnostic config object."""
    _validate_config(config)
    if config.firm == "lucidflex":
        return simulate_lucidflex_pipeline(
            strategy,
            ruleset=config.lucidflex_ruleset,
            seed=seed,
            max_eval_days=config.max_eval_days,
            max_funded_days=config.max_funded_days,
        )

    if config.firm == "topstep":
        return simulate_topstep_pipeline(
            strategy,
            ruleset=config.topstep_ruleset,
            payout_path=config.topstep_payout_path,
            use_daily_loss_limit=config.topstep_use_daily_loss_limit,
            seed=seed,
            max_combine_days=config.max_eval_days,
            max_xfa_days=config.max_funded_days,
            payout_cap=config.payout_cap,
            max_back2funded_reactivations=config.topstep_max_back2funded_reactivations,
        )

    raise ValueError(f"unknown firm: {config.firm}")


def simulate_many(
    strategy: Strategy,
    config: SimulationConfig,
    *,
    n_simulations: int,
    seed: int = 0,
) -> MonteCarloResult:
    """Run Monte Carlo using the same firm-agnostic config."""
    _validate_config(config)
    return run_monte_carlo(
        strategy,
        firm=config.firm,
        n_simulations=n_simulations,
        seed=seed,
        lucidflex_ruleset=config.lucidflex_ruleset,
        topstep_ruleset=config.topstep_ruleset,
        topstep_payout_path=config.topstep_payout_path,
        topstep_use_daily_loss_limit=config.topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=config.topstep_max_back2funded_reactivations,
        max_eval_days=config.max_eval_days,
        max_funded_days=config.max_funded_days,
        payout_cap=config.payout_cap,
    )


def _validate_config(config: SimulationConfig) -> None:
    if config.max_eval_days <= 0:
        raise ValueError("max_eval_days must be positive")
    if config.max_funded_days <= 0:
        raise ValueError("max_funded_days must be positive")
    if config.payout_cap is not None and config.payout_cap <= 0:
        raise ValueError("payout_cap must be positive when provided")
    if config.topstep_max_back2funded_reactivations < 0:
        raise ValueError("topstep_max_back2funded_reactivations must be non-negative")

    if config.firm == "lucidflex":
        if config.topstep_ruleset is not None:
            raise ValueError("topstep_ruleset is invalid for LucidFlex")
        if config.topstep_payout_path != TopStepPayoutPath.STANDARD:
            raise ValueError("topstep_payout_path is invalid for LucidFlex")
        if config.topstep_use_daily_loss_limit:
            raise ValueError("topstep_use_daily_loss_limit is invalid for LucidFlex")
        if config.topstep_max_back2funded_reactivations:
            raise ValueError("topstep_max_back2funded_reactivations is invalid for LucidFlex")
        if config.payout_cap is not None:
            raise ValueError("payout_cap is invalid for LucidFlex")
        return

    if config.firm == "topstep":
        if config.lucidflex_ruleset is not None:
            raise ValueError("lucidflex_ruleset is invalid for TopStep")
        return

    raise ValueError(f"unknown firm: {config.firm}")
