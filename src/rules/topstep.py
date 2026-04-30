"""TopStep 50K No Activation Fee ruleset encoding.

Source documents:
- ``Rulesets/TopStep/TopStep NoFee.md`` (compiled encoding reference + verbatim
  paste from the official help center)
- ``Rulesets/PHASE1_RULESET_AUDIT.md`` (Phase 1 reviewer audit notes)

Reviewer pass: Claude Code, 2026-04-30. The Trading Combine ("eval") and
Express Funded Account ("XFA", funded) are encoded as separate phases. XFA
scaling tiers in ``max_contracts`` remain provisional — the source doc shows
them as graphs only and the audit flags them as third-party-derived until
dashboard verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo


class TopStepPayoutPath(StrEnum):
    """The two XFA payout paths (chosen at activation, locked per account).

    See source doc, "Payout Policy". Standard requires 5 winning days of
    ≥$150 P&L; Consistency requires 3 trading days with the largest day
    ≤40% of total profit. Caps and per-request math differ.
    """

    STANDARD = "standard"
    CONSISTENCY = "consistency"


@dataclass(frozen=True)
class TopStepNoFee50K:
    """TopStep 50K No Activation Fee path.

    Numeric values are taken from
    ``Rulesets/TopStep/TopStep NoFee.md``. Items marked ``[VERIFY]`` in the
    audit (XFA scaling tiers) remain reviewer-gated.
    """

    account_size: int = 50_000
    combine_profit_target: int = 3_000
    max_loss_limit: int = 2_000

    # Source doc, Trading Combine "Objectives": "Best Day below 50% of total
    # profits". Encoded with ``<=`` to match Lucid's wording — the dollar
    # boundary is too narrow to materially differ.
    combine_consistency_limit: float = 0.50

    # Source doc, "Trading Combine Maximum Position Size", 50K row:
    # 5 minis or 50 micros (10:1 conversion at TopstepX).
    combine_max_mini_contracts: int = 5
    combine_max_micro_contracts: int = 50

    # Source doc, "Daily Loss Limit": 50K DLL is $1,000. Optional in Combine
    # and XFA, automatic in Live. Hitting it locks the session only — it is
    # NOT a rule violation.
    daily_loss_limit: int = 1_000

    # Source doc, "Pricing": post-2026-04-28 No Activation Fee path.
    nofee_monthly_fee: int = 95
    nofee_reset_cost: int = 109
    activation_fee: int = 0
    back2funded_cost: int = 599
    max_back2funded_reactivations: int = 2

    # Source doc, "Per-request mechanics": min payout $125; per-account caps
    # below; Standard/Consistency caps differ.
    payout_minimum: int = 125
    standard_payout_maximum: int = 2_000
    consistency_payout_maximum: int = 3_000
    standard_winning_days_required: int = 5
    standard_min_winning_day: int = 150
    consistency_days_required: int = 3
    xfa_consistency_limit: float = 0.40
    profit_split: float = 0.90

    # Source doc, "Trading Hours, Products, Position Rules": "flat by
    # 3:10:00 PM CT Mon-Fri; reopen 5:00 PM CT weekdays / 5:00 PM CT Sunday".
    # No swing trading in Combine or XFA. Holding past flatten_time = breach.
    # Timezone America/Chicago handles CST/CDT transitions automatically.
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Chicago"))
    flatten_time: time = time(15, 10)
    reopen_time: time = time(17, 0)

    @property
    def combine_starting_balance(self) -> int:
        return self.account_size

    @property
    def combine_initial_mll(self) -> int:
        # Combine MLL starts at (account_size - max_loss_limit) and trails up
        # from there. See ``update_combine_mll_after_close``.
        return self.account_size - self.max_loss_limit

    @property
    def combine_pass_balance(self) -> int:
        return self.account_size + self.combine_profit_target

    @property
    def xfa_starting_balance(self) -> int:
        # XFA displays balance as $0 at activation; profit accumulates from 0.
        return 0

    @property
    def xfa_initial_mll(self) -> int:
        # XFA MLL begins at -$2,000 and trails up to $0, where it locks
        # permanently. After the first payout, MLL is set to $0 outright.
        return -self.max_loss_limit

    def update_combine_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        """Apply EOD trailing-drawdown update for the Trading Combine.

        Source doc behavior: trails the highest end-of-day balance, never
        moves down, and **locks at the original starting balance** ($50,000
        for 50K) — not above it. After lock, no further movement.
        """
        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, self.combine_starting_balance)))

    def update_xfa_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        """Apply EOD trailing-drawdown update for the XFA.

        Source doc behavior: MLL begins at -$2,000, trails up with the highest
        end-of-day balance, and **locks at $0** (the displayed starting
        balance). Never moves down.
        """
        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, 0.0)))

    def combine_consistency_ok(self, daily_pnls: list[float], total_profit: float) -> bool:
        """Check the Combine "best day below 50% of total profits" objective."""
        if total_profit < self.combine_profit_target:
            return False
        if total_profit <= 0:
            return False
        return max(daily_pnls, default=0.0) / total_profit <= self.combine_consistency_limit

    def xfa_consistency_ok(self, cycle_daily_pnls: list[float], cycle_profit: float) -> bool:
        """Check the XFA Consistency-path payout requirement.

        Source doc: at least 3 trading days, largest day ≤ 40% of total
        profit. Day count is enforced at the call site
        (``TopStepNoFeeAccountState._payout_eligible``); this method only
        checks the ratio.
        """
        if cycle_profit <= 0:
            return False
        return max(cycle_daily_pnls, default=0.0) / cycle_profit <= self.xfa_consistency_limit

    def payout_request_amount(
        self,
        balance: float,
        path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    ) -> float:
        """Return gross payout request before the 90/10 split.

        Source doc: each request capped at 50% of account balance, subject to
        the per-size cap (Standard: $2,000 for 50K; Consistency: $3,000 for
        50K). Min request $125.

        For XFA, ``balance`` is profit-from-zero by construction (XFA starts
        at $0 displayed balance), so 50% of balance = 50% of cycle profit.
        """
        if balance <= 0:
            return 0.0
        cap = (
            self.standard_payout_maximum
            if path == TopStepPayoutPath.STANDARD
            else self.consistency_payout_maximum
        )
        request = min(balance * 0.50, cap)
        if request < self.payout_minimum:
            return 0.0
        return float(request)

    def trader_payout_amount(self, gross_request: float) -> float:
        return gross_request * self.profit_split

    def max_contracts(
        self,
        *,
        micros: bool = False,
        phase: str = "combine",
        balance: float = 0.0,
    ) -> int:
        """Return the contract cap.

        Combine: flat ceiling per source doc, "Trading Combine Maximum
        Position Size" — 5 minis / 50 micros for 50K, no scaling.

        XFA: scaling-plan tiers from the audit's third-party-sourced 50K
        table. **Reviewer-gated** until dashboard graph confirmation:
            < $1,500           → 2 lots
            $1,500 – $2,000    → 3 lots
            > $2,000           → 5 lots (cap)
        """
        if phase == "combine":
            return self.combine_max_micro_contracts if micros else self.combine_max_mini_contracts

        if phase != "xfa":
            msg = f"unknown TopStep phase: {phase}"
            raise ValueError(msg)

        # [VERIFY] XFA tier boundaries from audit. Lower edge of $1,500–$2,000
        # is inclusive in the source table, encoded as ``< 1_500`` then
        # ``elif <= 2_000``.
        if balance < 1_500:
            minis = 2
        elif balance <= 2_000:
            minis = 3
        else:
            minis = 5

        return minis * 10 if micros else minis

    def must_be_flat(self, ts: datetime) -> bool:
        """Return True if the firm requires positions to be flat at ``ts``.

        Source doc: "Daily flatten: All positions must close before
        3:10:00 PM CT, Monday-Friday. Reopen: 5:00 PM CT weekdays / 5:00 PM
        CT Sunday." No swing trading in Combine or XFA.

        Saturday is fully flat. Sunday is flat until 5:00 PM (reopen for the
        Monday session). Friday is flat from 3:10 PM through the weekend.
        Mon-Thu have a daily 3:10 PM-5:00 PM closed window.

        ``ts`` must be timezone-aware. Same rationale as the LucidFlex
        version: replaying historical trades across DST transitions makes
        silent-naive assumptions a correctness trap.
        """
        if ts.tzinfo is None:
            raise ValueError("must_be_flat requires a timezone-aware datetime")

        local_ts = ts.astimezone(self.timezone)
        weekday = local_ts.weekday()  # Monday = 0, Sunday = 6
        local_time = local_ts.time()

        if weekday == 5:  # Saturday
            return True
        if weekday == 6:  # Sunday
            return local_time < self.reopen_time
        if weekday == 4:  # Friday
            return local_time >= self.flatten_time
        # Monday-Thursday: daily flatten window.
        return self.flatten_time <= local_time < self.reopen_time

    def is_tradeable(self, ts: datetime) -> bool:
        """Inverse of ``must_be_flat`` — convenience for strategy code."""
        return not self.must_be_flat(ts)
