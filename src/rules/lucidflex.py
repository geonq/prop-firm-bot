"""LucidFlex ruleset encoding.

Source: Rulesets/LucidFlex/LucidFlex Rules.md and
Rulesets/PHASE1_RULESET_AUDIT.md, both last updated 2026-04-30.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LucidFlex50K:
    """LucidFlex 50K rule parameters used by the simulator.

    This first encoding focuses on the evaluation phase because that is the
    gating step for the initial strategy probe. Funded payout rules are kept as
    constants here but are not simulated yet.
    """

    account_size: int = 50_000
    profit_target: int = 3_000
    max_loss_limit: int = 2_000
    initial_trail_balance: int = 52_100
    locked_mll_balance: int = 50_100
    eval_consistency_limit: float = 0.52
    max_mini_contracts_eval: int = 4
    max_micro_contracts_eval: int = 40
    funded_profit_split: float = 0.90
    payout_minimum: int = 500
    payout_maximum: int = 2_000
    payout_min_profitable_days: int = 5
    payout_min_daily_profit: int = 150
    eval_fee: int = 175
    reset_cost_estimate: int = 61

    @property
    def starting_balance(self) -> int:
        return self.account_size

    @property
    def initial_mll(self) -> int:
        return self.account_size - self.max_loss_limit

    @property
    def pass_balance(self) -> int:
        return self.account_size + self.profit_target

    def update_mll_after_close(self, closing_balance: float, current_mll: float) -> float:
        """Update the end-of-day trailing MLL from the session close."""
        if closing_balance >= self.initial_trail_balance:
            return float(self.locked_mll_balance)

        candidate = closing_balance - self.max_loss_limit
        return float(max(current_mll, min(candidate, self.locked_mll_balance)))

    def consistency_ok(self, daily_pnls: list[float], total_profit: float) -> bool:
        """Return whether eval consistency permits upgrade at current profit."""
        if total_profit < self.profit_target:
            return False
        if total_profit <= 0:
            return False

        largest_day = max(daily_pnls, default=0.0)
        return largest_day / total_profit <= self.eval_consistency_limit

    def max_contracts(self, *, micros: bool = False, phase: str = "eval", simulated_profit: float = 0.0) -> int:
        """Return the max allowed contracts for 50K.

        Evaluation has no scaling plan. Funded scaling updates EOD and is based
        on simulated profits.
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

        return minis * 10 if micros else minis
