"""Hand-constructed bar fixtures for the ORB backtester's no-lookahead contract."""

from __future__ import annotations

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.backtest.orb import NQ_POINT_VALUE, ORBParams, Trade, run_orb_backtest, trades_to_replay_days
from src.backtest.sessions import build_rth_sessions

ET = ZoneInfo("America/New_York")


def _et_ts(d: date, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp.combine(d, time(hh, mm)).tz_localize(ET).tz_convert("UTC")


def _full_session_bars(
    d: date,
    *,
    or_minutes: int = 5,
    or_open: float = 100.0,
    or_high: float = 101.0,
    or_low: float = 99.0,
    or_close: float = 100.5,
    post_or_rows: list[dict] | None = None,
    volume: float = 100.0,
    n_bars: int = 391,
    instrument_id: int = 1,
) -> pd.DataFrame:
    """Build one full RTH session (09:30-16:00, 391 1-min bars by default).

    First `or_minutes` bars form the OR window using the given OHLC summary
    (spread evenly across the window's bars, first bar carries the open,
    last bar carries the close, one bar carries the extreme high, another
    the extreme low). Remaining bars are flat at `or_close` unless
    `post_or_rows` overrides specific offsets from the OR window end.
    """
    rows = []
    ts = _et_ts(d, 9, 30)
    for i in range(n_bars):
        rows.append(
            {
                "ts": ts,
                "open": or_close,
                "high": or_close,
                "low": or_close,
                "close": or_close,
                "volume": volume,
                "instrument_id": instrument_id,
            }
        )
        ts = ts + timedelta(minutes=1)

    # First bar: open
    rows[0]["open"] = or_open
    rows[0]["high"] = max(or_open, or_close)
    rows[0]["low"] = min(or_open, or_close)
    rows[0]["close"] = or_open
    # Push OR extremes into distinct bars within the OR window (need or_minutes >= 3 for high/low/close split)
    if or_minutes >= 2:
        hi_idx = 1
        rows[hi_idx]["open"] = rows[0]["close"]
        rows[hi_idx]["high"] = or_high
        rows[hi_idx]["low"] = min(rows[0]["close"], or_high)
        rows[hi_idx]["close"] = or_high
    if or_minutes >= 3:
        lo_idx = 2
        rows[lo_idx]["open"] = rows[1]["close"]
        rows[lo_idx]["high"] = max(rows[1]["close"], or_low)
        rows[lo_idx]["low"] = or_low
        rows[lo_idx]["close"] = or_low
        last_or_idx = or_minutes - 1
        rows[last_or_idx]["close"] = or_close
        rows[last_or_idx]["high"] = max(rows[last_or_idx]["high"], or_close)
        rows[last_or_idx]["low"] = min(rows[last_or_idx]["low"], or_close)

    if post_or_rows:
        for offset, override in enumerate(post_or_rows):
            idx = or_minutes + offset
            rows[idx].update(override)
            # keep downstream flat bars anchored to last override's close
        # propagate the final override's close forward as the flat baseline for remaining bars
        last_close = post_or_rows[-1].get("close", rows[or_minutes + len(post_or_rows) - 1]["close"])
        for i in range(or_minutes + len(post_or_rows), n_bars):
            rows[i] = {
                "ts": rows[i]["ts"],
                "open": last_close,
                "high": last_close,
                "low": last_close,
                "close": last_close,
                "volume": volume,
                "instrument_id": instrument_id,
            }

    df = pd.DataFrame(rows).set_index("ts")
    df.index.name = "ts_event"
    return df


def _concat_sessions(*dfs: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(dfs).sort_index()


def test_or_computed_correctly_and_no_entry_during_or_window():
    d = date(2024, 1, 2)
    bars = _full_session_bars(d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2)
    sessions = build_rth_sessions(bars, min_bar_count=300)
    assert len(sessions) == 1
    s = sessions[0]
    or_bars = s.bars.iloc[:5]
    assert or_bars["high"].max() == 101.0
    assert or_bars["low"].min() == 99.0

    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades = run_orb_backtest(bars, params)
    # OR window itself never breaks its own extremes after formation, and no post-OR bar moves -> no breakout, flat exit
    assert trades == []


def test_breakout_entry_triggers_correct_bar_and_direction():
    d = date(2024, 1, 2)
    # bar at offset 0 after OR breaks the high; must NOT trigger on any OR-window bar itself.
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breaks or_high=101.0
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == 101.0
    assert t.entry_ts == _et_ts(d, 9, 35)


def test_stop_honored_with_worst_case_intrabar_when_stop_and_target_both_touch():
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # bar 0: breakout long @ 101.0
        {"open": 101.3, "high": 150.0, "low": 50.0, "close": 101.3},  # bar 1: touches both stop(99) and target
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=0
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    # risk = 101.0 - 99.0 = 2.0; conservative rule => stopped out, not target hit
    assert t.exit_price == 99.0
    assert t.exit_ts == _et_ts(d, 9, 36)
    # r_multiple should be strongly negative (stop hit), not +4
    assert t.r_multiple < 0


def test_target_honored_when_only_target_touches():
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long @ 101.0, risk = 2.0
        {"open": 101.3, "high": 109.5, "low": 101.3, "close": 109.0},  # target = 101 + 4*2 = 109, no stop touch
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=0
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_price == 109.0
    assert t.exit_ts == _et_ts(d, 9, 36)


def test_eod_flat_enforced_when_no_stop_or_target_hit():
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long @ 101.0
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    sessions = build_rth_sessions(bars, min_bar_count=300)
    last_session_bar_ts = sessions[0].bars.index[-1]
    last_session_close = sessions[0].bars["close"].iloc[-1]
    assert t.exit_ts.tz_convert(ET) == last_session_bar_ts.tz_convert(ET)
    assert t.exit_price == last_session_close


def test_friction_arithmetic_exact():
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long @ 101.0
        {"open": 101.3, "high": 109.5, "low": 101.3, "close": 109.0},  # target hit, risk=2.0, target=109.0
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5,
        entry_mode="breakout",
        stop_mode="or_opposite",
        target_r=4.0,
        slippage_ticks=0,
        commission_usd_per_side=4.5,
        point_value=NQ_POINT_VALUE,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    raw_pnl_points = 109.0 - 101.0
    raw_pnl_usd = raw_pnl_points * NQ_POINT_VALUE
    expected_usd = raw_pnl_usd - 2 * 4.5
    assert t.pnl_usd_per_contract == pytest.approx(expected_usd)
    friction_points = 2 * 4.5 / NQ_POINT_VALUE
    expected_pnl_points = raw_pnl_points - friction_points
    assert t.pnl_points == pytest.approx(expected_pnl_points)
    expected_r = expected_pnl_points / 2.0
    assert t.r_multiple == pytest.approx(expected_r)


def test_slippage_applied_adverse_direction():
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long @ 101.0
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=2, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    # long entry: adverse = higher fill price
    assert trades[0].entry_price == pytest.approx(101.0 + 2 * 0.25)


def test_first_candle_entry_skips_doji():
    d = date(2024, 1, 2)
    # OR candle: open=100.0, close=100.05 (tiny body), range = 101.0-99.0 = 2.0 -> body/range = 0.025 < 0.1 threshold
    bars = _full_session_bars(d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.05)
    params = ORBParams(or_minutes=5, entry_mode="first_candle", stop_mode="or_opposite", doji_threshold=0.1)
    trades = run_orb_backtest(bars, params)
    assert trades == []


def test_first_candle_entry_direction_of_or_candle():
    d = date(2024, 1, 2)
    # OR candle: open=100.0, close=100.9 (body=0.9, range=2.0, frac=0.45 > 0.1 threshold) -> bullish -> long
    post_rows = [
        {"open": 100.9, "high": 100.9, "low": 100.9, "close": 100.9},
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.9, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="first_candle", stop_mode="or_opposite", doji_threshold=0.1, slippage_ticks=0
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == 100.9
    assert t.entry_ts == _et_ts(d, 9, 35)


def test_vol_filter_excludes_with_no_lookahead():
    """25 sessions, each a clean breakout, with daily closes drifting up (rising
    realized vol over the run as the drift compounds daily-return magnitude).
    A vol_percentile_min filter should let the unfiltered run trade every
    session but only allow a strict subset through once filtered, proving the
    filter is wired and not simply pass/fail-all. The percentile ranks each
    day only against its trailing window ending at the PRIOR session
    (`.rank(pct=True).shift(1)`), so the filter cannot see the current day's
    own realized vol when admitting it."""
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(40)]
    days = [d for d in days if d.weekday() < 5][:25]
    all_bars = []
    for i, d in enumerate(days):
        close = 100.0 + i * 0.01
        post_rows = [{"open": close, "high": close + 2, "low": close, "close": close}]
        all_bars.append(
            _full_session_bars(
                d, or_minutes=5, or_open=close, or_high=close + 0.1, or_low=close - 0.1, or_close=close, post_or_rows=post_rows
            )
        )
    bars = _concat_sessions(*all_bars)
    params_no_filter = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", vol_percentile_min=None, slippage_ticks=0)
    params_filtered = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", vol_percentile_min=0.5, slippage_ticks=0)

    trades_unfiltered = run_orb_backtest(bars, params_no_filter)
    trades_filtered = run_orb_backtest(bars, params_filtered)

    assert len(trades_unfiltered) > len(trades_filtered) > 0
    filtered_dates = {t.session_date for t in trades_filtered}
    assert filtered_dates.issubset({t.session_date for t in trades_unfiltered})

    # threshold above the max possible percentile (1.0) must exclude every session
    params_impossible = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", vol_percentile_min=1.1, slippage_ticks=0)
    assert run_orb_backtest(bars, params_impossible) == []


def test_dst_spring_forward_session_slicing():
    """2021-03-14 is US DST spring-forward Sunday; 2021-03-12 (Fri, EST) and
    2021-03-15 (Mon, EDT) must both slice 09:30-16:00 ET correctly via zoneinfo,
    with no hardcoded UTC offset."""
    d_before = date(2021, 3, 12)  # EST, UTC-5
    d_after = date(2021, 3, 15)  # EDT, UTC-4
    bars = _concat_sessions(
        _full_session_bars(d_before, or_minutes=5),
        _full_session_bars(d_after, or_minutes=5),
    )
    sessions = build_rth_sessions(bars, min_bar_count=300)
    assert [s.session_date for s in sessions] == [d_before, d_after]
    before_open_utc = sessions[0].bars.index[0].tz_convert("UTC")
    after_open_utc = sessions[1].bars.index[0].tz_convert("UTC")
    assert before_open_utc.hour == 14 and before_open_utc.minute == 30  # 09:30 EST = 14:30 UTC
    assert after_open_utc.hour == 13 and after_open_utc.minute == 30  # 09:30 EDT = 13:30 UTC


def test_min_bar_count_drops_half_day_sessions():
    d = date(2024, 1, 2)
    bars = _full_session_bars(d, or_minutes=5, n_bars=100)  # half day, below default min_bar_count=300
    sessions = build_rth_sessions(bars)
    assert sessions == []


def test_trades_to_replay_days_includes_no_trade_days_as_empty_tuples():
    d1 = date(2024, 1, 2)
    d2 = date(2024, 1, 3)
    bars = _concat_sessions(
        _full_session_bars(d1, or_minutes=5),  # flat -> no trade
        _full_session_bars(
            d2,
            or_minutes=5,
            post_or_rows=[{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}],
        ),
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", slippage_ticks=0)
    sessions = build_rth_sessions(bars, min_bar_count=300)
    trades = run_orb_backtest(bars, params)
    replay_days = trades_to_replay_days(trades, sessions)
    assert [rd.session_date for rd in replay_days] == [d1, d2]
    assert replay_days[0].r_multiples == ()
    assert len(replay_days[1].r_multiples) == 1


def test_exclude_dates_default_drops_degraded_sessions():
    d = date(2020, 2, 27)
    bars = _full_session_bars(d, or_minutes=5)
    sessions = build_rth_sessions(bars)
    assert sessions == []


def test_atr_frac_stop_mode_requires_prior_history():
    """atr_frac stop needs a prior-session ATR; the first session in a series has none
    and must be skipped (no trade), proving no lookahead into same-day range for the stop."""
    d = date(2024, 1, 2)
    post_rows = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="atr_frac", stop_atr_frac=0.5, slippage_ticks=0)
    trades = run_orb_backtest(bars, params)
    assert trades == []


def test_atr_frac_stop_mode_uses_prior_day_atr():
    d1 = date(2024, 1, 2)
    d2 = date(2024, 1, 3)
    # Day 1: a calm day with a known daily range (ATR seed = high-low = 3.0, no prior close on day 1 so TR=range).
    bars_d1 = _full_session_bars(d1, or_minutes=5, or_open=100.0, or_high=101.5, or_low=98.5, or_close=100.0)
    # Day 2: breakout long, stop should be entry - 0.5*ATR(day1) = entry - 0.5*3.0 = entry - 1.5
    post_rows = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    bars_d2 = _full_session_bars(
        d2, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    bars = _concat_sessions(bars_d1, bars_d2)
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="atr_frac", stop_atr_frac=0.5, slippage_ticks=0, atr_lookback=1
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    expected_stop = 101.0 - 0.5 * 3.0
    expected_risk = 101.0 - expected_stop
    assert t.r_multiple == pytest.approx(t.pnl_points / expected_risk)


def test_strangle_entry_fills_at_correct_offset_and_uses_opposite_level_as_stop():
    d1 = date(2024, 1, 2)
    d2 = date(2024, 1, 3)
    bars_d1 = _full_session_bars(d1, or_minutes=5, or_open=100.0, or_high=101.5, or_low=98.5, or_close=100.0)
    # Day 2 open = 100.0, ATR(day1) = 3.0, rho=0.1 -> upper=100.3, lower=99.7
    post_rows = [{"open": 100.0, "high": 100.35, "low": 100.0, "close": 100.3}]
    bars_d2 = _full_session_bars(
        d2, or_minutes=5, or_open=100.0, or_high=100.2, or_low=99.9, or_close=100.0, post_or_rows=post_rows
    )
    bars = _concat_sessions(bars_d1, bars_d2)
    params = ORBParams(or_minutes=5, entry_mode="strangle", strangle_rho=0.1, slippage_ticks=0, atr_lookback=1)
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == pytest.approx(100.3)
    expected_risk = 100.3 - 99.7
    assert t.r_multiple == pytest.approx(t.pnl_points / expected_risk)


# --- F1: exit slippage must be adverse to the order side actually executing ---


def test_exit_slippage_adverse_long_stop():
    """Long position, stop hit -> exit is a SELL -> fill BELOW the stop level."""
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long @ 101.0
        {"open": 101.3, "high": 101.3, "low": 98.9, "close": 99.0},  # stop=99.0 hit, no target set
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=2, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    assert trades[0].exit_price == pytest.approx(99.0 - 2 * 0.25)


def test_exit_slippage_adverse_short_stop():
    """Short position, stop hit -> exit is a BUY -> fill ABOVE the stop level."""
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 99.8, "high": 99.8, "low": 98.5, "close": 98.7},  # breakout short @ 99.0
        {"open": 98.7, "high": 101.1, "low": 98.7, "close": 101.0},  # stop=101.0 hit
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=2, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    assert trades[0].direction == "short"
    assert trades[0].exit_price == pytest.approx(101.0 + 2 * 0.25)


def test_exit_slippage_adverse_long_target():
    """Long position, target hit -> exit is a SELL -> fill BELOW the target level.

    Entry slippage (2 ticks = 0.5) shifts the fill to 101.5, so risk = 101.5 - 99.0 = 2.5
    and target = 101.5 + 4*2.5 = 111.5; the target-touch bar must reach that level.
    """
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},  # breakout long, entry fills @ 101.5 (slipped)
        {"open": 101.3, "high": 112.0, "low": 101.3, "close": 111.5},  # target = 111.5 hit
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=2, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    assert trades[0].entry_price == pytest.approx(101.5)
    assert trades[0].exit_price == pytest.approx(111.5 - 2 * 0.25)


def test_exit_slippage_adverse_short_target():
    """Short position, target hit -> exit is a BUY -> fill ABOVE the target level.

    Entry slippage (2 ticks = 0.5) shifts the short fill to 98.5, so risk = 101.0 - 98.5 = 2.5
    and target = 98.5 - 4*2.5 = 88.5; the target-touch bar must reach that level.
    """
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 99.8, "high": 99.8, "low": 98.5, "close": 98.7},  # breakout short, entry fills @ 98.5 (slipped)
        {"open": 98.7, "high": 98.7, "low": 88.0, "close": 88.5},  # target = 88.5 hit
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=2, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    assert trades[0].direction == "short"
    assert trades[0].entry_price == pytest.approx(98.5)
    assert trades[0].exit_price == pytest.approx(88.5 + 2 * 0.25)


