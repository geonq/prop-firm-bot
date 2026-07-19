"""Per-bar mark-to-market daily-loss kill switch tests (reviewer Fix 3, 2026-07-18).

Background: the engine's own TradeClosed event for a stop-hit always reports
the MODELED stop price as the fill (src/live/engine.py's
`fill_price(state.stop_price, ...)`), exactly mirroring
`src.backtest.orb._walk_to_exit`'s "gap-through optimism" convention (see
that module's docstring). That means a bar whose low/high crosses the stop
by a huge margin (a genuine gap-through) still reports a fill AT the stop
price from the engine's point of view -- a realized-P&L-only kill switch
would never see the real damage until (if ever) the engine itself decides to
exit. This is exactly the live-money gap the reviewer flagged: with a large
contract count, a bar that gaps far past the stop can lose far more than the
modeled $400 risk before the engine's own bar-close bookkeeping catches up.

These tests build a small synthetic parquet (same schema as the real
DataLocal file: tz-aware UTC DatetimeIndex, open/high/low/close/volume
columns) with a session engineered to enter long, then gap catastrophically
below the stop on the very next bar, and drive it through the REAL
`run_replay` (not a mocked broker) to prove:
1. The per-bar mark-to-market check (using PaperBroker.unrealized_pnl_usd at
   the bar's close, independent of the engine's own optimistic stop fill)
   catches the loss and flattens/halts BEFORE it grows further.
2. Reverting to a realized-PnL-only check (the pre-fix behavior) lets the
   position ride past the cap unflagged for that bar -- demonstrated
   explicitly by temporarily monkeypatching the mark-to-market path off.
3. A normal at-stop loss (no gap) NEVER trips the cap, matching the
   documented invariant (cap default $600 > $400 risk + slippage buffer).
"""

from __future__ import annotations

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.live import runner as runner_module
from src.live.config import DEFAULT_DAILY_LOSS_CAP_USD, MNQ, RISK_PER_TRADE_USD
from src.live.runner import run_replay

ET = ZoneInfo("America/New_York")


