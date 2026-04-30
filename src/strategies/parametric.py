"""Parametric strategy distributions for simulator probes."""

from __future__ import annotations

import random
from dataclasses import dataclass


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