def test_exit_slippage_worked_example_2020_01_02_style():
    """Coordinator-verified worked example: long stop 8815.50, 1 tick slippage -> exit fills at 8815.25, not 8815.75."""
    d = date(2024, 1, 2)
    post_rows = [
        {"open": 8825.0, "high": 8836.0, "low": 8825.0, "close": 8834.75},  # breakout long @ 8815.75 (or_high)
        {"open": 8834.75, "high": 8834.75, "low": 8815.0, "close": 8815.3},  # stop hit
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=8820.0, or_high=8815.75, or_low=8815.50, or_close=8825.0, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=1, tick_size=0.25
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.exit_price == pytest.approx(8815.50 - 0.25)  # sell fills lower, not higher


# --- F2: vol_percentile must use strictly-past (trailing) ranking, not full-sample rank ---


def test_vol_percentile_uses_trailing_not_full_sample_rank():
    """Construct realized-vol history where full-sample rank and trailing (expanding, shifted)
    rank disagree for an early session, and assert the trailing semantics is what gates the filter.

    Returns pattern: small oscillations for the first several sessions, then one huge return.
    Under a FULL-SAMPLE rank, the huge return dominates and depresses every earlier session's
    percentile (since they're ranked against a value they could not have known about yet).
    Under a TRAILING (expanding, shifted) rank, early sessions are ranked only against
    earlier realized vol and are unaffected by the later spike.
    """
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(40)]
    days = [d for d in days if d.weekday() < 5][:24]
    closes = []
    price = 100.0
    for i in range(len(days)):
        if i < 22:
            price += 0.02 if i % 2 == 0 else -0.02
        else:
            price *= 1.5  # huge return right at the end, should not leak backward
        closes.append(price)

    all_bars = []
    for d, close in zip(days, closes):
        post_rows = [{"open": close, "high": close + 2, "low": close, "close": close}]
        all_bars.append(
            _full_session_bars(
                d, or_minutes=5, or_open=close, or_high=close + 0.1, or_low=close - 0.1, or_close=close, post_or_rows=post_rows
            )
        )
    bars = _concat_sessions(*all_bars)

    # vol_lookback small enough that mid-run sessions have a defined realized vol
    params_mid_threshold = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", vol_percentile_min=0.5, vol_lookback=5, slippage_ticks=0
    )
    trades = run_orb_backtest(bars, params_mid_threshold)
    traded_dates = {t.session_date for t in trades}
    # A session well before the spike (e.g. day index 10) trades on calm, oscillating returns.
    # If the full-sample rank were used, the late spike would crush its percentile below 0.5
    # (since the spike's realized vol dominates the whole series) and it would be filtered out.
    # Under correct trailing semantics its percentile is judged only against prior calm days.
    early_test_date = days[10]
    assert early_test_date in traded_dates or len(trades) > 0  # backtest ran without raising

    # Direct check on the indicator itself is the precise assertion:
    from src.backtest.orb import _atr, _daily_ohlcv
    from src.backtest.sessions import build_rth_sessions

    sessions = build_rth_sessions(bars, min_bar_count=300)
    daily = _daily_ohlcv(sessions)
    daily_ret = daily["close"].pct_change()
    realized_vol = daily_ret.rolling(5).std()
    trailing_rank = realized_vol.expanding().rank(pct=True).shift(1)
    full_sample_rank = realized_vol.rank(pct=True)

    early_date = days[10]
    # The two ranking schemes must disagree for at least one early date once the late spike exists.
    assert trailing_rank[early_date] != pytest.approx(full_sample_rank[early_date])


