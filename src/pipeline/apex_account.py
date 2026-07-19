"""Apex Trader Funding 4.0 account state machine.

Drives one account from a fresh evaluation through PA (funded) payouts and
terminal states. Source rules live in ``src/rules/apex.py``; this module is
the time-domain integration layer (apply trade -> check breach -> close day
-> request payout).

Supports both published drawdown variants via ``drawdown_variant``:
- "eod": threshold recalculates once per day at close off the closing
  balance; has a soft daily loss limit that pauses the session (not a
  breach).
- "intraday": threshold trails the real-time peak balance including
  unrealized profit, updated on every ``update(pnl)`` call (conservative
  modeling choice — see ``src/rules/apex.py:update_intraday_threshold``);
  no daily loss limit.

Touching the trailing threshold fails the account in either variant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.rules.apex import Apex50K


class ApexPhase(StrEnum):
    """Lifecycle phases for one Apex account.

    ``MAX_CYCLES`` is not a real Apex terminal state (Apex payouts are
    uncapped from cycle 7 onward) — v1 simulation exposes it only if a
    caller explicitly bounds the number of simulated payout cycles.
    """

    EVAL = "eval"
    PA = "pa"
    BREACHED_EVAL = "breached_eval"
    BREACHED_PA = "breached_pa"


@dataclass(frozen=True)
class ApexAccountEvent:
    """One state-machine transition result, returned by ``update``/``close_day``."""

    phase: ApexPhase
    balance: float
    threshold: float
    message: str


@dataclass
class ApexAccountState:
    """State machine for one Apex 50K account path.

    Trade sequencing assumption: ``update(pnl)`` is called once per trade in
    chronological order; ``close_day()`` is called once per session
    boundary. Intraday threshold breach is checked after each ``update``.
    For the EOD variant, the trailing threshold only moves in
    ``close_day()``; for the intraday variant it moves on every ``update``
    against the running peak balance.
    """

    ruleset: Apex50K = field(default_factory=Apex50K)
    drawdown_variant: str = "eod"
    phase: ApexPhase = ApexPhase.EVAL
    balance: float | None = None
    threshold: float | None = None
    peak_balance: float | None = None
    total_fees_paid: float = 0.0
    payout_count: int = 0
    total_trader_payouts: float = 0.0
    current_day_pnl: float = 0.0
    daily_locked: bool = False
    eval_daily_pnls: list[float] = field(default_factory=list)
    cycle_start_balance: float | None = None
    cycle_daily_pnls: list[float] = field(default_factory=list)
    cycle_qualifying_days: int = 0

    def __post_init__(self) -> None:
        if self.drawdown_variant not in {"eod", "intraday"}:
            msg = f"unknown Apex drawdown variant: {self.drawdown_variant}"
            raise ValueError(msg)
        if self.balance is None:
            self.balance = float(self.ruleset.starting_balance)
        if self.threshold is None:
            self.threshold = float(self.ruleset.eval_initial_threshold)
        if self.peak_balance is None:
            self.peak_balance = float(self.balance)
        if self.cycle_start_balance is None:
            self.cycle_start_balance = float(self.balance)
        if self.total_fees_paid == 0:
            # Every fresh account is paid for: charge the eval fee up front
            # so ``net_ev`` reflects sunk cost from day 1.
            self.total_fees_paid = float(self.ruleset.eval_fee(variant=self.drawdown_variant))

    @property
    def is_breached(self) -> bool:
        return self.phase in {ApexPhase.BREACHED_EVAL, ApexPhase.BREACHED_PA}

    @property
    def is_passed_eval(self) -> bool:
        return self.phase in {ApexPhase.PA, ApexPhase.BREACHED_PA}

    @property
    def total_profit(self) -> float:
        return self.balance - self.ruleset.starting_balance

    @property
    def cycle_net_profit(self) -> float:
        return self.balance - self.cycle_start_balance

    @property
    def net_ev(self) -> float:
        return self.total_trader_payouts - self.total_fees_paid

    def update(self, trade_pnl: float) -> ApexAccountEvent:
        """Apply one trade's P&L and check intraday breach + eval pass.

        Order matters:
        1. Reject if terminal phase or DLL-locked session (EOD variant).
        2. Apply P&L to balance and current-day total.
        3. Intraday variant only: ratchet the peak balance and trailing
           threshold on this same trade (conservative — worse for the
           trader than an EOD-only ratchet).
        4. Check the threshold — breach is immediate in both variants.
        5. EOD variant only: check the soft daily loss limit (pauses the
           session, does not breach).
        6. If still alive and in eval, check whether the running profit
           clears the eval target (no consistency rule, no minimum days).
        """
        if self.phase not in {ApexPhase.EVAL, ApexPhase.PA}:
            raise RuntimeError(f"cannot trade terminal Apex phase {self.phase}")
        if self.daily_locked:
            raise RuntimeError("Apex DLL lock prevents more trades this session")

        self.balance += trade_pnl
        self.current_day_pnl += trade_pnl

        if self.drawdown_variant == "intraday":
            self.peak_balance = max(self.peak_balance, self.balance)
            self.threshold = self.ruleset.update_intraday_threshold(self.peak_balance, self.threshold)

        if self.balance <= self.threshold:
            if self.phase == ApexPhase.EVAL:
                self.phase = ApexPhase.BREACHED_EVAL
                return ApexAccountEvent(self.phase, self.balance, self.threshold, "eval threshold breached")
            self.phase = ApexPhase.BREACHED_PA
            return ApexAccountEvent(self.phase, self.balance, self.threshold, "PA threshold breached")

        if (
            self.drawdown_variant == "eod"
            and self.current_day_pnl <= -self.ruleset.eod_soft_daily_loss_limit
        ):
            # Soft DLL: session-only lock, NOT a rule violation. Only
            # applies to the EOD variant per Apex's published rules.
            self.daily_locked = True
            return ApexAccountEvent(self.phase, self.balance, self.threshold, "soft DLL locked for session")

        if self.phase == ApexPhase.EVAL and self.total_profit >= self.ruleset.profit_target:
            self._activate_pa()
            return ApexAccountEvent(self.phase, self.balance, self.threshold, "eval passed")

        return ApexAccountEvent(self.phase, self.balance, self.threshold, "trade applied")

    def close_day(self) -> ApexAccountEvent:
        """Close the trading session.

        Eval: append today's P&L to daily history, re-check pass condition
        (target hit at the bell still qualifies), clear the DLL lock.

        PA: count the day toward payout eligibility if it cleared the
        qualifying-day threshold, then (EOD variant only) run the EOD
        trailing-threshold update off the closing balance. The intraday
        variant already ratcheted the threshold per-trade in ``update``, so
        ``close_day`` does not move it again for that variant.
        """
        if self.phase == ApexPhase.EVAL:
            self.eval_daily_pnls.append(self.current_day_pnl)
            if self.drawdown_variant == "eod":
                self.threshold = self.ruleset.update_eod_threshold_after_close(self.balance, self.threshold)
            self.current_day_pnl = 0.0
            self.daily_locked = False
            if self.total_profit >= self.ruleset.profit_target:
                self._activate_pa()
                return ApexAccountEvent(self.phase, self.balance, self.threshold, "eval passed at day close")
            return ApexAccountEvent(self.phase, self.balance, self.threshold, "eval day closed")

        if self.phase == ApexPhase.PA:
            self.cycle_daily_pnls.append(self.current_day_pnl)
            if self.ruleset.is_qualifying_day(self.current_day_pnl):
                self.cycle_qualifying_days += 1
            if self.drawdown_variant == "eod":
                self.threshold = self.ruleset.update_eod_threshold_after_close(self.balance, self.threshold)
            self.current_day_pnl = 0.0
            self.daily_locked = False
            return ApexAccountEvent(self.phase, self.balance, self.threshold, "PA day closed")

        self.current_day_pnl = 0.0
        self.daily_locked = False
        return ApexAccountEvent(self.phase, self.balance, self.threshold, "terminal day ignored")

    def request_payout(self) -> float:
        """Request a payout per Apex PA payout rules.

        All eligibility checks must pass:
        - phase is PA (not breached)
        - cycle has >=5 qualifying days (net daily profit >= $150 for 50K)
        - balance clears (safety_net_balance + $500). This gate uses the
          FIXED safety_net_balance regardless of whether the trailing
          threshold has actually frozen yet — that is the literal reading
          of the source spec's "balance > safety net + $500" wording,
          pending verification against the Apex help center.
        - cycle-consistency: no single day > 50% of net profit accrued
          THIS cycle (this check only DELAYS eligibility — it never fails
          the account; the ratio denominator is deliberately the per-cycle
          window, not all-time withdrawable profit, so a lopsided day only
          taints its own cycle)
        - request amount clears the $500 minimum

        Payout size is drawn from ALL-TIME WITHDRAWABLE PROFIT
        (``total_profit`` = balance - starting_balance), capped per the
        cycle ladder (``payout_caps_by_cycle`` for cycles 1-6, uncapped
        from cycle 7) — mirroring LucidFlex's ``total_profit``-based
        ``payout_request_amount`` call (see lucidflex_account.py). Apex
        caps limit the per-cycle PAYOUT AMOUNT, they do not forfeit
        profit: any residual above a cycle's cap stays in balance and
        rolls forward, fully withdrawable in a later (or uncapped
        cycle-7+) payout. Using ``cycle_net_profit`` here instead would
        silently strand over-cap profit forever, since resetting
        ``cycle_start_balance`` to the post-payout balance would erase the
        residual from every future cycle's profit calculation.

        After payout, the cycle counters reset; the trailing threshold is
        NOT reset by a payout (unlike LucidFlex/TopStep) because Apex's
        safety-net freeze is a one-way, balance-driven event independent of
        payout requests — this is the conservative reading given no source
        evidence describes a post-payout threshold reset.
        """
        if self.phase != ApexPhase.PA:
            raise RuntimeError("Apex payout is only available in PA phase")
        if self.cycle_qualifying_days < self.ruleset.payout_qualifying_days_required:
            raise RuntimeError("Apex payout requires 5 qualifying days")
        if self.balance <= self.ruleset.safety_net_balance + self.ruleset.payout_balance_buffer_above_safety_net:
            raise RuntimeError("Apex payout requires balance above safety net + $500")
        if not self.ruleset.payout_consistency_ok(self.cycle_daily_pnls, self.cycle_net_profit):
            raise RuntimeError("Apex payout blocked by consistency rule (largest day > 50% of cycle profit)")

        gross_request = self.ruleset.payout_request_amount(
            self.total_profit, cycle_number=self.payout_count + 1
        )
        if gross_request <= 0:
            raise RuntimeError("Apex payout minimum is not met")

        trader_receives = self.ruleset.trader_payout_amount(gross_request)
        self.balance -= gross_request
        self.total_trader_payouts += trader_receives
        self.payout_count += 1
        self.cycle_qualifying_days = 0
        self.cycle_daily_pnls.clear()
        self.cycle_start_balance = self.balance
        self.current_day_pnl = 0.0

        if self.balance <= self.threshold:
            self.phase = ApexPhase.BREACHED_PA

        return trader_receives

    def max_contracts(self, *, micros: bool = False) -> int:
        """Forward to the ruleset using the current phase + simulated profit."""
        phase = "pa" if self.phase == ApexPhase.PA else "eval"
        simulated_profit = self.cycle_net_profit if self.phase == ApexPhase.PA else 0.0
        return self.ruleset.max_contracts(micros=micros, phase=phase, simulated_profit=simulated_profit)

    def _activate_pa(self) -> None:
        # PA starts fresh: reset balance to the starting balance and the
        # threshold to the eval initial threshold, plus charge the
        # one-time PA activation fee. Eval daily history is no longer
        # relevant; cycle counters reset.
        self.phase = ApexPhase.PA
        self.balance = float(self.ruleset.starting_balance)
        self.threshold = float(self.ruleset.eval_initial_threshold)
        self.peak_balance = float(self.balance)
        self.current_day_pnl = 0.0
        self.daily_locked = False
        self.eval_daily_pnls.clear()
        self.cycle_start_balance = self.balance
        self.cycle_daily_pnls.clear()
        self.cycle_qualifying_days = 0
        self.total_fees_paid += self.ruleset.pa_activation_fee(variant=self.drawdown_variant)
