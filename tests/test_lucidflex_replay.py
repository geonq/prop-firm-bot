from datetime import date, timedelta

import pytest

from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.sizing.dynamic import BufferAwareSizing, FixedSizing
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


def test_replay_rejects_sizing_fn_and_fixed_risk_together() -> None:
    with pytest.raises(ValueError, match="either sizing_fn or eval_risk/funded_risk"):
        simulate_lucidflex_trade_replay(
            _winning_days(2),
            sizing_fn=FixedSizing(eval_size=750, funded_size=200),
            eval_risk=750,
            funded_risk=200,
        )


def test_replay_rejects_neither_sizing_fn_nor_fixed_risk() -> None:
    with pytest.raises(ValueError, match="required when sizing_fn is omitted"):
        simulate_lucidflex_trade_replay(_winning_days(2))


def test_replay_sizing_fn_equivalent_to_fixed_risk_is_bit_identical() -> None:
    days = _winning_days(30)

    fixed = simulate_lucidflex_trade_replay(
        days,
        eval_risk=750,
        funded_risk=200,
        max_eval_days=10,
        max_funded_days=30,
    )
    via_sizing_fn = simulate_lucidflex_trade_replay(
        days,
        sizing_fn=FixedSizing(eval_size=750, funded_size=200),
        max_eval_days=10,
        max_funded_days=30,
    )

    assert via_sizing_fn == fixed


def test_replay_buffer_aware_sizing_shrinks_near_mll() -> None:
    # Default LucidFlex50K starts with buffer_fraction exactly at
    # BufferAwareSizing's full_buffer_fraction (0.04, i.e. the $2,000 buffer
    # over the $50,000 account size), so the first day's trade is sized at
    # full base risk ($1,000). Each subsequent losing day shrinks the
    # buffer further, so the per-trade dollar loss should shrink
    # monotonically as the balance approaches the MLL floor.
    sizing_fn = BufferAwareSizing(eval_base=1_000, funded_base=1_000)
    days = [
        ReplayDay.from_values(date(2026, 1, 2), -1.0),
        ReplayDay.from_values(date(2026, 1, 3), -1.0),
        ReplayDay.from_values(date(2026, 1, 4), -1.0),
    ]

    result = simulate_lucidflex_trade_replay(
        days,
        sizing_fn=sizing_fn,
        max_eval_days=3,
        max_funded_days=1,
    )

    assert result.eval_days == 3
    assert result.terminal_reason == "eval_breach"
    day1_loss = 1_000.0  # full base risk, buffer_fraction == full_buffer_fraction
    day2_loss = 50_000.0 - day1_loss - 48_375.0  # balance after day 2 close
    day3_loss = abs(result.eval_result.largest_day_profit)  # only losing day, so this is day 3's loss
    assert day2_loss == pytest.approx(625.0)
    assert day3_loss == pytest.approx(390.625)
    # Strictly shrinking per-trade dollar loss as the buffer closes in:
    assert day1_loss > day2_loss > day3_loss
