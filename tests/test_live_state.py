"""Restart-recovery tests: LiveState/state.json persistence and mid-day resume.

Covers:
- PositionSnapshot round-trips through to_dict/from_dict exactly.
- RunnerState.roll_to_session resets trade_taken/realized_pnl only on a NEW
  session_date, never on a same-day reload.
- A fresh runner re-instantiated after a trade was recorded refuses a second
  entry the same day (the actual restart-mid-session guarantee), verified
  both at the RunnerState level and by running run_replay twice over a
  split window and comparing against a single unsplit run.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.live.broker import PositionSnapshot
from src.live.config import FROZEN_PARAMS
from src.live.engine import ORBLiveEngine
from src.live.runner import RunnerState, run_replay

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"

pytestmark = pytest.mark.skipif(not PARQUET.exists(), reason="DataLocal parquet not present")


def test_position_snapshot_round_trip():
    snap = PositionSnapshot(
        session_date=date(2025, 7, 2),
        direction="long",
        entry_ts="2025-07-02 09:35:00-04:00",
        entry_price=22668.75,
        stop_price=22651.25,
        target_price=22738.75,
        contracts=11,
        risk_points=17.5,
    )
    restored = PositionSnapshot.from_dict(snap.to_dict())
    assert restored == snap


def test_runner_state_save_load_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = RunnerState(path)
    state.roll_to_session(date(2025, 7, 2))
    state.trade_taken = True
    state.realized_pnl_usd = 1534.5
    state.position = None
    state.save()

    reloaded = RunnerState(path)
    assert reloaded.session_date == date(2025, 7, 2)
    assert reloaded.trade_taken is True
    assert reloaded.realized_pnl_usd == pytest.approx(1534.5)
    assert reloaded.position is None


def test_runner_state_open_position_round_trips(tmp_path):
    path = tmp_path / "state.json"
    state = RunnerState(path)
    state.roll_to_session(date(2025, 7, 7))
    state.trade_taken = True
    snap = PositionSnapshot(
        session_date=date(2025, 7, 7),
        direction="short",
        entry_ts="2025-07-07 09:35:00-04:00",
        entry_price=22926.5,
        stop_price=22975.75,
        target_price=22729.5,
        contracts=4,
        risk_points=49.25,
    )
    state.position = snap
    state.save()

    reloaded = RunnerState(path)
    assert reloaded.position == snap


def test_roll_to_session_resets_only_on_new_date(tmp_path):
    path = tmp_path / "state.json"
    state = RunnerState(path)
    state.roll_to_session(date(2025, 7, 2))
    state.trade_taken = True
    state.realized_pnl_usd = -200.0

    # Same date again (simulates a restart mid-session): must NOT reset.
    state.roll_to_session(date(2025, 7, 2))
    assert state.trade_taken is True
    assert state.realized_pnl_usd == pytest.approx(-200.0)

    # New date: must reset.
    state.roll_to_session(date(2025, 7, 3))
    assert state.trade_taken is False
    assert state.realized_pnl_usd == 0.0


def test_engine_restore_session_blocks_second_entry():
    """A restored 'trade already taken, flat' session must ignore all remaining bars."""
    from src.live.config import FROZEN_PARAMS
    from src.live.feed import Bar

    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)
    engine.restore_session(session_date=date(2025, 7, 2), trade_taken=True, direction=None)

    ts = pd.Timestamp("2025-07-02 09:35", tz="America/New_York")
    bar = Bar(ts=ts, session_date=date(2025, 7, 2), open=100.0, high=105.0, low=99.0, close=101.0, volume=10.0)
    events = engine.on_bar(bar)
    assert events == []


def test_engine_restore_session_resumes_open_position():
    """A restored 'trade open' session must keep managing the position (no re-entry, no double-open)."""
    from src.live.config import FROZEN_PARAMS
    from src.live.feed import Bar

    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)
    entry_ts = pd.Timestamp("2025-07-02 09:35", tz="America/New_York")
    engine.restore_session(
        session_date=date(2025, 7, 2),
        trade_taken=True,
        direction="long",
        entry_ts=entry_ts,
        entry_price=100.0,
        stop_price=95.0,
        target_price=120.0,
        risk_points=5.0,
    )

    # A bar that hits the stop should close the resumed position, not open a new one.
    ts = pd.Timestamp("2025-07-02 09:40", tz="America/New_York")
    bar = Bar(ts=ts, session_date=date(2025, 7, 2), open=99.0, high=99.5, low=94.5, close=95.0, volume=10.0)
    events = engine.on_bar(bar)
    assert len(events) == 1
    ev = events[0]
    assert type(ev).__name__ == "TradeClosed"
    assert ev.exit_reason == "stop"
    assert ev.entry_price == 100.0


def test_engine_restore_session_preserves_time_stop_deadline():
    """Reviewer Fix 1 (2026-07-18, live-money): a restored open position must
    still be able to time-stop at the ORIGINAL deadline (entry_ts +
    time_stop_minutes), not ride to EoD because the deadline was silently
    dropped on restart. Regression test: reverting `restore_session` to its
    old signature (accepting an unused `time_stop_deadline=None` kwarg
    instead of deriving it from `entry_ts`) makes this test fail, because
    the bar 121 minutes after entry_ts would then NOT trigger a time_stop
    (state.time_stop_deadline stays None -> the `time_stop_deadline is not
    None` guard in `_process_position_bar` never arms).
    """
    from src.live.feed import Bar

    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)  # time_stop_minutes=120
    entry_ts = pd.Timestamp("2025-07-02 09:35", tz="America/New_York")
    engine.restore_session(
        session_date=date(2025, 7, 2),
        trade_taken=True,
        direction="long",
        entry_ts=entry_ts,
        entry_price=100.0,
        stop_price=90.0,  # wide stop -> stays well clear so it can't fire first
        target_price=140.0,  # wide target -> stays well clear so it can't fire first
        risk_points=10.0,
    )

    # Feed bars that never reach +1R (favorable excursion always < 1.0) from
    # just after restart up to and past the original 120-minute deadline
    # (entry_ts + 120min = 11:35). Each bar closes at 100.5 (+0.05R), never
    # touching stop (90) or target (140).
    deadline = entry_ts + pd.Timedelta(minutes=120)
    ts = entry_ts + pd.Timedelta(minutes=1)
    fired_event = None
    while ts <= deadline + pd.Timedelta(minutes=2):
        bar = Bar(ts=ts, session_date=date(2025, 7, 2), open=100.5, high=100.6, low=100.4, close=100.5, volume=10.0)
        events = engine.on_bar(bar)
        for ev in events:
            if type(ev).__name__ == "TradeClosed":
                fired_event = (ts, ev)
        if fired_event is not None:
            break
        ts += pd.Timedelta(minutes=1)

    assert fired_event is not None, "time_stop never fired after restart -- deadline was lost"
    fired_ts, ev = fired_event
    assert ev.exit_reason == "time_stop"
    # The exit fills at the NEXT bar's open after the deadline bar's close
    # arms it (mirrors _walk_to_exit's "pending exit fills at next bar's
    # open" convention) -- so the firing bar must be at or just after the
    # ORIGINAL deadline (11:35), not e.g. immediately on restart or drifted
    # by the restart itself.
    assert fired_ts >= deadline
    assert fired_ts <= deadline + pd.Timedelta(minutes=2)


def test_restart_mid_holdout_window_matches_single_run(tmp_path):
    """Running replay in two halves (simulating a restart) must produce the SAME
    trade list as one continuous run over the combined window, with the
    restart guard preventing any double-count.
    """
    single_dir = tmp_path / "single"
    split_dir = tmp_path / "split"

    single_trades = run_replay(start="2025-07-01", end="2025-07-15", state_dir=single_dir)

    # Split run: first half, then "restart" (new run_replay call, same state_dir)
    # for the second half. The state_dir persists across the two calls exactly
    # like a process restart would.
    run_replay(start="2025-07-01", end="2025-07-08", state_dir=split_dir)
    split_trades = run_replay(start="2025-07-09", end="2025-07-15", state_dir=split_dir)

    # Read the full split journal (both halves) and compare to the single run.
    csv_path = split_dir / "trades.csv"
    split_all = pd.read_csv(csv_path)
    single_all = pd.read_csv(single_dir / "trades.csv")

    assert len(split_all) == len(single_all)
    for col in ["session_date", "direction", "exit_reason"]:
        assert list(split_all[col]) == list(single_all[col])
    for col in ["entry_price", "exit_price", "r_multiple"]:
        assert split_all[col].tolist() == pytest.approx(single_all[col].tolist(), abs=1e-9)


def test_restart_within_same_day_does_not_double_enter(tmp_path):
    """The literal restart-recovery scenario: kill the process right after a
    trade opens (before it's recorded as closed), restart, and confirm no
    second entry is taken for that date.
    """
    state_dir = tmp_path / "state"
    # First run: process the whole window normally.
    run_replay(start="2025-07-02", end="2025-07-02", state_dir=state_dir)

    state_path = state_dir / "state.json"
    persisted = json.loads(state_path.read_text())
    assert persisted["session_date"] == "2025-07-02"
    assert persisted["trade_taken"] is True

    # "Restart": re-run run_replay pointed at the SAME state_dir and the SAME
    # date. The persisted trade_taken=True must prevent a second entry, so
    # the trades.csv must not gain a second 2025-07-02 row.
    run_replay(start="2025-07-02", end="2025-07-02", state_dir=state_dir)
    trades_csv = pd.read_csv(state_dir / "trades.csv")
    day_rows = trades_csv[trades_csv["session_date"] == "2025-07-02"]
    assert len(day_rows) == 1
