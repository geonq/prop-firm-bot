"""LucidFlex account state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.rules.lucidflex import LucidFlex50K


class LucidFlexPhase(StrEnum):
    EVAL = "eval"
    FUNDED = "funded"
    BREACHED_EVAL = "breached_eval"
    BREACHED_FUNDED = "breached_funded"
    MAX_PAYOUTS = "max_payouts"


@dataclass(frozen=True)
class AccountEvent:
    phase: LucidFlexPhase
    balance: float
    mll: float
    message: str


@dataclass
class LucidFlexAccountState:
    """State machine for one LucidFlex 50K account path.

    The machine tracks one account from evaluation through funded payouts. It
    intentionally does not model live transition mechanics after the fifth
    simulated payout; `MAX_PAYOUTS` is the terminal sim-funded state for v1.
    """

    ruleset: LucidFlex50K = field(default_factory=LucidFlex50K)
    phase: LucidFlexPhase = LucidFlexPhase.EVAL
    balance: float | None = None
    mll: float | None = None
    total_fees_paid: float = 0.0
    reset_count: int = 0
    payout_count: int = 0
    total_trader_payouts: float = 0.0
    current_day_pnl: float = 0.0
    eval_daily_pnls: list[float] = field(default_factory=list)
    cycle_start_balance: float | None = None
    cycle_profitable_days: int = 0

    def __post_init__(self) -> None:
        if self.balance is None:
            self.balance = float(self.ruleset.starting_balance)
        if self.mll is None:
            self.mll = float(self.ruleset.initial_mll)
        if self.cycle_start_balance is None:
            self.cycle_start_balance = float(self.balance)
        if self.total_fees_paid == 0:
            self.total_fees_paid = float(self.ruleset.eval_fee)

    @property
    def is_breached(self) -> bool:
        return self.phase in {LucidFlexPhase.BREACHED_EVAL, LucidFlexPhase.BREACHED_FUNDED}

    @property
    def is_passed_eval(self) -> bool:
        return self.phase in {LucidFlexPhase.FUNDED, LucidFlexPhase.MAX_PAYOUTS, LucidFlexPhase.BREACHED_FUNDED}

    @property
    def total_profit(self) -> float:
        return self.balance - self.ruleset.starting_balance

    @property
    def cycle_net_profit(self) -> float:
        return self.balance - self.cycle_start_balance

    @property
    def net_ev(self) -> float:
        return self.total_trader_payouts - self.total_fees_paid

    def update(self, trade_pnl: float) -> AccountEvent:
        if self.phase not in {LucidFlexPhase.EVAL, LucidFlexPhase.FUNDED}:
            raise RuntimeError(f"cannot trade terminal LucidFlex phase {self.phase}")

        self.balance += trade_pnl
        self.current_day_pnl += trade_pnl

        if self.balance <= self.mll:
            if self.phase == LucidFlexPhase.EVAL:
                self.phase = LucidFlexPhase.BREACHED_EVAL
                return AccountEvent(self.phase, self.balance, self.mll, "eval MLL breached")
            self.phase = LucidFlexPhase.BREACHED_FUNDED
            return AccountEvent(self.phase, self.balance, self.mll, "funded MLL breached")

        if self.phase == LucidFlexPhase.EVAL and self._eval_can_pass_now():
            self._activate_funded()
            return AccountEvent(self.phase, self.balance, self.mll, "eval passed")

        return AccountEvent(self.phase, self.balance, self.mll, "trade applied")

    def close_day(self) -> AccountEvent:
        if self.phase == LucidFlexPhase.EVAL:
            self.eval_daily_pnls.append(self.current_day_pnl)
            self.mll = self.ruleset.update_mll_after_close(self.balance, self.mll)
            self.current_day_pnl = 0.0
            if self._eval_can_pass_now():
                self._activate_funded()
                return AccountEvent(self.phase, self.balance, self.mll, "eval passed at day close")
            return AccountEvent(self.phase, self.balance, self.mll, "eval day closed")

        if self.phase == LucidFlexPhase.FUNDED:
            if self.current_day_pnl >= self.ruleset.payout_min_daily_profit:
                self.cycle_profitable_days += 1
            self.mll = self.ruleset.update_mll_after_close(self.balance, self.mll)
            self.current_day_pnl = 0.0
            return AccountEvent(self.phase, self.balance, self.mll, "funded day closed")

        return AccountEvent(self.phase, self.balance, self.mll, "terminal day ignored")

    def request_payout(self) -> float:
        if self.phase != LucidFlexPhase.FUNDED:
            raise RuntimeError("LucidFlex payout is only available in funded phase")
        if self.payout_count >= self.ruleset.max_simulated_payouts:
            raise RuntimeError("LucidFlex max simulated payouts already reached")
        if self.cycle_profitable_days < self.ruleset.payout_min_profitable_days:
            raise RuntimeError("LucidFlex payout requires 5 profitable days")
        if self.cycle_net_profit <= 0:
            raise RuntimeError("LucidFlex payout requires positive cycle net profit")

        gross_request = self.ruleset.payout_request_amount(self.total_profit)
        if gross_request <= 0:
            raise RuntimeError("LucidFlex payout minimum is not met")

        trader_receives = self.ruleset.trader_payout_amount(gross_request)
        self.balance -= gross_request
        self.total_trader_payouts += trader_receives
        self.payout_count += 1
        self.cycle_profitable_days = 0
        self.cycle_start_balance = self.balance
        self.mll = float(self.ruleset.locked_mll_balance)
        self.current_day_pnl = 0.0

        if self.balance <= self.mll:
            self.phase = LucidFlexPhase.BREACHED_FUNDED
        elif self.payout_count >= self.ruleset.max_simulated_payouts:
            self.phase = LucidFlexPhase.MAX_PAYOUTS

        return trader_receives

    def attempt_reset(self) -> float:
        if self.phase != LucidFlexPhase.BREACHED_EVAL:
            raise RuntimeError("LucidFlex reset is only modeled for breached eval accounts")

        self.phase = LucidFlexPhase.EVAL
        self.balance = float(self.ruleset.starting_balance)
        self.mll = float(self.ruleset.initial_mll)
        self.current_day_pnl = 0.0
        self.eval_daily_pnls.clear()
        self.cycle_start_balance = self.balance
        self.cycle_profitable_days = 0
        self.reset_count += 1
        self.total_fees_paid += self.ruleset.reset_cost_estimate
        return float(self.ruleset.reset_cost_estimate)

    def _eval_can_pass_now(self) -> bool:
        total_profit = self.balance - self.ruleset.starting_balance
        daily_pnls = self.eval_daily_pnls + [self.current_day_pnl]
        return self.ruleset.consistency_ok(daily_pnls, total_profit)

    def _activate_funded(self) -> None:
        self.phase = LucidFlexPhase.FUNDED
        self.balance = float(self.ruleset.starting_balance)
        self.mll = float(self.ruleset.initial_mll)
        self.current_day_pnl = 0.0
        self.eval_daily_pnls.clear()
        self.cycle_start_balance = self.balance
        self.cycle_profitable_days = 0
