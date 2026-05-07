"""LucidFlex 50K ruleset encoding.

Source documents:
- ``Rulesets/LucidFlex/LucidFlex Rules.md`` (verbatim official help-center paste)
- ``Rulesets/PHASE1_RULESET_AUDIT.md`` (Phase 1 reviewer audit notes)

Reviewer pass: Claude Code, 2026-04-30. Notable correction in this pass:
``eval_consistency_limit`` was 0.52 (the cushion *example* value, $1,560 / $3,000),
which is not the rule. The source doc states the threshold strictly as 50%
(``Largest Single Day Profit / Account Profit <= 50%``) and describes the
cushion as a soft, trader-specific buffer, not a fixed numeric threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class LucidFlex50K:
    """LucidFlex 50K rule parameters used by the simulator.

    Numeric values are taken directly from
    ``Rulesets/LucidFlex/LucidFlex Rules.md``. Dashboard-only economics are
    encoded from Georg's 2026-05-01 verification: 50K eval is $98 with the
    nearly always available 30% coupon, and reset is $95.
    """

    account_size: int = 50_000
    profit_target: int = 3_000
    max_loss_limit: int = 2_000

    # Source doc, "LucidFlex Drawdown" section: 50K initial trail balance is
    # $52,100 and the MLL locks at "initial balance plus $100" = $50,100.
    initial_trail_balance: int = 52_100
    locked_mll_balance: int = 50_100

    # Source doc, "LucidFlex Consistency Percentage": "must have Consistency
    # Percentage of 50% or less to be eligible to upgrade". The cushion
    # mentioned in the help center is described as "calculated on what your
    # actual profit earned is for the day and will vary from trader to trader"
    # — explicitly NOT a fixed threshold. Encode the rule strictly at 50%; do
    # not bake the cushion in as a constant.
    eval_consistency_limit: float = 0.50

    # Source doc, "LucidFlex Evaluation Account": 50K row → "4 mini or 40
    # micros". No scaling plan during eval.
    max_mini_contracts_eval: int = 4
    max_micro_contracts_eval: int = 40

    # Source doc, "Profit Split Structure": 90% trader / 10% Lucid.
    funded_profit_split: float = 0.90

    # Source doc, "Payout Minimums and Maximums": min $500, max 50% of profit
    # capped at $2,000 for 50K. Five trading days with $150+ profit each are
    # required per cycle. Max 5 simulated payouts before move-to-live.
    payout_minimum: int = 500
    payout_maximum: int = 2_000
    payout_min_profitable_days: int = 5
    payout_min_daily_profit: int = 150
    max_simulated_payouts: int = 5
    microscalping_hold_seconds: int = 5
    microscalping_profit_share_limit: float = 0.50

    # Dashboard/commercial economics verified by Georg on 2026-05-01. Use the
    # coupon-adjusted eval cost because the 30% coupon is nearly always
    # available and is the realistic attempt cost outside vault promos.
    base_eval_fee: int = 140
    eval_fee: int = 98
    reset_cost_estimate: int = 95
    vault_discount_account_count: int = 5
    vault_discount_floor: float = 0.40
    vault_discount_ceiling: float = 0.50

    # Current public doc, "Allowed Trading Times": "flat by 4:45 PM EST
    # Mon-Fri; reopen 6:00 PM EST Sun-Thu". Lucid auto-closes open positions
    # at the cutoff and says holding past it does not fail the account. We
    # still expose ``must_be_flat`` so bot/order logic can avoid forced exits.
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/New_York"))
    flatten_time: time = time(16, 45)
    reopen_time: time = time(18, 0)

    @property
    def starting_balance(self) -> int:
        return self.account_size

    @property
    def initial_mll(self) -> int:
        # Eval and funded both start MLL at (starting_balance - max_loss_limit).
        return self.account_size - self.max_loss_limit

    @property
    def pass_balance(self) -> int:
        return self.account_size + self.profit_target

    def eval_fee_from_discount(self, discount: float) -> int:
        """Return rounded 50K eval cost after a realized discount.

        ``discount`` is expressed as a fraction: 0.40 means 40% off the base
        eval price. This intentionally models realized commercial pricing; it
        is not a trading rule.
        """
        if not 0 <= discount < 1:
            raise ValueError("discount must be in [0, 1)")
        return round(self.base_eval_fee * (1 - discount))

    def eval_fee_for_vault_account(
        self,
        *,
        accounts_used_in_cycle: int,
        realized_discount: float | None,
    ) -> int:
        """Return current eval fee given the active vault-cycle state.

        LucidFlex vault-cycle discounts are only modeled when Georg supplies
        the realized discount. If no realized discount is known, fall back to
        the normal coupon-adjusted ``eval_fee``.
        """
        if accounts_used_in_cycle < 0:
            raise ValueError("accounts_used_in_cycle must be non-negative")
        if realized_discount is None:
            return self.eval_fee
        if accounts_used_in_cycle >= self.vault_discount_account_count:
            return self.eval_fee
        return self.eval_fee_from_discount(realized_discount)

    def update_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        """Apply the EOD trailing-drawdown update.

        Source doc behavior:
        - MLL trails the highest end-of-day balance; never moves down.
        - Once balance reaches the initial trail balance ($52,100 for 50K), the
          MLL locks permanently at the locked-MLL balance ($50,100 = start +
          $100 buffer). After the lock, no further MLL movement.
        """
        if closing_balance >= self.initial_trail_balance:
            return float(self.locked_mll_balance)

        # Trailing candidate = closing - max_loss. The cap to locked_mll_balance
        # is defensive (this branch can only be hit when closing < trail), and
        # the max() with current_mll enforces the never-moves-down invariant.
        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, self.locked_mll_balance)))

    def consistency_ok(self, daily_pnls: list[float], total_profit: float) -> bool:
        """Return whether eval consistency permits upgrade at current profit.

        Source doc formula:
            Largest Single Day Profit / Account Profit <= 50%

        The check only runs once the trader is at or above the profit target;
        below target the trader can keep adding days to dilute the largest day.
        Negative profit is treated as a fail to avoid divide-by-zero edge cases.
        """
        if total_profit < self.profit_target:
            return False
        if total_profit <= 0:
            return False

        largest_day = max(daily_pnls, default=0.0)
        return largest_day / total_profit <= self.eval_consistency_limit

    def payout_request_amount(self, simulated_profit: float) -> float:
        """Return gross payout request amount before the 90/10 split.

        Source doc, 50K row: "50% of Profit, up to $2,000". The min request is
        $500 — below that, no request is allowed (we encode that as 0.0).

        Note: the help-center prose says "50% of their account balance"; the
        per-size table says "50% of Profit". For Lucid funded accounts the
        "balance" colloquially means simulated profit above starting balance,
        so passing ``simulated_profit = balance - starting_balance`` is the
        intended quantity.
        """
        if simulated_profit <= 0:
            return 0.0

        request = min(simulated_profit * 0.50, self.payout_maximum)
        if request < self.payout_minimum:
            return 0.0
        return float(request)

    def trader_payout_amount(self, gross_request: float) -> float:
        """Apply the 90/10 split to a gross payout request."""
        return gross_request * self.funded_profit_split

    def microscalping_profit_share(
        self,
        trade_profits: list[float],
        hold_seconds: list[float],
    ) -> float:
        """Share of positive profits from trades held at most 5 seconds.

        Current Lucid help text flags accounts if more than 50% of profits are
        generated from trades held for 5 seconds or less. Losses are excluded
        from the denominator because the policy describes profit generation,
        not net P&L.
        """
        if len(trade_profits) != len(hold_seconds):
            raise ValueError("trade_profits and hold_seconds must have same length")
        total_positive_profit = sum(max(0.0, pnl) for pnl in trade_profits)
        if total_positive_profit <= 0:
            return 0.0
        fast_positive_profit = sum(
            max(0.0, pnl)
            for pnl, seconds in zip(trade_profits, hold_seconds, strict=True)
            if seconds <= self.microscalping_hold_seconds
        )
        return fast_positive_profit / total_positive_profit

    def microscalping_flagged(
        self,
        trade_profits: list[float],
        hold_seconds: list[float],
    ) -> bool:
        """Return whether Lucid's published microscalping flag is tripped."""
        return (
            self.microscalping_profit_share(trade_profits, hold_seconds)
            > self.microscalping_profit_share_limit
        )

    def order_rate_flagged(
        self,
        *,
        order_count: int,
        window_minutes: float,
        max_orders_per_minute: float,
    ) -> bool:
        """Configurable HFT guard for Lucid's qualitative HFT prohibition.

        Lucid's public HFT article describes high order volume in very short
        time frames but does not publish one canonical numeric threshold.
        Deployment code must therefore supply the operator's chosen hard stop.
        """
        if order_count < 0:
            raise ValueError("order_count must be non-negative")
        if window_minutes <= 0:
            raise ValueError("window_minutes must be positive")
        if max_orders_per_minute <= 0:
            raise ValueError("max_orders_per_minute must be positive")
        return order_count / window_minutes > max_orders_per_minute

    def max_contracts(
        self,
        *,
        micros: bool = False,
        phase: str = "eval",
        simulated_profit: float = 0.0,
    ) -> int:
        """Return the contract cap for 50K under either phase.

        Source doc, "LucidFlex Scaling Plan", 50K column:
        - Eval phase: no scaling, fixed cap of 4 minis / 40 micros.
        - Funded phase, by simulated profit:
            $0 - $999      → 2 minis (20 micros)
            $1,000 - $1,999 → 3 minis (30 micros)
            $2,000+         → 4 minis (40 micros)

        The doc shows "$3,000-$4,499 → -" for 50K (no separate row). We treat
        anything above $2,000 as the 4-mini cap, which is also the size cap.
        """
        if phase == "eval":
            return self.max_micro_contracts_eval if micros else self.max_mini_contracts_eval

        if phase != "funded":
            msg = f"unknown LucidFlex phase: {phase}"
            raise ValueError(msg)

        if simulated_profit < 1_000:
            minis = 2
        elif simulated_profit < 2_000:
            minis = 3
        else:
            minis = 4

        # 1 mini = 10 micros at LucidFlex (consistent with TopStep's 10:1).
        return minis * 10 if micros else minis

    def must_be_flat(self, ts: datetime) -> bool:
        """Return True if the firm requires positions to be flat at ``ts``.

        Source doc: "flat by 4:45 PM EST Mon-Fri; reopen 6:00 PM EST Sun-Thu".
        Saturday is fully flat. Sunday is flat until 6:00 PM (reopen for the
        Monday session). Friday is flat from 4:45 PM through the weekend.
        Mon-Thu have a daily 4:45 PM-6:00 PM closed window.

        Current public Lucid text says open positions are automatically closed
        at 4:45 PM and that holding past this time does not fail the account.
        Treat True as "must not initiate/hold intentionally", not as a breach.

        ``ts`` must be timezone-aware. Naive datetimes raise ``ValueError`` —
        silently assuming UTC or local time would be a correctness trap when
        replaying historical trades across daylight-saving transitions.
        """
        if ts.tzinfo is None:
            raise ValueError("must_be_flat requires a timezone-aware datetime")

        local_ts = ts.astimezone(self.timezone)
        weekday = local_ts.weekday()  # Monday = 0, Sunday = 6
        local_time = local_ts.time()

        if weekday == 5:  # Saturday
            return True
        if weekday == 6:  # Sunday
            # Flat until reopen; at exactly reopen_time, tradeable.
            return local_time < self.reopen_time
        if weekday == 4:  # Friday
            # Flat from flatten_time through the weekend (no Friday reopen).
            return local_time >= self.flatten_time
        # Monday-Thursday: daily flatten window.
        return self.flatten_time <= local_time < self.reopen_time

    def is_tradeable(self, ts: datetime) -> bool:
        """Inverse of ``must_be_flat`` — convenience for strategy code."""
        return not self.must_be_flat(ts)
