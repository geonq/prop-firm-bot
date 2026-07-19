"""Tests for src/live/live_runner.py::run_auto / should_run_today -- self-gating and wait-loop safety."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.live.live_runner import LOCK_FILENAME, ProcessLock, run_auto, should_run_today

ET = ZoneInfo("America/New_York")


def test_should_run_today_false_on_saturday(tmp_path):
    should_run, reason = should_run_today(date(2026, 7, 18), state_dir=tmp_path)  # Saturday
    assert should_run is False
    assert "weekend" in reason


def test_should_run_today_false_on_sunday(tmp_path):
    should_run, reason = should_run_today(date(2026, 7, 19), state_dir=tmp_path)  # Sunday
    assert should_run is False


def test_should_run_today_true_on_weekday_with_no_state(tmp_path):
    should_run, reason = should_run_today(date(2026, 7, 20), state_dir=tmp_path)  # Monday
    assert should_run is True
    assert reason == "ok"


def test_should_run_today_false_when_already_traded(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"session_date": "2026-07-20", "trade_taken": True, "realized_pnl_usd": 0.0, "position": None}))
    should_run, reason = should_run_today(date(2026, 7, 20), state_dir=tmp_path)
    assert should_run is False
    assert "already traded" in reason


def test_should_run_today_true_when_state_is_for_a_different_date(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"session_date": "2026-07-17", "trade_taken": True, "realized_pnl_usd": 0.0, "position": None}))
    should_run, reason = should_run_today(date(2026, 7, 20), state_dir=tmp_path)
    assert should_run is True


def test_run_auto_returns_0_and_prints_skip_reason_on_weekend(tmp_path, capsys):
    code = run_auto(mode="paper", state_dir=tmp_path, now_fn=lambda: datetime(2026, 7, 18, 8, 0, tzinfo=ET))
    assert code == 0
    out = capsys.readouterr().out
    assert "skipping today" in out
    assert "weekend" in out


def test_run_auto_returns_0_when_already_traded(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"session_date": "2026-07-20", "trade_taken": True, "realized_pnl_usd": 0.0, "position": None}))
    code = run_auto(mode="paper", state_dir=tmp_path, now_fn=lambda: datetime(2026, 7, 20, 8, 0, tzinfo=ET))
    assert code == 0
    assert "already traded" in capsys.readouterr().out


class _AdvancingClock:
    """Real advancing fake clock -- sleep() moves time forward, unlike a
    constant lambda (which would spin the wait loop forever)."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += timedelta(seconds=seconds)


def test_run_auto_waits_until_0925_et_then_attempts_session_and_fails_cleanly_without_creds(tmp_path, monkeypatch):
    """No credentials exist in this test environment -- run_auto must wait out
    the clock, THEN attempt the session, THEN fail cleanly (return 1) rather
    than hang or crash uncaught. Also proves the wait loop actually
    terminates with an advancing clock (regression coverage for the
    constant-clock infinite-loop trap found during manual testing).
    """
    monkeypatch.delenv("PROJECTX_USERNAME", raising=False)
    monkeypatch.delenv("PROJECTX_API_KEY", raising=False)
    clock = _AdvancingClock(datetime(2026, 7, 20, 9, 20, tzinfo=ET))  # Monday, 5 min before 09:25
    code = run_auto(mode="paper", state_dir=tmp_path, now_fn=clock.now, sleep_fn=clock.sleep)
    assert code == 1
    assert clock.now() >= datetime(2026, 7, 20, 9, 25, tzinfo=ET)
    assert len(clock.sleep_calls) > 0  # actually waited, not a no-op


