"""Monte Carlo over historical replay days via block bootstrap.

Single-shot replay through `simulate_topstep_trade_replay` /
`simulate_lucidflex_trade_replay` answers "what happened in this exact trade
sequence." It does not answer "what fraction of plausible orderings of these
trades pass the eval and survive funded." Block bootstrap resamples the
historical sequence many times to estimate that distribution with CIs, while
preserving short-run autocorrelation through the block size.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal

from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.monte_carlo import MonteCarloResult, summarize_pipeline_results
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.sizing.dynamic import SizingFunction
from src.strategies.replay import ReplayDay


FirmName = Literal["lucidflex", "topstep"]


_BOOTSTRAP_DATE_ANCHOR = date(2026, 1, 5)


def block_bootstrap_replay_days(
    replay_days: Sequence[ReplayDay],
    *,
    target_length: int,
    block_size: int,
    rng: random.Random,
    restamp_dates: bool = True,
) -> tuple[ReplayDay, ...]:
    """Block-bootstrap a sequence of `target_length` ReplayDays.

    Picks `ceil(target_length / block_size)` random start indices uniformly from
    `[0, len(replay_days) - block_size]`, concatenates the corresponding blocks,
    and truncates to `target_length`.

    `restamp_dates=True` (default) overwrites each sampled day's `session_date`
    with a synthetic ascending sequence so the result satisfies replay-pipeline
    validators (which require monotonically increasing dates). Trade outcomes
    are unchanged; only the date label moves.
    """
    if not replay_days:
        raise ValueError("replay_days must not be empty")
    if target_length <= 0:
        raise ValueError("target_length must be positive")
    if block_size <= 0:
        raise ValueError("block_size must be positive")

    source_len = len(replay_days)
    effective_block = min(block_size, source_len)
    max_start = source_len - effective_block
    out: list[ReplayDay] = []
    while len(out) < target_length:
        start = rng.randint(0, max_start)
        out.extend(replay_days[start : start + effective_block])
    out = out[:target_length]
    if restamp_dates:
        out = [
            ReplayDay(session_date=_BOOTSTRAP_DATE_ANCHOR + timedelta(days=i), r_multiples=day.r_multiples)
            for i, day in enumerate(out)
        ]
    return tuple(out)


def run_replay_monte_carlo(
    replay_days: Sequence[ReplayDay],
    *,
    firm: FirmName,
    n_simulations: int = 10_000,
    seed: int = 0,
    block_size: int = 5,
    target_length: int | None = None,
    # TopStep wiring
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
) -> MonteCarloResult:
    """Block-bootstrap a TV trade list `n_simulations` times and aggregate.

    The replay pipelines are deterministic given a sequence; the Monte Carlo
    randomness lives entirely in the block bootstrap of the input sequence.
    Bootstrapped sequence length defaults to the source length, which makes the
    CI a "what-if-resample-this-history" estimate.

    For LucidFlex, both `lucidflex_eval_risk` and `lucidflex_funded_risk` must
    be provided (mirroring the single-shot `simulate_lucidflex_trade_replay`
    contract — Lucid replay does not currently accept a sizing function).
    """
    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive")
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
    results = []
    for _ in range(n_simulations):
        sampled = block_bootstrap_replay_days(
            replay_days,
            target_length=sample_length,
            block_size=block_size,
            rng=rng,
        )
        if firm == "topstep":
            results.append(
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
        elif firm == "lucidflex":
            results.append(
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
        else:
            raise ValueError(f"unknown firm: {firm}")

    return summarize_pipeline_results(results, firm=firm)