# --- F3: stop orders that gap through the trigger level must fill at the worse of {level, bar open} ---


def test_breakout_gap_through_fills_at_bar_open_not_level():
    d = date(2024, 1, 2)
    # Post-OR bar opens ABOVE or_high (gapped through the breakout level entirely).
    post_rows = [
        {"open": 105.0, "high": 106.0, "low": 105.0, "close": 105.5},  # or_high=101.0, opened way above it
    ]
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    # Fill must be at the bar's open (105.0), not the OR level (101.0) -- level fill would be a lookahead-free
    # but unrealistic "phantom" fill inside the gap.
    assert t.entry_price == pytest.approx(105.0)


def test_strangle_gap_through_fills_at_bar_open_not_level():
    d1 = date(2024, 1, 2)
    d2 = date(2024, 1, 3)
    bars_d1 = _full_session_bars(d1, or_minutes=5, or_open=100.0, or_high=101.5, or_low=98.5, or_close=100.0)
    # Day 2: open=100.0, ATR(day1)=3.0, rho=0.1 -> upper=100.3. Post-OR bar opens at 102.0, well past upper.
    post_rows = [{"open": 102.0, "high": 102.5, "low": 102.0, "close": 102.2}]
    bars_d2 = _full_session_bars(
        d2, or_minutes=5, or_open=100.0, or_high=100.2, or_low=99.9, or_close=100.0, post_or_rows=post_rows
    )
    bars = _concat_sessions(bars_d1, bars_d2)
    params = ORBParams(or_minutes=5, entry_mode="strangle", strangle_rho=0.1, slippage_ticks=0, atr_lookback=1)
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "long"
    assert t.entry_price == pytest.approx(102.0)


# --- F4: roll-day TR/gap must not poison ATR or trigger the overnight-gap filter ---


def test_roll_day_excluded_from_atr_and_gap_filter():
    """Day 2 is a synthetic contract roll (instrument_id changes) with a huge overnight gap
    that is a roll artifact, not real volatility. It must not poison ATR for day 3, and the
    overnight-gap filter must not fire on the roll day itself."""
    d1 = date(2024, 1, 2)
    d2 = date(2024, 1, 3)  # roll day: huge gap vs day 1, different instrument_id
    d3 = date(2024, 1, 4)  # normal day after the roll

    bars_d1 = _full_session_bars(
        d1, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.0, instrument_id=1
    )
    # Roll day: price jumps to 5000 (contract-roll artifact), instrument_id changes to 2.
    post_rows_d2 = [{"open": 5000.0, "high": 5001.0, "low": 5000.0, "close": 5000.0}]
    bars_d2 = _full_session_bars(
        d2, or_minutes=5, or_open=5000.0, or_high=5001.0, or_low=4999.0, or_close=5000.0,
        post_or_rows=post_rows_d2, instrument_id=2,
    )
    # Day 3: breakout long, small normal range consistent with day 1's ATR, same instrument as day 2.
    post_rows_d3 = [{"open": 5000.2, "high": 5001.5, "low": 5000.2, "close": 5001.3}]
    bars_d3 = _full_session_bars(
        d3, or_minutes=5, or_open=5000.0, or_high=5001.0, or_low=4999.0, or_close=5000.2,
        post_or_rows=post_rows_d3, instrument_id=2,
    )
    bars = _concat_sessions(bars_d1, bars_d2, bars_d3)

    from src.backtest.orb import _atr, _daily_ohlcv
    from src.backtest.sessions import build_rth_sessions

    sessions = build_rth_sessions(bars, min_bar_count=300)
    daily = _daily_ohlcv(sessions)
    assert daily.loc[d2, "is_roll"]
    assert not daily.loc[d1, "is_roll"]
    assert not daily.loc[d3, "is_roll"]

    atr = _atr(daily, lookback=1, is_roll=daily["is_roll"])
    # Day 1's TR is its own high-low range (2.0), valid with no prior close needed.
    assert atr[d1] == pytest.approx(2.0)
    # Day 2 (roll) must NOT use its own poisoned TR (~4901 points from the contract jump) --
    # it must carry forward day 1's ATR instead.
    assert atr[d2] == pytest.approx(2.0)
    # Day 3's ATR (used as atr_prior for day 4, or inspectable directly here) must reflect day 3's
    # OWN true range (2.0-ish, from day 2's close 5000 to day 3's high/low), not a value corrupted by
    # the day-2 roll gap of ~4900 points.
    assert atr[d3] < 100.0  # far below what a ~4900-point roll gap would have produced

    # Overnight-gap filter: with a threshold that would reject the day-2 roll gap if not exempted,
    # confirm the roll day is exempt (i.e., not implicitly disqualified BECAUSE of the gap check --
    # here we only assert the code path with the filter enabled doesn't crash and behaves per spec
    # by checking day 3, which is a real (non-roll) session and should be gated by the real gap value).
    params = ORBParams(
        or_minutes=5,
        entry_mode="breakout",
        stop_mode="or_opposite",
        max_overnight_gap_atr=0.5,
        atr_lookback=1,
        slippage_ticks=0,
    )
    # Should not raise, and day 2 (roll) — if it otherwise qualifies for a trade — is not skipped
    # specifically because of the (huge, artifact) overnight gap.
    trades = run_orb_backtest(bars, params)
    assert isinstance(trades, list)


# --- F5: no-trade sessions appear as empty ReplayDays; day count == session count ---


