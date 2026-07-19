"""Apex Trader Funding 4.0 end-to-end pipeline simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.pipeline.apex_account import ApexAccountState, ApexPhase
from src.pipeline.eval_simulator import EvalAttemptResult
from src.rules.apex import Apex50K
from src.sizing.dynamic import SizingContext
from src.strategies.parametric import (
    AutocorrelatedPhaseAwareBernoulliStrategy,
    BernoulliTradeStrategy,
    PhaseAwareBernoulliStrategy,
    RegimeSwitchingPhaseAwareBernoulliStrategy,
    StateAwareBernoulliStrategy,
)


Strategy = (
    BernoulliTradeStrategy
    | PhaseAwareBernoulliStrategy
    | StateAwareBernoulliStrategy
    | AutocorrelatedPhaseAwareBernoulliStrategy
    | RegimeSwitchingPhaseAwareBernoulliStrategy
)


@dataclass(frozen=True)
class ApexPipelineResult:
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


def simulate_apex_pipeline(
    strategy: Strategy,
    *,
    ruleset: Apex50K | None = None,
    drawdown_variant: str = "eod",
    seed: int | None = None,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    payout_cap: int | None = None,
) -> ApexPipelineResult:
    """Run eval -> PA payouts -> breach/timeout for one Apex attempt.

    ``payout_cap`` is a simulation stop, not an Apex rule — Apex payouts are
    uncapped from cycle 7 onward. Leave it as ``None`` to let the finite
    funded horizon decide termination.
    """
    rules = ruleset or Apex50K()
    rng = random.Random(seed)
    _reset_strategy(strategy)
    account = ApexAccountState(ruleset=rules, drawdown_variant=drawdown_variant)
    eval_days = 0
    funded_days = 0
    eval_result: EvalAttemptResult | None = None

    for eval_day in range(1, max_eval_days + 1):
        eval_days = eval_day
        for _ in range(strategy.trades_per_day):
            account.update(_sample_trade(strategy, rng, account=account, phase="eval"))
            if account.phase == ApexPhase.BREACHED_EVAL:
                eval_result = _account_eval_result(account, days_used=eval_day, timed_out=False)
                break
            if account.phase == ApexPhase.PA:
                eval_result = _account_eval_result(account, days_used=eval_day, timed_out=False, passed=True)
                break
            if account.daily_locked:
                break
        if eval_result is not None:
            break
        account.close_day()
        if account.phase == ApexPhase.PA:
            eval_result = _account_eval_result(account, days_used=eval_day, timed_out=False, passed=True)
            break

    if eval_result is None:
        eval_result = _account_eval_result(account, days_used=max_eval_days, timed_out=True)

    if not eval_result.passed:
        return ApexPipelineResult(
            eval_result=eval_result,
            funded_breached=False,
            funded_timed_out=False,
            completed_max_payouts=False,
            eval_days=eval_days,
            funded_days=0,
            payout_count=0,
            gross_payouts=0.0,
            trader_payouts=0.0,
            net_ev=account.net_ev,
            ending_funded_balance=None,
        )

    gross_payouts = 0.0

    for funded_day in range(1, max_funded_days + 1):
        funded_days = funded_day
        for _ in range(strategy.trades_per_day):
            account.update(_sample_trade(strategy, rng, account=account, phase="funded"))
            if account.phase == ApexPhase.BREACHED_PA:
                return ApexPipelineResult(
                    eval_result=eval_result,
                    funded_breached=True,
                    funded_timed_out=False,
                    completed_max_payouts=False,
                    eval_days=eval_days,
                    funded_days=funded_days,
                    payout_count=account.payout_count,
                    gross_payouts=gross_payouts,
                    trader_payouts=account.total_trader_payouts,
                    net_ev=account.net_ev,
                    ending_funded_balance=account.balance,
                )
            if account.daily_locked:
                break

        account.close_day()
        try:
            before_balance = account.balance
            account.request_payout()
        except RuntimeError:
            pass
        else:
            gross_payouts += before_balance - account.balance
            # A large uncapped (cycle 7+) payout can legitimately pull
            # balance to/below the frozen threshold and breach the account
            # inside request_payout() itself -- check immediately so a
            # breached account is never traded again on the next iteration.
            if account.phase == ApexPhase.BREACHED_PA:
                return ApexPipelineResult(
                    eval_result=eval_result,
                    funded_breached=True,
                    funded_timed_out=False,
                    completed_max_payouts=False,
                    eval_days=eval_days,
                    funded_days=funded_days,
                    payout_count=account.payout_count,
                    gross_payouts=gross_payouts,
                    trader_payouts=account.total_trader_payouts,
                    net_ev=account.net_ev,
                    ending_funded_balance=account.balance,
                )
            if payout_cap is not None and account.payout_count >= payout_cap:
                return ApexPipelineResult(
                    eval_result=eval_result,
                    funded_breached=account.phase == ApexPhase.BREACHED_PA,
                    funded_timed_out=False,
                    completed_max_payouts=True,
                    eval_days=eval_days,
                    funded_days=funded_days,
                    payout_count=account.payout_count,
                    gross_payouts=gross_payouts,
                    trader_payouts=account.total_trader_payouts,
                    net_ev=account.net_ev,
                    ending_funded_balance=account.balance,
                )

    return ApexPipelineResult(
        eval_result=eval_result,
        funded_breached=account.phase == ApexPhase.BREACHED_PA,
        funded_timed_out=True,
        completed_max_payouts=False,
        eval_days=eval_days,
        funded_days=max_funded_days,
        payout_count=account.payout_count,
        gross_payouts=gross_payouts,
        trader_payouts=account.total_trader_payouts,
        net_ev=account.net_ev,
        ending_funded_balance=account.balance,
    )


def _sample_trade(
    strategy: Strategy,
    rng: random.Random,
    *,
    account: ApexAccountState,
    phase: str,
) -> float:
    if isinstance(strategy, StateAwareBernoulliStrategy):
        ctx = SizingContext(
            phase=phase,
            balance=account.balance,
            mll=account.threshold,
            starting_balance=float(account.ruleset.starting_balance),
            payout_count=account.payout_count,
        )
        return strategy.sample_trade(rng, ctx=ctx)
    if isinstance(
        strategy,
        (
            PhaseAwareBernoulliStrategy,
            AutocorrelatedPhaseAwareBernoulliStrategy,
            RegimeSwitchingPhaseAwareBernoulliStrategy,
        ),
    ):
        return strategy.sample_trade(rng, phase=phase)
    return strategy.sample_trade(rng)


def _reset_strategy(strategy: Strategy) -> None:
    reset = getattr(strategy, "reset", None)
    if callable(reset):
        reset()


def _account_eval_result(
    account: ApexAccountState,
    *,
    days_used: int,
    timed_out: bool,
    passed: bool = False,
) -> EvalAttemptResult:
    breached = account.phase == ApexPhase.BREACHED_EVAL
    return EvalAttemptResult(
        passed=passed or account.phase in {ApexPhase.PA, ApexPhase.BREACHED_PA},
        breached=breached,
        timed_out=timed_out,
        target_touches_before_consistency=0,
        days_used=days_used,
        ending_balance=account.balance,
        mll=account.threshold,
        largest_day_profit=max(account.eval_daily_pnls + [account.current_day_pnl], default=0.0),
        total_profit=account.balance - account.ruleset.starting_balance if not passed else account.ruleset.profit_target,
    )
