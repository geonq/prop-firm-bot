"""TopStep No Activation Fee ruleset encoding.

Source: Rulesets/TopStep/TopStep NoFee.md and
Rulesets/PHASE1_RULESET_AUDIT.md, both last updated 2026-04-30.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TopStepPayoutPath(StrEnum):
    STANDARD = "standard"
    CONSISTENCY = "consistency"


@dataclass(frozen=True)
class TopStepNoFee50K:
    """TopStep 50K No Activation Fee path.

    This covers the Trading Combine plus Express Funded Account (XFA) rules
    needed for v1 simulation. XFA scaling thresholds are still reviewer-gated
    because the local audit flags the official graph values for confirmation.
    """

    account_size: int = 50_000
    combine_profit_target: int = 3_000
    max_loss_limit: int = 2_000
    combine_consistency_limit: float = 0.50
    combine_max_mini_contracts: int = 5
    combine_max_micro_contracts: int = 50
    daily_loss_limit: int = 1_000
    nofee_monthly_fee: int = 95
    nofee_reset_cost: int = 109
    activation_fee: int = 0
    back2funded_cost: int = 599
    max_back2funded_reactivations: int = 2
    payout_minimum: int = 125
    standard_payout_maximum: int = 2_000
    consistency_payout_maximum: int = 3_000
    standard_winning_days_required: int = 5
    standard_min_winning_day: int = 150
    consistency_days_required: int = 3
    xfa_consistency_limit: float = 0.40
    profit_split: float = 0.90

    @property
    def combine_starting_balance(self) -> int:
        return self.account_size

    @property
    def combine_initial_mll(self) -> int:
        return self.account_size - self.max_loss_limit

    @property
    def combine_pass_balance(self) -> int:
        return self.account_size + self.combine_profit_target

    @property
    def xfa_starting_balance(self) -> int:
        return 0

    @property
    def xfa_initial_mll(self) -> int:
        return -self.max_loss_limit

    def update_combine_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, self.combine_starting_balance)))

    def update_xfa_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, 0.0)))

    def combine_consistency_ok(self, daily_pnls: list[float], total_profit: float) -> bool:
        if total_profit < self.combine_profit_target:
            return False
        if total_profit <= 0:
            return False
        return max(daily_pnls, default=0.0) / total_profit <= self.combine_consistency_limit

    def xfa_consistency_ok(self, cycle_daily_pnls: list[float], cycle_profit: float) -> bool:
        if cycle_profit <= 0:
            return False
        return max(cycle_daily_pnls, default=0.0) / cycle_profit <= self.xfa_consistency_limit

    def payout_request_amount(self, balance: float, path: TopStepPayoutPath = TopStepPayoutPath.STANDARD) -> float:
        if balance <= 0:
            return 0.0
        cap = self.standard_payout_maximum if path == TopStepPayoutPath.STANDARD else self.consistency_payout_maximum
        request = min(balance * 0.50, cap)
        if request < self.payout_minimum:
            return 0.0
        return float(request)

    def trader_payout_amount(self, gross_request: float) -> float:
        return gross_request * self.profit_split

    def max_contracts(self, *, micros: bool = False, phase: str = "combine", balance: float = 0.0) -> int:
        if phase == "combine":
            return self.combine_max_micro_contracts if micros else self.combine_max_mini_contracts

        if phase != "xfa":
            msg = f"unknown TopStep phase: {phase}"
            raise ValueError(msg)

        # Reviewer-gated 50K XFA values from local audit. Use only as a
        # provisional simulation clamp until graph/dashboard confirmation.
        if balance < 1_500:
            minis = 2
        elif balance <= 2_000:
            minis = 3
        else:
            minis = 5

        return minis * 10 if micros else minis
