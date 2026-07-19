"""Bar feed abstraction: something that yields completed 1-minute bars, one at a time.

`ReplayFeed` streams historical bars from the DataLocal parquet for a date
range, session-sliced the same way the backtester is (`build_rth_sessions`,
same default `exclude_dates`), so the parity test walks the identical
session universe the backtester would see.

`LiveBarFeed` (Phase 6B) streams REAL bars via `ProjectXClient.retrieve_bars`
polling -- see its own docstring below for the full poll-cadence / late-bar /
missing-OR-window policy. Both implement the same `BarFeed` protocol so
`src/live/engine.py` never needs to know which one it's fed by.

Incremental contract: `ReplayFeed.__iter__` yields bars strictly in
timestamp order, one at a time, and never exposes anything the consumer
hasn't been handed yet. `max_timestamp_served` lets tests assert the engine
never made a decision using information from a bar it had not yet been
served (see tests/test_live_parity.py).
"""

from __future__ import annotations

import time as _time_module
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterator, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from src.backtest.sessions import ET, Session, build_rth_sessions


@dataclass(frozen=True)
class Bar:
    """One completed 1-minute bar, ET-localized timestamp."""

    ts: pd.Timestamp
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarFeed(Protocol):
    """Anything that can stream completed bars, one at a time, in order."""

    def __iter__(self) -> Iterator[Bar]: ...

    @property
    def max_timestamp_served(self) -> pd.Timestamp | None:
        """Timestamp of the most recent bar yielded so far, or None before iteration starts."""
        ...