def test_run_auto_does_not_wait_if_already_past_0925(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECTX_USERNAME", raising=False)
    monkeypatch.delenv("PROJECTX_API_KEY", raising=False)
    clock = _AdvancingClock(datetime(2026, 7, 20, 10, 0, tzinfo=ET))
    code = run_auto(mode="paper", state_dir=tmp_path, now_fn=clock.now, sleep_fn=clock.sleep)
    assert code == 1
    assert clock.sleep_calls == []  # no waiting needed, already past 09:25


def test_run_auto_wait_loop_gives_up_with_stuck_clock(tmp_path, capsys):
    """Regression test for the infinite-loop trap: if now_fn() NEVER advances
    (a stuck/frozen clock), run_auto must still terminate (via the
    max_wait_iterations safety cap) rather than spin forever.
    """
    frozen_time = datetime(2026, 7, 20, 9, 20, tzinfo=ET)
    code = run_auto(mode="paper", state_dir=tmp_path, now_fn=lambda: frozen_time, sleep_fn=lambda s: None)
    assert code == 1
    err = capsys.readouterr().err
    assert "gave up waiting" in err or "clock may be stuck" in err


# ---------------------------------------------------------------------------
# FIX 1 (reviewer, 2026-07-19, CRITICAL): exclusive process lock prevents a
# launchd double-fire from placing a duplicate entry. See
# src/live/live_runner.py::ProcessLock's docstring for the exact race this
# closes -- should_run_today's weekday/already-traded check alone does NOT
# prevent two processes racing before either has set trade_taken.
# ---------------------------------------------------------------------------


def test_process_lock_acquire_and_release(tmp_path):
    lock = ProcessLock(tmp_path / LOCK_FILENAME)
    assert lock.acquire() is True
    lock.release()
    # Released -> a second acquire (simulating a later, non-overlapping run) succeeds.
    lock2 = ProcessLock(tmp_path / LOCK_FILENAME)
    assert lock2.acquire() is True
    lock2.release()


def test_process_lock_second_acquire_fails_while_first_holds_it(tmp_path):
    lock_path = tmp_path / LOCK_FILENAME
    holder = ProcessLock(lock_path)
    assert holder.acquire() is True
    try:
        contender = ProcessLock(lock_path)
        assert contender.acquire() is False
    finally:
        holder.release()


def test_run_auto_exits_0_and_journals_lock_held_when_lock_already_held(tmp_path, capsys):
    """The actual reviewer-mandated behavior: acquire the lock in the TEST
    process first (simulating a concurrent launchd fire already running),
    then invoke run_auto and assert no session ran -- it must detect the
    held lock, journal LockHeldExit, and exit 0 WITHOUT ever reaching
    should_run_today/the credential/session logic (the weekday gate would
    have been satisfied on a Monday, so if the lock check were missing or
    broken, this test would proceed into session setup and fail differently
    -- e.g. on missing credentials with exit code 1, not 0).

    Revert-proof: temporarily short-circuiting run_auto's lock check (see
    the accompanying manual verification in the report) makes this test
    fail because a weekday with no prior state.json would proceed past
    should_run_today and hit the credential-missing path, returning 1
    instead of 0, and events.jsonl would contain no LockHeldExit record.
    """
    lock_path = tmp_path / LOCK_FILENAME
    external_holder = ProcessLock(lock_path)
    assert external_holder.acquire() is True
    try:
        monday = datetime(2026, 7, 20, 9, 20, tzinfo=ET)  # a weekday, well within a plausible double-fire window
        code = run_auto(mode="paper", state_dir=tmp_path, now_fn=lambda: monday, sleep_fn=lambda s: None)
        assert code == 0

        out = capsys.readouterr().out
        assert "already held by another process" in out

        events_text = (tmp_path / "events.jsonl").read_text()
        assert "LockHeldExit" in events_text

        # No state.json trade_taken flag was ever set -- confirms the session
        # logic (which would set it) never ran.
        state_path = tmp_path / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            assert not state.get("trade_taken")
    finally:
        external_holder.release()


def test_run_auto_releases_lock_on_normal_exit_so_a_later_run_can_acquire_it(tmp_path, monkeypatch):
    """The lock must not leak past process lifetime -- a SUBSEQUENT (not
    concurrent) run_auto call, after the first one has returned, must be
    able to acquire the lock fresh. This is what distinguishes "held for
    process lifetime" from "held forever."
    """
    monkeypatch.delenv("PROJECTX_USERNAME", raising=False)
    monkeypatch.delenv("PROJECTX_API_KEY", raising=False)
    monday = datetime(2026, 7, 20, 9, 20, tzinfo=ET)

    code1 = run_auto(mode="paper", state_dir=tmp_path, now_fn=lambda: monday, sleep_fn=lambda s: None)
    assert code1 == 1  # fails on missing credentials, but that's AFTER the lock was acquired and released

    # Lock must be free again now -- prove it by acquiring it directly.
    lock = ProcessLock(tmp_path / LOCK_FILENAME)
    assert lock.acquire() is True
    lock.release()
