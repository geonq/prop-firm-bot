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
    ``Rulesets/LucidFlex/LucidFlex Rules.md``. Any value flagged as
    ``[VERIFY]`` in the audit is reproduced here only as a working estimate
    until dashboard verification — see ``eval_fee`` and ``reset_cost_estimate``.
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

    # [VERIFY] Both fees still need dashboard/commercial confirmation per the
    # audit. Treat as provisional.
    eval_fee: int = 175
    reset_cost_estimate: int = 61

    # Source doc, "Trading Hours": "flat by 4:45 PM EST Mon-Fri; reopen
    # 6:00 PM EST Sun-Thu". The firm uses "EST" colloquially — the actual
    # timezone is America/New_York, which handles EST/EDT transitions.
    # Holding past flatten_time = breach. Weekend hold prohibited.
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