def _et_ts(d: date, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp.combine(d, time(hh, mm)).tz_localize(ET).tz_convert("UTC")


def _build_session_with_gap_through_stop(d: date) -> pd.DataFrame:
    """One RTH session: OR window forms a clean bullish (long) first candle,
    entry fills at 09:35 open, then the very next bar (09:36) GAPS
    catastrophically below the stop -- open/high/low/close all far below the
    OR low -- simulating a violent gap-through. All bars after that stay
    flat so nothing else in the session confuses the picture.

    OR window (09:30-09:34, or_minutes=5): open=100, close=100.5 (bullish,
    body/range=0.5/1.5=0.33 > doji_threshold 0.1 -> long entry), high=101,
    low=99.5. Entry at 09:35 open (=100.5, +1 tick slippage per _fill_price)
    -> long. Stop = or_low = 99.5. risk_points ~= 1.0-ish -> at MNQ $2/pt,
    1 contract's risk is ~$2, so with the default $400 risk budget the
    sizing gate lets in MANY contracts (floor(400/~2) clamped to
    max_contracts=20) -- exactly the "large contract count" scenario the
    reviewer's finding describes, since a tiny OR range sizes up hard.

    Bar 2 (09:36): open=40.0, high=40.0, low=30.0, close=30.0 -- a
    catastrophic ~60-70 point gap-through below the 99.5 stop. The engine's
    own stop-hit fill still reports exit_price ~= 99.5 - 1 tick (the MODELED
    stop, not the real bar), but the bar's REAL close (30.0) implies a much
    larger unrealized loss at mark-to-market than the modeled stop would
    ever report.
    """
    rows: list[dict] = []
    ts = _et_ts(d, 9, 30)

    # OR window: 5 bars, or_open=100.0 (bar0 open), or_close=100.5 (bar4 close),
    # or_high=101.0, or_low=99.5.
    or_rows = [
        {"open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1},
        {"open": 100.1, "high": 101.0, "low": 100.0, "close": 100.8},
        {"open": 100.8, "high": 100.9, "low": 99.5, "close": 100.0},
        {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.2},
        {"open": 100.2, "high": 100.6, "low": 100.1, "close": 100.5},
    ]
    for r in or_rows:
        rows.append({"ts": ts, "volume": 100.0, **r})
        ts += timedelta(minutes=1)

    # Bar at 09:35 (entry bar): open=100.5 (fills the long entry via
    # _fill_price adverse slippage), stays flat otherwise so it doesn't
    # itself trigger stop/target.
    rows.append({"ts": ts, "open": 100.5, "high": 100.6, "low": 100.4, "close": 100.5, "volume": 100.0})
    ts += timedelta(minutes=1)

    # Bar at 09:36: catastrophic gap-through below the stop (99.5).
    rows.append({"ts": ts, "open": 40.0, "high": 40.0, "low": 30.0, "close": 30.0, "volume": 100.0})
    ts += timedelta(minutes=1)

    # Remaining bars flat at 30.0 through end of RTH (09:37 .. 15:59 = 383 more bars).
    session_end = _et_ts(d, 16, 0)
    while ts < session_end:
        rows.append({"ts": ts, "open": 30.0, "high": 30.0, "low": 30.0, "close": 30.0, "volume": 100.0})
        ts += timedelta(minutes=1)

    df = pd.DataFrame(rows).set_index("ts")
    df.index.name = "ts_event"
    return df


def _write_parquet(tmp_path, bars: pd.DataFrame) -> str:
    path = tmp_path / "synthetic.parquet"
    bars.to_parquet(path)
    return str(path)


def test_gap_through_stop_trips_mark_to_market_cap_before_engine_reports_it(tmp_path):
    d = date(2025, 6, 2)  # a Monday, ordinary trading day
    bars = _build_session_with_gap_through_stop(d)
    parquet_path = _write_parquet(tmp_path, bars)
    state_dir = tmp_path / "state"

    trades = run_replay(
        start=str(d),
        end=str(d),
        parquet_path=parquet_path,
        state_dir=state_dir,
        daily_loss_cap_usd=600.0,
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "daily_loss_cap"
    # Flattened at the gap bar's REAL close (30.0), not at the modeled stop
    # price (~99.5) -- proves the mark-to-market check used the actual bar,
    # not the engine's optimistic stop fill.
    assert trade.exit_price == pytest.approx(30.0, abs=1e-9)
    assert trade.pnl_usd < -600.0  # real loss exceeds the cap (cap triggers on breach, doesn't cap the loss itself)

    events_path = state_dir / "events.jsonl"
    assert events_path.exists()
    events_text = events_path.read_text()
    assert "DailyLossCapHit" in events_text
    assert '"exit_reason": "target"' not in events_text  # sanity: this scenario never reaches target


def test_normal_at_stop_loss_never_trips_the_cap(tmp_path):
    """Invariant the reviewer asked to be documented and enforced: a NORMAL
    (non-gap) stop-out, at the default $400 risk budget and $600 cap, must
    never trigger the daily-loss kill switch. Uses the real holdout data's
    first stopped-out session (2025-07-07, from the earlier manual
    verification run: entry 22926.5, stop fill 22976.0, pnl -396.0) as a
    real-world instance, rather than another synthetic fixture.
    """
    from pathlib import Path

    parquet = Path(__file__).resolve().parents[1] / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
    if not parquet.exists():
        pytest.skip("DataLocal parquet not present")

    state_dir = tmp_path / "state"
    trades = run_replay(start="2025-07-07", end="2025-07-07", parquet_path=parquet, state_dir=state_dir)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "stop"
    assert abs(trade.pnl_usd) < DEFAULT_DAILY_LOSS_CAP_USD

    events_text = (state_dir / "events.jsonl").read_text()
    assert "DailyLossCapHit" not in events_text


def test_realized_only_check_would_have_missed_the_gap(tmp_path, monkeypatch):
    """Negative-control regression test: with the mark-to-market check
    disabled (monkeypatched to always report 0 unrealized P&L, simulating
    the PRE-FIX realized-only behavior), the same catastrophic-gap fixture
    must NOT flatten via daily_loss_cap on the gap bar -- proving the
    mark-to-market check (not something else) is what makes the fix work.
    The position instead rides until the engine's own EoD flatten fires
    (since the modeled stop distance is tiny and the loop moves on).
    """
    d = date(2025, 6, 3)
    bars = _build_session_with_gap_through_stop(d)
    parquet_path = _write_parquet(tmp_path, bars)
    state_dir = tmp_path / "state"

    from src.live.broker import PaperBroker

    monkeypatch.setattr(PaperBroker, "unrealized_pnl_usd", lambda self, mark_price: 0.0)

    trades = run_replay(
        start=str(d),
        end=str(d),
        parquet_path=parquet_path,
        state_dir=state_dir,
        daily_loss_cap_usd=600.0,
    )

    assert len(trades) == 1
    trade = trades[0]
    # Without mark-to-market, the daily_loss_cap path is never reached on the
    # gap bar; the engine's own stop-hit logic (modeled stop, not the gap
    # price) determines the exit instead.
    assert trade.exit_reason != "daily_loss_cap"
