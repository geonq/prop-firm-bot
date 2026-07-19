"""Session-calendar edge cases for the live runner: a DST transition week and a half-day.

Uses real DataLocal bars (not synthetic fixtures) so the actual UTC->ET
zoneinfo conversion and the `min_bar_count=300` half-day drop
(src/backtest/sessions.py) are exercised exactly as production would see
them, not re-approximated.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.orb import run_orb_backtest
from src.live.broker import PaperBroker
from src.live.config import FROZEN_PARAMS, MNQ
from src.live.engine import ORBLiveEngine
from src.live.feed import ReplayFeed

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"

pytestmark = pytest.mark.skipif(not PARQUET.exists(), reason="DataLocal parquet not present")


def _run_engine_over_window(start: str, end: str):
    feed = ReplayFeed(PARQUET, start=start, end=end)
    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)
    broker = PaperBroker(point_value=MNQ.point_value)
    trades = []
    for session in feed.sessions:
        last_bar = None
        for ts, row in session.bars.iterrows():
            from src.live.feed import Bar

            bar = Bar(
                ts=ts,
                session_date=session.session_date,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for ev in engine.on_bar(bar):
                if type(ev).__name__ == "TradeOpened":
                    broker.place_bracket(
                        session_date=ev.session_date,
                        direction=ev.direction,
                        entry_price=ev.entry_price,
                        stop_price=ev.stop_price,
                        target_price=ev.target_price,
                        contracts=1,
                        entry_ts=ev.entry_ts,
                    )
                elif type(ev).__name__ == "TradeClosed":
                    trades.append(broker.close_position(exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason))
            last_bar = bar
        if last_bar is not None:
            for ev in engine.on_session_end(last_bar):
                trades.append(broker.close_position(exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason))
    return feed.sessions, trades


def _reference_trades(start: str, end: str) -> list:
    bars = pd.read_parquet(PARQUET)
    start_utc = pd.Timestamp(start, tz="UTC")
    end_utc = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    window_bars = bars.loc[(bars.index >= start_utc) & (bars.index < end_utc)]
    return run_orb_backtest(window_bars, FROZEN_PARAMS)


def test_dst_spring_forward_week_session_calendar_and_parity():
    """2025-03-09 (spring forward) week: RTH sessions must each have 390 bars
    (09:30-15:59 ET) despite the UTC offset shifting from -05:00 to -04:00
    mid-week, and the live engine's trade list must match the backtest's.
    """
    start, end = "2025-03-10", "2025-03-14"
    sessions, live_trades = _run_engine_over_window(start, end)
    assert [s.session_date for s in sessions] == [
        date(2025, 3, 10),
        date(2025, 3, 11),
        date(2025, 3, 12),
        date(2025, 3, 13),
        date(2025, 3, 14),
    ]
    for s in sessions:
        assert len(s.bars) == 390

    reference = _reference_trades(start, end)
    assert len(live_trades) == len(reference)
    for lt, rt in zip(live_trades, reference):
        assert lt.session_date == rt.session_date
        assert lt.direction == rt.direction
        assert lt.entry_price == pytest.approx(rt.entry_price, abs=1e-9)
        assert lt.exit_price == pytest.approx(rt.exit_price, abs=1e-9)


def test_dst_fall_back_week_session_calendar_and_parity():
    """2025-11-02 (fall back) week: same invariants, offset shifts -04:00 -> -05:00."""
    start, end = "2025-11-03", "2025-11-07"
    sessions, live_trades = _run_engine_over_window(start, end)
    assert [s.session_date for s in sessions] == [
        date(2025, 11, 3),
        date(2025, 11, 4),
        date(2025, 11, 5),
        date(2025, 11, 6),
        date(2025, 11, 7),
    ]
    for s in sessions:
        assert len(s.bars) == 390

    reference = _reference_trades(start, end)
    assert len(live_trades) == len(reference)
    for lt, rt in zip(live_trades, reference):
        assert lt.session_date == rt.session_date
        assert lt.direction == rt.direction
        assert lt.entry_price == pytest.approx(rt.entry_price, abs=1e-9)
        assert lt.exit_price == pytest.approx(rt.exit_price, abs=1e-9)


def test_half_day_is_excluded_from_session_universe():
    """The Friday after Thanksgiving 2025 (2025-11-28) is a documented half-day
    (225 RTH bars < min_bar_count=300) and must be dropped from the session
    universe entirely -- not sessionized as a short day, not silently
    producing a spurious trade. ReplayFeed must agree with build_rth_sessions
    on this (same function, same default min_bar_count).
    """
    feed = ReplayFeed(PARQUET, start="2025-11-24", end="2025-11-29")
    session_dates = {s.session_date for s in feed.sessions}
    assert date(2025, 11, 28) not in session_dates
    # Thanksgiving Thursday itself (2025-11-27) is a full holiday -> no bars at all.
    assert date(2025, 11, 27) not in session_dates
    # The surrounding regular sessions must still be present.
    assert date(2025, 11, 26) in session_dates
    assert date(2025, 11, 24) in session_dates


def test_half_day_window_parity_with_backtest():
    """Even with a half-day inside the window, live engine trades must still
    match the backtest exactly (the half-day contributes zero trades to both,
    since neither traversal ever sees a session for that date).
    """
    start, end = "2025-11-24", "2025-11-29"
    _, live_trades = _run_engine_over_window(start, end)
    reference = _reference_trades(start, end)
    assert len(live_trades) == len(reference)
    for lt, rt in zip(live_trades, reference):
        assert lt.session_date == rt.session_date
        assert lt.direction == rt.direction
        assert lt.entry_price == pytest.approx(rt.entry_price, abs=1e-9)
        assert lt.exit_price == pytest.approx(rt.exit_price, abs=1e-9)