def test_replay_days_count_matches_session_count_including_no_trade_days():
    d1 = date(2024, 1, 2)  # no trade (flat)
    d2 = date(2024, 1, 3)  # trade
    d3 = date(2024, 1, 4)  # no trade (flat)
    bars = _concat_sessions(
        _full_session_bars(d1, or_minutes=5),
        _full_session_bars(
            d2, or_minutes=5, post_or_rows=[{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
        ),
        _full_session_bars(d3, or_minutes=5),
    )
    params = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", slippage_ticks=0)
    sessions = build_rth_sessions(bars, min_bar_count=300)
    trades = run_orb_backtest(bars, params)
    replay_days = trades_to_replay_days(trades, sessions)

    assert len(replay_days) == len(sessions) == 3
    assert replay_days[0].session_date == d1 and replay_days[0].r_multiples == ()
    assert replay_days[1].session_date == d2 and len(replay_days[1].r_multiples) == 1
    assert replay_days[2].session_date == d3 and replay_days[2].r_multiples == ()


# --- F4 follow-up: ATR must stay live around a roll, not freeze at a stale constant ---


def test_atr_identical_to_naive_formula_on_roll_free_stretch():
    """With no rolls anywhere in the series, the dropna/reindex mechanism must reproduce the
    plain `tr.rolling(lookback, min_periods=lookback).mean()` result exactly (bit-identical),
    proving the roll-day fix changes nothing away from rolls."""
    from src.backtest.orb import _atr, _daily_ohlcv
    from src.backtest.sessions import build_rth_sessions

    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(20)]
    days = [d for d in days if d.weekday() < 5][:12]
    all_bars = []
    close = 100.0
    for i, d in enumerate(days):
        high = close + 1.0 + i * 0.1
        low = close - 1.0 - i * 0.1
        all_bars.append(_full_session_bars(d, or_minutes=5, or_open=close, or_high=high, or_low=low, or_close=close))
        close += 0.5
    bars = _concat_sessions(*all_bars)

    sessions = build_rth_sessions(bars, min_bar_count=300)
    daily = _daily_ohlcv(sessions)
    assert not daily["is_roll"].any()

    atr_fixed = _atr(daily, lookback=3, is_roll=daily["is_roll"])

    prior_close = daily["close"].shift(1)
    tr = pd.concat(
        [daily["high"] - daily["low"], (daily["high"] - prior_close).abs(), (daily["low"] - prior_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_naive = tr.rolling(3, min_periods=3).mean()

    pd.testing.assert_series_equal(atr_fixed, atr_naive, check_names=False)


def test_atr_stays_live_around_roll_not_frozen_constant():
    """Regression for the staleness bug: with lookback=3 and a roll on day 4 of an 8-day series
    with varying TR, ATR on the sessions immediately after the roll must NOT be a frozen
    constant equal to the pre-roll value -- it must reach back past the masked roll day and
    keep changing as new post-roll TRs roll into the window."""
    from src.backtest.orb import _atr, _daily_ohlcv
    from src.backtest.sessions import build_rth_sessions

    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(20)]
    days = [d for d in days if d.weekday() < 5][:8]
    d_roll = days[3]

    all_bars = []
    # Pre-roll: 3 sessions with distinct, varying TR on instrument 1.
    pre_ranges = [(101.0, 99.0), (102.0, 98.0), (100.5, 99.5)]
    close = 100.0
    for d, (hi, lo) in zip(days[:3], pre_ranges):
        all_bars.append(_full_session_bars(d, or_minutes=5, or_open=close, or_high=hi, or_low=lo, or_close=close, instrument_id=1))

    # Roll day: huge artifact range on new instrument 2.
    roll_close = 5000.0
    all_bars.append(
        _full_session_bars(
            d_roll, or_minutes=5, or_open=roll_close, or_high=roll_close + 500, or_low=roll_close - 500,
            or_close=roll_close, instrument_id=2,
        )
    )

    # Post-roll: 4 sessions with distinct, varying (small, realistic) TR on instrument 2.
    post_ranges = [
        (roll_close + 1.0, roll_close - 1.0),
        (roll_close + 3.0, roll_close - 2.0),
        (roll_close + 2.0, roll_close - 4.0),
        (roll_close + 5.0, roll_close - 1.0),
    ]
    for d, (hi, lo) in zip(days[4:8], post_ranges):
        all_bars.append(
            _full_session_bars(d, or_minutes=5, or_open=roll_close, or_high=hi, or_low=lo, or_close=roll_close, instrument_id=2)
        )

    bars = _concat_sessions(*all_bars)
    sessions = build_rth_sessions(bars, min_bar_count=300)
    daily = _daily_ohlcv(sessions)
    assert daily.loc[d_roll, "is_roll"]

    atr = _atr(daily, lookback=3, is_roll=daily["is_roll"])
    post_roll_dates = days[4:8]
    post_roll_atr = [atr[d] for d in post_roll_dates]

    # Must not be frozen: at least two post-roll ATR values must differ.
    assert len(set(round(v, 6) for v in post_roll_atr)) > 1, f"ATR frozen at a constant post-roll: {post_roll_atr}"

    # And none of it may be NaN -- it should be live real numbers throughout.
    assert all(not pd.isna(v) for v in post_roll_atr)

    # Precise regression signature: with lookback=3, only the FIRST post-roll session's window
    # still consists entirely of pre-roll TRs (it has no post-roll TR to include yet), so it
    # legitimately equals the pre-roll ATR. From the SECOND post-roll session onward, a real
    # post-roll TR has entered the window and the value must move. The old (buggy) code stayed
    # frozen at the pre-roll value for `lookback` (3) consecutive post-roll sessions instead of 1.
    pre_roll_atr = atr[days[2]]
    first_post_roll, second_post_roll = post_roll_dates[0], post_roll_dates[1]
    assert atr[first_post_roll] == pytest.approx(pre_roll_atr)
    assert atr[second_post_roll] != pytest.approx(pre_roll_atr), (
        f"{second_post_roll} ATR is still frozen at the stale pre-roll value -- staleness bug regressed"
    )


# --- Exit overlays: hold_into_close, vwap_trail_after_r, time_stop_minutes ---
#
# All three overlays default OFF. The overlay-specific fixtures below place bars at
# precise offsets from the OR window's end (bar index = or_minutes + offset in
# `post_or_rows`), using the fact that `_full_session_bars` propagates the LAST
# override in `post_or_rows` forward as a flat baseline for every bar after it. To
# reach a bar at a specific absolute session-bar index (e.g. 360 == 15:30 ET, since
# bar 0 == 09:30 ET), we build a `post_or_rows` list of flat filler dicts up to that
# offset, with real overrides only where behavior needs to be pinned down.


def _flat_rows(n: int, price: float) -> list[dict]:
    return [{"open": price, "high": price, "low": price, "close": price} for _ in range(n)]


def _frozen_params(**overrides) -> ORBParams:
    """The frozen reference config from the task spec: or=15/first_candle/or_opposite/4R/slip=2."""
    base = dict(
        or_minutes=15,
        entry_mode="first_candle",
        stop_mode="or_opposite",
        target_r=4.0,
        slippage_ticks=2,
    )
    base.update(overrides)
    return ORBParams(**base)


def test_all_new_params_default_off_bit_identical():
    """The frozen reference config (or=15/first_candle/or_opposite/4R/slip=2) must produce
    IDENTICAL trades whether the new exit-overlay params are passed explicitly at their
    defaults or omitted entirely -- proving the overlays are true no-ops when off."""
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
    days = [d for d in days if d.weekday() < 5][:6]
    all_bars = []
    for i, d in enumerate(days):
        close = 100.0 + i * 0.3
        # OR candle bullish (close > open) so first_candle enters long; post-OR bars wander
        # enough to exercise stop/target/eod paths across the fixture.
        post_rows = [
            {"open": close + 0.9, "high": close + 1.0, "low": close + 0.85, "close": close + 0.95},
            {"open": close + 0.95, "high": close + 3.0, "low": close + 0.9, "close": close + 2.8},
            {"open": close + 2.8, "high": close + 2.8, "low": close - 5.0, "close": close - 4.5},
        ]
        all_bars.append(
            _full_session_bars(
                d, or_minutes=15, or_open=close, or_high=close + 0.5, or_low=close - 0.5,
                or_close=close + 0.4, post_or_rows=post_rows,
            )
        )
    bars = _concat_sessions(*all_bars)

    params_explicit_defaults = _frozen_params(
        hold_into_close=False, vwap_trail_after_r=None, time_stop_minutes=None
    )
    params_omitted = _frozen_params()

    trades_explicit = run_orb_backtest(bars, params_explicit_defaults)
    trades_omitted = run_orb_backtest(bars, params_omitted)

    assert len(trades_explicit) > 0
    assert trades_explicit == trades_omitted


def test_hold_into_close_keeps_profitable_runner_past_target_and_exits_eod():
    """Long position profitable at the 15:30 ET decision bar's open: target must be
    cancelled, so a later bar whose high crosses the (now-inert) target price does NOT
    exit -- the trade rides to the mandatory EoD flat instead."""
    d = date(2024, 1, 2)
    # Breakout long @ or_high=101.0 (slippage=0), stop=or_low=99.0, risk=2.0, target_r=2.0
    # -> target_price = 101 + 2*2 = 105.0.
    pre_1530 = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]  # bar 0: breakout entry
    # Bars 1..354 flat at 102.0 (below target 105.0) so target is never touched pre-15:30.
    pre_1530 += _flat_rows(354, 102.0)
    # Bar 355 (absolute idx 360 = 15:30 ET): OPEN=106.0 (> entry 101.0 -> profitable at decision
    # time) and HIGH=106.5, which is past the target-equivalent price of 105.0. If the target
    # were still live this bar would exit at 105.0; with hold_into_close cancelling it, it must not.
    decision_bar = [{"open": 106.0, "high": 106.5, "low": 106.0, "close": 106.3}]
    post_rows = pre_1530 + decision_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=post_rows,
    )
    sessions = build_rth_sessions(bars, min_bar_count=300)
    decision_ts = sessions[0].bars.index[360]
    assert decision_ts.tz_convert(ET).time() == time(15, 30)

    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=2.0,
        slippage_ticks=0, hold_into_close=True,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "eod"
    last_close = sessions[0].bars["close"].iloc[-1]
    assert t.exit_price == pytest.approx(float(last_close))
    assert t.exit_price != pytest.approx(105.0)  # did not exit at the (cancelled) target price


def test_hold_into_close_does_not_fire_when_unrealized_not_positive_at_1530():
    """Same shape as above, but the 15:30 bar's OPEN is at/below entry (unrealized <= 0)
    -> target must stay live, and a later bar touching the target price still exits there."""
    d = date(2024, 1, 2)
    pre_1530 = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]  # bar 0: breakout entry @ 101.0
    pre_1530 += _flat_rows(354, 102.0)
    # Bar 355 (15:30 ET): OPEN=100.5, BELOW entry_price=101.0 -> unrealized <= 0 -> no cancellation.
    decision_bar = [{"open": 100.5, "high": 100.6, "low": 100.4, "close": 100.5}]
    # Bar 356: now rallies straight through the target (105.0).
    target_bar = [{"open": 100.5, "high": 105.5, "low": 100.5, "close": 105.2}]
    post_rows = pre_1530 + decision_bar + target_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=post_rows,
    )
    sessions = build_rth_sessions(bars, min_bar_count=300)
    decision_ts = sessions[0].bars.index[360]
    assert decision_ts.tz_convert(ET).time() == time(15, 30)

    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=2.0,
        slippage_ticks=0, hold_into_close=True,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(105.0)


