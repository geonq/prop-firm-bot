from datetime import date, timedelta

import pytest

from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import AdaptiveSizing
from src.strategies.replay import ReplayDay


def _days(count: int, *r_multiples: float) -> list[ReplayDay]:
    start = date(2026, 1, 5)
    return [ReplayDay.from_values(start + timedelta(days=i), *r_multiples) for i in range(count)]


def test_replay_winning_days_reaches_topstep_payout_cap() -> None:
    result = simulate_topstep_trade_replay(
        _days(30, 1.0),
        eval_risk=1_000,
        funded_risk=800,
        payout_path=TopStepPayoutPath.CONSISTENCY,
        max_combine_days=10,
        max_xfa_days=30,
        payout_cap=2,
    )

    assert result.terminal_reason == "payout_cap"
    assert result.eval_passed
    assert result.combine_days == 3
    assert result.payout_count == 2
    assert result.trader_payouts > 0
    assert result.net_ev > 0


def test_replay_losing_days_breaches_combine_fee_only() -> None:
    result = simulate_topstep_trade_replay(
        _days(2, -5.0),
        eval_risk=500,
        funded_risk=250,
    )

    assert result.terminal_reason == "combine_breach"
    assert result.eval_days == 1
    assert result.funded_days == 0
    assert result.trader_payouts == 0
    assert result.net_ev == -95


def test_replay_adaptive_sizing_and_back2funded() -> None:
    replay_days = [
        *(_days(3, 1.0)),
        ReplayDay.from_values(date(2026, 1, 8), -10.0),
        *[ReplayDay.from_values(date(2026, 1, 9) + timedelta(days=i), 1.0) for i in range(10)],
    ]

    result = simulate_topstep_trade_replay(
        replay_days,
        sizing_fn=AdaptiveSizing(eval_base=1_000, funded_base=300),
        payout_path=TopStepPayoutPath.CONSISTENCY,
        max_back2funded_reactivations=1,
        max_combine_days=10,
        max_xfa_days=30,
        payout_cap=1,
    )

    assert result.eval_passed
    assert result.back2funded_count == 1
    assert result.terminal_reason == "payout_cap"


def test_replay_empty_days_count_toward_combine_timeout() -> None:
    result = simulate_topstep_trade_replay(
        _days(3),
        eval_risk=250,
        funded_risk=125,
        max_combine_days=3,
    )

    assert result.terminal_reason == "combine_timeout"
    assert result.combine_days == 3
    assert result.net_ev == -95


def test_replay_requires_sorted_days() -> None:
    days = [
        ReplayDay.from_values(date(2026, 1, 6), 1.0),
        ReplayDay.from_values(date(2026, 1, 5), 1.0),
    ]

    with pytest.raises(ValueError, match="sorted"):
        simulate_topstep_trade_replay(days, eval_risk=250, funded_risk=125)
