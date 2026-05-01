from datetime import date, timedelta

import pytest

from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.strategies.replay import ReplayDay


def _winning_days(count: int) -> list[ReplayDay]:
    start = date(2026, 1, 2)
    return [ReplayDay.from_values(start + timedelta(days=i), 1.0) for i in range(count)]


def test_replay_winning_days_reaches_max_payouts_with_phase_risk() -> None:
    result = simulate_lucidflex_trade_replay(
        _winning_days(30),
        eval_risk=750,
        funded_risk=200,
        max_eval_days=10,
        max_funded_days=30,
    )

    assert result.terminal_reason == "max_payouts"
    assert result.eval_days == 4
    assert result.funded_days == 25
    assert result.payout_count == 5
    assert result.gross_payouts == 4_031.25
    assert result.trader_payouts == 3_628.125
    assert result.net_ev == 3_530.125


def test_replay_losing_days_breaches_eval_fee_only() -> None:
    days = [
        ReplayDay.from_values(date(2026, 1, 2), -5.0),
        ReplayDay.from_values(date(2026, 1, 3), -5.0),
    ]

    result = simulate_lucidflex_trade_replay(days, eval_risk=300, funded_risk=125)

    assert result.terminal_reason == "eval_breach"
    assert result.eval_days == 2
    assert result.funded_days == 0
    assert result.trader_payouts == 0
    assert result.net_ev == -98


def test_replay_empty_days_count_toward_eval_timeout() -> None:
    days = [
        ReplayDay.from_values(date(2026, 1, 2)),
        ReplayDay.from_values(date(2026, 1, 3)),
        ReplayDay.from_values(date(2026, 1, 4)),
    ]

    result = simulate_lucidflex_trade_replay(days, eval_risk=250, funded_risk=125, max_eval_days=3)

    assert result.terminal_reason == "eval_timeout"
    assert result.eval_days == 3
    assert result.net_ev == -98


def test_replay_requires_sorted_days() -> None:
    days = [
        ReplayDay.from_values(date(2026, 1, 3), 1.0),
        ReplayDay.from_values(date(2026, 1, 2), 1.0),
    ]

    with pytest.raises(ValueError, match="sorted"):
        simulate_lucidflex_trade_replay(days, eval_risk=250, funded_risk=125)