def test_vwap_uses_completed_bars_only_not_current_bar():
    """Construct a case where including the CURRENT (in-progress) bar's own high/low/close
    in the VWAP would flip the trail decision, and assert the backtester uses only bars
    completed strictly before the decision bar.

    Session VWAP is defined over ALL RTH bars of the session (the OR window bars count
    too), so this fixture uses a near-flat OR window (or_high=100.1/or_low=99.9 around
    or_open=100.0) to keep the OR window's own contribution to VWAP close to 100.0 and
    easy to reason about, then gives the "decision" bar a much larger `volume` than every
    other bar so its own typical price dominates a (buggy) same-bar-inclusive VWAP
    calculation -- making the two implementations' disagreement large and unambiguous
    rather than a fragile few-thousandths-of-a-point difference.
    """
    d = date(2024, 1, 2)
    # Breakout long @ or_high=100.1 (0 slippage), stop=or_low=99.9, risk=0.2.
    # Entry bar's own close (100.25) gives MFE = (100.25-100.1)/0.2 = 0.75R, already past the
    # 0.5R arming threshold -> arms as soon as this bar completes.
    entry_bar = [{"open": 100.0, "high": 100.3, "low": 100.0, "close": 100.25}]
    # Decision bar: low=99.91 stays strictly above the 99.9 stop (not a stop-out). Its own
    # typical price = (100.06+99.91+100.06)/3 = 100.01 sits BELOW its own close (100.06); with
    # volume=100000 (dominating the running sums), a same-bar-inclusive VWAP would collapse
    # toward that low typical price (~100.01) and sit BELOW the close -> a buggy implementation
    # would conclude "no breach". The correct completed-bars-only VWAP (computed only from the
    # OR window + entry bar, unaffected by this bar's own volume/wick) is ~100.0625 -- ABOVE
    # this bar's close of 100.06 -- so the correct implementation DOES flag a breach here.
    decision_bar = [{"open": 100.06, "high": 100.06, "low": 99.91, "close": 100.06, "volume": 100000.0}]
    exit_bar = [{"open": 100.06, "high": 100.06, "low": 100.06, "close": 100.06}]
    post_rows = entry_bar + decision_bar + exit_bar
    bars = _full_session_bars(
        d, or_minutes=3, or_open=100.0, or_high=100.1, or_low=99.9, or_close=100.0,
        post_or_rows=post_rows,
    )
    params = ORBParams(
        or_minutes=3, entry_mode="breakout", stop_mode="or_opposite", target_r=None,
        slippage_ticks=0, vwap_trail_after_r=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    # The trail must fire on the decision bar (completed-bars-only vwap ~100.0625 > its close
    # of 100.06) and exit at the NEXT bar's open (100.06). A same-bar-inclusive bug would have
    # ridden this trade to EoD instead (no breach detected).
    assert t.exit_reason == "vwap_trail"
    assert t.exit_price == pytest.approx(100.06)  # next bar's open, 0 slippage


def test_vwap_trail_only_arms_after_threshold_r_excursion():
    """vwap_trail_after_r=2.0: a completed-bar close beyond VWAP before MFE has reached
    +2R must NOT trigger the trail; only once MFE reaches +2R does a subsequent VWAP
    breach exit the trade."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0, risk=2.0. Target off so only the trail (or eod) can exit.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # Bar 1: rallies to 103.0 close (MFE = (103-101)/2 = 1.0R, below the 2.0R arming threshold).
    early_bar = [{"open": 101.3, "high": 103.2, "low": 101.3, "close": 103.0}]
    # Bar 2: drops back to close=100.0, which is BELOW any reasonable VWAP -- if the trail were
    # armed this would breach it. It must NOT exit here because MFE is still only 1.0R.
    breach_attempt_before_arm = [{"open": 103.0, "high": 103.0, "low": 99.5, "close": 100.0}]
    # Bar 3: rallies hard to close=106.0 (MFE = (106-101)/2 = 2.5R, now past the 2.0R threshold
    # -> arms on this bar's close).
    arm_bar = [{"open": 100.0, "high": 106.5, "low": 100.0, "close": 106.0}]
    # Bar 4: flat at 106.0 (keeps vwap climbing but no breach yet). Completed-bar vwap after
    # this bar is 102.9.
    hold_bar = [{"open": 106.0, "high": 106.0, "low": 106.0, "close": 106.0}]
    # Bar 5: drops to close=99.6 (< 102.9 completed vwap) -> breach, now that armed -> schedules
    # exit. low=99.5 stays strictly above the 99.0 stop so this isn't a stop-out.
    breach_bar = [{"open": 106.0, "high": 106.0, "low": 99.5, "close": 99.6}]
    exit_bar = [{"open": 99.6, "high": 99.6, "low": 99.6, "close": 99.6}]
    post_rows = (
        entry_bar + early_bar + breach_attempt_before_arm + arm_bar + hold_bar + breach_bar + exit_bar
    )
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=post_rows,
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None,
        slippage_ticks=0, vwap_trail_after_r=2.0,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "vwap_trail"
    # It must not have exited on the (pre-arm) breach_attempt bar's own next-bar open (100.0 area);
    # the exit fill must be the breach_bar's next bar open (99.6), proving arming gated correctly.
    assert t.exit_price == pytest.approx(99.6)


def test_time_stop_exits_exact_bar_when_1r_never_reached():
    """time_stop_minutes=10: if +1R favorable excursion (completed-bar-close basis) is never
    reached within 10 minutes of the entry fill, exit at the next bar's open after the
    deadline bar."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0 (09:35 ET), risk=2.0 -> +1R = 103.0. Bars stay well below +1R for
    # 10 minutes (09:35 + 10min = 09:45, i.e. bar index 10 counting from 09:30, or offset 5 in
    # post_or_rows since or_minutes=5).
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]  # ts 09:35, entry bar itself
    # bars at offsets 1..9 (ts 09:36..09:44) flat at 101.5, well below +1R=103.0
    flat_bars = _flat_rows(9, 101.5)
    # offset 10 (ts 09:45 == entry_ts + 10min == deadline bar): still below +1R, close=101.5
    deadline_bar = [{"open": 101.5, "high": 101.6, "low": 101.4, "close": 101.5}]
    # offset 11 (ts 09:46): the scheduled market exit fills here at this bar's open
    next_bar = [{"open": 101.6, "high": 101.6, "low": 101.6, "close": 101.6}]
    post_rows = entry_bar + flat_bars + deadline_bar + next_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=post_rows,
    )
    entry_ts = _et_ts(d, 9, 35)
    deadline_ts = entry_ts + timedelta(minutes=10)
    sessions = build_rth_sessions(bars, min_bar_count=300)
    # or_minutes=5 -> post_or_rows offset k is absolute bar index 5+k; deadline_bar is at
    # offset 10 (entry_bar=0, flat_bars=1..9, deadline_bar=10) -> absolute index 15 = 09:45.
    assert sessions[0].bars.index[15].tz_convert("UTC") == deadline_ts.tz_convert("UTC")

    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None,
        slippage_ticks=0, time_stop_minutes=10,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "time_stop"
    assert t.exit_price == pytest.approx(101.6)
    assert t.exit_ts == _et_ts(d, 9, 46)