class ReplayFeed:
    """Streams RTH-session bars from a DataLocal parquet file for [start, end)."""

    def __init__(
        self,
        parquet_path: str | Path,
        *,
        start: str | date,
        end: str | date,
        exclude_dates: frozenset[date] | None = None,
        min_bar_count: int = 300,
    ) -> None:
        self._parquet_path = Path(parquet_path)
        start_date = pd.Timestamp(start).date()
        end_date = pd.Timestamp(end).date()

        bars = pd.read_parquet(self._parquet_path)
        # Pre-filter to a generous UTC window around [start_date, end_date] before
        # session-building: a session's RTH bars are always on the SAME UTC
        # calendar date as its ET session_date or the day after (ET is behind
        # UTC), so one extra day of padding on each side is always sufficient
        # and never drops a bar build_rth_sessions would have kept. This is a
        # pure performance optimization (avoids re-sessionizing the full ~10
        # years of history for a one-day replay window) — the post-filter below
        # still exists and enforces exact date bounds either way.
        window_start_utc = pd.Timestamp(start_date, tz="UTC") - pd.Timedelta(days=1)
        window_end_utc = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=2)
        bars = bars.loc[(bars.index >= window_start_utc) & (bars.index < window_end_utc)]

        kwargs: dict[str, object] = {"min_bar_count": min_bar_count}
        if exclude_dates is not None:
            kwargs["exclude_dates"] = exclude_dates
        all_sessions = build_rth_sessions(bars, **kwargs)

        self.sessions: list[Session] = [
            s for s in all_sessions if start_date <= s.session_date <= end_date
        ]
        self._max_timestamp_served: pd.Timestamp | None = None

    @property
    def max_timestamp_served(self) -> pd.Timestamp | None:
        return self._max_timestamp_served

    def __iter__(self) -> Iterator[Bar]:
        for session in self.sessions:
            for ts, row in session.bars.iterrows():
                bar = Bar(
                    ts=ts,
                    session_date=session.session_date,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                self._max_timestamp_served = ts
                yield bar


FEED_WINDOW_START_ET = time(9, 25)
FEED_WINDOW_END_ET = time(11, 40)
POLL_DELAY_AFTER_MINUTE_SECONDS = 2.0
DEFAULT_LATE_BAR_RETRY_SECONDS = 30.0
DEFAULT_POLL_RETRY_INTERVAL_SECONDS = 2.0
OR_WINDOW_DEADLINE_ET = time(9, 35, 30)  # per spec: OR (09:30-09:35) incomplete by this time -> skip the day


class LiveFeedSkipDay(RuntimeError):
    """Raised when the OR window (09:30-09:35 ET) is not fully available by
    09:35:30 ET -- the documented "safe failure mode" (skip the day, no
    trade) rather than trading on a stale/incomplete OR. Carries the
    session_date being skipped and the reason so the runner can journal it.
    """

    def __init__(self, session_date: date, reason: str) -> None:
        super().__init__(f"{session_date}: {reason}")
        self.session_date = session_date
        self.reason = reason


class RetrieveBarsFn(Protocol):
    """Callable shape LiveBarFeed needs from a ProjectXClient (or a fake for tests):
    `retrieve_bars(contract_id, start_time=..., end_time=..., unit=..., unit_number=...,
    limit=..., include_partial_bar=...)  -> list[objects with .t/.o/.h/.l/.c/.v]`.
    Kept as a narrow Protocol (not a direct ProjectXClient type import) so
    tests can pass a trivial fake without constructing a real client.
    """

    def __call__(self, contract_id: str, **kwargs) -> list: ...


@dataclass
class LiveBarFeed:
    """Polls ProjectX's retrieveBars for completed 1-minute bars during the RTH open.

    Poll cadence (spec, Tasks/todo.md "Phase 6B"): once per minute, ~2s
    after the minute boundary (`POLL_DELAY_AFTER_MINUTE_SECONDS`), only
    within `FEED_WINDOW_START_ET`..`FEED_WINDOW_END_ET` (09:25-11:40 ET --
    wide enough to cover the OR window, the 120-minute time-stop, and a
    comfortable margin, without polling all day for a strategy that only
    ever trades in the first couple hours).

    Late-bar tolerance: if the expected bar for a given minute is not yet
    present in the API's response (e.g. the exchange/gateway lags), this
    retries every `DEFAULT_POLL_RETRY_INTERVAL_SECONDS` up to
    `DEFAULT_LATE_BAR_RETRY_SECONDS` total before giving up on that specific
    minute and moving on (a genuinely missing bar is journaled via
    `on_late_bar`, not silently skipped without a trace).

    Missing-OR-window policy (spec, load-bearing for the no-trade-is-safe
    contract): if by `OR_WINDOW_DEADLINE_ET` (09:35:30) the feed has not
    been able to serve all 5 of the OR window's bars (09:30-09:34), this
    raises `LiveFeedSkipDay` rather than ever handing the engine a partial
    or synthetic OR window -- the caller (runner `--auto`/`--mode
    paper|live`) journals the reason and does not trade today. This mirrors
    the backtester's own conservative defaults elsewhere in this project
    (e.g. src/backtest/regime.py's NaN-blocks-the-trade convention) --
    incomplete information is always treated as "no trade," never as
    permission to trade on a best guess.

    `on_wait_tick` (reviewer Fix 6, 2026-07-19, OPS): called roughly once
    per second while waiting for the next minute's bar (via `_wait_until`).
    `src/live/live_runner.py` uses this to poll the LiveBroker's OCO status
    every ~10s instead of only once per bar -- a bar only arrives once per
    minute, but a real stop/target fill can happen at any moment and the
    runner should notice sooner than 60s later. Defaults to a no-op so
    ReplayFeed-equivalent usage (or any caller that doesn't need this) pays
    nothing extra.

    Clock sanity: `clock_skew_check(server_time_iso)` compares the local
    machine clock against a server timestamp IF the docs exposed one to
    check against. UNVERIFIED (see src/live/projectx.py module docstring):
    no fetched ProjectX Gateway doc page returns a server-time field on any
    endpoint checked (Auth/loginKey, Account/search, History/retrieveBars
    all return only success/errorCode/errorMessage plus their own payload,
    never a timestamp of "now" on the server). This class exposes
    `clock_skew_check` as a best-effort hook using the LATEST BAR's own `t`
    timestamp as a proxy for server time (a real bar's timestamp cannot be
    later than the server's own clock) -- flagged as an approximation, not
    a true clock-sync check, in its own docstring.
    """

    retrieve_bars: RetrieveBarsFn
    contract_id: str
    session_date: date
    now: Callable[[], datetime] = field(default=lambda: datetime.now(ET))
    sleep: Callable[[float], None] = _time_module.sleep
    on_late_bar: Callable[[str], None] = field(default=lambda msg: None)
    on_wait_tick: Callable[[], None] = field(default=lambda: None)
    poll_delay_seconds: float = POLL_DELAY_AFTER_MINUTE_SECONDS
    late_bar_retry_seconds: float = DEFAULT_LATE_BAR_RETRY_SECONDS
    poll_retry_interval_seconds: float = DEFAULT_POLL_RETRY_INTERVAL_SECONDS
    window_start_et: time = FEED_WINDOW_START_ET
    window_end_et: time = FEED_WINDOW_END_ET
    or_window_deadline_et: time = OR_WINDOW_DEADLINE_ET
    or_minutes: int = 5

    _max_timestamp_served: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _served_minutes: set = field(default_factory=set, init=False, repr=False)

    @property
    def max_timestamp_served(self) -> pd.Timestamp | None:
        return self._max_timestamp_served

    def clock_skew_check(self, *, max_skew_seconds: float = 5.0) -> float | None:
        """Best-effort local-clock-vs-exchange-data sanity check (see class docstring).

        Fetches the most recent 1 completed minute bar and compares its
        timestamp to the local clock's current minute. Returns the skew in
        seconds (local_now - bar_ts, expected to be small and positive
        since the bar is always at least ~1 poll-interval old), or None if
        no bars were returned (e.g. outside RTH). Does not raise on its
        own -- callers (--preflight) decide what skew is acceptable.
        """
        now = self.now()
        end = now
        start = end - timedelta(minutes=5)
        bars = self.retrieve_bars(
            self.contract_id,
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            unit=2,
            unit_number=1,
            limit=5,
            include_partial_bar=False,
        )
        if not bars:
            return None
        latest = max(bars, key=lambda b: b.t)
        bar_ts = pd.Timestamp(latest.t)
        skew = (pd.Timestamp(now) - bar_ts).total_seconds()
        return skew

    def _in_window(self, now: datetime) -> bool:
        """True if `now` (any tz-aware datetime) falls within the configured
        polling window (09:25-11:40 ET by default). Used as a startup guard
        in `__iter__` -- the loop itself only ever waits/polls between 09:30
        and `window_end_et` (the actual RTH session the engine trades), but
        the runner must not have STARTED this feed before `window_start_et`
        either (per spec: "poll cadence ... during 09:25-11:40 ET window").
        """
        now_et = now.astimezone(ET)
        t = now_et.timetz().replace(tzinfo=None)
        return self.window_start_et <= t <= self.window_end_et

    def _fetch_minute_bar(self, minute_start: datetime) -> Bar | None:
        """Poll for the single completed bar starting at `minute_start` (ET)."""
        minute_end = minute_start + timedelta(minutes=1)
        raw_bars = self.retrieve_bars(
            self.contract_id,
            start_time=minute_start.isoformat(),
            end_time=minute_end.isoformat(),
            unit=2,
            unit_number=1,
            limit=5,
            include_partial_bar=False,
        )
        matches = [b for b in raw_bars if self._same_minute(b.t, minute_start)]
        if not matches:
            return None
        raw = matches[0]
        return Bar(
            ts=pd.Timestamp(minute_start),
            session_date=self.session_date,
            open=float(raw.o),
            high=float(raw.h),
            low=float(raw.l),
            close=float(raw.c),
            volume=float(raw.v),
        )

    @staticmethod
    def _same_minute(raw_ts: str, minute_start: datetime) -> bool:
        ts = pd.Timestamp(raw_ts)
        ts_et = ts.tz_convert(ET) if ts.tzinfo is not None else ts.tz_localize("UTC").tz_convert(ET)
        target = pd.Timestamp(minute_start)
        target_et = target.tz_convert(ET) if target.tzinfo is not None else target.tz_localize(ET)
        return ts_et.replace(second=0, microsecond=0) == target_et.replace(second=0, microsecond=0)

    def __iter__(self) -> Iterator[Bar]:
        if not self._in_window(self.now()):
            raise LiveFeedSkipDay(
                self.session_date,
                f"feed started outside the {self.window_start_et}-{self.window_end_et} ET polling window "
                f"(now={self.now()})",
            )
        session_start = datetime.combine(self.session_date, time(9, 30), tzinfo=ET)
        minute = session_start
        or_window_end = session_start + timedelta(minutes=self.or_minutes)
        or_deadline = datetime.combine(self.session_date, self.or_window_deadline_et, tzinfo=ET)
        window_end = datetime.combine(self.session_date, self.window_end_et, tzinfo=ET)

        while minute < window_end:
            target_boundary = minute + timedelta(minutes=1)
            self._wait_until(target_boundary + timedelta(seconds=self.poll_delay_seconds))

            bar = self._poll_with_late_tolerance(minute)

            if bar is None:
                if minute < or_window_end and self.now() >= or_deadline:
                    raise LiveFeedSkipDay(
                        self.session_date,
                        f"OR window bar for {minute.time()} ET not available by {self.or_window_deadline_et} ET deadline",
                    )
                minute = target_boundary
                continue

            self._max_timestamp_served = bar.ts
            self._served_minutes.add(minute)
            yield bar
            minute = target_boundary

    def _poll_with_late_tolerance(self, minute: datetime) -> Bar | None:
        deadline = self.now() + timedelta(seconds=self.late_bar_retry_seconds)
        while True:
            bar = self._fetch_minute_bar(minute)
            if bar is not None:
                return bar
            if self.now() >= deadline:
                self.on_late_bar(f"bar for {minute.time()} ET not available after {self.late_bar_retry_seconds}s of retries")
                return None
            self.sleep(self.poll_retry_interval_seconds)

    def _wait_until(self, target: datetime) -> None:
        """Sleeps in <=1s increments until `target`, calling `on_wait_tick()`
        (reviewer Fix 6, 2026-07-19, OPS) once per iteration -- this is the
        hook `src/live/live_runner.py` uses to poll OCO status every ~10s
        WHILE waiting for the next bar, instead of only once per bar
        (once/minute), without this feed needing to know anything about
        OCO/orders/brokers itself.
        """
        while True:
            now = self.now()
            if now >= target:
                return
            self.on_wait_tick()
            remaining = (target - now).total_seconds()
            self.sleep(min(remaining, 1.0))
