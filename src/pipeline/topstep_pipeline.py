"""TopStep end-to-end pipeline simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.pipeline.eval_simulator import EvalAttemptResult
from src.pipeline.topstep_account import TopStepNoFeeAccountState, TopStepPhase
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
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
class TopStepPipelineResult:
    combine_result: EvalAttemptResult
    xfa_closed: bool
    xfa_timed_out: bool
    completed_payout_cap: bool
    combine_days: int
    xfa_days: int
    payout_count: int
    gross_payouts: float
    trader_payouts: float
    net_ev: float
    ending_xfa_balance: float | None
    back2funded_count: int = 0

    @property
    def eval_result(self) -> EvalAttemptResult:
        """Compatibility alias for LucidFlex-style aggregate code."""
        return self.combine_result

    @property
    def eval_passed(self) -> bool:
        return self.combine_result.passed

    @property
    def funded_breached(self) -> bool:
        return self.xfa_closed

    @property
    def funded_timed_out(self) -> bool:
        return self.xfa_timed_out

    @property
    def completed_max_payouts(self) -> bool:
        return self.completed_payout_cap

    @property
    def eval_days(self) -> int:
        return self.combine_days

    @property
    def funded_days(self) -> int:
        return self.xfa_days

    @property
    def terminal_reason(self) -> str:
        if not self.combine_result.passed:
            if self.combine_result.breached:
                return "combine_breach"
            if self.combine_result.timed_out:
                return "combine_timeout"
            return "combine_failed"
        if self.completed_payout_cap:
            return "payout_cap"
        if self.xfa_closed:
            return "xfa_closed"
        if self.xfa_timed_out:
            return "xfa_timeout"
        return "unknown"


def simulate_topstep_pipeline(
    strategy: Strategy,
    *,
    ruleset: TopStepNoFee50K | None = None,
    payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    use_daily_loss_limit: bool = False,
    seed: int | None = None,
    max_combine_days: int = 90,
    max_xfa_days: int = 180,
    payout_cap: int | None = None,
    max_back2funded_reactivations: int = 0,
) -> TopStepPipelineResult:
    """Run Combine -> XFA payouts -> close/timeout for one TopStep attempt.

    ``payout_cap`` is a simulation stop, not a TopStep rule. Leave it as
    ``None`` to let the finite funded horizon decide termination.
    """
    rules = ruleset or TopStepNoFee50K()
    rng = random.Random(seed)
    _reset_strategy(strategy)
    account = TopStepNoFeeAccountState(
        ruleset=rules,
        payout_path=payout_path,
        use_daily_loss_limit=use_daily_loss_limit,
    )
    combine_days = 0
    xfa_days = 0
    combine_result: EvalAttemptResult | None = None

    for combine_day in range(1, max_combine_days + 1):
        combine_days = combine_day
        for _ in range(strategy.trades_per_day):
            account.update(_sample_trade(strategy, rng, account=account, phase="eval"))
            if account.phase == TopStepPhase.COMBINE_FAILED:
                combine_result = _account_combine_result(
                    account,
                    days_used=combine_day,
                    timed_out=False,
                )
                break
            if account.phase == TopStepPhase.XFA:
                combine_result = _account_combine_result(
                    account,
                    days_used=combine_day,
                    timed_out=False,
                    passed=True,
                )
                break
            if account.daily_locked:
                break
        if combine_result is not None:
            break

        account.close_day()
        if account.phase == TopStepPhase.XFA:
            combine_result = _account_combine_result(
                account,
                days_used=combine_day,
                timed_out=False,
                passed=True,
            )
            break

    if combine_result is None:
        combine_result = _account_combine_result(
            account,
            days_used=max_combine_days,
            timed_out=True,
        )

    if not combine_result.passed:
        return TopStepPipelineResult(
            combine_result=combine_result,
            xfa_closed=False,
            xfa_timed_out=False,
            completed_payout_cap=False,
            combine_days=combine_days,
            xfa_days=0,
            payout_count=0,
            gross_payouts=0.0,
            trader_payouts=0.0,
            net_ev=account.net_ev,
            ending_xfa_balance=None,
        )

    gross_payouts = 0.0

    for xfa_day in range(1, max_xfa_days + 1):
        xfa_days = xfa_day
        reactivated = False
        for _ in range(strategy.trades_per_day):
            account.update(_sample_trade(strategy, rng, account=account, phase="funded"))
            if account.phase == TopStepPhase.XFA_CLOSED:
                if _try_back2funded(account, max_back2funded_reactivations):
                    reactivated = True
                    break
                return _topstep_result(
                    account,
                    combine_result=combine_result,
                    combine_days=combine_days,
                    xfa_days=xfa_days,
                    gross_payouts=gross_payouts,
                    xfa_closed=True,
                    xfa_timed_out=False,
                    completed_payout_cap=False,
                )
            if account.daily_locked:
                break

        if reactivated:
            continue

        account.close_day()
        try:
            before_balance = account.balance
            account.request_payout()
        except RuntimeError:
            pass
        else:
            gross_payouts += before_balance - account.balance
            if payout_cap is not None and account.payout_count >= payout_cap:
                return _topstep_result(
                    account,
                    combine_result=combine_result,
                    combine_days=combine_days,
                    xfa_days=xfa_days,
                    gross_payouts=gross_payouts,
                    xfa_closed=account.phase == TopStepPhase.XFA_CLOSED,
                    xfa_timed_out=False,
                    completed_payout_cap=True,
                )

    return _topstep_result(
        account,
        combine_result=combine_result,
        combine_days=combine_days,
        xfa_days=max_xfa_days,
        gross_payouts=gross_payouts,
        xfa_closed=account.phase == TopStepPhase.XFA_CLOSED,
        xfa_timed_out=True,
        completed_payout_cap=False,
    )


def _sample_trade(
    strategy: Strategy,
    rng: random.Random,
    *,
    account: TopStepNoFeeAccountState,
    phase: str,
) -> float:
    if isinstance(strategy, StateAwareBernoulliStrategy):
        ctx = SizingContext(
            phase=phase,
            balance=float(account.balance),
            mll=float(account.mll),
            starting_balance=float(account.ruleset.account_size),
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


def _account_combine_result(
    account: TopStepNoFeeAccountState,
    *,
    days_used: int,
    timed_out: bool,
    passed: bool = False,
) -> EvalAttemptResult:
    breached = account.phase == TopStepPhase.COMBINE_FAILED
    if passed:
        ending_balance = float(account.ruleset.combine_pass_balance)
        mll = float(account.ruleset.combine_initial_mll)
        total_profit = float(account.ruleset.combine_profit_target)
    else:
        ending_balance = float(account.balance)
        mll = float(account.mll)
        total_profit = ending_balance - account.ruleset.combine_starting_balance
    daily_pnls = account.combine_daily_pnls + [account.current_day_pnl]
    return EvalAttemptResult(
        passed=passed or account.phase in {TopStepPhase.XFA, TopStepPhase.XFA_CLOSED},
        breached=breached,
        timed_out=timed_out,
        target_touches_before_consistency=0,
        days_used=days_used,
        ending_balance=ending_balance,
        mll=mll,
        largest_day_profit=max(daily_pnls, default=0.0),
        total_profit=total_profit,
    )


def _topstep_result(
    account: TopStepNoFeeAccountState,
    *,
    combine_result: EvalAttemptResult,
    combine_days: int,
    xfa_days: int,
    gross_payouts: float,
    xfa_closed: bool,
    xfa_timed_out: bool,
    completed_payout_cap: bool,
) -> TopStepPipelineResult:
    return TopStepPipelineResult(
        combine_result=combine_result,
        xfa_closed=xfa_closed,
        xfa_timed_out=xfa_timed_out,
        completed_payout_cap=completed_payout_cap,
        combine_days=combine_days,
        xfa_days=xfa_days,
        payout_count=account.payout_count,
        gross_payouts=gross_payouts,
        trader_payouts=account.total_trader_payouts,
        net_ev=account.net_ev,
        ending_xfa_balance=float(account.balance),
        back2funded_count=account.back2funded_count,
    )


def _try_back2funded(account: TopStepNoFeeAccountState, max_reactivations: int) -> bool:
    if max_reactivations <= 0:
        return False
    if account.back2funded_count >= max_reactivations:
        return False
    try:
        account.attempt_back2funded()
    except RuntimeError:
        return False
    return True