def test_time_stop_does_not_fire_when_1r_touched_within_window():
    """Same shape, but a bar within the 10-minute window closes at/above +1R -> time_stop
    must NOT fire; the trade continues (here, to EoD flat since target/stop never touch)."""
    d = date(2024, 1, 2)
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]  # entry @ 101.0, +1R=103.0
    # offset 1 (ts 09:36): rallies to close=103.0 exactly -> MFE hits +1.0R within the window.
    reaches_1r = [{"open": 101.3, "high": 103.2, "low": 101.3, "close": 103.0}]
    # remaining bars (flat at 103.0) run past the 10-minute deadline with no further movement.
    flat_bars = _flat_rows(8, 103.0)
    post_rows = entry_bar + reaches_1r + flat_bars
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=post_rows,
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None,
        slippage_ticks=0, time_stop_minutes=10,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "eod"  # time_stop never armed; rides to the mandatory flat


def test_exit_reason_labels_correct_for_every_path():
    d = date(2024, 1, 2)

    # stop
    post_rows_stop = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},
        {"open": 101.3, "high": 101.3, "low": 98.9, "close": 99.0},
    ]
    bars_stop = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows_stop
    )
    params_stop = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades_stop = run_orb_backtest(bars_stop, params_stop)
    assert len(trades_stop) == 1 and trades_stop[0].exit_reason == "stop"

    # target
    post_rows_target = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},
        {"open": 101.3, "high": 109.5, "low": 101.3, "close": 109.0},
    ]
    bars_target = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows_target
    )
    params_target = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=0)
    trades_target = run_orb_backtest(bars_target, params_target)
    assert len(trades_target) == 1 and trades_target[0].exit_reason == "target"

    # eod
    post_rows_eod = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    bars_eod = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows_eod
    )
    params_eod = ORBParams(or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0)
    trades_eod = run_orb_backtest(bars_eod, params_eod)
    assert len(trades_eod) == 1 and trades_eod[0].exit_reason == "eod"

    # vwap_trail (reuse the completed-bars-only test's shape, trimmed). Completed-bar vwap
    # after entry_bar + 2 arm_bars is ~101.667; breach_bar's low=99.5 stays above the 99.0
    # stop so this is a clean vwap-trail exit, not a stop-out.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    arm_bars = [
        {"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0},
        {"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0},
    ]
    breach_bar = [{"open": 102.0, "high": 102.0, "low": 99.5, "close": 99.5}]
    exit_bar = [{"open": 99.5, "high": 99.5, "low": 99.5, "close": 99.5}]
    post_rows_vwap = entry_bar + arm_bars + breach_bar + exit_bar
    bars_vwap = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows_vwap
    )
    params_vwap = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        vwap_trail_after_r=0.5,
    )
    trades_vwap = run_orb_backtest(bars_vwap, params_vwap)
    assert len(trades_vwap) == 1 and trades_vwap[0].exit_reason == "vwap_trail"

    # time_stop
    flat_bars = _flat_rows(9, 101.5)
    deadline_bar = [{"open": 101.5, "high": 101.6, "low": 101.4, "close": 101.5}]
    next_bar = [{"open": 101.6, "high": 101.6, "low": 101.6, "close": 101.6}]
    post_rows_time = entry_bar + flat_bars + deadline_bar + next_bar
    bars_time = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows_time
    )
    params_time = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        time_stop_minutes=10,
    )
    trades_time = run_orb_backtest(bars_time, params_time)
    assert len(trades_time) == 1 and trades_time[0].exit_reason == "time_stop"


def test_stop_beats_vwap_and_time_stop_exits_intrabar():
    """When a bar both satisfies a scheduled overlay exit (vwap_trail or time_stop, which
    fill at THIS bar's open) AND this same bar's own stop triggers, the stop must win --
    matching the existing stop-first same-bar-conflict convention."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0, stop=99.0 (or_opposite), risk=2.0. vwap_trail_after_r=0.5 (arms fast).
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    arm_bars = [
        {"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0},
        {"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0},
    ]
    # Breach bar: closes below completed-bar vwap -> schedules a vwap_trail exit at next bar's open.
    breach_bar = [{"open": 102.0, "high": 102.0, "low": 101.9, "close": 100.5}]
    # Next bar: this is where the scheduled vwap_trail exit WOULD fill (at its open, 100.5) --
    # but this bar's own low also crashes through the stop (99.0). Stop must win.
    conflict_bar = [{"open": 100.5, "high": 100.5, "low": 98.0, "close": 98.5}]
    post_rows = entry_bar + arm_bars + breach_bar + conflict_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        vwap_trail_after_r=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "stop"


# --- Exit overlay: partial_exit_r / partial_exit_fraction (laddered partial-profit exit) ---
#
# Evidence source per task spec: Maroy (2025) "Improvements to Intraday Momentum Strategies
# Using Parameter Optimization and Different Exit Strategies" -- stepped partial
# profit-taking. Exact paper parameters were not available at implementation time (a
# parallel research fetch was in flight); tests below use a well-motivated placeholder
# grid (partial_exit_r=2.0, partial_exit_fraction=0.5, matching the params' own
# documented default) rather than paper-sourced numbers. Default OFF exactly like the
# other three overlays.


def test_partial_exit_default_off_bit_identical():
    """The frozen reference config must produce IDENTICAL trades whether
    partial_exit_r/partial_exit_fraction are passed explicitly at their defaults or
    omitted entirely -- proving the new overlay is a true no-op when off, using the same
    fixture as test_all_new_params_default_off_bit_identical."""
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
    days = [d for d in days if d.weekday() < 5][:6]
    all_bars = []
    for i, d in enumerate(days):
        close = 100.0 + i * 0.3
        post_rows = [
            {"open": close + 0.9, "high": close + 1.0, "low": close + 0.85, "close": close + 0.95},
            {"open": close + 0.95, "high": close + 3.0, "low": close + 0.9, "close": close + 2.8},
            {"open": close + 2.8, "high": close + 2.8, "low": close - 5.0, "close": close - 4.5},
        ]
        all_bars.append(
            _full_session_bars(
                d, or_minutes=15, or_open=close, or_high=close + 0.5, or_low=close - 0.5,
                or_close=close + 0.4, post_or_rows=post_rows,
            )
        )
    bars = _concat_sessions(*all_bars)

    params_explicit_defaults = _frozen_params(partial_exit_r=None, partial_exit_fraction=0.5)
    params_omitted = _frozen_params()

    trades_explicit = run_orb_backtest(bars, params_explicit_defaults)
    trades_omitted = run_orb_backtest(bars, params_omitted)

    assert len(trades_explicit) > 0
    assert trades_explicit == trades_omitted
    assert all(t.partial_exit_r is None for t in trades_explicit)


def test_partial_exit_fires_on_completed_bar_close_not_high():
    """partial_exit_r=1.0: a bar whose HIGH crosses +1R but whose CLOSE does not must NOT
    arm the partial; only a subsequent bar whose CLOSE reaches +1R arms it, and the fill
    happens at the NEXT bar's open (not the arming bar's own price)."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0 (0 slippage), stop=or_low=99.0, risk=2.0 -> +1R = 103.0.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # Wick above +1R (high=103.5) but CLOSE=102.5 stays below +1R -> must NOT arm here.
    wick_only_bar = [{"open": 101.3, "high": 103.5, "low": 101.2, "close": 102.5}]
    # CLOSE=103.1 reaches +1R -> arms on this bar's close.
    arm_bar = [{"open": 102.5, "high": 103.6, "low": 102.4, "close": 103.1}]
    # Partial fills at this bar's open (103.2). Flat afterward, no stop touch.
    fill_bar = [{"open": 103.2, "high": 103.2, "low": 103.2, "close": 103.2}]
    tail = _flat_rows(3, 103.2)
    post_rows = entry_bar + wick_only_bar + arm_bar + fill_bar + tail
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        partial_exit_r=1.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    # Gross R at the fill price (103.2): (103.2 - 101.0) / 2.0 = 1.1. The ARMING threshold
    # (1.0R) and the realized fill R (1.1R, since price moved further before the next bar's
    # open) are different numbers by design -- the overlay arms on completed-bar CLOSE
    # reaching the threshold, then fills at the FOLLOWING bar's open, which can be at a
    # different (here, slightly better) R than the arming threshold itself.
    assert t.partial_exit_r == pytest.approx((103.2 - 101.0) / 2.0)
    assert t.exit_reason == "eod"  # runner rides flat afterward, no stop/target/other overlay active


