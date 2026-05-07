"""TopStep historical trade replay pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.pipeline.eval_simulator import EvalAttemptResult
from src.pipeline.topstep_account import TopStepNoFeeAccountState, TopStepPhase
from src.pipeline.topstep_pipeline import TopStepPipelineResult
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.sizing.dynamic import FixedSizing, SizingContext, SizingFunction
from src.strategies.replay import ReplayDay


def simulate_topstep_trade_replay(
    replay_days: Sequence[ReplayDay],
    *,
    sizing_fn: SizingFunction | None = None,
    eval_risk: float | None = None,
    funded_risk: float | None = None,
    ruleset: TopStepNoFee50K | None = None,
    payout_path: TopStepPayoutPath = TopStepPayoutPath.STANDARD,
    use_daily_loss_limit: bool = False,
    eval_cost_per_trade: float = 0.0,
    funded_cost_per_trade: float = 0.0,
    max_combine_days: int = 90,
    max_xfa_days: int = 180,
    payout_cap: int | None = None,
    max_back2funded_reactivations: int = 0,
) -> TopStepPipelineResult:
    """Replay dated trade R-multiples through TopStep Combine -> XFA.

    The replay consumes days sequentially. Combine passing starts XFA replay on
    the next available replay day, matching the LucidFlex replay convention so
    one session never mixes eval and funded state.
    """
    sizing = _resolve_sizing_fn(sizing_fn, eval_risk=eval_risk, funded_risk=funded_risk)
    _validate_replay_inputs(
        replay_days,
        eval_cost_per_trade=eval_cost_per_trade,
        funded_cost_per_trade=funded_cost_per_trade,
        max_combine_days=max_combine_days,
        max_xfa_days=max_xfa_days,
        payout_cap=payout_cap,
        max_back2funded_reactivations=max_back2funded_reactivations,
    )

    account = TopStepNoFeeAccountState(
        ruleset=ruleset or TopStepNoFee50K(),
        payout_path=payout_path,
        use_daily_loss_limit=use_daily_loss_limit,
    )
    combine_days = 0
    xfa_days = 0
    combine_result: EvalAttemptResult | None = None
    gross_payouts = 0.0

    for replay_day in replay_days:
        if account.phase == TopStepPhase.COMBINE:
            if combine_days >= max_combine_days:
                break
            combine_days += 1
            combine_result = _apply_combine_day(
                account,
                replay_day,
                sizing,
                eval_cost_per_trade,
                combine_days,
            )
            if combine_result is not None:
                if combine_result.passed:
                    continue
                return _terminal_result(
                    account,
                    combine_result=combine_result,
                    combine_days=combine_days,
                    xfa_days=0,
                    gross_payouts=0.0,
                    xfa_closed=False,
                    xfa_timed_out=False,
                    completed_payout_cap=False,
                )
            continue

        if account.phase == TopStepPhase.XFA:
            if xfa_days >= max_xfa_days:
                break
            xfa_days += 1
            day_result = _apply_xfa_day(
                account,
                replay_day,
                sizing,
                funded_cost_per_trade,
                max_back2funded_reactivations=max_back2funded_reactivations,
            )
            gross_payouts += day_result.gross_payout
            if day_result.reactivated:
                continue
            if day_result.xfa_closed:
                return _terminal_result(
                    account,
                    combine_result=combine_result
                    or _combine_result(
                        account,
                        days_used=combine_days,
                        timed_out=False,
                        passed=True,
                    ),
                    combine_days=combine_days,
                    xfa_days=xfa_days,
                    gross_payouts=gross_payouts,
                    xfa_closed=True,
                    xfa_timed_out=False,
                    completed_payout_cap=False,
                )
            if payout_cap is not None and account.payout_count >= payout_cap:
                return _terminal_result(
                    account,
                    combine_result=combine_result
                    or _combine_result(
                        account,
                        days_used=combine_days,
                        timed_out=False,
                        passed=True,
                    ),
                    combine_days=combine_days,
                    xfa_days=xfa_days,
                    gross_payouts=gross_payouts,
                    xfa_closed=account.phase == TopStepPhase.XFA_CLOSED,
                    xfa_timed_out=False,
                    completed_payout_cap=True,
                )

    if combine_result is None:
        combine_result = _combine_result(account, days_used=combine_days, timed_out=True)

    if not combine_result.passed:
        return _terminal_result(
            account,
            combine_result=combine_result,
            combine_days=combine_days,
            xfa_days=0,
            gross_payouts=0.0,
            xfa_closed=False,
            xfa_timed_out=False,
            completed_payout_cap=False,
        )

    return _terminal_result(
        account,
        combine_result=combine_result,
        combine_days=combine_days,
        xfa_days=xfa_days,
        gross_payouts=gross_payouts,
        xfa_closed=account.phase == TopStepPhase.XFA_CLOSED,
        xfa_timed_out=account.phase == TopStepPhase.XFA,
        completed_payout_cap=False,
    )


def _apply_combine_day(
    account: TopStepNoFeeAccountState,
    replay_day: ReplayDay,
    sizing_fn: SizingFunction,
    cost_per_trade: float,
    combine_days: int,
) -> EvalAttemptResult | None:
    for r_multiple in replay_day.r_multiples:
        account.update(
            r_multiple * _risk_amount(account, sizing_fn, phase="eval") - cost_per_trade
        )
        if account.phase == TopStepPhase.COMBINE_FAILED:
            return _combine_result(account, days_used=combine_days, timed_out=False)
        if account.phase == TopStepPhase.XFA:
            return _combine_result(account, days_used=combine_days, timed_out=False, passed=True)
        if account.daily_locked:
            break

    account.close_day()
    if account.phase == TopStepPhase.XFA:
        return _combine_result(account, days_used=combine_days, timed_out=False, passed=True)
    return None


@dataclass(frozen=True)
class _XfaDayResult:
    gross_payout: float = 0.0
    xfa_closed: bool = False
    reactivated: bool = False


def _apply_xfa_day(
    account: TopStepNoFeeAccountState,
    replay_day: ReplayDay,
    sizing_fn: SizingFunction,
    cost_per_trade: float,
    *,
    max_back2funded_reactivations: int,
) -> _XfaDayResult:
    for r_multiple in replay_day.r_multiples:
        account.update(
            r_multiple * _risk_amount(account, sizing_fn, phase="funded")
            - cost_per_trade
        )
        if account.phase == TopStepPhase.XFA_CLOSED:
            if _try_back2funded(account, max_back2funded_reactivations):
                return _XfaDayResult(reactivated=True)
            return _XfaDayResult(xfa_closed=True)
        if account.daily_locked:
            break

    account.close_day()
    try:
        before_balance = account.balance
        account.request_payout()
    except RuntimeError:
        return _XfaDayResult(xfa_closed=account.phase == TopStepPhase.XFA_CLOSED)
    return _XfaDayResult(
        gross_payout=before_balance - account.balance,
        xfa_closed=account.phase == TopStepPhase.XFA_CLOSED,
    )


def _risk_amount(
    account: TopStepNoFeeAccountState,
    sizing_fn: SizingFunction,
    *,
    phase: str,
) -> float:
    return sizing_fn(
        SizingContext(
            phase=phase,
            balance=float(account.balance),
            mll=float(account.mll),
            starting_balance=float(account.ruleset.account_size),
            payout_count=account.payout_count,
        )
    )


def _resolve_sizing_fn(
    sizing_fn: SizingFunction | None,
    *,
    eval_risk: float | None,
    funded_risk: float | None,
) -> SizingFunction:
    if sizing_fn is not None:
        if eval_risk is not None or funded_risk is not None:
            raise ValueError("pass either sizing_fn or eval_risk/funded_risk, not both")
        return sizing_fn
    if eval_risk is None or funded_risk is None:
        raise ValueError("eval_risk and funded_risk are required when sizing_fn is omitted")
    if eval_risk <= 0 or funded_risk <= 0:
        raise ValueError("risk values must be positive")
    return FixedSizing(eval_size=eval_risk, funded_size=funded_risk)


def _combine_result(
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


def _terminal_result(
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
        ending_xfa_balance=float(account.balance) if combine_result.passed else None,
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


def _validate_replay_inputs(
    replay_days: Sequence[ReplayDay],
    *,
    eval_cost_per_trade: float,
    funded_cost_per_trade: float,
    max_combine_days: int,
    max_xfa_days: int,
    payout_cap: int | None,
    max_back2funded_reactivations: int,
) -> None:
    if eval_cost_per_trade < 0 or funded_cost_per_trade < 0:
        raise ValueError("costs must be non-negative")
    if max_combine_days <= 0:
        raise ValueError("max_combine_days must be positive")
    if max_xfa_days <= 0:
        raise ValueError("max_xfa_days must be positive")
    if payout_cap is not None and payout_cap <= 0:
        raise ValueError("payout_cap must be positive when provided")
    if max_back2funded_reactivations < 0:
        raise ValueError("max_back2funded_reactivations must be non-negative")

    session_dates = [day.session_date for day in replay_days]
    if session_dates != sorted(session_dates):
        raise ValueError("replay_days must be sorted by session_date")
