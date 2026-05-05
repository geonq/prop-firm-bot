"""Parametric strategy distributions for simulator probes."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.sizing.dynamic import SizingContext, SizingFunction


@dataclass(frozen=True)
class BernoulliTradeStrategy:
    """I.i.d. win/loss trade generator.

    This is not a claim about real ORB profitability. It is a controlled proxy
    for testing whether a trade distribution shape can survive a prop-firm
    ruleset.
    """

    win_rate: float
    rr_ratio: float
    loss_size: float
    trades_per_day: int = 1
    cost_per_trade: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be in [0, 1]")
        if self.rr_ratio <= 0:
            raise ValueError("rr_ratio must be positive")
        if self.loss_size <= 0:
            raise ValueError("loss_size must be positive")
        if self.trades_per_day <= 0:
            raise ValueError("trades_per_day must be positive")
        if self.cost_per_trade < 0:
            raise ValueError("cost_per_trade must be non-negative")

    @property
    def win_size(self) -> float:
        return self.rr_ratio * self.loss_size

    @property
    def expected_value_per_trade(self) -> float:
        gross = self.win_rate * self.win_size - (1 - self.win_rate) * self.loss_size
        return gross - self.cost_per_trade

    def sample_trade(self, rng: random.Random) -> float:
        gross_pnl = self.win_size if rng.random() < self.win_rate else -self.loss_size
        return gross_pnl - self.cost_per_trade


@dataclass(frozen=True)
class PhaseAwareBernoulliStrategy:
    """Bernoulli generator with separate eval and funded risk.

    Win-rate and R:R are kept constant so this isolates the effect of sizing
    across account phases.
    """

    win_rate: float
    rr_ratio: float
    eval_loss_size: float
    funded_loss_size: float
    trades_per_day: int = 1
    eval_cost_per_trade: float = 0.0
    funded_cost_per_trade: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be in [0, 1]")
        if self.rr_ratio <= 0:
            raise ValueError("rr_ratio must be positive")
        if self.eval_loss_size <= 0:
            raise ValueError("eval_loss_size must be positive")
        if self.funded_loss_size <= 0:
            raise ValueError("funded_loss_size must be positive")
        if self.trades_per_day <= 0:
            raise ValueError("trades_per_day must be positive")
        if self.eval_cost_per_trade < 0 or self.funded_cost_per_trade < 0:
            raise ValueError("costs must be non-negative")

    def loss_size(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_loss_size
        if phase == "funded":
            return self.funded_loss_size
        msg = f"unknown phase: {phase}"
        raise ValueError(msg)

    def cost_per_trade(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_cost_per_trade
        if phase == "funded":
            return self.funded_cost_per_trade
        msg = f"unknown phase: {phase}"
        raise ValueError(msg)

    def expected_value_per_trade(self, phase: str) -> float:
        loss_size = self.loss_size(phase)
        gross = self.win_rate * self.rr_ratio * loss_size - (1 - self.win_rate) * loss_size
        return gross - self.cost_per_trade(phase)

    def sample_trade(self, rng: random.Random, *, phase: str) -> float:
        loss_size = self.loss_size(phase)
        win_size = self.rr_ratio * loss_size
        gross_pnl = win_size if rng.random() < self.win_rate else -loss_size
        return gross_pnl - self.cost_per_trade(phase)


@dataclass(frozen=True)
class StrategyRegime:
    """One probabilistic regime for synthetic stress tests."""

    name: str
    probability: float
    win_rate: float
    rr_ratio: float

    def __post_init__(self) -> None:
        if self.probability <= 0:
            raise ValueError("regime probability must be positive")
        if not 0 <= self.win_rate <= 1:
            raise ValueError("regime win_rate must be in [0, 1]")
        if self.rr_ratio <= 0:
            raise ValueError("regime rr_ratio must be positive")


@dataclass
class AutocorrelatedPhaseAwareBernoulliStrategy:
    """Phase-aware Bernoulli generator with win/loss persistence.

    ``autocorrelation`` controls outcome clustering:
    - 0.0 = i.i.d. Bernoulli with ``win_rate``
    - 1.0 = once the first result is sampled, every future result repeats it

    This intentionally models path risk, not edge. Same headline WR/reward-risk
    can become worse under prop-firm drawdown rules if losses cluster.
    """

    win_rate: float
    rr_ratio: float
    eval_loss_size: float
    funded_loss_size: float
    trades_per_day: int = 1
    autocorrelation: float = 0.0
    eval_cost_per_trade: float = 0.0
    funded_cost_per_trade: float = 0.0
    _last_win: bool | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be in [0, 1]")
        if self.rr_ratio <= 0:
            raise ValueError("rr_ratio must be positive")
        if self.eval_loss_size <= 0 or self.funded_loss_size <= 0:
            raise ValueError("loss sizes must be positive")
        if self.trades_per_day <= 0:
            raise ValueError("trades_per_day must be positive")
        if not 0 <= self.autocorrelation <= 1:
            raise ValueError("autocorrelation must be in [0, 1]")
        if self.eval_cost_per_trade < 0 or self.funded_cost_per_trade < 0:
            raise ValueError("costs must be non-negative")

    def reset(self) -> None:
        self._last_win = None

    def loss_size(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_loss_size
        if phase == "funded":
            return self.funded_loss_size
        raise ValueError(f"unknown phase: {phase}")

    def cost_per_trade(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_cost_per_trade
        if phase == "funded":
            return self.funded_cost_per_trade
        raise ValueError(f"unknown phase: {phase}")

    def _next_win_probability(self) -> float:
        if self._last_win is None:
            return self.win_rate
        if self._last_win:
            return self.win_rate + self.autocorrelation * (1.0 - self.win_rate)
        return self.win_rate * (1.0 - self.autocorrelation)

    def sample_trade(self, rng: random.Random, *, phase: str) -> float:
        loss_size = self.loss_size(phase)
        p_win = self._next_win_probability()
        is_win = rng.random() < p_win
        self._last_win = is_win
        gross_pnl = self.rr_ratio * loss_size if is_win else -loss_size
        return gross_pnl - self.cost_per_trade(phase)


@dataclass(frozen=True)
class RegimeSwitchingPhaseAwareBernoulliStrategy:
    """Phase-aware generator that samples from named market regimes per trade."""

    regimes: tuple[StrategyRegime, ...]
    eval_loss_size: float
    funded_loss_size: float
    trades_per_day: int = 1
    eval_cost_per_trade: float = 0.0
    funded_cost_per_trade: float = 0.0

    def __post_init__(self) -> None:
        if not self.regimes:
            raise ValueError("at least one regime is required")
        if self.eval_loss_size <= 0 or self.funded_loss_size <= 0:
            raise ValueError("loss sizes must be positive")
        if self.trades_per_day <= 0:
            raise ValueError("trades_per_day must be positive")
        if self.eval_cost_per_trade < 0 or self.funded_cost_per_trade < 0:
            raise ValueError("costs must be non-negative")

    def loss_size(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_loss_size
        if phase == "funded":
            return self.funded_loss_size
        raise ValueError(f"unknown phase: {phase}")

    def cost_per_trade(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_cost_per_trade
        if phase == "funded":
            return self.funded_cost_per_trade
        raise ValueError(f"unknown phase: {phase}")

    def sample_regime(self, rng: random.Random) -> StrategyRegime:
        total = sum(r.probability for r in self.regimes)
        draw = rng.random() * total
        cumulative = 0.0
        for regime in self.regimes:
            cumulative += regime.probability
            if draw <= cumulative:
                return regime
        return self.regimes[-1]

    def sample_trade(self, rng: random.Random, *, phase: str) -> float:
        regime = self.sample_regime(rng)
        loss_size = self.loss_size(phase)
        gross_pnl = regime.rr_ratio * loss_size if rng.random() < regime.win_rate else -loss_size
        return gross_pnl - self.cost_per_trade(phase)


@dataclass(frozen=True)
class StateAwareBernoulliStrategy:
    """Bernoulli generator with a state-dependent sizing function.

    The sizer is called per trade with a ``SizingContext`` snapshot of the
    account, returning the dollar loss-size. Win amount is ``rr_ratio *
    loss_size``. Cost per trade is phase-keyed and applied symmetrically.

    This is the strategy class the optimizer searches over: hold WR/RR fixed,
    sweep the parameters of the sizing function, and find which sizing shape
    maximizes net EV through eval → funded → payouts.
    """

    win_rate: float
    rr_ratio: float
    sizing_fn: SizingFunction
    trades_per_day: int = 1
    eval_cost_per_trade: float = 0.0
    funded_cost_per_trade: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be in [0, 1]")
        if self.rr_ratio <= 0:
            raise ValueError("rr_ratio must be positive")
        if self.trades_per_day <= 0:
            raise ValueError("trades_per_day must be positive")
        if self.eval_cost_per_trade < 0 or self.funded_cost_per_trade < 0:
            raise ValueError("costs must be non-negative")

    def cost_per_trade(self, phase: str) -> float:
        if phase == "eval":
            return self.eval_cost_per_trade
        if phase == "funded":
            return self.funded_cost_per_trade
        msg = f"unknown phase: {phase}"
        raise ValueError(msg)

    def sample_trade(self, rng: random.Random, *, ctx: SizingContext) -> float:
        loss_size = self.sizing_fn(ctx)
        if loss_size <= 0:
            return -self.cost_per_trade(ctx.phase)
        win_size = self.rr_ratio * loss_size
        gross_pnl = win_size if rng.random() < self.win_rate else -loss_size
        return gross_pnl - self.cost_per_trade(ctx.phase)
