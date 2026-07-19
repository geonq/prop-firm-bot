"""Slice a UTC 1-min bar DataFrame into America/New_York RTH sessions.

No hardcoded DST offsets: all UTC->ET conversion goes through `zoneinfo`, so
the spring-forward / fall-back transition is handled by the tz database, not
by an assumed fixed offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class Session:
    """One RTH session's bars, indexed by ET-local timestamp."""

    session_date: date
    bars: pd.DataFrame

    def __post_init__(self) -> None:
        if self.bars.empty:
            raise ValueError("Session bars must not be empty")


def validate_bars(bars: pd.DataFrame) -> None:
    """Empty/NaN/dtype/monotonic checks on the raw OHLCV frame before use."""
    if bars.empty:
        raise ValueError("bars is empty")
    required = ("open", "high", "low", "close", "volume")
    missing = [c for c in required if c not in bars.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {missing}")
    for col in required:
        if not pd.api.types.is_numeric_dtype(bars[col]):
            raise TypeError(f"column {col!r} must be numeric, got {bars[col].dtype}")
    if bars[list(required)].isna().any().any():
        raise ValueError("bars contains NaN values in OHLCV columns")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise TypeError("bars.index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("bars.index must be tz-aware (UTC)")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("bars.index must be monotonically increasing")


def build_rth_sessions(
    bars: pd.DataFrame,
    *,
    exclude_dates: frozenset[date] = frozenset(
        {
            date(2017, 11, 13),
            date(2018, 10, 21),
            date(2019, 1, 15),
            date(2020, 2, 27),
            date(2020, 2, 28),
            date(2020, 6, 30),
        }
    ),
    min_bar_count: int = 300,
) -> list[Session]:
    """Convert UTC bars to ET, slice the 09:30-16:00 RTH window, group by day.

    Tolerates holidays/half-days: a session is whatever bars exist in the
    window on that calendar date. Sessions with fewer than `min_bar_count`
    bars are dropped (half-days, data gaps, degraded days not caught by
    `exclude_dates`). `exclude_dates` are ET calendar dates, checked before
    the RTH slice.

    Modeling consequence of the `min_bar_count=300` default: US equity-index
    early-close half-days (e.g. the Friday after Thanksgiving, July 3rd when
    it falls on a weekday) have far fewer than 391 RTH minutes and are
    dropped entirely rather than sessionized as short days. This removes
    roughly 4-5 sessions per year from the backtest universe. That is an
    accepted modeling choice (thin, atypical liquidity on those days), not a
    bug — do not "fix" it by lowering the default without deciding the
    tradeoff explicitly.
    """
    validate_bars(bars)

    et_index = bars.index.tz_convert(ET)
    et_bars = bars.copy()
    et_bars.index = et_index

    session_dates = pd.Index(et_index.normalize().unique())
    sessions: list[Session] = []
    for ts in sorted(session_dates):
        session_date = ts.date()
        if session_date in exclude_dates:
            continue
        day_start = pd.Timestamp.combine(session_date, RTH_OPEN).tz_localize(ET)
        day_end = pd.Timestamp.combine(session_date, RTH_CLOSE).tz_localize(ET)
        day_bars = et_bars.loc[(et_bars.index >= day_start) & (et_bars.index < day_end)]
        if len(day_bars) < min_bar_count:
            continue
        sessions.append(Session(session_date=session_date, bars=day_bars))
    return sessions
