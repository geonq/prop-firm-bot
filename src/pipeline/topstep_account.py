"""TopStep No Activation Fee account state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath


class TopStepPhase(StrEnum):
    COMBINE = "combine"
    XFA = "xfa"
    COMBINE_FAILED = "combine_failed"
    XFA_CLOSED = "xfa_closed"


@dataclass(frozen=True)
class TopStepAccountEvent:
    phase: TopStepPhase
    balance: float
    mll: float
    message: str


@dataclass
class TopStepNoFeeAccountState:
    """State machine for one TopStep 50K No Activation Fee account path."""

    ruleset: TopStepNoFee50K = field(default_factory=TopStepNoFee50K)
    payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD
    use_daily_loss_limit: bool = False
    phase: TopStepPhase = TopStepPhase.COMBINE
    balance: float | None = None
    mll: float | None = None
    total_fees_paid: float = 0.0
    reset_count: int = 0
    back2funded_count: int = 0
    payout_count: int = 0
    total_trader_payouts: float = 0.0
    current_day_pnl: float = 0.0
    combine_daily_pnls: list[float] = field(default_factory=list)
    cycle_daily_pnls: list[float] = field(default_factory=list)
    standard_winning_days: int = 0
    daily_locked: bool = False

    def __post_init__(self) -> None:
        if self.balance is None:
            self.balance = float(self.ruleset.combine_starting_balance)
        if self.mll is None:
            self.mll = float(self.ruleset.combine_initial_mll)
        if self.total_fees_paid == 0:
            self.total_fees_paid = float(self.ruleset.nofee_monthly_fee)

    @property
    def is_breached(self) -> bool:
        return self.phase in {TopStepPhase.COMBINE_FAILED, TopStepPhase.XFA_CLOSED}

    @property
    def is_passed_eval(self) -> bool:
        return self.phase in {TopStepPhase.XFA, TopStepPhase.XFA_CLOSED}

    @property
    def net_ev(self) -> float:
        return self.total_trader_payouts - self.total_fees_paid

    def update(self, trade_pnl: float) -> TopStepAccountEvent:
        if self.phase not in {TopStepPhase.COMBINE, TopStepPhase.XFA}:
            raise RuntimeError(f"cannot trade terminal TopStep phase {self.phase}")
        if self.daily_locked:
            raise RuntimeError("TopStep DLL lock prevents more trades this session")

        self.balance += trade_pnl
        self.current_day_pnl += trade_pnl

        if self.balance <= self.mll:
            if self.phase == TopStepPhase.COMBINE:
                self.phase = TopStepPhase.COMBINE_FAILED
                return TopStepAccountEvent(self.phase, self.balance, self.mll, "combine MLL breached")
            self.phase = TopStepPhase.XFA_CLOSED
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "XFA MLL breached")

        if self.use_daily_loss_limit and self.current_day_pnl <= -self.ruleset.daily_loss_limit:
            self.daily_locked = True
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "DLL locked for session")

        if self.phase == TopStepPhase.COMBINE and self._combine_can_pass_now():
            self._activate_xfa()
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "combine passed")

        return TopStepAccountEvent(self.phase, self.balance, self.mll, "trade applied")

    def close_day(self) -> TopStepAccountEvent:
        if self.phase == TopStepPhase.COMBINE:
            self.combine_daily_pnls.append(self.current_day_pnl)
            self.mll = self.ruleset.update_combine_mll_after_close(self.balance, self.mll)
            self.current_day_pnl = 0.0
            self.daily_locked = False
            if self._combine_can_pass_now():
                self._activate_xfa()
                return TopStepAccountEvent(self.phase, self.balance, self.mll, "combine passed at day close")
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "combine day closed")

        if self.phase == TopStepPhase.XFA:
            self.cycle_daily_pnls.append(self.current_day_pnl)
            if self.current_day_pnl >= self.ruleset.standard_min_winning_day:
                self.standard_winning_days += 1
            self.mll = self.ruleset.update_xfa_mll_after_close(self.balance, self.mll)
            self.current_day_pnl = 0.0
            self.daily_locked = False
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "XFA day closed")

        self.current_day_pnl = 0.0
        self.daily_locked = False
        return TopStepAccountEvent(self.phase, self.balance, self.mll, "terminal day ignored")

    def request_payout(self) -> float:
        if self.phase != TopStepPhase.XFA:
            raise RuntimeError("TopStep payout is only available in XFA")
        if not self._payout_eligible():
            raise RuntimeError("TopStep payout is not currently eligible")

        gross_request = self.ruleset.payout_request_amount(self.balance, self.payout_path)
        if gross_request <= 0:
            raise RuntimeError("TopStep payout minimum is not met")

        trader_receives = self.ruleset.trader_payout_amount(gross_request)
        self.balance -= gross_request
        self.total_trader_payouts += trader_receives
        self.payout_count += 1
        self.standard_winning_days = 0
        self.cycle_daily_pnls.clear()
        self.current_day_pnl = 0.0
        self.mll = 0.0

        if self.balance <= self.mll:
            self.phase = TopStepPhase.XFA_CLOSED

        return trader_receives

    def attempt_reset(self) -> float:
        if self.phase != TopStepPhase.COMBINE_FAILED:
            raise RuntimeError("TopStep reset is only modeled for failed Trading Combines")

        self.phase = TopStepPhase.COMBINE
        self.balance = float(self.ruleset.combine_starting_balance)
        self.mll = float(self.ruleset.combine_initial_mll)
        self.current_day_pnl = 0.0
        self.combine_daily_pnls.clear()
        self.daily_locked = False
        self.reset_count += 1
        self.total_fees_paid += self.ruleset.nofee_reset_cost
        return float(self.ruleset.nofee_reset_cost)

    def attempt_back2funded(self) -> float:
        if self.phase != TopStepPhase.XFA_CLOSED:
            raise RuntimeError("Back2Funded is only modeled for closed XFAs")
        if self.payout_count > 0:
            raise RuntimeError("Back2Funded is unavailable after first payout")
        if self.back2funded_count >= self.ruleset.max_back2funded_reactivations:
            raise RuntimeError("Back2Funded reactivation limit reached")

        self._activate_xfa()
        self.back2funded_count += 1
        self.total_fees_paid += self.ruleset.back2funded_cost
        return float(self.ruleset.back2funded_cost)

    def max_contracts(self, *, micros: bool = False) -> int:
        phase = "xfa" if self.phase == TopStepPhase.XFA else "combine"
        return self.ruleset.max_contracts(micros=micros, phase=phase, balance=self.balance)

    def _combine_can_pass_now(self) -> bool:
        total_profit = self.balance - self.ruleset.combine_starting_balance
        daily_pnls = self.combine_daily_pnls + [self.current_day_pnl]
        return self.ruleset.combine_consistency_ok(daily_pnls, total_profit)

    def _payout_eligible(self) -> bool:
        if self.payout_path == TopStepPayoutPath.STANDARD:
            return self.standard_winning_days >= self.ruleset.standard_winning_days_required and self.balance > 0

        if len(self.cycle_daily_pnls) < self.ruleset.consistency_days_required:
            return False
        return self.ruleset.xfa_consistency_ok(self.cycle_daily_pnls, self.balance)

    def _activate_xfa(self) -> None:
        self.phase = TopStepPhase.XFA
        self.balance = float(self.ruleset.xfa_starting_balance)
        self.mll = float(self.ruleset.xfa_initial_mll)
        self.current_day_pnl = 0.0
        self.combine_daily_pnls.clear()
        self.cycle_daily_pnls.clear()
        self.standard_winning_days = 0
        self.daily_locked = False
