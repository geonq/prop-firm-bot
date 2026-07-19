"""Unit tests for src/backtest/regime.py -- causal regime-gate signals.

Lookahead in these signals is the single biggest risk in Phase 6A-R (see
Tasks/todo.md "Phase 6A-R" reviewer-pass note), so every signal function has
an explicit mutate-the-future-and-assert-nothing-changed test in addition to
hand-computed value checks.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.backtest.regime import (
    RegimeFilterSpec,
    apply_gate,
    gated_trades_for_spec,
    kaufman_er,
    trailing_shadow_r,
)
from src.backtest.orb import Trade


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _trade(d: date, r: float) -> Trade:
    ts = pd.Timestamp(d).tz_localize("UTC")
    return Trade(
        session_date=d,
        direction="long",
        entry_ts=ts,
        entry_price=100.0,
        exit_ts=ts,
        exit_price=100.0 + r,
        r_multiple=r,
        pnl_points=r,
        pnl_usd_per_contract=r * 20.0,
        exit_reason="target" if r > 0 else "stop",
    )


# ---------------------------------------------------------------------------
# kaufman_er
# ---------------------------------------------------------------------------


def test_kaufman_er_hand_computed():
    dates = _dates(6)
    closes = pd.Series([100.0, 102.0, 101.0, 105.0, 104.0, 108.0], index=dates)
    er = kaufman_er(closes, lookback=3)

    # raw ER at day index 3 (close=105): net=|105-100|=5, path=|102-100|+|101-102|+|105-101|=2+1+4=7
    assert er.loc[dates[4]] == pytest.approx(5 / 7)
    # raw ER at day index 4 (close=104): net=|104-102|=2, path=|101-102|+|105-101|+|104-105|=1+4+1=6
    assert er.loc[dates[5]] == pytest.approx(2 / 6)
    # warmup: first lookback+1 rows (shift eats one more) are NaN
    assert er.loc[dates[0]:dates[3]].isna().all()


def test_kaufman_er_pure_trend_is_one():
    dates = _dates(6)
    closes = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0], index=dates)
    er = kaufman_er(closes, lookback=3)
    assert er.loc[dates[4]] == pytest.approx(1.0)
    assert er.loc[dates[5]] == pytest.approx(1.0)


def test_kaufman_er_full_round_trip_is_zero():
    dates = _dates(6)
    # up 2, down 2, back to start over a 4-day window, then flat -> net displacement 0
    closes = pd.Series([100.0, 102.0, 104.0, 102.0, 100.0, 100.0], index=dates)
    er = kaufman_er(closes, lookback=4)
    # raw ER at idx4 (close=100): net=|100-100|=0, path=2+2+2+2=8 -> 0/8=0.0, appears at idx5 after shift(1)
    assert er.loc[dates[5]] == pytest.approx(0.0)


def test_kaufman_er_requires_sorted_index():
    dates = _dates(4)
    closes = pd.Series([1.0, 2.0, 3.0, 4.0], index=list(reversed(dates)))
    with pytest.raises(ValueError):
        kaufman_er(closes, lookback=2)


def test_kaufman_er_rejects_non_positive_lookback():
    dates = _dates(4)
    closes = pd.Series([1.0, 2.0, 3.0, 4.0], index=dates)
    with pytest.raises(ValueError):
        kaufman_er(closes, lookback=0)


def test_kaufman_er_no_lookahead_future_close_mutation_does_not_change_past_signal():
    """The actual no-lookahead proof: today's ER must be identical whether or
    not FUTURE closes (after today) are later revised to something wildly
    different -- since the signal at day t only reads closes through t-1.
    """
    dates = _dates(10)
    base_closes = [100.0, 103.0, 106.0, 104.0, 108.0, 111.0, 109.0, 113.0, 116.0, 112.0]
    closes_a = pd.Series(base_closes, index=dates)

    # Mutate everything from day index 6 onward to wildly different values.
    mutated = list(base_closes)
    for i in range(6, len(mutated)):
        mutated[i] = 9999.0
    closes_b = pd.Series(mutated, index=dates)

    er_a = kaufman_er(closes_a, lookback=3)
    er_b = kaufman_er(closes_b, lookback=3)

    # Signal values through day index 6 (inclusive) must be identical: er[t] only
    # depends on closes through t-1, and closes[0:6] are unchanged between A and B,
    # so er[0..6] must match (er[6] depends on closes[2..5], all unmutated).
    for i in range(0, 7):
        a, b = er_a.loc[dates[i]], er_b.loc[dates[i]]
        if pd.isna(a):
            assert pd.isna(b)
        else:
            assert a == pytest.approx(b)

    # Sanity: the mutation actually DOES perturb later signal values (otherwise this
    # test would vacuously pass regardless of whether shift(1) is present at all).
    assert er_a.loc[dates[9]] != pytest.approx(er_b.loc[dates[9]])


# ---------------------------------------------------------------------------
# trailing_shadow_r
# ---------------------------------------------------------------------------


def test_trailing_shadow_r_hand_computed():
    dates = _dates(6)
    shadow = [_trade(dates[0], 1.0), _trade(dates[1], -1.0), _trade(dates[2], 2.0), _trade(dates[3], -0.5)]
    # signal for dates[4]: last K=3 trades strictly before dates[4] -> trades at dates[1,2,3] -> mean(-1,2,-0.5)
    sig = trailing_shadow_r(shadow, [dates[4]], K=3)
    assert sig.loc[dates[4]] == pytest.approx((-1.0 + 2.0 - 0.5) / 3)


def test_trailing_shadow_r_excludes_same_day_trade():
    """A shadow trade ON the date being scored must NOT count toward its own signal
    (session_date < d is strict, not <=) -- this is the actual causal boundary.
    """
    dates = _dates(5)
    shadow = [_trade(dates[0], 1.0), _trade(dates[1], 1.0), _trade(dates[2], 1.0), _trade(dates[3], -100.0)]
    # scoring dates[3] itself: only trades strictly before dates[3] count (dates[0..2]), K=3
    sig = trailing_shadow_r(shadow, [dates[3]], K=3)
    assert sig.loc[dates[3]] == pytest.approx(1.0)  # mean(1,1,1), NOT polluted by the -100 trade on dates[3] itself


def test_trailing_shadow_r_insufficient_history_is_nan():
    dates = _dates(5)
    shadow = [_trade(dates[0], 1.0), _trade(dates[1], 1.0)]
    sig = trailing_shadow_r(shadow, [dates[2]], K=5)
    assert pd.isna(sig.loc[dates[2]])


def test_trailing_shadow_r_rejects_non_positive_k():
    with pytest.raises(ValueError):
        trailing_shadow_r([], [date(2024, 1, 1)], K=0)


def test_trailing_shadow_r_no_lookahead_future_trade_mutation_does_not_change_past_signal():
    """Mutating/adding shadow trades on or after day t must not change t's own signal."""
    dates = _dates(10)
    shadow_a = [_trade(dates[i], float(i)) for i in range(5)]  # trades on days 0..4
    query_date = dates[5]

    sig_a = trailing_shadow_r(shadow_a, [query_date], K=3)

    # Now mutate/extend with trades ON and AFTER query_date with wildly different R.
    shadow_b = list(shadow_a) + [_trade(dates[5], 9999.0), _trade(dates[6], -9999.0), _trade(dates[7], 9999.0)]
    sig_b = trailing_shadow_r(shadow_b, [query_date], K=3)

    assert sig_a.loc[query_date] == pytest.approx(sig_b.loc[query_date])
    # Sanity: had the future trades been (wrongly) included, the signal would have
    # been wildly different -- confirms this isn't a vacuous "nothing changed" test.
    assert sig_a.loc[query_date] == pytest.approx((2.0 + 3.0 + 4.0) / 3)


