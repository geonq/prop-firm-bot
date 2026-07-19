"""Apex Trader Funding 4.0 historical trade replay pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.pipeline.apex_account import ApexAccountState, ApexPhase
from src.pipeline.apex_pipeline import ApexPipelineResult
from src.pipeline.eval_simulator import EvalAttemptResult
from src.rules.apex import Apex50K
from src.sizing.dynamic import FixedSizing, SizingContext, SizingFunction
from src.strategies.replay import ReplayDay


def simulate_apex_trade_replay(
    replay_days: Sequence[ReplayDay],
    *,
    sizing_fn: SizingFunction | None = None,
    eval_risk: float | None = None,
    funded_risk: float | None = None,
    ruleset: Apex50K | None = None,
    drawdown_variant: str = "eod",
    eval_cost_per_trade: float = 0.0,
    funded_cost_per_trade: float = 0.0,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
    payout_cap: int | None = None,
) -> ApexPipelineResult:
    """Replay dated trade R-multiples through the Apex account machine.

    Mirrors ``simulate_lucidflex_trade_replay`` in shape: the replay consumes
    days sequentially, and eval passing starts PA replay on the next
    available replay day so one session never mixes eval and PA state.

    ``drawdown_variant`` is forwarded straight to ``ApexAccountState`` — see
    ``src/pipeline/apex_account.py`` for the EOD vs. intraday semantics
    (EOD: threshold moves only at day close, soft DLL pauses remaining
    trades for the session; intraday: threshold ratchets on the running
    peak balance per trade, no DLL).

    ``payout_cap`` mirrors the parametric ``simulate_apex_pipeline`` — it is
    a simulation stop, not an Apex rule (Apex payouts are uncapped from
    cycle 7 onward). Leave it as ``None`` to let the finite funded replay
    horizon decide termination.
    """
    sizing = _resolve_sizing_fn(sizing_fn, eval_risk=eval_risk, funded_risk=funded_risk)
    _validate_replay_inputs(
        replay_days,
        eval_cost_per_trade=eval_cost_per_trade,
        funded_cost_per_trade=funded_cost_per_trade,
        max_eval_days=max_eval_days,
        max_funded_days=max_funded_days,
        payout_cap=payout_cap,
    )

    rules = ruleset or Apex50K()
    account = ApexAccountState(ruleset=rules, drawdown_variant=drawdown_variant)
    eval_days = 0
    funded_days = 0
    eval_result: EvalAttemptResult | None = None
    gross_payouts = 0.0

    for replay_day in replay_days:
        if account.phase == ApexPhase.EVAL:
            if eval_days >= max_eval_days:
                break
            eval_days += 1
            eval_result = _apply_eval_day(account, replay_day, sizing, eval_cost_per_trade, eval_days)
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

        if account.phase == ApexPhase.PA:
            if funded_days >= max_funded_days:
                break
            funded_days += 1
            terminal = _apply_funded_day(account, replay_day, sizing, funded_cost_per_trade)
            gross_payouts += terminal.gross_payout if terminal.gross_payout else 0.0
            if terminal.phase == ApexPhase.BREACHED_PA:
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
            if payout_cap is not None and account.payout_count >= payout_cap:
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
        funded_breached=account.phase == ApexPhase.BREACHED_PA,
        funded_timed_out=account.phase == ApexPhase.PA,
        completed_max_payouts=False,
        gross_payouts=gross_payouts,
    )


def _apply_eval_day(
    account: ApexAccountState,
    replay_day: ReplayDay,
    sizing_fn: SizingFunction,
    cost_per_trade: float,
    eval_days: int,
) -> EvalAttemptResult | None:
    for r_multiple in replay_day.r_multiples:
        account.update(r_multiple * _risk_amount(account, sizing_fn, phase="eval") - cost_per_trade)
        if account.phase == ApexPhase.BREACHED_EVAL:
            return _eval_result(account, days_used=eval_days, timed_out=False)
        if account.phase == ApexPhase.PA:
            return _eval_result(account, days_used=eval_days, timed_out=False, passed=True)
        if account.daily_locked:
            # EOD-variant soft DLL: remaining trades this session are
            # skipped, matching the parametric apex_pipeline convention.
            break

    account.close_day()
    if account.phase == ApexPhase.PA:
        return _eval_result(account, days_used=eval_days, timed_out=False, passed=True)
    return None


@dataclass(frozen=True)
class _FundedDayResult:
    phase: ApexPhase
    gross_payout: float = 0.0


def _apply_funded_day(
    account: ApexAccountState,
    replay_day: ReplayDay,
    sizing_fn: SizingFunction,
    cost_per_trade: float,
) -> _FundedDayResult:
    for r_multiple in replay_day.r_multiples:
        account.update(r_multiple * _risk_amount(account, sizing_fn, phase="funded") - cost_per_trade)
        if account.phase == ApexPhase.BREACHED_PA:
            return _FundedDayResult(account.phase)
        if account.daily_locked:
            break

    account.close_day()
    try:
        before_balance = account.balance
        account.request_payout()
    except RuntimeError:
        return _FundedDayResult(account.phase)
    return _FundedDayResult(account.phase, gross_payout=before_balance - account.balance)


def _terminal_result(
    account: ApexAccountState,
    *,
    eval_result: EvalAttemptResult,
    eval_days: int,
    funded_days: int,
    funded_breached: bool,
    funded_timed_out: bool,
    completed_max_payouts: bool,
    gross_payouts: float,
) -> ApexPipelineResult:
    return ApexPipelineResult(
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


def _risk_amount(
    account: ApexAccountState,
    sizing_fn: SizingFunction,
    *,
    phase: str,
) -> float:
    return sizing_fn(
        SizingContext(
            phase=phase,
            balance=float(account.balance),
            mll=float(account.threshold),
            starting_balance=float(account.ruleset.starting_balance),
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


def _validate_replay_inputs(
    replay_days: Sequence[ReplayDay],
    *,
    eval_cost_per_trade: float,
    funded_cost_per_trade: float,
    max_eval_days: int,
    max_funded_days: int,
    payout_cap: int | None = None,
) -> None:
    if eval_cost_per_trade < 0 or funded_cost_per_trade < 0:
        raise ValueError("costs must be non-negative")
    if max_eval_days <= 0:
        raise ValueError("max_eval_days must be positive")
    if max_funded_days <= 0:
        raise ValueError("max_funded_days must be positive")
    if payout_cap is not None and payout_cap <= 0:
        raise ValueError("payout_cap must be positive when provided")

    session_dates = [day.session_date for day in replay_days]
    if session_dates != sorted(session_dates):
        raise ValueError("replay_days must be sorted by session_date")
