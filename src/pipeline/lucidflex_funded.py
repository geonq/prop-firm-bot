"""LucidFlex funded account state.

This module models deterministic funded-account mechanics needed before the
Monte Carlo pipeline can score strategies by payout EV.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rules.lucidflex import LucidFlex50K


@dataclass(frozen=True)
class PayoutResult:
    gross_request: float
    trader_receives: float
    account_balance_after: float
    payout_count: int


@dataclass
class LucidFlexFundedAccount:
    ruleset: LucidFlex50K = field(default_factory=LucidFlex50K)
    balance: float | None = None
    mll: float | None = None
    cycle_start_balance: float | None = None
    cycle_profitable_days: int = 0
    payout_count: int = 0
    total_trader_payouts: float = 0.0
    breached: bool = False
    current_day_pnl: float = 0.0

    def __post_init__(self) -> None:
        if self.balance is None:
            self.balance = float(self.ruleset.starting_balance)
        if self.mll is None:
            self.mll = float(self.ruleset.initial_mll)
        if self.cycle_start_balance is None:
            self.cycle_start_balance = float(self.balance)

    @property
    def simulated_profit(self) -> float:
        return self.balance - self.ruleset.starting_balance

    @property
    def cycle_net_profit(self) -> float:
        return self.balance - self.cycle_start_balance

    def apply_trade(self, pnl: float) -> None:
        if self.breached:
            raise RuntimeError("cannot trade a breached account")

        self.balance += pnl
        self.current_day_pnl += pnl
        if self.balance <= self.mll:
            self.breached = True

    def close_day(self) -> None:
        if self.breached:
            return

        if self.current_day_pnl >= self.ruleset.payout_min_daily_profit:
            self.cycle_profitable_days += 1

        self.mll = self.ruleset.update_mll_after_close(self.balance, self.mll)
        self.current_day_pnl = 0.0

    def max_contracts(self, *, micros: bool = False) -> int:
        return self.ruleset.max_contracts(
            micros=micros,
            phase="funded",
            simulated_profit=self.simulated_profit,
        )

    def eligible_payout_request_amount(self) -> float:
        if self.breached:
            return 0.0
        if self.payout_count >= self.ruleset.max_simulated_payouts:
            return 0.0
        if self.cycle_profitable_days < self.ruleset.payout_min_profitable_days:
            return 0.0
        if self.cycle_net_profit <= 0:
            return 0.0

        return self.ruleset.payout_request_amount(self.simulated_profit)

    def payout_eligible(self) -> bool:
        return self.eligible_payout_request_amount() > 0

    def request_payout(self) -> PayoutResult:
        gross_request = self.eligible_payout_request_amount()
        if gross_request <= 0:
            raise RuntimeError("payout is not currently eligible")

        trader_receives = self.ruleset.trader_payout_amount(gross_request)
        self.balance -= gross_request
        self.total_trader_payouts += trader_receives
        self.payout_count += 1
        self.cycle_profitable_days = 0
        self.cycle_start_balance = self.balance
        self.mll = float(self.ruleset.locked_mll_balance)

        if self.balance <= self.mll:
            self.breached = True

        return PayoutResult(
            gross_request=gross_request,
            trader_receives=trader_receives,
            account_balance_after=self.balance,
            payout_count=self.payout_count,
        )
