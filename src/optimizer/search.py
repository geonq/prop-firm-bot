"""Grid search over sizing function parameters per WR/reward-risk cell.

For a fixed (win_rate, reward/risk) profile, sweeps the parameter grid of an
``AdaptiveSizing`` function and ranks each parameter combination by mean net
EV across N Monte Carlo pipelines. The point: prove (or falsify) that
state-dependent sizing flips negative-EV cells positive — the load-bearing
test of the structured-product thesis.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.pipeline.monte_carlo import FirmName, run_monte_carlo
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import AdaptiveSizing
from src.strategies.parametric import StateAwareBernoulliStrategy


@dataclass(frozen=True)
class OptimizerCellResult:
    firm: FirmName
    win_rate: float
    rr_ratio: float
    eval_base: float
    funded_base: float
    buffer_full_frac: float
    buffer_floor: float
    post_payout_shrink: float
    n_sims: int
    eval_pass_rate: float
    funded_breach_after_pass_rate: float
    max_payout_rate: float
    mean_net_ev: float
    median_net_ev: float
    ev_stddev: float
    topstep_payout_path: TopStepPayoutPath | None = None
    topstep_use_daily_loss_limit: bool = False
    topstep_max_back2funded_reactivations: int = 0

    @property
    def ev_stderr(self) -> float:
        return self.ev_stddev / (self.n_sims ** 0.5) if self.n_sims else 0.0


def _evaluate(
    firm: FirmName,
    win_rate: float,
    rr_ratio: float,
    sizing: AdaptiveSizing,
    n_sims: int,
    max_eval_days: int,
    max_funded_days: int,
    eval_cost_per_trade: float,
    funded_cost_per_trade: float,
    topstep_payout_path: TopStepPayoutPath,
    topstep_use_daily_loss_limit: bool,
    topstep_max_back2funded_reactivations: int,
    payout_cap: int | None,
) -> OptimizerCellResult:
    strategy = StateAwareBernoulliStrategy(
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        sizing_fn=sizing,
        trades_per_day=1,
        eval_cost_per_trade=eval_cost_per_trade,
        funded_cost_per_trade=funded_cost_per_trade,
    )
    seed_base = int(
        (100_000_000 if firm == "topstep" else 0)
        + win_rate * 10_000
        + rr_ratio * 1_000
        + sizing.eval_base * 10
        + sizing.funded_base
        + sizing.buffer_full_frac * 100
        + sizing.buffer_floor * 100
        + sizing.post_payout_shrink * 100
    )
    result = run_monte_carlo(
        strategy,
        firm=firm,
        n_simulations=n_sims,
        seed=seed_base,
        max_eval_days=max_eval_days,
        max_funded_days=max_funded_days,
        topstep_payout_path=topstep_payout_path,
        topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=topstep_max_back2funded_reactivations,
        payout_cap=payout_cap,
    )
    return OptimizerCellResult(
        firm=firm,
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        eval_base=sizing.eval_base,
        funded_base=sizing.funded_base,
        buffer_full_frac=sizing.buffer_full_frac,
        buffer_floor=sizing.buffer_floor,
        post_payout_shrink=sizing.post_payout_shrink,
        n_sims=n_sims,
        eval_pass_rate=result.eval_pass_rate,
        funded_breach_after_pass_rate=result.funded_breach_after_pass_rate,
        max_payout_rate=result.max_payout_rate,
        mean_net_ev=result.mean_net_ev,
        median_net_ev=result.median_net_ev,
        ev_stddev=result.ev_stddev,
        topstep_payout_path=topstep_payout_path if firm == "topstep" else None,
        topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=(
            topstep_max_back2funded_reactivations if firm == "topstep" else 0
        ),
    )


def search_adaptive_grid(
    win_rate: float,
    rr_ratio: float,
    eval_bases: Sequence[float],
    funded_bases: Sequence[float],
    buffer_full_fracs: Sequence[float] = (0.04,),
    buffer_floors: Sequence[float] = (0.25,),
    post_payout_shrinks: Sequence[float] = (1.0,),
    n_sims: int = 1_000,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    eval_cost_per_trade: float = 5.0,
    funded_cost_per_trade: float = 5.0,
    firm: FirmName = "lucidflex",
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    topstep_use_daily_loss_limit: bool = False,
    topstep_max_back2funded_reactivations: int = 0,
    payout_cap: int | None = None,
) -> list[OptimizerCellResult]:
    """Sweep AdaptiveSizing parameters for one WR/reward-risk cell.

    Returns rows sorted by mean net EV descending. Caller decides what
    "winning" means (highest mean, best EV/stderr ratio, etc.).
    """
    rows: list[OptimizerCellResult] = []
    for eval_base in eval_bases:
        for funded_base in funded_bases:
            for buffer_full_frac in buffer_full_fracs:
                for buffer_floor in buffer_floors:
                    for post_payout_shrink in post_payout_shrinks:
                        sizing = AdaptiveSizing(
                            eval_base=eval_base,
                            funded_base=funded_base,
                            buffer_full_frac=buffer_full_frac,
                            buffer_floor=buffer_floor,
                            post_payout_shrink=post_payout_shrink,
                        )
                        rows.append(
                            _evaluate(
                                firm=firm,
                                win_rate=win_rate,
                                rr_ratio=rr_ratio,
                                sizing=sizing,
                                n_sims=n_sims,
                                max_eval_days=max_eval_days,
                                max_funded_days=max_funded_days,
                                eval_cost_per_trade=eval_cost_per_trade,
                                funded_cost_per_trade=funded_cost_per_trade,
                                topstep_payout_path=topstep_payout_path,
                                topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
                                topstep_max_back2funded_reactivations=topstep_max_back2funded_reactivations,
                                payout_cap=payout_cap,
                            )
                        )
    rows.sort(key=lambda r: r.mean_net_ev, reverse=True)
    return rows


def search_profiles(
    profiles: Iterable[tuple[float, float]],
    eval_bases: Sequence[float],
    funded_bases: Sequence[float],
    buffer_full_fracs: Sequence[float] = (0.04,),
    buffer_floors: Sequence[float] = (0.25,),
    post_payout_shrinks: Sequence[float] = (1.0,),
    n_sims: int = 1_000,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    eval_cost_per_trade: float = 5.0,
    funded_cost_per_trade: float = 5.0,
    firm: FirmName = "lucidflex",
    topstep_payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    topstep_use_daily_loss_limit: bool = False,
    topstep_max_back2funded_reactivations: int = 0,
    payout_cap: int | None = None,
) -> list[OptimizerCellResult]:
    """Run ``search_adaptive_grid`` over multiple (WR, R:R) profiles."""
    rows: list[OptimizerCellResult] = []
    for win_rate, rr_ratio in profiles:
        rows.extend(
            search_adaptive_grid(
                win_rate=win_rate,
                rr_ratio=rr_ratio,
                eval_bases=eval_bases,
                funded_bases=funded_bases,
                buffer_full_fracs=buffer_full_fracs,
                buffer_floors=buffer_floors,
                post_payout_shrinks=post_payout_shrinks,
                n_sims=n_sims,
                max_eval_days=max_eval_days,
                max_funded_days=max_funded_days,
                eval_cost_per_trade=eval_cost_per_trade,
                funded_cost_per_trade=funded_cost_per_trade,
                firm=firm,
                topstep_payout_path=topstep_payout_path,
                topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
                topstep_max_back2funded_reactivations=topstep_max_back2funded_reactivations,
                payout_cap=payout_cap,
            )
        )
    return rows
