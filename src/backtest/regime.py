"""Causal regime-gate signals for the frozen ORB base config (Phase 6A-R).

Post-hoc filters applied to an already-computed, UNFILTERED "shadow" trade
list -- this module never touches `src/backtest/orb.py`'s decision logic.
Two signal families, per the pre-registered spec in Tasks/todo.md
"Phase 6A-R":

  (A) Kaufman Efficiency Ratio (`kaufman_er`) on daily RTH closes -- a
      trend-persistence proxy (net directional move / total path length).
  (B) Trailing shadow-ORB performance (`trailing_shadow_r`) -- mean R of the
      last K shadow (unfiltered) trades strictly before the session being
      gated.

Both signals are computed causally: the signal attached to session date `t`
uses only information available at or before `t`'s own decision point
(09:35 ET for the frozen config), and is used to gate `t`'s own trade via
`apply_gate`. Every function in this module is covered by an explicit
no-lookahead test in tests/test_regime.py (mutate future data, assert
today's signal is unchanged) -- lookahead in these signals is the single
biggest risk in this phase (see Tasks/todo.md "Reviewer pass ... lookahead
in signals = the kill risk").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.backtest.orb import Trade
from src.strategies.replay import ReplayDay


def kaufman_er(daily_closes: pd.Series, lookback: int) -> pd.Series:
    """Kaufman Efficiency Ratio, indexed by session_date, causal (shift(1)).

    ER[t-1] = |C[t-1] - C[t-1-lookback]| / sum(|C[i] - C[i-1]| for i in
    (t-1-lookback, t-1]) -- i.e. net directional displacement over the
    `lookback`-day window ending YESTERDAY, divided by the total path
    length (sum of daily absolute changes) over that same window. ER is in
    [0, 1]: 1.0 means every day moved in the same direction (pure trend),
    0.0 means the path fully round-tripped (pure chop).

    `daily_closes` must be indexed by `session_date` (a `datetime.date`),
    sorted ascending, one row per RTH session -- exactly the shape
    `src.backtest.orb._daily_ohlcv(sessions)["close"]` produces.

    Returned series is indexed the SAME as `daily_closes` (one entry per
    session date `t`), but every value is computed from closes strictly
    BEFORE `t` (`.shift(1)` moves "the window ending at t-1" onto row t) --
    this is what makes it safe to use as session `t`'s own gating signal
    without leaking `t`'s own (not-yet-known-at-09:35) close into the
    computation. The first `lookback` rows (plus the shift) are NaN
    (insufficient warmup history); `apply_gate` treats NaN as "block the
    trade" (conservative default -- see module docstring and `apply_gate`).
    """
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if not daily_closes.index.is_monotonic_increasing:
        raise ValueError("daily_closes must be sorted ascending by session_date")

    daily_change = daily_closes.diff()
    net_change = daily_closes.diff(lookback).abs()
    path_length = daily_change.abs().rolling(lookback, min_periods=lookback).sum()

    er = net_change / path_length
    # path_length == 0 only when every daily change in the window is exactly
    # zero (a fully flat market) -- 0/0 -> NaN via pandas, which then blocks
    # the trade via apply_gate's NaN handling (conservative default, not a
    # forced "efficient" or "inefficient" read of a degenerate window).
    return er.shift(1)


def trailing_shadow_r(shadow_trades: list[Trade], trade_dates: list[date], K: int) -> pd.Series:
    """Mean R of the last K shadow trades strictly before each date in `trade_dates`.

    Causal invariant (load-bearing, states why this is safe): the frozen
    ORB config is ALWAYS flat by end-of-day (`exit_reason="eod"` mandatory
    flatten, or an earlier stop/target/time_stop exit -- see
    src/backtest/orb.py's no-overnight-position contract). That means every
    shadow trade with `session_date < d` has ALREADY FULLY RESOLVED (entry
    AND exit both known) well before session `d`'s own 09:35 ET
    OR-completion decision. There is no possible ordering of intraday
    events on day `d-1` and day `d` that could leak day `d-1`'s trade
    OUTCOME into day `d`'s gate, because day `d-1`'s position is closed
    hours before day `d` even opens. `shadow_trades` must be the
    UNFILTERED backtest output (not a previously-gated list) specifically
    so the trailing window keeps advancing through a dormant (gated-out)
    stretch instead of stalling on a shrinking or stale trade count -- see
    module docstring.

    `trade_dates` is the list of session dates to compute a signal FOR
    (typically every session date in the fold, trade or not, so `apply_gate`
    has a value to look up for every row). Returns a Series indexed by
    `trade_dates` (in the given order); NaN wherever fewer than K prior
    shadow trades exist (insufficient history -- blocks the trade, same
    conservative default as `kaufman_er`).
    """
    if K <= 0:
        raise ValueError("K must be positive")
    sorted_shadow = sorted(shadow_trades, key=lambda t: t.session_date)
    shadow_dates = [t.session_date for t in sorted_shadow]
    shadow_r = [t.r_multiple for t in sorted_shadow]

    import bisect

    values = []
    for d in trade_dates:
        # Index of the first shadow trade at or after `d` -- everything
        # strictly before that index has session_date < d (strict
        # inequality preserves the causal invariant: a shadow trade ON day
        # `d` itself, if `d` happens to also be a shadow-trade date, must
        # NOT be included, since it hasn't happened yet at d's own
        # decision point).
        cutoff = bisect.bisect_left(shadow_dates, d)
        if cutoff < K:
            values.append(float("nan"))
            continue
        window = shadow_r[cutoff - K : cutoff]
        values.append(sum(window) / K)

    return pd.Series(values, index=pd.Index(trade_dates, name="session_date"))


def apply_gate(
    shadow_trades: list[Trade],
    signal_by_date: pd.Series,
    threshold: float,
) -> list[Trade]:
    """Drop shadow trades whose session_date's signal is < threshold or NaN.

    NaN (insufficient warmup / insufficient trailing trade history) is
    treated as "block the trade" -- the conservative default stated in the
    docstrings of `kaufman_er` and `trailing_shadow_r`: an unreadable regime
    signal is never treated as permission to trade. `signal_by_date` must be
    indexed by `session_date` (a `datetime.date`); a shadow trade whose date
    is missing from the index is also blocked (same conservative default,
    covers a signal series that wasn't built over the full session
    universe).
    """
    kept = []
    for t in shadow_trades:
        signal = signal_by_date.get(t.session_date)
        if signal is None or pd.isna(signal):
            continue
        if signal < threshold:
            continue
        kept.append(t)
    return kept


@dataclass(frozen=True)
class RegimeFilterSpec:
    """One point in the pre-registered Phase 6A-R grid (Tasks/todo.md).

    `family` is "er" (Kaufman Efficiency Ratio) or "trailing_r" (trailing
    shadow-ORB mean R); `lookback_or_k` is the ER lookback (10 or 20) or the
    trailing-R K (20 or 40) depending on family; `threshold` is the ER
    threshold (0.25 or 0.35) or the trailing-R threshold (0.0 or 0.05).
    `label` is a short human-readable name used in output tables/filenames.
    """

    label: str
    family: str  # "er" | "trailing_r" | "unfiltered"
    lookback_or_k: int | None
    threshold: float | None

    def __post_init__(self) -> None:
        if self.family not in ("er", "trailing_r", "unfiltered"):
            raise ValueError(f"unknown family: {self.family!r}")
        if self.family != "unfiltered" and (self.lookback_or_k is None or self.threshold is None):
            raise ValueError("lookback_or_k and threshold are required for filtered families")


def gated_trades_for_spec(
    spec: RegimeFilterSpec,
    *,
    shadow_trades: list[Trade],
    daily_closes: pd.Series,
    session_dates: list[date],
) -> list[Trade]:
    """Resolve one RegimeFilterSpec against a fold's shadow trades -> gated Trade list.

    `daily_closes` and `session_dates` must span (at least) the fold's full
    warmup+OOS window -- `daily_closes` needs enough history before the OOS
    window for the ER/trailing-R lookback to warm up; `session_dates` is the
    OOS window's own session calendar (one signal lookup per session,
    whether or not a shadow trade happened that day, so `apply_gate` always
    has something to check a shadow trade's date against).
    """
    if spec.family == "unfiltered":
        return list(shadow_trades)
    if spec.family == "er":
        signal = kaufman_er(daily_closes, spec.lookback_or_k)
        signal_by_date = signal.reindex(session_dates)
    elif spec.family == "trailing_r":
        signal_by_date = trailing_shadow_r(shadow_trades, session_dates, spec.lookback_or_k)
    else:  # pragma: no cover - guarded by __post_init__
        raise ValueError(f"unknown family: {spec.family!r}")
    return apply_gate(shadow_trades, signal_by_date, spec.threshold)


def replay_days_from_trades(trades: list[Trade], sessions) -> list[ReplayDay]:
    """Thin re-export of the same conversion `run_orb_backtest`'s callers use.

    Kept here (rather than importing `trades_to_replay_days` at every call
    site) purely so `Analysis/scripts/orb_regime_filter_run.py` has one
    import path for both regime-gate application and the ReplayDay
    conversion it always needs immediately afterward.
    """
    from src.backtest.orb import trades_to_replay_days

    return trades_to_replay_days(trades, sessions)
