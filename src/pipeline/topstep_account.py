"""TopStep No Activation Fee account state machine.

Drives one TopStep 50K account from Trading Combine through Express Funded
Account (XFA) payouts to terminal states. Source rules live in
``src/rules/topstep.py``; this module is the time-domain integration layer.

Reviewer pass: Claude Code, 2026-04-30. The XFA scaling tiers used in
``max_contracts`` are reviewer-gated — see ``src/rules/topstep.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath


class TopStepPhase(StrEnum):
    """Lifecycle phases for one TopStep account.

    ``XFA_CLOSED`` is reachable from XFA via MLL breach; ``COMBINE_FAILED`` is
    reachable from Combine via MLL breach. Back2Funded is only available from
    ``XFA_CLOSED`` if no payout has been taken yet.
    """

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
    """State machine for one TopStep 50K No Activation Fee account.

    The DLL is opt-in via ``use_daily_loss_limit`` — Combine and XFA both
    expose it as a checkout-time choice. When enabled and tripped, the
    session locks (no further trades that day) but the account is NOT
    breached. ``close_day`` clears the lock for the next session.
    """

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
            # Charge the first month's NoFee subscription up front so that
            # ``net_ev`` reflects that cost from the start.
            self.total_fees_paid = float(self.ruleset.nofee_monthly_fee)

    @property
    def is_breached(self) -> bool:
        return self.phase in {TopStepPhase.COMBINE_FAILED, TopStepPhase.XFA_CLOSED}

    @property
    def is_passed_eval(self) -> bool:
        # ``XFA_CLOSED`` implies the Combine was passed before the XFA breach.
        return self.phase in {TopStepPhase.XFA, TopStepPhase.XFA_CLOSED}

    @property
    def net_ev(self) -> float:
        return self.total_trader_payouts - self.total_fees_paid

    def update(self, trade_pnl: float) -> TopStepAccountEvent:
        """Apply one trade's P&L.

        Order matters:
        1. Reject if terminal phase or session is DLL-locked.
        2. Apply P&L.
        3. Check MLL — intraday breach is immediate.
        4. Check optional DLL — locks session but does not breach.
        5. In Combine, check whether profit target + consistency permit upgrade.
        """
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
            # DLL: session-only lock, NOT a rule violation. Account stays
            # in its current phase; lock clears at the next ``close_day``.
            self.daily_locked = True
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "DLL locked for session")

        if self.phase == TopStepPhase.COMBINE and self._combine_can_pass_now():
            self._activate_xfa()
            return TopStepAccountEvent(self.phase, self.balance, self.mll, "combine passed")

        return TopStepAccountEvent(self.phase, self.balance, self.mll, "trade applied")

    def close_day(self) -> TopStepAccountEvent:
        """Close the trading session.

        Combine: append today's P&L to daily history, run EOD trailing update,
        re-check pass conditions (target hit at the bell still qualifies),
        clear the DLL lock.

        XFA: append to cycle daily history, count toward Standard winning
        days if ≥$150, run EOD trailing update, clear the DLL lock.
        """
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

        # Terminal phases: still reset transient counters in case the caller
        # is replaying day boundaries blindly.
        self.current_day_pnl = 0.0
        self.daily_locked = False
        return TopStepAccountEvent(self.phase, self.balance, self.mll, "terminal day ignored")

    def request_payout(self) -> float:
        """Request a payout per the configured XFA path.

        Standard path: ≥5 days of ≥$150 net P&L, balance > 0 (which under
        XFA's $0-displayed model also enforces "positive profit since last
        payout" because MLL is set to $0 after each payout).

        Consistency path: ≥3 trading days, largest day ≤40% of total profit,
        positive cycle profit.

        After payout, MLL is set to $0 (per source doc), the cycle resets,
        and the account terminates if the post-deduction balance is at or
        below MLL.
        """
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
        # Source doc: "After payout: MLL set to $0".
        self.mll = 0.0

        if self.balance <= self.mll:
            self.phase = TopStepPhase.XFA_CLOSED

        return trader_receives

    def attempt_reset(self) -> float:
        """Reset a failed Trading Combine.

        Charges the NoFee reset cost ($109 for 50K). The account returns to
        a pristine Combine phase. XFA failure is NOT resettable via this
        method — that path uses Back2Funded if pre-first-payout.
        """
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
        """Reactivate a closed XFA via Back2Funded.

        Source doc: only available pre-first-payout, max 2 reactivations per
        XFA. Costs $599 for 50K. After reactivation, balance and MLL return
        to fresh-XFA values (`$0` / `-$2,000`).
        """
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
        """Forward to the ruleset using the current phase + balance.

        Note: XFA uses the reviewer-gated scaling tiers in
        ``src/rules/topstep.py:max_contracts``.
        """
        phase = "xfa" if self.phase == TopStepPhase.XFA else "combine"
        return self.ruleset.max_contracts(micros=micros, phase=phase, balance=self.balance)

    def _combine_can_pass_now(self) -> bool:
        # Mirror the LucidFlex pattern: include intraday P&L in the daily
        # snapshot so a mid-session pass still respects "best day so far".
        total_profit = self.balance - self.ruleset.combine_starting_balance
        daily_pnls = self.combine_daily_pnls + [self.current_day_pnl]
        return self.ruleset.combine_consistency_ok(daily_pnls, total_profit)

    def _payout_eligible(self) -> bool:
        if self.payout_path == TopStepPayoutPath.STANDARD:
            return (
                self.standard_winning_days >= self.ruleset.standard_winning_days_required
                and self.balance > 0
            )

        # Consistency path: day count is enforced here; ratio in the rule.
        if len(self.cycle_daily_pnls) < self.ruleset.consistency_days_required:
            return False
        return self.ruleset.xfa_consistency_ok(self.cycle_daily_pnls, self.balance)

    def _activate_xfa(self) -> None:
        # XFA starts at $0 displayed balance, MLL at -$2,000, fresh cycle.
        self.phase = TopStepPhase.XFA
        self.balance = float(self.ruleset.xfa_starting_balance)
        self.mll = float(self.ruleset.xfa_initial_mll)
        self.current_day_pnl = 0.0
        self.combine_daily_pnls.clear()
        self.cycle_daily_pnls.clear()
        self.standard_winning_days = 0
        self.daily_locked = False