def test_trailing_shadow_r_survives_dormant_stretch():
    """A gated-out (dormant) stretch in the FILTERED trade list must not stall the
    trailing window -- this is exactly why the spec requires shadow_trades to
    always be the UNFILTERED list: the signal keeps advancing through history
    that a filtered list would have dropped.
    """
    dates = _dates(30)
    shadow = [_trade(dates[i], 1.0) for i in range(0, 10)]  # 10 shadow trades, all in the first third
    query_date = dates[29]  # long after the last shadow trade
    sig = trailing_shadow_r(shadow, [query_date], K=5)
    # Still resolves (uses the last 5 of the 10 shadow trades, regardless of the
    # long dormant gap between them and query_date) rather than going NaN just
    # because trading activity paused.
    assert sig.loc[query_date] == pytest.approx(1.0)


def test_trailing_shadow_r_needs_pre_window_history_not_just_in_window_trades():
    """Regression coverage for a real bug found while building
    Analysis/scripts/orb_regime_filter_run.py (2026-07-18): a fold's
    trailing-R signal must be computed from shadow trades spanning the
    fold's FULL warmup+OOS history, not just trades that happen to fall
    inside the OOS-scored window -- otherwise the first K trading days of
    every OOS window spuriously read NaN/blocked even when real prior
    trading history existed (just outside the scored window). This test
    demonstrates the failure mode directly: scoring the same query date with
    only "in-window" shadow trades available (as if the fold's warmup-period
    trades had been wrongly clipped away before this function ever saw
    them) produces NaN, while including the full history resolves cleanly
    to the correct trailing mean -- proving `trailing_shadow_r` itself does
    the right thing GIVEN sufficient history; the caller is responsible for
    actually supplying that history (which is why the fix belongs in the
    script's shadow-trade construction, not in this function).
    """
    dates = _dates(15)
    # 8 shadow trades entirely BEFORE the "OOS window" boundary (day 10).
    pre_window_shadow = [_trade(dates[i], 1.0) for i in range(2, 10)]
    query_date = dates[10]  # first day of the "OOS window"

    # Wrongly clipped: only trades inside [query_date, ...) are visible -> none exist yet -> NaN.
    clipped_shadow = [t for t in pre_window_shadow if t.session_date >= query_date]
    sig_clipped = trailing_shadow_r(clipped_shadow, [query_date], K=5)
    assert pd.isna(sig_clipped.loc[query_date])

    # Correctly given full history (including the pre-window trades) -> resolves.
    sig_full = trailing_shadow_r(pre_window_shadow, [query_date], K=5)
    assert sig_full.loc[query_date] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# apply_gate
