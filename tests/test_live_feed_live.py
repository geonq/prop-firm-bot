"""Tests for src/live/feed.py::LiveBarFeed -- fake retrieve_bars + controllable clock, no real I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytest

from src.live.feed import ET, LiveBarFeed, LiveFeedSkipDay


@dataclass
class _RawBar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: int


class FakeClock:
    """Controllable now()/sleep(): sleep() advances the clock instead of blocking."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now = self._now + timedelta(seconds=seconds)

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


class FakeBarSource:
    """bars_by_minute: {datetime (minute start, ET): _RawBar}. Missing minutes return []."""

    def __init__(self, bars_by_minute: dict[datetime, _RawBar]) -> None:
        self.bars_by_minute = bars_by_minute
        self.calls: list[tuple] = []

    def __call__(self, contract_id: str, **kwargs) -> list:
        self.calls.append((contract_id, kwargs))
        start = datetime.fromisoformat(kwargs["start_time"])
        bar = self.bars_by_minute.get(start)
        return [bar] if bar is not None else []


def _minute(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=ET)


def _bar_at(d: date, hh: int, mm: int, *, o=100.0, h=101.0, l=99.0, c=100.5, v=10) -> _RawBar:
    ts = _minute(d, hh, mm)
    return _RawBar(t=ts.isoformat(), o=o, h=h, l=l, c=c, v=v)


def _full_session_bars(d: date, *, n_bars: int = 130) -> dict[datetime, _RawBar]:
    """09:30 through 09:30+n_bars-1 minutes, all present, flat OHLC."""
    bars = {}
    for i in range(n_bars):
        m = _minute(d, 9, 30) + timedelta(minutes=i)
        bars[m] = _RawBar(t=m.isoformat(), o=100.0, h=100.5, l=99.5, c=100.0, v=10)
    return bars


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_yields_bars_in_order_for_a_full_session_slice():
    d = date(2026, 7, 20)  # a Monday
    source = FakeBarSource(_full_session_bars(d, n_bars=15))
    clock = FakeClock(_minute(d, 9, 25))

    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="CON.F.US.MNQ.U25", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 45),
    )
    bars = list(feed)
    assert [b.ts.time() for b in bars] == [time(9, 30 + i) for i in range(15)]
    assert feed.max_timestamp_served == bars[-1].ts


def test_polls_with_delay_after_minute_boundary():
    d = date(2026, 7, 20)
    source = FakeBarSource(_full_session_bars(d, n_bars=2))
    clock = FakeClock(_minute(d, 9, 29, ))
    clock._now = _minute(d, 9, 29)

    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 33), poll_delay_seconds=2.0,
    )
    list(feed)
    # first bar (09:30) polled at 09:31:02 (target_boundary=09:31 + 2s delay)
    assert clock._now >= _minute(d, 9, 31) + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# late bar tolerance
# ---------------------------------------------------------------------------


def test_late_bar_appears_after_retries_within_tolerance():
    d = date(2026, 7, 20)
    late_minute = _minute(d, 9, 31)
    bars = _full_session_bars(d, n_bars=5)

    call_count = {"n": 0}
    original_source = FakeBarSource(bars)

    def flaky_source(contract_id, **kwargs):
        start = datetime.fromisoformat(kwargs["start_time"])
        if start == late_minute:
            call_count["n"] += 1
            if call_count["n"] < 3:
                return []  # not there yet, first two polls
        return original_source(contract_id, **kwargs)

    clock = FakeClock(_minute(d, 9, 25))
    late_events = []
    feed = LiveBarFeed(
        retrieve_bars=flaky_source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 35), on_late_bar=late_events.append,
        late_bar_retry_seconds=30.0, poll_retry_interval_seconds=2.0,
    )
    served = list(feed)
    assert late_minute in [b.ts.to_pydatetime().replace(tzinfo=ET) for b in served]
    assert late_events == []  # eventually succeeded, no late-bar journal needed


def test_late_bar_exhausts_retry_budget_and_reports_via_on_late_bar():
    d = date(2026, 7, 20)
    missing_minute = _minute(d, 9, 32)
    bars = _full_session_bars(d, n_bars=7)  # covers 09:30..09:36 so window_end_et=9:37 has no OTHER gaps
    del bars[missing_minute]  # this minute's bar NEVER shows up
    source = FakeBarSource(bars)

    clock = FakeClock(_minute(d, 9, 25))
    late_events = []
    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 37), on_late_bar=late_events.append,
        late_bar_retry_seconds=10.0, poll_retry_interval_seconds=2.0,
    )
    served = list(feed)
    served_minutes = [b.ts.time() for b in served]
    assert time(9, 32) not in served_minutes  # skipped, never served
    assert time(9, 33) in served_minutes  # feed moves on to the next minute
    assert len(late_events) == 1
    assert "09:32" in late_events[0]


