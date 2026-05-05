"""State-dependent sizing functions.

Each sizing function is a callable taking a ``SizingContext`` and returning the
dollar loss-size for the next trade. The context exposes only the account state
the sizer needs (balance, MLL, phase, payout count). The Monte Carlo engine
calls the sizer before each trade so adaptive rules — e.g. shrink risk as the
trailing drawdown closes in — can react to the live account state.

The structured-product thesis turns on whether such state-dependence flips
negative-EV WR/R:R cells positive. Without it, the sweep can only show what
fixed-risk geometry produces; with it, the optimizer can search for sizing
shapes that exploit the convex eval-fee → payout payoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SizingContext:
    """Snapshot of account state visible to a sizing function.

    Pulled from ``LucidFlexAccountState`` (and the future TopStep equivalent)
    before every trade. Keep this minimal — sizers should not be coupled to
    ruleset internals.
    """

    phase: str  # "eval" or "funded"
    balance: float
    mll: float
    starting_balance: float
    payout_count: int

    @property
    def buffer(self) -> float:
        """Distance from current balance to the trailing drawdown floor."""
        return max(0.0, self.balance - self.mll)

    @property
    def buffer_fraction(self) -> float:
        """Buffer as a fraction of starting balance (0.0 = at MLL, larger = safer)."""
        if self.starting_balance <= 0:
            return 0.0
        return self.buffer / self.starting_balance


class SizingFunction(Protocol):
    def __call__(self, ctx: SizingContext) -> float: ...


@dataclass(frozen=True)
class FixedSizing:
    """Constant per-trade dollar risk by phase.

    Baseline / null hypothesis: state-dependence does nothing if FixedSizing
    matches the optimizer's best AdaptiveSizing.
    """

    eval_size: float
    funded_size: float

    def __post_init__(self) -> None:
        if self.eval_size <= 0 or self.funded_size <= 0:
            raise ValueError("sizes must be positive")

    def __call__(self, ctx: SizingContext) -> float:
        return self.eval_size if ctx.phase == "eval" else self.funded_size


@dataclass(frozen=True)
class BufferAwareSizing:
    """Linear-shrink sizing as balance approaches the trailing drawdown floor.

    Per phase, risk is ``base_size * scale(buffer_fraction)`` where ``scale``
    grows linearly from ``min_scale`` (at zero buffer) to 1.0 once the buffer
    fraction reaches ``full_buffer_fraction``. Above that, risk is constant
    at the base. Below it, risk is floored at ``min_scale * base``.
    """

    eval_base: float
    funded_base: float
    full_buffer_fraction: float = 0.04  # 4% of starting balance = "fully safe"
    min_scale: float = 0.25  # never drop below 25% of base risk

    def __post_init__(self) -> None:
        if self.eval_base <= 0 or self.funded_base <= 0:
            raise ValueError("base sizes must be positive")
        if not 0 < self.full_buffer_fraction <= 1:
            raise ValueError("full_buffer_fraction must be in (0, 1]")
        if not 0 < self.min_scale <= 1:
            raise ValueError("min_scale must be in (0, 1]")

    def __call__(self, ctx: SizingContext) -> float:
        base = self.eval_base if ctx.phase == "eval" else self.funded_base
        ratio = ctx.buffer_fraction / self.full_buffer_fraction
        scale = self.min_scale + (1.0 - self.min_scale) * min(1.0, max(0.0, ratio))
        return base * scale


@dataclass(frozen=True)
class AdaptiveSizing:
    """Fully parameterized sizing for the optimizer search space.

    Combines per-phase base risk with a buffer-aware multiplier and a
    post-payout shrink factor (funded only). All knobs are continuous so a
    grid or Bayesian search can sweep them.

    - ``eval_base`` / ``funded_base``: dollar risk at full buffer
    - ``buffer_full_frac``: buffer fraction at which scale = 1.0
    - ``buffer_floor``: minimum scale when buffer = 0
    - ``post_payout_shrink``: multiplier on funded risk for the first cycle
      after each payout (MLL re-locks at $50,100, so the buffer is thinner)
    """

    eval_base: float
    funded_base: float
    buffer_full_frac: float = 0.04
    buffer_floor: float = 0.25
    post_payout_shrink: float = 1.0

    def __post_init__(self) -> None:
        if self.eval_base <= 0 or self.funded_base <= 0:
            raise ValueError("base sizes must be positive")
        if not 0 < self.buffer_full_frac <= 1:
            raise ValueError("buffer_full_frac must be in (0, 1]")
        if not 0 < self.buffer_floor <= 1:
            raise ValueError("buffer_floor must be in (0, 1]")
        if not 0 < self.post_payout_shrink <= 1:
            raise ValueError("post_payout_shrink must be in (0, 1]")

    def __call__(self, ctx: SizingContext) -> float:
        base = self.eval_base if ctx.phase == "eval" else self.funded_base
        ratio = ctx.buffer_fraction / self.buffer_full_frac
        scale = self.buffer_floor + (1.0 - self.buffer_floor) * min(1.0, max(0.0, ratio))
        if ctx.phase == "funded" and ctx.payout_count > 0:
            scale *= self.post_payout_shrink
        return base * scale
