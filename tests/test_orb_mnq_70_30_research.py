from __future__ import annotations

from datetime import date

import pandas as pd

from Analysis.scripts.orb_mnq_70_30_research import (
    Candidate,
    chronological_split,
    percentile_rank,
    simulate_day,
    summarize_daily,
)


def test_chronological_split_is_strictly_70_30_without_overlap() -> None:
    dates = [date(2026, 1, day) for day in range(1, 11)]
    insample, outsample = chronological_split(dates, 0.70)
    assert len(insample) == 7
    assert len(outsample) == 3
    assert max(insample) < min(outsample)


def test_percentile_rank_places_worst_observation_at_zero() -> None:
    assert percentile_rank(-5.0, [-4.0, -1.0, 2.0]) == 0.0
    assert percentile_rank(3.0, [-4.0, -1.0, 2.0]) == 100.0


def test_summarize_daily_includes_no_trade_sessions_and_drawdown() -> None:
    daily = pd.Series([1.0, 0.0, -2.0, 0.5])
    result = summarize_daily(daily, trade_count=3)
    assert result["sessions"] == 4
    assert result["trades"] == 3
    assert result["total_r"] == -0.5
    assert result["max_drawdown_r"] == 2.0


def test_first_candle_or_close_reference_does_not_use_next_bar_open() -> None:
    index = pd.date_range("2026-01-02 09:30", periods=3, freq="5min", tz="America/New_York")
    day = pd.DataFrame(
        {
            "open": [100.0, 103.0, 103.0],
            "high": [102.0, 104.0, 104.0],
            "low": [99.0, 100.0, 100.0],
            "close": [101.0, 103.0, 103.0],
            "volume": [100.0, 100.0, 100.0],
        },
        index=index,
    )
    feature = pd.Series(
        {"atr_prior": 20.0, "rel_volume": 1.0, "vol_percentile": 0.5, "or_range_atr": 0.15}
    )

    trade = simulate_day(
        day,
        index[0].date(),
        Candidate("corrected", "first_candle", first_candle_reference="or_close"),
        feature,
    )

    assert trade is not None
    assert trade.entry_price == 101.25