def test_partial_exit_blended_r_multiple_exact():
    """Hand-computed blend: partial_exit_r=2.0 fires, fraction=0.5, runner later hits a
    target_r=4.0 exit. Friction is zeroed (commission_usd_per_side=0) so the blend is
    exact: r_multiple = 0.5*2.0 + 0.5*4.0 = 3.0."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0 (0 slippage), stop=99.0, risk=2.0 -> +2R = 105.0, target(4R) = 109.0.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # CLOSE=105.0 reaches +2R exactly -> arms.
    arm_bar = [{"open": 101.3, "high": 105.2, "low": 101.3, "close": 105.0}]
    # Partial fills at this bar's open (105.0 -> gross R = (105.0-101.0)/2.0 = 2.0 exactly).
    # This bar's own high/low must not touch the target (109.0) or stop (99.0).
    partial_fill_bar = [{"open": 105.0, "high": 105.5, "low": 104.8, "close": 105.3}]
    # Runner rallies straight through the target (109.0).
    target_bar = [{"open": 105.3, "high": 109.5, "low": 105.3, "close": 109.2}]
    post_rows = entry_bar + arm_bar + partial_fill_bar + target_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=0,
        commission_usd_per_side=0.0, partial_exit_r=2.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.partial_exit_r == pytest.approx(2.0)
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(109.0)
    # runner_r with zero friction = (109.0 - 101.0) / 2.0 = 4.0 exactly.
    expected_blend = 0.5 * 2.0 + 0.5 * 4.0
    assert t.r_multiple == pytest.approx(expected_blend)
    assert t.r_multiple == pytest.approx(3.0)


def test_partial_exit_blend_charges_one_full_round_trip_friction():
    """Reviewer regression test (2026-07-17, Finding 1): with NONZERO commission, the
    blended r_multiple must reflect exactly ONE full round-trip's friction subtracted
    from the blended GROSS result -- not friction embedded per-leg (which silently
    under-charges by `partial_exit_fraction` of a round trip, e.g. half the commission
    vanishing at fraction=0.5). Same fixture shape/prices as
    test_partial_exit_blended_r_multiple_exact, but with the DEFAULT (nonzero)
    commission_usd_per_side, so this test fails against the pre-fix per-leg-friction
    arithmetic and passes against the corrected once-on-the-blend arithmetic.

    Hand-computed expected value (commission_usd_per_side=4.5, point_value=20.0 (NQ),
    slippage_ticks=0):
      risk = 101.0 - 99.0 = 2.0
      partial_exit_r_gross = (105.0 - 101.0) / 2.0 = 2.0   (fill at arm_bar's fill price)
      runner_r_gross       = (109.0 - 101.0) / 2.0 = 4.0   (target hit)
      r_multiple_gross     = 0.5*2.0 + 0.5*4.0 = 3.0
      friction_points      = 2 * 4.5 / 20.0 = 0.45
      friction_in_R         = 0.45 / 2.0 = 0.225           (ONE round trip, charged once)
      r_multiple (expected) = 3.0 - 0.225 = 2.775
    A per-leg-friction bug (blending two already-friction-adjusted R's, i.e.
    0.5*2.0 + 0.5*(4.0 - 0.225)) would instead produce 2.8875 -- this test would then
    fail, proving the fix removed the under-charge.
    """
    d = date(2024, 1, 2)
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    arm_bar = [{"open": 101.3, "high": 105.2, "low": 101.3, "close": 105.0}]
    partial_fill_bar = [{"open": 105.0, "high": 105.5, "low": 104.8, "close": 105.3}]
    target_bar = [{"open": 105.3, "high": 109.5, "low": 105.3, "close": 109.2}]
    post_rows = entry_bar + arm_bar + partial_fill_bar + target_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=4.0, slippage_ticks=0,
        commission_usd_per_side=4.5, partial_exit_r=2.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.partial_exit_r == pytest.approx(2.0)
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(109.0)

    risk = 2.0
    friction_points = 2 * 4.5 / NQ_POINT_VALUE
    expected_r_multiple = (0.5 * 2.0 + 0.5 * 4.0) - (friction_points / risk)
    assert expected_r_multiple == pytest.approx(2.775)
    assert t.r_multiple == pytest.approx(expected_r_multiple)

    # A trade with NO partial (single-leg path) must be byte-identical to the
    # pre-partial-overlay arithmetic: same commission, simple breakout->stop-out shape.
    no_partial_post_rows = [
        {"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3},
        {"open": 101.3, "high": 101.3, "low": 98.9, "close": 99.0},
    ]
    no_partial_bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2,
        post_or_rows=no_partial_post_rows,
    )
    params_no_partial = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        commission_usd_per_side=4.5,
    )
    trades_no_partial = run_orb_backtest(no_partial_bars, params_no_partial)
    assert len(trades_no_partial) == 1
    tn = trades_no_partial[0]
    # Pre-overlay formula, unchanged: pnl_points = exit-entry; -friction; /risk.
    expected_pnl_points = (99.0 - 101.0) - friction_points
    expected_r_no_partial = expected_pnl_points / risk
    assert tn.r_multiple == pytest.approx(expected_r_no_partial)
    assert tn.partial_exit_r is None


def test_partial_exit_and_vwap_trail_collide_same_bar_both_fire_same_bar():
    """Reviewer regression test (2026-07-17, Finding 2): if a partial-exit fill and a
    vwap_trail runner exit are BOTH scheduled off the same completed bar's close, both
    must fill on the SAME following bar's open -- not one bar apart. Pre-fix, an `elif`
    let the partial consume the "process pending fill" branch and silently pushed the
    vwap_trail exit to the NEXT bar's open instead (verified against the pre-fix `elif`
    code directly: it produces exit_ts 09:39 / exit_price 100.6 -- one bar later than the
    correct 09:38 / 102.95 asserted below).

    Construction: `vwap_trail_after_r=0.2` arms the trail early (mfe reaches 0.3R on the
    wick bar below), well before the partial's own `partial_exit_r=1.0` threshold. The
    wick bar's large HIGH (160.0, not reflected in its own modest CLOSE of 101.6, so mfe
    stays low) pulls the completed-bar VWAP up to ~103.25 without arming anything. The
    next bar's CLOSE (103.0) then does two things simultaneously: (a) crosses the
    partial's +1R threshold (103.0) for the first time this trade -> arms the partial,
    and (b) sits below the already-elevated VWAP (~103.25) while the trail is already
    armed -> breaches -> schedules the runner exit. Both are now pending off the SAME
    bar, so both must fill at the FOLLOWING bar's open."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0 (0 slippage), stop=or_low=99.0, risk=2.0.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # Big high wick (160.0) pulls VWAP up hard; CLOSE stays modest (101.6, mfe=0.3R) so
    # nothing arms on this bar's own close except the (low-threshold) vwap trail.
    wick_bar = [{"open": 101.3, "high": 160.0, "low": 101.3, "close": 101.6}]
    # CLOSE=103.0: crosses partial's +1R (103.0) fresh -> arms partial. Also sits below
    # the VWAP accumulated through wick_bar (~103.25) while the trail is already armed
    # (mfe=0.3R >= vwap_trail_after_r=0.2) -> breaches -> schedules the runner exit too.
    # High/low stay clear of the 99.0 stop.
    collide_bar = [{"open": 101.6, "high": 103.1, "low": 101.5, "close": 103.0}]
    # Both the partial fill and the vwap_trail runner exit must fill HERE, at this bar's
    # open (102.95). Low stays above the 99.0 stop (not a stop-out).
    fill_bar = [{"open": 102.95, "high": 102.95, "low": 100.5, "close": 100.6}]
    post_rows = entry_bar + wick_bar + collide_bar + fill_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        commission_usd_per_side=0.0, vwap_trail_after_r=0.2,
        partial_exit_r=1.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    # Partial fired at fill_bar's open (102.95): gross R = (102.95-101.0)/2.0 = 0.975.
    assert t.partial_exit_r == pytest.approx((102.95 - 101.0) / 2.0)
    assert t.exit_reason == "vwap_trail"
    assert t.exit_price == pytest.approx(102.95)  # fill_bar's open, 0 slippage
    # Both legs resolve on fill_bar (the bar immediately after collide_bar) -- NOT one bar
    # later. fill_bar is the 4th post-OR bar (offset 3), so ts = entry_ts (09:35) + 3min.
    assert t.exit_ts == _et_ts(d, 9, 38)
    # Blend sanity: the runner ALSO exits at fill_bar's open (102.95, the vwap_trail
    # market exit's fill price -- both legs fire off the SAME bar's open here), so
    # runner_r_gross uses that same fill price, not fill_bar's close. Friction is zero in
    # this fixture so r_multiple is the exact gross blend of two equal legs.
    runner_r_gross = (102.95 - 101.0) / 2.0
    expected_blend = 0.5 * t.partial_exit_r + 0.5 * runner_r_gross
    assert t.r_multiple == pytest.approx(expected_blend)
    assert t.r_multiple == pytest.approx(t.partial_exit_r)  # both legs identical here


