"""LucidFlex historical trade replay pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.pipeline.eval_simulator import EvalAttemptResult
from src.pipeline.lucidflex_account import LucidFlexAccountState, LucidFlexPhase
from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult
from src.rules.lucidflex import LucidFlex50K
from src.strategies.replay import ReplayDay


def simulate_lucidflex_trade_replay(
    replay_days: Sequence[ReplayDay],
    *,
    eval_risk: float,
    funded_risk: float,
    ruleset: LucidFlex50K | None = None,
    eval_cost_per_trade: float = 0.0,
    funded_cost_per_trade: float = 0.0,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
) -> LucidFlexPipelineResult:
    """Replay dated trade R-multiples through the LucidFlex account machine.

    The replay consumes days sequentially. Eval passing starts funded replay on
    the next available replay day, which keeps one session from mixing eval and
    funded trade states.
    """
    _validate_replay_inputs(
        replay_days,
        eval_risk=eval_risk,
        funded_risk=funded_risk,
        eval_cost_per_trade=eval_cost_per_trade,
        funded_cost_per_trade=funded_cost_per_trade,
        max_eval_days=max_eval_days,
        max_funded_days=max_funded_days,
    )

    rules = ruleset or LucidFlex50K()
    account = LucidFlexAccountState(ruleset=rules)
    eval_days = 0
    funded_days = 0
    eval_result: EvalAttemptResult | None = None
    gross_payouts = 0.0

    for replay_day in replay_days:
        if account.phase == LucidFlexPhase.EVAL:
            if eval_days >= max_eval_days:
                break
            eval_days += 1
            eval_result = _apply_eval_day(account, replay_day, eval_risk, eval_cost_per_trade, eval_days)
            if eval_result is not None:
                if eval_result.passed:
                    continue
                return _terminal_result(
                    account,
                    eval_result=eval_result,
                    eval_days=eval_days,
                    funded_days=funded_days,
                    funded_breached=False,
                    funded_timed_out=False,
                    completed_max_payouts=False,
                    gross_payouts=gross_payouts,
                )
            continue

        if account.phase == LucidFlexPhase.FUNDED:
            if funded_days >= max_funded_days:
                break
            funded_days += 1
            terminal = _apply_funded_day(account, replay_day, funded_risk, funded_cost_per_trade)
            gross_payouts += terminal.gross_payout if terminal.gross_payout else 0.0
            if terminal.phase == LucidFlexPhase.BREACHED_FUNDED:
                return _terminal_result(
                    account,
                    eval_result=eval_result or _eval_result(account, days_used=eval_days, timed_out=False, passed=True),
                    eval_days=eval_days,
                    funded_days=funded_days,
                    funded_breached=True,
                    funded_timed_out=False,
                    completed_max_payouts=False,
                    gross_payouts=gross_payouts,
                )
            if terminal.phase == LucidFlexPhase.MAX_PAYOUTS:
                return _terminal_result(
                    account,
                    eval_result=eval_result or _eval_result(account, days_used=eval_days, timed_out=False, passed=True),
                    eval_days=eval_days,
                    funded_days=funded_days,
                    funded_breached=False,
                    funded_timed_out=False,
                    completed_max_payouts=True,
                    gross_payouts=gross_payouts,
                )
            if funded_days >= max_funded_days:
                break

    if eval_result is None:
        eval_result = _eval_result(account, days_used=eval_days, timed_out=True)

    if not eval_result.passed:
        return _terminal_result(
            account,
            eval_result=eval_result,
            eval_days=eval_days,
            funded_days=0,
            funded_breached=False,
            funded_timed_out=False,
            completed_max_payouts=False,
            gross_payouts=0.0,
        )

    return _terminal_result(
        account,
        eval_result=eval_result,
        eval_days=eval_days,
        funded_days=funded_days,
        funded_breached=account.phase == LucidFlexPhase.BREACHED_FUNDED,
        funded_timed_out=account.phase == LucidFlexPhase.FUNDED,
        completed_max_payouts=account.phase == LucidFlexPhase.MAX_PAYOUTS,
        gross_payouts=gross_payouts,
    )


def _apply_eval_day(
    account: LucidFlexAccountState,
    replay_day: ReplayDay,
    risk_amount: float,
    cost_per_trade: float,
    eval_days: int,
) -> EvalAttemptResult | None:
    for r_multiple in replay_day.r_multiples:
        account.update(r_multiple * risk_amount - cost_per_trade)
        if account.phase == LucidFlexPhase.BREACHED_EVAL:
            return _eval_result(account, days_used=eval_days, timed_out=False)
        if account.phase == LucidFlexPhase.FUNDED:
            return _eval_result(account, days_used=eval_days, timed_out=False, passed=True)

    account.close_day()
    if account.phase == LucidFlexPhase.FUNDED:
        return _eval_result(account, days_used=eval_days, timed_out=False, passed=True)
    return None


@dataclass(frozen=True)
class _FundedDayResult:
    phase: LucidFlexPhase
    gross_payout: float = 0.0


def _apply_funded_day(
    account: LucidFlexAccountState,
    replay_day: ReplayDay,
    risk_amount: float,
    cost_per_trade: float,
) -> _FundedDayResult:
    for r_multiple in replay_day.r_multiples:
        account.update(r_multiple * risk_amount - cost_per_trade)
        if account.phase == LucidFlexPhase.BREACHED_FUNDED:
            return _FundedDayResult(account.phase)

    account.close_day()
    try:
        before_balance = account.balance
        account.request_payout()
    except RuntimeError:
        return _FundedDayResult(account.phase)
    return _FundedDayResult(account.phase, gross_payout=before_balance - account.balance)


def _terminal_result(
    account: LucidFlexAccountState,
    *,
    eval_result: EvalAttemptResult,
    eval_days: int,
    funded_days: int,
    funded_breached: bool,
    funded_timed_out: bool,
    completed_max_payouts: bool,
    gross_payouts: float,
) -> LucidFlexPipelineResult:
    return LucidFlexPipelineResult(
        eval_result=eval_result,
        funded_breached=funded_breached,
        funded_timed_out=funded_timed_out,
        completed_max_payouts=completed_max_payouts,
        eval_days=eval_days,
        funded_days=funded_days,
        payout_count=account.payout_count,
        gross_payouts=gross_payouts,
        trader_payouts=account.total_trader_payouts,
        net_ev=account.net_ev,
        ending_funded_balance=account.balance if eval_result.passed else None,
    )


def _eval_result(
    account: LucidFlexAccountState,
    *,
    days_used: int,
    timed_out: bool,
    passed: bool = False,
) -> EvalAttemptResult:
    breached = account.phase == LucidFlexPhase.BREACHED_EVAL
    return EvalAttemptResult(
        passed=passed or account.phase in {LucidFlexPhase.FUNDED, LucidFlexPhase.MAX_PAYOUTS, LucidFlexPhase.BREACHED_FUNDED},
        breached=breached,
        timed_out=timed_out,
        target_touches_before_consistency=0,
        days_used=days_used,
        ending_balance=account.balance,
        mll=account.mll,
        largest_day_profit=max(account.eval_daily_pnls + [account.current_day_pnl], default=0.0),
        total_profit=account.balance - account.ruleset.starting_balance if not passed else account.ruleset.profit_target,
    )


def _validate_replay_inputs(
    replay_days: Sequence[ReplayDay],
    *,
    eval_risk: float,
    funded_risk: float,
    eval_cost_per_trade: float,
    funded_cost_per_trade: float,
    max_eval_days: int,
    max_funded_days: int,
) -> None:
    if eval_risk <= 0:
        raise ValueError("eval_risk must be positive")
    if funded_risk <= 0:
        raise ValueError("funded_risk must be positive")
    if eval_cost_per_trade < 0 or funded_cost_per_trade < 0:
        raise ValueError("costs must be non-negative")
    if max_eval_days <= 0:
        raise ValueError("max_eval_days must be positive")
    if max_funded_days <= 0:
        raise ValueError("max_funded_days must be positive")

    session_dates = [day.session_date for day in replay_days]
    if session_dates != sorted(session_dates):
        raise ValueError("replay_days must be sorted by session_date")
