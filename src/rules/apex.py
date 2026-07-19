"""Apex Trader Funding 4.0 ruleset encoding.

Specs sourced from third-party reviews 2026-07-17 (Apex blocks fetchers);
pending verification against Apex help center.

Apex publishes two Eval → PA (funded) paths distinguished by which drawdown
variant is active:
- EOD-trailing: trailing threshold recalculates once per day at close off
  the closing balance (intraday unrealized P&L does NOT ratchet it); this
  variant has a soft daily loss limit (DLL) that pauses trading for the
  rest of the session without failing the account.
- Intraday-trailing: threshold trails the real-time peak balance, including
  unrealized profit ratchets; NO daily loss limit exists for this variant.

Both variants fail the account the instant balance touches the trailing
threshold. All numeric values below are 50K reference figures parameterized
so 25K/100K/150K accounts are constructible via the same dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Apex50K:
    """Apex Trader Funding 4.0 rule parameters used by the simulator.

    ``drawdown_variant`` selects which of Apex's two published drawdown
    mechanics is active for this account (see module docstring). Every
    money figure defaults to the 50K reference tier; construct with
    different values for 25K/100K/150K.
    """

    account_size: int = 50_000
    profit_target: int = 3_000
    trailing_drawdown: int = 2_000

    # Third-party reviews list separate eval fees per variant with frequent
    # promo pricing; expose both as parameters rather than a single default
    # so callers can model whichever pricing was actually paid.
    eval_fee_eod: int = 197
    eval_fee_intraday: int = 131

    # PA (funded) one-time activation fee, also variant-dependent.
    pa_activation_fee_eod: int = 99
    pa_activation_fee_intraday: int = 79

    # Eval: no minimum trading days, no consistency rule (per third-party
    # reviews). Max size in eval: 6 minis (60 micros).
    eval_max_mini_contracts: int = 6
    eval_max_micro_contracts: int = 60

    # EOD variant only: soft daily loss limit. Hitting it pauses the
    # session (does NOT breach the account). Intraday variant has none —
    # callers must not enable ``use_daily_loss_limit`` for that variant.
    eod_soft_daily_loss_limit: int = 1_000

    # PA "safety net": once the trailing threshold reaches
    # (start + trailing_drawdown + $100), it freezes permanently at that
    # balance level for both variants. For 50K: 50,000 + 2,000 + 100 -
    # 2,000 (drawdown offset) = 50,100 in balance terms — i.e. the
    # threshold locks at start + $100, mirroring LucidFlex/TopStep's
    # "start + buffer" lock convention.
    safety_net_buffer: int = 100

    # PA contract scaling tiers, updated off prior day's close balance.
    # 50K reference: starts at 2 minis, caps at 4 minis. Conservative
    # interpretation: hold the 2-tier ladder used elsewhere in this
    # codebase (start tier / max tier) since the exact intermediate
    # breakpoints are not confirmed by the source reviews.
    pa_start_minis: int = 2
    pa_max_minis: int = 4
    pa_scaling_step_profit: int = 2_500

    # Payout eligibility (PA only). Qualifying day = net daily profit >=
    # this threshold (parameterized per account size; 50K default $150).
    payout_qualifying_days_required: int = 5
    payout_qualifying_day_min_profit: int = 150
    payout_minimum: int = 500
    payout_balance_buffer_above_safety_net: int = 500

    # Consistency rule applies ONLY at payout time (never fails the
    # account, only delays payout eligibility): no single day may exceed
    # this fraction of net profit since the last payout.
    payout_consistency_limit: float = 0.50

    funded_profit_split: float = 1.00

    # Payout caps per cycle, cycles 1-6 (50K ladder); uncapped from cycle 7.
    payout_caps_by_cycle: tuple[int, ...] = field(
        default_factory=lambda: (1_500, 1_800, 2_100, 2_400, 2_700, 3_000)
    )

    # Activity rule: >= 2 days with >= $50 net profit per rolling 30 days,
    # else the account goes dormant/closed. Modeled as an optional terminal
    # condition; default OFF because our strategies trade daily and would
    # never trip it, and the exact rolling-window mechanics are not
    # confirmed by the source reviews (conservative: don't fabricate a
    # behavior we can't verify).
    enforce_activity_rule: bool = False
    activity_window_days: int = 30
    activity_min_qualifying_days: int = 2
    activity_min_daily_profit: int = 50

    @property
    def starting_balance(self) -> int:
        return self.account_size

    @property
    def eval_initial_threshold(self) -> int:
        # Eval trailing threshold starts at (start - trailing_drawdown).
        return self.account_size - self.trailing_drawdown

    @property
    def pass_balance(self) -> int:
        return self.account_size + self.profit_target

    @property
    def safety_net_balance(self) -> int:
        # Threshold freezes permanently once it reaches this balance.
        # Conservative reading of "start + drawdown + $100" as the freeze
        # trigger, with the frozen THRESHOLD level itself at start + $100
        # (mirrors LucidFlex's "start + $100" lock convention, since Apex
        # third-party sources describe the freeze in the same shape).
        return self.account_size + self.safety_net_buffer

    def eval_fee(self, *, variant: str) -> int:
        """Return the eval fee for the given drawdown variant."""
        if variant == "eod":
            return self.eval_fee_eod
        if variant == "intraday":
            return self.eval_fee_intraday
        msg = f"unknown Apex drawdown variant: {variant}"
        raise ValueError(msg)

    def pa_activation_fee(self, *, variant: str) -> int:
        """Return the one-time PA activation fee for the given variant."""
        if variant == "eod":
            return self.pa_activation_fee_eod
        if variant == "intraday":
            return self.pa_activation_fee_intraday
        msg = f"unknown Apex drawdown variant: {variant}"
        raise ValueError(msg)

    def update_eod_threshold_after_close(
        self, closing_balance: float, current_threshold: float
    ) -> float:
        """Apply the EOD-trailing threshold update (EOD variant only).

        Trails the highest end-of-day closing balance; never moves down.
        Intraday unrealized P&L does NOT ratchet it — only the balance at
        the close of the session matters. Once the threshold would reach
        or exceed the safety-net balance, it locks there permanently.
        """
        if closing_balance >= self.safety_net_balance + self.trailing_drawdown:
            return float(self.safety_net_balance)

        candidate = closing_balance - self.trailing_drawdown
        return float(max(current_threshold, min(candidate, self.safety_net_balance)))

    def update_intraday_threshold(
        self, peak_balance: float, current_threshold: float
    ) -> float:
        """Apply the intraday-trailing threshold update (intraday variant only).

        Conservative model: the threshold trails the real-time PEAK balance
        (including unrealized profit), applied on every ``update(pnl)`` call
        rather than only at day close — this is worse for the trader than an
        EOD-only ratchet and matches Apex's published "trails in real time"
        description for this variant. Never moves down; locks permanently
        once it reaches the safety-net balance.
        """
        if peak_balance >= self.safety_net_balance + self.trailing_drawdown:
            return float(self.safety_net_balance)

        candidate = peak_balance - self.trailing_drawdown
        return float(max(current_threshold, min(candidate, self.safety_net_balance)))

    def is_qualifying_day(self, daily_pnl: float) -> bool:
        return daily_pnl >= self.payout_qualifying_day_min_profit

    def payout_consistency_ok(self, cycle_daily_pnls: list[float], cycle_profit: float) -> bool:
        """Check the payout-time-only consistency rule.

        Source: no single day may exceed 50% of net profit since the last
        payout. This does NOT fail the account — it only delays payout
        eligibility until diluted by additional days (call site handles
        that; this method only checks the ratio for the current cycle).
        """
        if cycle_profit <= 0:
            return False
        return max(cycle_daily_pnls, default=0.0) / cycle_profit <= self.payout_consistency_limit

    def payout_request_amount(self, cycle_profit: float, *, cycle_number: int) -> float:
        """Return gross payout request amount before the profit split.

        Source: 100% profit split, so gross request = capped cycle profit.
        Cycles 1-6 use ``payout_caps_by_cycle``; cycle 7+ is uncapped.
        ``cycle_number`` is 1-indexed (first payout cycle = 1).
        """
        if cycle_number < 1:
            raise ValueError("cycle_number must be >= 1")
        if cycle_profit <= 0:
            return 0.0

        if cycle_number <= len(self.payout_caps_by_cycle):
            cap = self.payout_caps_by_cycle[cycle_number - 1]
            request = min(cycle_profit, cap)
        else:
            request = cycle_profit

        if request < self.payout_minimum:
            return 0.0
        return float(request)

    def trader_payout_amount(self, gross_request: float) -> float:
        """Apply the 100% profit split to a gross payout request."""
        return gross_request * self.funded_profit_split

    def max_contracts(
        self,
        *,
        micros: bool = False,
        phase: str = "eval",
        simulated_profit: float = 0.0,
    ) -> int:
        """Return the contract cap for 50K under either phase.

        Eval: flat cap of 6 minis / 60 micros, no scaling.
        PA: starts at ``pa_start_minis`` (2), scales up by one mini per
        ``pa_scaling_step_profit`` of simulated profit, capped at
        ``pa_max_minis`` (4). The exact intermediate breakpoints are not
        confirmed by the source reviews; this linear-step model is the
        conservative placeholder — it never scales UP faster than a
        confirmed source would justify.
        """
        if phase == "eval":
            return self.eval_max_micro_contracts if micros else self.eval_max_mini_contracts

        if phase != "pa":
            msg = f"unknown Apex phase: {phase}"
            raise ValueError(msg)

        if simulated_profit <= 0:
            minis = self.pa_start_minis
        else:
            steps = int(simulated_profit // self.pa_scaling_step_profit)
            minis = min(self.pa_start_minis + steps, self.pa_max_minis)

        return minis * 10 if micros else minis

    def payout_cap_for_cycle(self, cycle_number: int) -> float | None:
        """Return the payout cap for a given cycle, or None if uncapped."""
        if cycle_number < 1:
            raise ValueError("cycle_number must be >= 1")
        if cycle_number <= len(self.payout_caps_by_cycle):
            return float(self.payout_caps_by_cycle[cycle_number - 1])
        return None