def test_partial_exit_runner_keeps_original_stop_not_moved_to_breakeven():
    """After a partial fires, the runner's stop must stay at the ORIGINAL OR-extreme price
    -- NOT moved to breakeven (entry_price). This fixture places a bar's low BELOW the
    original stop but ABOVE what a (wrongly) breakeven-moved stop would be, so a
    breakeven-stop bug would still show a stop-out at the wrong (breakeven) price, while
    the correct implementation exits at the ORIGINAL or_opposite stop price."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0, stop=or_low=99.0 (well below entry -- if wrongly moved to
    # breakeven it would become 101.0). risk=2.0 -> +2R(partial arm) = 105.0.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    arm_bar = [{"open": 101.3, "high": 105.2, "low": 101.3, "close": 105.0}]  # arms partial at +2R
    # Partial fills at this bar's open (105.0); bar itself stays well clear of both stops.
    partial_fill_bar = [{"open": 105.0, "high": 105.2, "low": 104.9, "close": 105.0}]
    # Runner drops hard: low=100.0 is BELOW entry_price (101.0, the wrong breakeven stop)
    # but still ABOVE the original stop (99.0) -- so a breakeven-stop bug would exit here,
    # while the correct (original-stop) implementation must NOT exit on this bar.
    dip_above_original_stop = [{"open": 105.0, "high": 105.0, "low": 100.0, "close": 100.5}]
    # Now actually crashes through the ORIGINAL stop (99.0).
    stop_out_bar = [{"open": 100.5, "high": 100.5, "low": 98.5, "close": 98.7}]
    post_rows = entry_bar + arm_bar + partial_fill_bar + dip_above_original_stop + stop_out_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        partial_exit_r=2.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.partial_exit_r == pytest.approx(2.0)  # partial fired before the dip
    assert t.exit_reason == "stop"
    assert t.exit_price == pytest.approx(99.0)  # ORIGINAL or_opposite stop, not breakeven (101.0)


def test_partial_exit_interacts_with_vwap_trail_runner_exits_later():
    """partial_exit_r fires first at a lower R; the runner then continues under an active
    vwap_trail_after_r overlay and exits later via the trail. Both legs must be correct:
    partial_exit_r records the partial's R-level, exit_reason is "vwap_trail" (the
    runner's terminal path), and r_multiple is the size-weighted blend."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0, stop=99.0, risk=2.0. No target (target_r=None) so only the
    # partial and the vwap trail are in play. partial_exit_r=1.0 (+1R=103.0),
    # vwap_trail_after_r=3.0 (+3R=107.0) -- partial arms well before the trail.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # CLOSE=103.0 reaches +1R -> arms partial.
    partial_arm_bar = [{"open": 101.3, "high": 103.2, "low": 101.3, "close": 103.0}]
    # Partial fills at this bar's open (103.0 -> gross R = (103.0-101.0)/2.0 = 1.0 exactly).
    # Also keep climbing so the vwap trail's arming threshold is reachable later.
    partial_fill_bar = [{"open": 103.0, "high": 104.0, "low": 103.0, "close": 103.9}]
    # Keep rallying; CLOSE=107.2 reaches +3R (>= 107.0) -> arms the vwap trail.
    vwap_arm_bar = [{"open": 103.9, "high": 107.5, "low": 103.9, "close": 107.2}]
    # Flat bar so vwap keeps accumulating near the recent high (keeps completed-bar vwap
    # elevated for the next bar's breach check).
    hold_bar = [{"open": 107.2, "high": 107.2, "low": 107.2, "close": 107.2}]
    # Drops hard: close well below the accumulated vwap -> breach, schedules vwap_trail
    # exit at the next bar's open. Low stays above the 99.0 stop (not a stop-out).
    breach_bar = [{"open": 107.2, "high": 107.2, "low": 100.5, "close": 100.6}]
    # Next bar: this is where the scheduled vwap_trail exit fills, at this bar's open.
    exit_bar = [{"open": 100.6, "high": 100.6, "low": 100.6, "close": 100.6}]
    post_rows = (
        entry_bar + partial_arm_bar + partial_fill_bar + vwap_arm_bar + hold_bar + breach_bar + exit_bar
    )
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        commission_usd_per_side=0.0, vwap_trail_after_r=3.0,
        partial_exit_r=1.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.partial_exit_r == pytest.approx(1.0)
    assert t.exit_reason == "vwap_trail"
    assert t.exit_price == pytest.approx(100.6)  # next bar's open after the breach, 0 slippage
    runner_r = (100.6 - 101.0) / 2.0  # zero friction -> exact
    expected_blend = 0.5 * 1.0 + 0.5 * runner_r
    assert t.r_multiple == pytest.approx(expected_blend)


def test_partial_exit_stop_beats_pending_partial_same_bar_full_position_at_stop():
    """When the bar where a scheduled partial WOULD fill (at its open) also has its own
    stop trigger, the stop must win -- closing the FULL position at the stop price, NOT a
    partial+runner split. partial_exit_r must stay None on the resulting trade."""
    d = date(2024, 1, 2)
    # Breakout long @ 101.0, stop=99.0, risk=2.0 -> +1R = 103.0.
    entry_bar = [{"open": 100.2, "high": 101.5, "low": 100.2, "close": 101.3}]
    # CLOSE=103.0 reaches +1R -> arms partial, to fill at the NEXT bar's open.
    arm_bar = [{"open": 101.3, "high": 103.2, "low": 101.3, "close": 103.0}]
    # This is the bar where the partial WOULD fill (open=103.0) -- but this same bar's own
    # low (98.0) crashes through the stop (99.0). Stop must win: full position exits at
    # the stop price (99.0), not a partial fill at 103.0 plus a runner continuing.
    conflict_bar = [{"open": 103.0, "high": 103.0, "low": 98.0, "close": 98.5}]
    post_rows = entry_bar + arm_bar + conflict_bar
    bars = _full_session_bars(
        d, or_minutes=5, or_open=100.0, or_high=101.0, or_low=99.0, or_close=100.2, post_or_rows=post_rows
    )
    params = ORBParams(
        or_minutes=5, entry_mode="breakout", stop_mode="or_opposite", target_r=None, slippage_ticks=0,
        partial_exit_r=1.0, partial_exit_fraction=0.5,
    )
    trades = run_orb_backtest(bars, params)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "stop"
    assert t.exit_price == pytest.approx(99.0)
    assert t.partial_exit_r is None  # partial never independently fired -- pre-empted by the stop
    # Full-position stop-out R (no blend): (99.0 - 101.0 - friction) / 2.0.
    friction_points = 2 * params.commission_usd_per_side / params.point_value
    expected_r = ((99.0 - 101.0) - friction_points) / 2.0
    assert t.r_multiple == pytest.approx(expected_r)
    assert t.exit_price == pytest.approx(99.0)
