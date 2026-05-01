"""LucidFlex 50K account state machine.

Drives one account from a fresh evaluation through funded payouts and
terminal states. Source rules live in ``src/rules/lucidflex.py``; this module
is the time-domain integration layer (apply trade → check breach → close
day → request payout).

Reviewer pass: Claude Code, 2026-04-30. The earlier 0.52 consistency bug
lived in the rule module; this state machine consumes ``consistency_ok``
through the rule object, so it inherits the corrected 50% threshold without
local change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.rules.lucidflex import LucidFlex50K


class LucidFlexPhase(StrEnum):
    """Lifecycle phases for one LucidFlex account.

    ``MAX_PAYOUTS`` is the terminal sim-funded state for v1: real Lucid
    accounts are moved to live after the 5th payout, but live mechanics are
    out of scope for v1 simulation.
    """

    EVAL = "eval"
    FUNDED = "funded"
    BREACHED_EVAL = "breached_eval"
    BREACHED_FUNDED = "breached_funded"
    MAX_PAYOUTS = "max_payouts"


@dataclass(frozen=True)
class AccountEvent:
    """One state-machine transition result, returned by ``update``/``close_day``."""

    phase: LucidFlexPhase
    balance: float
    mll: float
    message: str


@dataclass
class LucidFlexAccountState:
    """State machine for one LucidFlex 50K account path.

    Trade sequencing assumption: ``update(pnl)`` is called once per trade in
    chronological order; ``close_day()`` is called once per session boundary.
    Intraday MLL is checked after each ``update``; EOD trailing-drawdown
    update is applied in ``close_day``.
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
        # Defaults derive from the ruleset so callers can construct a fresh
        # account with just ``LucidFlexAccountState()``.
        if self.balance is None:
            self.balance = float(self.ruleset.starting_balance)
        if self.mll is None:
            self.mll = float(self.ruleset.initial_mll)
        if self.cycle_start_balance is None:
            self.cycle_start_balance = float(self.balance)
        if self.total_fees_paid == 0:
            # Every fresh account is paid for: charge the eval fee up front so
            # ``net_ev`` reflects sunk cost from day 1.
            self.total_fees_paid = float(self.ruleset.eval_fee)

    @property
    def is_breached(self) -> bool:
        return self.phase in {LucidFlexPhase.BREACHED_EVAL, LucidFlexPhase.BREACHED_FUNDED}

    @property
    def is_passed_eval(self) -> bool:
        # FUNDED, MAX_PAYOUTS, and BREACHED_FUNDED all imply eval was passed
        # at some point — useful for conditional pass-rate metrics.
        return self.phase in {
            LucidFlexPhase.FUNDED,
            LucidFlexPhase.MAX_PAYOUTS,
            LucidFlexPhase.BREACHED_FUNDED,
        }

    @property
    def total_profit(self) -> float:
        return self.balance - self.ruleset.starting_balance

    @property
    def cycle_net_profit(self) -> float:
        # Cycle = period since the last payout (or since funded activation).
        # Required by the funded payout rule "positive net profit per cycle".
        return self.balance - self.cycle_start_balance

    @property
    def net_ev(self) -> float:
        # Trader payouts already net of the 90/10 split; fees include eval +
        # any reset costs accumulated.
        return self.total_trader_payouts - self.total_fees_paid

    def update(self, trade_pnl: float) -> AccountEvent:
        """Apply one trade's P&L and check intraday breach + eval pass.

        Order matters:
        1. Apply P&L to balance and current-day total.
        2. Check MLL — intraday breach is immediate (no day-close required).
        3. Only if still alive AND in eval, check whether the running total
           qualifies for upgrade (target met AND consistency holds).
        """
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
        """Close the trading session.

        Eval: append today's P&L to the daily history, run the EOD trailing
        update, and re-check eval pass conditions (a target hit at the closing
        bell still qualifies).

        Funded: count the day toward payout eligibility if it cleared the
        $150 minimum profit threshold, then run the EOD trailing update.
        """
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
        """Request a payout per LucidFlex funded rules.

        All eligibility checks must pass:
        - phase is FUNDED (not max-payouts terminal, not breached)
        - cycle has ≥5 days with ≥$150 profit each
        - cycle has positive net profit
        - request amount clears the $500 minimum

        After payout, MLL re-locks at $50,100 (`locked_mll_balance`) and the
        cycle counters reset. If the payout dropped balance to the locked
        MLL, the account is breached_funded; if this was the 5th payout, the
        account terminates at MAX_PAYOUTS.
        """
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
        # MLL re-locks at $50,100 after each payout — this is what stops
        # traders from rebuilding a small drawdown buffer post-payout.
        self.mll = float(self.ruleset.locked_mll_balance)
        self.current_day_pnl = 0.0

        if self.balance <= self.mll:
            self.phase = LucidFlexPhase.BREACHED_FUNDED
        elif self.payout_count >= self.ruleset.max_simulated_payouts:
            self.phase = LucidFlexPhase.MAX_PAYOUTS

        return trader_receives

    def attempt_reset(self) -> float:
        """Reset a breached eval account.

        Only modeled for breached eval — funded breach is terminal in v1.
        Resets cost ``reset_cost_estimate`` and add to the fee tally; the
        account returns to a pristine eval state.
        """
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
        # Includes ``current_day_pnl`` in the daily history snapshot — the
        # consistency check must reflect intraday state, not just closed days,
        # because a target hit mid-day must respect "largest day so far".
        total_profit = self.balance - self.ruleset.starting_balance
        daily_pnls = self.eval_daily_pnls + [self.current_day_pnl]
        return self.ruleset.consistency_ok(daily_pnls, total_profit)

    def _activate_funded(self) -> None:
        # Funded starts fresh: reset balance to $50,000 and MLL to $48,000.
        # Eval daily history is no longer relevant; cycle counters reset.
        self.phase = LucidFlexPhase.FUNDED
        self.balance = float(self.ruleset.starting_balance)
        self.mll = float(self.ruleset.initial_mll)
        self.current_day_pnl = 0.0
        self.eval_daily_pnls.clear()
        self.cycle_start_balance = self.balance
        self.cycle_profitable_days = 0