# ---------------------------------------------------------------------------


def test_apply_gate_drops_below_threshold():
    dates = _dates(3)
    trades = [_trade(d, 1.0) for d in dates]
    signal = pd.Series([0.5, 0.1, 0.9], index=dates)
    kept = apply_gate(trades, signal, threshold=0.3)
    assert [t.session_date for t in kept] == [dates[0], dates[2]]


def test_apply_gate_drops_nan():
    dates = _dates(3)
    trades = [_trade(d, 1.0) for d in dates]
    signal = pd.Series([0.5, float("nan"), 0.9], index=dates)
    kept = apply_gate(trades, signal, threshold=0.0)
    assert [t.session_date for t in kept] == [dates[0], dates[2]]


def test_apply_gate_drops_missing_date():
    dates = _dates(3)
    trades = [_trade(d, 1.0) for d in dates]
    signal = pd.Series([0.5, 0.9], index=[dates[0], dates[2]])  # dates[1] missing entirely
    kept = apply_gate(trades, signal, threshold=0.0)
    assert [t.session_date for t in kept] == [dates[0], dates[2]]


def test_apply_gate_threshold_is_exclusive_lower_bound():
    """signal < threshold drops; signal == threshold is KEPT (not dropped)."""
    dates = _dates(1)
    trades = [_trade(dates[0], 1.0)]
    signal = pd.Series([0.3], index=dates)
    assert apply_gate(trades, signal, threshold=0.3) == trades
    assert apply_gate(trades, signal, threshold=0.30001) == []


def test_apply_gate_empty_input():
    assert apply_gate([], pd.Series(dtype=float), threshold=0.0) == []


# ---------------------------------------------------------------------------
# RegimeFilterSpec / gated_trades_for_spec
# ---------------------------------------------------------------------------


def test_regime_filter_spec_validates_family():
    with pytest.raises(ValueError):
        RegimeFilterSpec(label="bad", family="not_a_family", lookback_or_k=10, threshold=0.25)


def test_regime_filter_spec_requires_params_for_filtered_family():
    with pytest.raises(ValueError):
        RegimeFilterSpec(label="er_missing", family="er", lookback_or_k=None, threshold=0.25)
    with pytest.raises(ValueError):
        RegimeFilterSpec(label="er_missing2", family="er", lookback_or_k=10, threshold=None)


def test_regime_filter_spec_unfiltered_allows_none_params():
    spec = RegimeFilterSpec(label="unfiltered", family="unfiltered", lookback_or_k=None, threshold=None)
    assert spec.family == "unfiltered"


def test_gated_trades_for_spec_unfiltered_returns_all_shadow_trades():
    dates = _dates(5)
    shadow = [_trade(d, 1.0) for d in dates]
    closes = pd.Series([100.0 + i for i in range(5)], index=dates)
    spec = RegimeFilterSpec(label="unfiltered", family="unfiltered", lookback_or_k=None, threshold=None)
    gated = gated_trades_for_spec(spec, shadow_trades=shadow, daily_closes=closes, session_dates=dates)
    assert gated == shadow


def test_gated_trades_for_spec_er_family_gates_correctly():
    dates = _dates(10)
    # Strong uptrend -> ER should be near 1.0 everywhere it's defined -> nothing gated
    closes = pd.Series([100.0 + i for i in range(10)], index=dates)
    shadow = [_trade(d, 1.0) for d in dates]
    spec = RegimeFilterSpec(label="er10_025", family="er", lookback_or_k=3, threshold=0.25)
    gated = gated_trades_for_spec(spec, shadow_trades=shadow, daily_closes=closes, session_dates=dates)
    # warmup days (first ~4) blocked (NaN signal), rest kept (ER=1.0 > 0.25 in a pure trend)
    gated_dates = {t.session_date for t in gated}
    assert dates[0] not in gated_dates  # warmup, always blocked
    assert dates[9] in gated_dates  # well past warmup, strong trend -> kept


def test_gated_trades_for_spec_trailing_r_family_gates_correctly():
    dates = _dates(10)
    closes = pd.Series([100.0 + i for i in range(10)], index=dates)
    # Shadow trades: losers for the first 5 days, winners after -- the trailing-R
    # gate should block early (trailing mean negative) and allow later (trailing mean positive).
    shadow = [_trade(dates[i], -1.0 if i < 5 else 1.0) for i in range(10)]
    spec = RegimeFilterSpec(label="trailingR_k3_0", family="trailing_r", lookback_or_k=3, threshold=0.0)
    gated = gated_trades_for_spec(spec, shadow_trades=shadow, daily_closes=closes, session_dates=dates)
    gated_dates = {t.session_date for t in gated}
    assert dates[9] in gated_dates  # trailing 3 trades all winners -> mean 1.0 > 0.0 -> kept
    assert dates[2] not in gated_dates  # trailing losers or insufficient history -> blocked
