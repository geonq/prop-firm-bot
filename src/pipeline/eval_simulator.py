"""Evaluation-phase simulator."""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.rules.lucidflex import LucidFlex50K
from src.strategies.parametric import BernoulliTradeStrategy


@dataclass(frozen=True)
class EvalAttemptResult:
    passed: bool
    breached: bool
    timed_out: bool
    target_touches_before_consistency: int
    days_used: int
    ending_balance: float
    mll: float
    largest_day_profit: float
    total_profit: float


def simulate_lucidflex_eval(
    strategy: BernoulliTradeStrategy,
    *,
    ruleset: LucidFlex50K | None = None,
    seed: int | None = None,
    rng: random.Random | None = None,
    max_days: int = 90,
) -> EvalAttemptResult:
    """Run one LucidFlex 50K evaluation attempt.

    LucidFlex uses EOD trailing drawdown and no daily loss limit. The MLL is
    checked against the current balance during the next session, while trailing
    updates occur from the session close.
    """
    rules = ruleset or LucidFlex50K()
    rng = rng or random.Random(seed)

    balance = float(rules.starting_balance)
    mll = float(rules.initial_mll)
    daily_pnls: list[float] = []
    target_touches_before_consistency = 0

    for day in range(1, max_days + 1):
        day_open_balance = balance
        for _ in range(strategy.trades_per_day):
            balance += strategy.sample_trade(rng)

            if balance <= mll:
                day_pnl = balance - day_open_balance
                daily_pnls_for_result = daily_pnls + [day_pnl]
                total_profit = balance - rules.starting_balance
                return EvalAttemptResult(
                    passed=False,
                    breached=True,
                    timed_out=False,
                    target_touches_before_consistency=target_touches_before_consistency,
                    days_used=day,
                    ending_balance=balance,
                    mll=mll,
                    largest_day_profit=max(daily_pnls_for_result, default=0.0),
                    total_profit=total_profit,
                )

            total_profit = balance - rules.starting_balance
            if total_profit >= rules.profit_target:
                day_pnl_at_target = balance - day_open_balance
                daily_pnls_for_check = daily_pnls + [day_pnl_at_target]
                if rules.consistency_ok(daily_pnls_for_check, total_profit):
                    return EvalAttemptResult(
                        passed=True,
                        breached=False,
                        timed_out=False,
                        target_touches_before_consistency=target_touches_before_consistency,
                        days_used=day,
                        ending_balance=balance,
                        mll=mll,
                        largest_day_profit=max(daily_pnls_for_check, default=0.0),
                        total_profit=total_profit,
                    )
                target_touches_before_consistency += 1

        day_pnl = balance - day_open_balance
        daily_pnls.append(day_pnl)
        mll = rules.update_mll_after_close(balance, mll)

    total_profit = balance - rules.starting_balance
    return EvalAttemptResult(
        passed=False,
        breached=False,
        timed_out=True,
        target_touches_before_consistency=target_touches_before_consistency,
        days_used=max_days,
        ending_balance=balance,
        mll=mll,
        largest_day_profit=max(daily_pnls, default=0.0),
        total_profit=total_profit,
    )
