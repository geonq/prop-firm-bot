"""Strict validation gates for historical replay exports.

The single-shot replay and replay Monte Carlo tools are useful diagnostics, but
Phase 4 needs a harder decision rule: a strategy must hold up in chronological
out-of-sample slices and in external volatility regimes before it is treated as
worth forward testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.pipeline.monte_carlo import MonteCarloResult
from src.strategies.replay import ReplayDay


SliceKind = Literal["full", "train", "oos", "fold", "vol_regime"]


@dataclass(frozen=True)
class ReplayDistributionStats:
    trades: int
    replay_days: int
    trading_days: int
    win_rate: float
    avg_win_loss_ratio: float
    trades_per_replay_day: float
    trades_per_trading_day: float
    lag10_outcome_autocorr: float
    inside_profile4: bool


@dataclass(frozen=True)
class ValidationGateConfig:
    min_trades: int = 100
    min_replay_days: int = 40
    min_trading_days: int = 20
    require_profile4: bool = True
    min_ev_ci_low: float = 0.0
    min_eval_pass_rate: float = 0.0
    max_funded_breach_after_pass_rate: float = 1.0


@dataclass(frozen=True)
class ValidationSliceResult:
    label: str
    kind: SliceKind
    stats: ReplayDistributionStats
    mc_result: MonteCarloResult | None
    passed: bool
    failures: tuple[str, ...]


def compute_replay_distribution_stats(
    replay_days: list[ReplayDay] | tuple[ReplayDay, ...],
) -> ReplayDistributionStats:
    """Compute the raw distribution gate used by Profile 4."""
    r_multiples = [r for day in replay_days for r in day.r_multiples]
    replay_day_count = len(replay_days)
    trading_days = sum(1 for day in replay_days if day.r_multiples)

    if not r_multiples:
        stats = ReplayDistributionStats(
            trades=0,
            replay_days=replay_day_count,
            trading_days=trading_days,
            win_rate=0.0,
            avg_win_loss_ratio=0.0,
            trades_per_replay_day=0.0,
            trades_per_trading_day=0.0,
            lag10_outcome_autocorr=0.0,
            inside_profile4=False,
        )
        return stats

    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    win_loss_ratio = avg_win / avg_loss if avg_loss else float("inf")
    stats = ReplayDistributionStats(
        trades=len(r_multiples),
        replay_days=replay_day_count,
        trading_days=trading_days,
        win_rate=len(wins) / len(r_multiples),
        avg_win_loss_ratio=win_loss_ratio,
        trades_per_replay_day=len(r_multiples) / replay_day_count
        if replay_day_count
        else 0.0,
        trades_per_trading_day=len(r_multiples) / trading_days
        if trading_days
        else 0.0,
        lag10_outcome_autocorr=_outcome_autocorr(r_multiples, lag=10),
        inside_profile4=False,
    )
    return ReplayDistributionStats(
        **{
            **stats.__dict__,
            "inside_profile4": _inside_profile4(stats),
        }
    )


def chronological_train_oos_split(
    replay_days: list[ReplayDay] | tuple[ReplayDay, ...],
    *,
    train_fraction: float,
) -> tuple[tuple[ReplayDay, ...], tuple[ReplayDay, ...]]:
    """Split ordered replay days into old train and newer OOS holdout."""
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if len(replay_days) < 2:
        raise ValueError("at least two replay days are required")

    split_index = int(len(replay_days) * train_fraction)
    split_index = max(1, min(split_index, len(replay_days) - 1))
    return tuple(replay_days[:split_index]), tuple(replay_days[split_index:])


def chronological_folds(
    replay_days: list[ReplayDay] | tuple[ReplayDay, ...],
    *,
    fold_count: int,
) -> tuple[tuple[ReplayDay, ...], ...]:
    """Return contiguous chronological folds covering the full replay."""
    if fold_count <= 0:
        raise ValueError("fold_count must be positive")
    if fold_count > len(replay_days):
        raise ValueError("fold_count cannot exceed replay day count")

    n = len(replay_days)
    folds: list[tuple[ReplayDay, ...]] = []
    for index in range(fold_count):
        start = round(index * n / fold_count)
        end = round((index + 1) * n / fold_count)
        folds.append(tuple(replay_days[start:end]))
    return tuple(folds)


def filter_replay_days_by_dates(
    replay_days: list[ReplayDay] | tuple[ReplayDay, ...],
    allowed_dates: set,
) -> tuple[ReplayDay, ...]:
    """Keep replay days whose session_date exists in `allowed_dates`."""
    return tuple(day for day in replay_days if day.session_date in allowed_dates)


def evaluate_validation_slice(
    *,
    label: str,
    kind: SliceKind,
    replay_days: list[ReplayDay] | tuple[ReplayDay, ...],
    gate: ValidationGateConfig,
    mc_result: MonteCarloResult | None = None,
) -> ValidationSliceResult:
    """Evaluate raw-distribution and optional MC conditions for one slice."""
    stats = compute_replay_distribution_stats(replay_days)
    failures: list[str] = []

    if stats.trades < gate.min_trades:
        failures.append(f"trades {stats.trades} < {gate.min_trades}")
    if stats.replay_days < gate.min_replay_days:
        failures.append(f"replay_days {stats.replay_days} < {gate.min_replay_days}")
    if stats.trading_days < gate.min_trading_days:
        failures.append(f"trading_days {stats.trading_days} < {gate.min_trading_days}")
    if gate.require_profile4 and not stats.inside_profile4:
        failures.append("raw distribution outside Profile 4")

    if mc_result is not None:
        if mc_result.ev_ci.low < gate.min_ev_ci_low:
            failures.append(
                f"MC EV CI low {mc_result.ev_ci.low:.0f} < {gate.min_ev_ci_low:.0f}"
            )
        if mc_result.eval_pass_rate < gate.min_eval_pass_rate:
            failures.append(
                "MC eval_pass "
                f"{mc_result.eval_pass_rate:.3f} < {gate.min_eval_pass_rate:.3f}"
            )
        if (
            mc_result.funded_breach_after_pass_rate
            > gate.max_funded_breach_after_pass_rate
        ):
            failures.append(
                "MC breach_after_pass "
                f"{mc_result.funded_breach_after_pass_rate:.3f} > "
                f"{gate.max_funded_breach_after_pass_rate:.3f}"
            )

    return ValidationSliceResult(
        label=label,
        kind=kind,
        stats=stats,
        mc_result=mc_result,
        passed=not failures,
        failures=tuple(failures),
    )


def _inside_profile4(stats: ReplayDistributionStats) -> bool:
    return (
        0.40 <= stats.win_rate <= 0.50
        and 1.7 <= stats.avg_win_loss_ratio <= 2.3
        and 2.0 <= stats.trades_per_replay_day <= 4.0
        and stats.lag10_outcome_autocorr <= 0.3
    )


def _outcome_autocorr(r_multiples: list[float], *, lag: int) -> float:
    outcomes = [1.0 if r > 0 else 0.0 for r in r_multiples if r != 0]
    if len(outcomes) <= lag:
        return 0.0
    x = outcomes[:-lag]
    y = outcomes[lag:]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in x)
    var_y = sum((b - mean_y) ** 2 for b in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x * var_y) ** 0.5
