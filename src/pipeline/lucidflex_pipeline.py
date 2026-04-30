"""LucidFlex end-to-end pipeline simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.pipeline.eval_simulator import EvalAttemptResult, simulate_lucidflex_eval
from src.pipeline.lucidflex_funded import LucidFlexFundedAccount, PayoutResult
from src.rules.lucidflex import LucidFlex50K
from src.strategies.parametric import BernoulliTradeStrategy


@dataclass(frozen=True)
class LucidFlexPipelineResult:
    eval_result: EvalAttemptResult
    funded_breached: bool
    funded_timed_out: bool
    completed_max_payouts: bool
    eval_days: int
    funded_days: int
    payout_count: int
    gross_payouts: float
    trader_payouts: float
    net_ev: float
    ending_funded_balance: float | None

    @property
    def eval_passed(self) -> bool:
        return self.eval_result.passed

    @property
    def terminal_reason(self) -> str:
        if not self.eval_result.passed:
            if self.eval_result.breached:
                return "eval_breach"
            if self.eval_result.timed_out:
                return "eval_timeout"
            return "eval_failed"
        if self.completed_max_payouts:
            return "max_payouts"
        if self.funded_breached:
            return "funded_breach"
        if self.funded_timed_out:
            return "funded_timeout"
        return "unknown"


def simulate_lucidflex_pipeline(
    strategy: BernoulliTradeStrategy,
    *,
    ruleset: LucidFlex50K | None = None,
    seed: int | None = None,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
) -> LucidFlexPipelineResult:
    """Run eval -> funded payouts -> breach/timeout for one LucidFlex attempt.

    This first full-pipeline version uses the same trade distribution in eval
    and funded. Future sizing code should replace this with phase-aware risk.
    """
    rules = ruleset or LucidFlex50K()
    rng = random.Random(seed)
    eval_result = simulate_lucidflex_eval(
        strategy,
        ruleset=rules,
        rng=rng,
        max_days=max_eval_days,
    )

    if not eval_result.passed:
        return LucidFlexPipelineResult(
            eval_result=eval_result,
            funded_breached=False,
            funded_timed_out=False,
            completed_max_payouts=False,
            eval_days=eval_result.days_used,
            funded_days=0,
            payout_count=0,
            gross_payouts=0.0,
            trader_payouts=0.0,
            net_ev=-float(rules.eval_fee),
            ending_funded_balance=None,
        )

    account = LucidFlexFundedAccount(ruleset=rules)
    gross_payouts = 0.0

    for funded_day in range(1, max_funded_days + 1):
        for _ in range(strategy.trades_per_day):
            account.apply_trade(strategy.sample_trade(rng))
            if account.breached:
                return LucidFlexPipelineResult(
                    eval_result=eval_result,
                    funded_breached=True,
                    funded_timed_out=False,
                    completed_max_payouts=False,
                    eval_days=eval_result.days_used,
                    funded_days=funded_day,
                    payout_count=account.payout_count,
                    gross_payouts=gross_payouts,
                    trader_payouts=account.total_trader_payouts,
                    net_ev=account.total_trader_payouts - rules.eval_fee,
                    ending_funded_balance=account.balance,
                )

        account.close_day()
        if account.payout_eligible():
            payout: PayoutResult = account.request_payout()
            gross_payouts += payout.gross_request
            if account.payout_count >= rules.max_simulated_payouts:
                return LucidFlexPipelineResult(
                    eval_result=eval_result,
                    funded_breached=account.breached,
                    funded_timed_out=False,
                    completed_max_payouts=True,
                    eval_days=eval_result.days_used,
                    funded_days=funded_day,
                    payout_count=account.payout_count,
                    gross_payouts=gross_payouts,
                    trader_payouts=account.total_trader_payouts,
                    net_ev=account.total_trader_payouts - rules.eval_fee,
                    ending_funded_balance=account.balance,
                )

    return LucidFlexPipelineResult(
        eval_result=eval_result,
        funded_breached=account.breached,
        funded_timed_out=True,
        completed_max_payouts=False,
        eval_days=eval_result.days_used,
        funded_days=max_funded_days,
        payout_count=account.payout_count,
        gross_payouts=gross_payouts,
        trader_payouts=account.total_trader_payouts,
        net_ev=account.total_trader_payouts - rules.eval_fee,
        ending_funded_balance=account.balance,
    )