# ---------------------------------------------------------------------------
# missing OR window -> skip day
# ---------------------------------------------------------------------------


def test_or_window_incomplete_by_deadline_raises_skip_day():
    d = date(2026, 7, 20)
    bars = _full_session_bars(d, n_bars=10)
    # 09:32 bar never arrives. Polling for it starts at 09:33:02 (target_boundary
    # 09:33 + 2s poll_delay); a 150s retry budget exhausts at 09:35:32, which is
    # PAST the 09:35:30 OR-window deadline -- this is what must trigger the skip.
    del bars[_minute(d, 9, 32)]
    source = FakeBarSource(bars)

    clock = FakeClock(_minute(d, 9, 25))
    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 45), or_minutes=5, or_window_deadline_et=time(9, 35, 30),
        late_bar_retry_seconds=150.0, poll_retry_interval_seconds=2.0,
    )
    with pytest.raises(LiveFeedSkipDay) as exc_info:
        list(feed)
    assert exc_info.value.session_date == d
    assert "09:32" in str(exc_info.value) or "OR window" in str(exc_info.value)


def test_or_window_complete_by_deadline_does_not_raise():
    d = date(2026, 7, 20)
    source = FakeBarSource(_full_session_bars(d, n_bars=10))
    clock = FakeClock(_minute(d, 9, 25))
    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 40), or_minutes=5, or_window_deadline_et=time(9, 35, 30),
    )
    served = list(feed)  # must not raise
    assert len(served) == 10


def test_missing_bar_after_or_window_does_not_trigger_skip_day():
    """The skip-day policy is specifically about the OR window (09:30-09:35) --
    a missing bar LATER in the session (e.g. 10:15) must not abort the whole feed.
    """
    d = date(2026, 7, 20)
    bars = _full_session_bars(d, n_bars=20)
    del bars[_minute(d, 9, 45)]
    source = FakeBarSource(bars)
    clock = FakeClock(_minute(d, 9, 25))
    feed = LiveBarFeed(
        retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep,
        window_end_et=time(9, 50), or_minutes=5, or_window_deadline_et=time(9, 35, 30),
        late_bar_retry_seconds=1.0, poll_retry_interval_seconds=0.5,
    )
    served = list(feed)  # must not raise
    served_minutes = {b.ts.time() for b in served}
    assert time(9, 45) not in served_minutes
    assert time(9, 46) in served_minutes


# ---------------------------------------------------------------------------
# window guard
# ---------------------------------------------------------------------------


def test_starting_feed_outside_polling_window_raises_skip_day():
    d = date(2026, 7, 20)
    source = FakeBarSource(_full_session_bars(d, n_bars=5))
    clock = FakeClock(_minute(d, 12, 0))  # way past window_end_et default (11:40)
    feed = LiveBarFeed(retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep)
    with pytest.raises(LiveFeedSkipDay):
        list(feed)


# ---------------------------------------------------------------------------
# clock skew check
# ---------------------------------------------------------------------------


def test_clock_skew_check_returns_seconds_of_skew():
    d = date(2026, 7, 20)
    bar_minute = _minute(d, 9, 34)
    bars = {bar_minute: _RawBar(t=bar_minute.isoformat(), o=1, h=1, l=1, c=1, v=1)}

    def source(contract_id, **kwargs):
        return list(bars.values())

    clock = FakeClock(_minute(d, 9, 35, ) )
    clock._now = _minute(d, 9, 35) + timedelta(seconds=3)
    feed = LiveBarFeed(retrieve_bars=source, contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep)
    skew = feed.clock_skew_check()
    assert skew is not None
    assert skew > 0  # local clock is ahead of the bar's own timestamp, as expected


def test_clock_skew_check_returns_none_when_no_bars():
    d = date(2026, 7, 20)
    clock = FakeClock(_minute(d, 9, 35))
    feed = LiveBarFeed(retrieve_bars=lambda *a, **k: [], contract_id="C", session_date=d, now=clock.now, sleep=clock.sleep)
    assert feed.clock_skew_check() is None
