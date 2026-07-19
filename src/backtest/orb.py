"""Bar-driven Opening Range Breakout backtester with a hard no-lookahead contract.

Decisions use only bars completed strictly before the decision point. The OR
is the first `or_minutes` of RTH; entries can only trigger starting from the
first bar whose open is at or after the OR-window close. Indicators (ATR,
realized-vol percentile, relative volume) are computed from prior sessions
only — never the current session.

Intra-bar ambiguity (a single bar's high/low range crosses both the stop and
the target, or both the entry trigger and the stop) is resolved
conservatively: the worst plausible ordering for the trade is assumed. A
breakout entry bar that also touches the stop is treated as stopped out on
entry's own bar only if the stop is on the far side of the trigger already
crossed conservatively (see `_simulate_session` for the exact ordering).

Optional exit overlays (all default-OFF; a run with every overlay at its
default is bit-identical to the pre-overlay backtester — see
`test_all_new_params_default_off_bit_identical` in tests/test_orb_backtest.py):

- `hold_into_close` (Baltussen et al., JFE 2021 gamma-hedging overlay): at the
  first bar whose ET clock time is >= 15:30, if the position is still open,
  the decision to cancel the R-target for the rest of the session uses that
  bar's OPEN price only (known at decision time, no intra-bar peeking). If
  unrealized PnL at that open is positive, the R-target is cancelled (stop
  stays active) and the trade rides to the mandatory EoD flat. If unrealized
  is <= 0 at that open, behavior is unchanged.
- `vwap_trail_after_r` (Zarattini SPY 2024 / Maroy 2025): session VWAP is
  cumulative sum(typical_price * volume) / sum(volume) over RTH bars of the
  CURRENT session only, computed on COMPLETED bars. The VWAP used for a
  decision made while processing bar t is the VWAP accumulated through bar
  t-1 (bar t's own volume/price has not happened yet from the decision's
  point of view). Once the trade's favorable excursion has reached
  `vwap_trail_after_r` R on a completed-bar-close basis, the exit arms: the
  next completed bar that CLOSES beyond VWAP against the position (long:
  close < vwap; short: close > vwap) triggers a market exit at the
  following bar's open. Stop and target remain active throughout (and take
  precedence intra-bar, stop-first on same-bar conflicts) unless
  `hold_into_close` has already cancelled the target.
- `time_stop_minutes` (Howard 2026): if the trade has not reached +1R
  favorable excursion (completed-bar-close basis) within N minutes of the
  entry fill, it exits at the next bar's open. Stop/target (and the VWAP
  trail once armed) still take precedence intra-bar per the existing
  conservative same-bar rules.
- `partial_exit_r` / `partial_exit_fraction` (Maroy 2025 stepped
  partial-profit-taking; exact paper parameters unconfirmed at implementation
  time -- see `test_partial_exit_*` docstrings for the placeholder grid used
  in tests): once the trade's favorable excursion first reaches
  `partial_exit_r` R on a completed-bar-close basis (same MFE convention as
  `vwap_trail_after_r`), a partial exit for `partial_exit_fraction` of the
  position arms and fills at the NEXT bar's open (adverse `_fill_price`,
  same as the other overlay-driven exits) -- UNLESS that next bar's own
  stop/target fires first, in which case stop-first precedence closes the
  FULL position there and the partial never independently fires (see
  same-bar-conflict note below). After a partial fires, the stop stays at
  its ORIGINAL OR-extreme price (never moved to breakeven -- breakeven-stop
  was explicitly rejected by Howard 2026 elsewhere in this codebase) and the
  runner continues under whatever other exit rules are active (target /
  vwap_trail / time_stop / eod), evaluated exactly as if the position had
  never been partially closed, since none of those rules depend on position
  size. The Trade's single `r_multiple` field remains one float: both legs'
  R are computed GROSS (no friction on either leg individually), blended by
  `partial_exit_fraction`, and then ONE full round-trip's friction (the same
  `commission_usd_per_side`-derived constant the single-leg path already
  uses) is subtracted from the blended total exactly once -- never per leg.
  Charging friction per leg (e.g. by blending two already-friction-adjusted
  R values) would under-charge the trade by `partial_exit_fraction` of a
  round trip; see `_simulate_session` for the exact arithmetic and
  `test_partial_exit_blend_charges_one_full_round_trip_friction` for the
  regression test (reviewer finding 2026-07-17, Finding 1).
  `exit_reason` records the RUNNER's terminal exit path (or "stop"/"target"
  if the full position closed before any partial could fire); a separate
  `Trade.partial_exit_r` field records the R-level a partial fired at
  (`None` if no partial fired), so downstream aggregate stats can
  distinguish laddered trades from single-leg ones without needing a second
  r_multiple.

All overlay-driven exits that aren't stop/target trigger-price fills (i.e.
the VWAP-trail exit, the time-stop exit, and the partial-profit fill) fill
via the existing adverse `_fill_price` helper at the next bar's open,
exactly like a market order. Terminal-bar edge: an overlay breach detected
on the last RTH bar has no next bar to fill at, so the trade falls through
to the mandatory EoD flat at the last close and is labeled
`exit_reason="eod"` (conservative; reviewer finding 2026-07-17 #1). A
pending partial that never gets a next bar to fill at is dropped the same
way -- it simply never fires, and the (now-unpartialed) full position rides
to the mandatory EoD flat like any other trade with no active overlay.

Same-bar precedence with a pending partial fill (mirrors the existing
stop-first convention used for vwap_trail/time_stop): if the bar where a
scheduled partial WOULD fill (at that bar's open) also has its own
stop or target trigger, stop wins first, then target -- either one closes
the FULL remaining position at that bar, and the partial is simply never
applied (it does not "partially apply" retroactively). This is identical in
spirit to how a pending vwap_trail/time_stop exit is pre-empted by a
same-bar stop/target today; the partial-fill slot uses the same fall-through
rule.

Same-bar COLLISION between a pending partial and a pending runner exit
(vwap_trail/time_stop): both can be scheduled off the same bar's close (the
partial arms and the runner overlay's exit both look at the same
completed-bar MFE/VWAP/deadline state), in which case both fill on the SAME
following bar's open -- the partial fill is applied first (reducing size),
then the runner's scheduled exit is also applied on that identical bar,
rather than deferring the runner's exit to the bar after. (Fixed 2026-07-17,
reviewer Finding 2 -- an earlier version used `elif` here and silently
delayed the runner's exit by one extra bar whenever a collision occurred.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from src.backtest.sessions import ET, Session, build_rth_sessions
from src.strategies.replay import ReplayDay

EntryMode = Literal["breakout", "first_candle", "strangle"]
StopMode = Literal["or_opposite", "atr_frac"]
Direction = Literal["long", "short"]
ExitReason = Literal["stop", "target", "eod", "vwap_trail", "time_stop"]

HOLD_INTO_CLOSE_ET_TIME = time(15, 30)

NQ_TICK = 0.25
NQ_POINT_VALUE = 20.0
MNQ_POINT_VALUE = 2.0


@dataclass(frozen=True)
class ORBParams:
    """All dimensions of the ORB strategy family. See module docstring for the no-lookahead contract."""

    or_minutes: int = 5
    entry_mode: EntryMode = "breakout"
    stop_mode: StopMode = "or_opposite"
    target_r: float | None = None

    # first_candle
    doji_threshold: float = 0.1  # body/range fraction below which OR candle is a doji -> skip

    # strangle
    strangle_rho: float = 0.1  # entry offsets = open +/- rho * daily ATR(14)

    # atr_frac stop
    stop_atr_frac: float = 0.5

    # filters (None / 0 disables)
    vol_percentile_min: float | None = None  # 20-day realized-vol percentile, prior-session only
    rel_volume_min: float | None = None  # OR-window volume / trailing 14-session avg of same window
    max_overnight_gap_atr: float | None = None  # skip if |prior RTH close -> today's RTH open| > x * daily ATR(14)
    allowed_weekdays: frozenset[int] | None = None  # Monday=0 ... Sunday=6

    # friction
    commission_usd_per_side: float = 4.5
    slippage_ticks: float = 1.0
    point_value: float = NQ_POINT_VALUE
    tick_size: float = NQ_TICK

    # indicator lookbacks
    atr_lookback: int = 14
    vol_lookback: int = 20
    rel_volume_lookback: int = 14

    # exit overlays (all default-OFF; see module docstring section on exit mechanisms)
    hold_into_close: bool = False
    vwap_trail_after_r: float | None = None
    time_stop_minutes: int | None = None
    partial_exit_r: float | None = None
    partial_exit_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.or_minutes <= 0:
            raise ValueError("or_minutes must be positive")
        if self.target_r is not None and self.target_r <= 0:
            raise ValueError("target_r must be positive when set")
        if not 0.0 <= self.doji_threshold <= 1.0:
            raise ValueError("doji_threshold must be in [0, 1]")
        if self.vwap_trail_after_r is not None and self.vwap_trail_after_r <= 0:
            raise ValueError("vwap_trail_after_r must be positive when set")
        if self.time_stop_minutes is not None and self.time_stop_minutes <= 0:
            raise ValueError("time_stop_minutes must be positive when set")
        if self.partial_exit_r is not None:
            if self.partial_exit_r <= 0:
                raise ValueError("partial_exit_r must be positive when set")
            if not 0.0 < self.partial_exit_fraction < 1.0:
                raise ValueError("partial_exit_fraction must be in (0, 1) when partial_exit_r is set")


@dataclass(frozen=True)
class Trade:
    """One completed (or attempted-but-filtered-out never appears here) ORB trade."""

    session_date: date
    direction: Direction
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    r_multiple: float
    pnl_points: float
    pnl_usd_per_contract: float
    # Default "eod" only affects manual Trade(...) construction elsewhere in the test
    # suite (e.g. tests/test_walk_forward.py's synthetic fixtures) that predate this
    # field; every Trade produced by run_orb_backtest sets exit_reason explicitly.
    exit_reason: ExitReason = "eod"
    # R-level a laddered partial-profit exit fired at (partial_exit_r overlay), or None if
    # no partial fired on this trade (overlay off, or stop/target pre-empted it same-bar --
    # see module docstring "Same-bar precedence with a pending partial fill"). r_multiple
    # above is ALWAYS the single size-weighted blend of the partial and runner legs when
    # this is set; there is no separate runner-only R field by design (see module docstring).
    partial_exit_r: float | None = None


def run_orb_backtest(bars: pd.DataFrame, params: ORBParams) -> list[Trade]:
    """Run the ORB backtest over all RTH sessions in `bars`. Returns Trade list ordered by session_date."""
    sessions = build_rth_sessions(bars)
    if not sessions:
        return []

    daily = _daily_ohlcv(sessions)
    daily_atr = _atr(daily, params.atr_lookback, is_roll=daily["is_roll"])
    daily_ret = daily["close"].pct_change()
    realized_vol = daily_ret.rolling(params.vol_lookback).std()
    # Percentile of YESTERDAY's realized vol within the expanding history of realized
    # vols up to and including yesterday (strictly past data only — no full-sample rank,
    # which would leak future sessions' vol into today's ranking). Then used to gate
    # today's trade. `.expanding().rank(pct=True)` ranks each point within itself + all
    # prior points; `.shift(1)` moves that from "today's own rank" to "yesterday's rank
    # as known at today's open."
    vol_percentile = realized_vol.expanding().rank(pct=True).shift(1)
    daily_atr_prior = daily_atr.shift(1)
    prior_close = daily["close"].shift(1)

    trades: list[Trade] = []
    or_window_volume: dict[date, float] = {}

    for i, session in enumerate(sessions):
        session_date = session.session_date
        bars_today = session.bars
        or_end = bars_today.index[0] + timedelta(minutes=params.or_minutes)
        or_bars = bars_today.loc[bars_today.index < or_end]
        post_or_bars = bars_today.loc[bars_today.index >= or_end]
        or_window_volume[session_date] = float(or_bars["volume"].sum())

        if or_bars.empty or post_or_bars.empty:
            continue

        or_high = float(or_bars["high"].max())
        or_low = float(or_bars["low"].min())

        if params.allowed_weekdays is not None:
            if session_date.weekday() not in params.allowed_weekdays:
                continue

        atr_required = (
            params.stop_mode == "atr_frac"
            or params.entry_mode == "strangle"
            or params.max_overnight_gap_atr is not None
        )
        atr_prior = daily_atr_prior.get(session_date)
        if atr_required and (atr_prior is None or pd.isna(atr_prior)):
            continue  # not enough history yet for ATR-dependent stop/entry/filter
        atr_prior_value = float(atr_prior) if atr_prior is not None and not pd.isna(atr_prior) else float("nan")

        if params.vol_percentile_min is not None:
            vp = vol_percentile.get(session_date)
            if vp is None or pd.isna(vp) or vp < params.vol_percentile_min:
                continue

        if params.rel_volume_min is not None:
            trailing_dates = [s.session_date for s in sessions[max(0, i - params.rel_volume_lookback) : i]]
            trailing_vols = [or_window_volume[d] for d in trailing_dates if d in or_window_volume]
            if len(trailing_vols) < params.rel_volume_lookback:
                continue
            avg_vol = float(np.mean(trailing_vols))
            if avg_vol <= 0 or (or_window_volume[session_date] / avg_vol) < params.rel_volume_min:
                continue

        if params.max_overnight_gap_atr is not None:
            if bool(daily.loc[session_date, "is_roll"]):
                pass  # roll-day gap is a contract-roll artifact, not a real overnight gap -> filter does not apply
            else:
                pc = prior_close.get(session_date)
                if pc is None or pd.isna(pc):
                    continue
                gap = abs(float(bars_today["open"].iloc[0]) - float(pc))
                if gap > params.max_overnight_gap_atr * atr_prior_value:
                    continue

        trade = _simulate_session(
            session_date=session_date,
            or_bars=or_bars,
            post_or_bars=post_or_bars,
            or_high=or_high,
            or_low=or_low,
            atr_prior=atr_prior_value,
            params=params,
        )
        if trade is not None:
            trades.append(trade)

    return trades


def trades_to_replay_days(trades: list[Trade], sessions: list[Session]) -> list[ReplayDay]:
    """Convert Trade records to ReplayDay list, one entry per session in `sessions`.

    ReplayDay's contract (src/strategies/replay.py) requires no-trade days to
    stay in the sequence as empty tuples, so every session date appears
    exactly once regardless of whether a trade fired. This intentionally
    differs from `src.data.replay_loader.load_replay_days_csv`, which omits
    dates absent from the source CSV entirely rather than emitting an empty
    day — that loader has no session universe to consult, so silence is its
    only "no trade" signal. Here we always have the full session list from
    `build_rth_sessions`, so no-trade days are represented explicitly (empty
    tuple) rather than by omission, matching the finite-horizon timeout math
    documented on `ReplayDay`.
    """
    trades_by_date: dict[date, list[float]] = {}
    for t in trades:
        trades_by_date.setdefault(t.session_date, []).append(t.r_multiple)
    return [
        ReplayDay(session_date=s.session_date, r_multiples=tuple(trades_by_date.get(s.session_date, [])))
        for s in sessions
    ]


def _daily_ohlcv(sessions: list[Session]) -> pd.DataFrame:
    """One row per RTH session: OHLC (from RTH bars only, no overnight span) + instrument_id + is_roll.

    `is_roll` marks sessions where the continuous-contract `instrument_id`
    changed from the prior session (front-month roll). Rolls happen
    overnight, never mid-RTH-session, so each session has a single
    `instrument_id` value.
    """
    rows = []
    for s in sessions:
        instrument_id = s.bars["instrument_id"].iloc[0] if "instrument_id" in s.bars.columns else None
        rows.append(
            {
                "session_date": s.session_date,
                "open": float(s.bars["open"].iloc[0]),
                "high": float(s.bars["high"].max()),
                "low": float(s.bars["low"].min()),
                "close": float(s.bars["close"].iloc[-1]),
                "instrument_id": instrument_id,
            }
        )
    df = pd.DataFrame(rows).set_index("session_date")
    if df["instrument_id"].isna().all():
        df["is_roll"] = False
    else:
        df["is_roll"] = df["instrument_id"].ne(df["instrument_id"].shift(1)) & df["instrument_id"].shift(1).notna()
    return df


def _atr(daily: pd.DataFrame, lookback: int, *, is_roll: pd.Series) -> pd.Series:
    """Rolling-mean true range from RTH-only OHLC, prior RTH close as the reference.

    Roll-day true range is a contract-swap artifact (front-month gap), not
    real volatility, so it's excluded from the average entirely rather than
    diluting it. Mechanism: mask roll-day TR to NaN, DROP those rows (not
    just mask them) before rolling, compute the plain trailing rolling mean
    over that valid-only subsequence, then reindex back onto the full daily
    calendar. Because `rolling(lookback, min_periods=lookback)` on a
    contiguous, NaN-free subsequence is a purely positional trailing window,
    this is equivalent to "the mean of the `lookback` most recent non-roll
    TRs" at every date — a window spanning a roll reaches one extra real
    session further back instead of going stale. On stretches with no rolls
    in the trailing `lookback` window, the dropna'd subsequence equals the
    original series exactly, so results are bit-identical to a naive
    `tr.rolling(lookback, min_periods=lookback).mean()` (verified by test).
    The roll day's own row is excluded from the reindex (implicitly NaN,
    since it was dropped) and then `ffill()`ed from the prior valid ATR,
    rather than computed from its own poisoned same-day TR.
    """
    prior_close = daily["close"].shift(1)
    tr = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prior_close).abs(),
            (daily["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr_clean = tr.mask(is_roll).dropna()
    atr_valid = tr_clean.rolling(lookback, min_periods=lookback).mean()
    atr = atr_valid.reindex(daily.index)
    return atr.ffill()


OrderSide = Literal["buy", "sell"]


def _fill_price(trigger: float, tick_size: float, slippage_ticks: float, side: OrderSide) -> float:
    """Apply slippage adverse to the order side actually executing: buys fill higher, sells fill lower."""
    offset = tick_size * slippage_ticks
    return trigger + offset if side == "buy" else trigger - offset


def _simulate_session(
    *,
    session_date: date,
    or_bars: pd.DataFrame,
    post_or_bars: pd.DataFrame,
    or_high: float,
    or_low: float,
    atr_prior: float,
    params: ORBParams,
) -> Trade | None:
    entry = _resolve_entry(
        or_bars=or_bars,
        post_or_bars=post_or_bars,
        or_high=or_high,
        or_low=or_low,
        atr_prior=atr_prior,
        params=params,
    )
    if entry is None:
        return None
    direction, entry_ts, entry_price, entry_bar_idx = entry

    if params.entry_mode == "strangle":
        # Spec: opposite resting level becomes the stop (overrides stop_mode).
        open_price = float(or_bars["open"].iloc[0])
        offset = params.strangle_rho * atr_prior
        stop_price = open_price - offset if direction == "long" else open_price + offset
    else:
        stop_price = _resolve_stop(
            direction=direction,
            entry_price=entry_price,
            or_high=or_high,
            or_low=or_low,
            atr_prior=atr_prior,
            params=params,
        )
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        return None

    target_price = None
    if params.target_r is not None:
        target_price = (
            entry_price + params.target_r * risk if direction == "long" else entry_price - params.target_r * risk
        )

    remaining = post_or_bars.iloc[entry_bar_idx:]
    # Full session bars (OR window + post-OR), needed for the VWAP overlay, which is a
    # session-level indicator computed from the session's own RTH open, not just from
    # entry onward.
    session_bars = pd.concat([or_bars, post_or_bars])
    exit_ts, exit_price, exit_reason, partial_exit_r = _walk_to_exit(
        direction=direction,
        entry_price=entry_price,
        entry_ts=entry_ts,
        stop_price=stop_price,
        target_price=target_price,
        risk=risk,
        remaining_bars=remaining,
        session_bars=session_bars,
        params=params,
    )

    friction_points = 2 * params.commission_usd_per_side / params.point_value

    if partial_exit_r is None:
        # Single-leg path: UNCHANGED arithmetic from the pre-partial-overlay backtester
        # (bit-identical -- this branch must never be touched by the blend logic below).
        pnl_points = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
        pnl_points_after_friction = pnl_points - friction_points
        r_multiple = pnl_points_after_friction / risk
        pnl_usd = pnl_points * params.point_value - 2 * params.commission_usd_per_side
    else:
        # Blended path (reviewer fix, Finding 1): compute BOTH legs GROSS (no friction on
        # either leg), blend the gross R by size fraction, THEN subtract ONE full
        # round-trip's friction-in-R terms from the blended result -- exactly once, on the
        # position as a whole, matching how the single-leg path above charges friction
        # exactly once per trade regardless of size. Charging friction per-leg (e.g. via
        # runner_r, which already has friction baked in, multiplied by (1-fraction)) would
        # silently under-charge commission by `fraction` of a round trip -- that was the
        # bug this fix corrects.
        runner_pnl_points_gross = (exit_price - entry_price) if direction == "long" else (entry_price - exit_price)
        runner_r_gross = runner_pnl_points_gross / risk
        fraction = params.partial_exit_fraction

        r_multiple_gross = fraction * partial_exit_r + (1 - fraction) * runner_r_gross
        r_multiple = r_multiple_gross - (friction_points / risk)

        pnl_points_gross = fraction * (partial_exit_r * risk) + (1 - fraction) * runner_pnl_points_gross
        pnl_points_after_friction = pnl_points_gross - friction_points
        pnl_usd = pnl_points_gross * params.point_value - 2 * params.commission_usd_per_side

    return Trade(
        session_date=session_date,
        direction=direction,
        entry_ts=entry_ts,
        entry_price=entry_price,
        exit_ts=exit_ts,
        exit_price=exit_price,
        r_multiple=r_multiple,
        pnl_points=pnl_points_after_friction,
        pnl_usd_per_contract=pnl_usd,
        exit_reason=exit_reason,
        partial_exit_r=partial_exit_r,
    )


def _resolve_entry(
    *,
    or_bars: pd.DataFrame,
    post_or_bars: pd.DataFrame,
    or_high: float,
    or_low: float,
    atr_prior: float,
    params: ORBParams,
) -> tuple[Direction, pd.Timestamp, float, int] | None:
    if params.entry_mode == "breakout":
        return _resolve_breakout_entry(post_or_bars, or_high, or_low, params)
    if params.entry_mode == "first_candle":
        return _resolve_first_candle_entry(or_bars, post_or_bars, params)
    if params.entry_mode == "strangle":
        return _resolve_strangle_entry(or_bars, post_or_bars, atr_prior, params)
    raise ValueError(f"unknown entry_mode: {params.entry_mode}")


def _resolve_breakout_entry(
    post_or_bars: pd.DataFrame, or_high: float, or_low: float, params: ORBParams
) -> tuple[Direction, pd.Timestamp, float, int] | None:
    """Stop order at OR high/low break; first bar (after OR) whose high/low crosses either level wins.

    If a single bar crosses both levels, resolve conservatively: for a
    breakout-only decision (no position yet) there's no "worse" side yet, so
    we pick the direction whose trigger is reached first in a worst-case
    ordering — conservatively assume the LONG trigger (or_high) is checked
    first only if it is the closer level from the open; otherwise treat as
    ambiguous and skip (no lookahead-safe way to prefer one direction).
    Simpler and strictly conservative: if both trigger in the same bar,
    reject the session (no trade) rather than guess a favorable direction.
    """
    for idx, (ts, row) in enumerate(post_or_bars.iterrows()):
        open_, high, low = float(row["open"]), float(row["high"]), float(row["low"])
        hit_long = high >= or_high
        hit_short = low <= or_low
        if hit_long and hit_short:
            return None  # ambiguous same-bar double breakout -> no trade (conservative)
        if hit_long:
            trigger = max(or_high, open_)  # gapped through: stop order fills at the worse of {level, bar open}
            fill = _fill_price(trigger, params.tick_size, params.slippage_ticks, "buy")
            return "long", ts, fill, idx
        if hit_short:
            trigger = min(or_low, open_)
            fill = _fill_price(trigger, params.tick_size, params.slippage_ticks, "sell")
            return "short", ts, fill, idx
    return None


def _resolve_first_candle_entry(
    or_bars: pd.DataFrame, post_or_bars: pd.DataFrame, params: ORBParams
) -> tuple[Direction, pd.Timestamp, float, int] | None:
    """Enter at the open of the first post-OR bar, in the direction of the OR candle. Skip if doji."""
    or_open = float(or_bars["open"].iloc[0])
    or_close = float(or_bars["close"].iloc[-1])
    or_high = float(or_bars["high"].max())
    or_low = float(or_bars["low"].min())
    or_range = or_high - or_low
    body = abs(or_close - or_open)
    if or_range <= 0 or (body / or_range) < params.doji_threshold:
        return None

    direction: Direction = "long" if or_close > or_open else "short"
    entry_row = post_or_bars.iloc[0]
    trigger = float(entry_row["open"])
    entry_side: OrderSide = "buy" if direction == "long" else "sell"
    fill = _fill_price(trigger, params.tick_size, params.slippage_ticks, entry_side)
    return direction, post_or_bars.index[0], fill, 0


def _resolve_strangle_entry(
    or_bars: pd.DataFrame, post_or_bars: pd.DataFrame, atr_prior: float, params: ORBParams
) -> tuple[Direction, pd.Timestamp, float, int] | None:
    """Resting orders at session open +/- rho*ATR(14 daily); first fill (post-OR) wins.

    The strangle levels are known at the session open (bar 0 of the OR
    window), but per the no-lookahead contract orders can only trigger from
    the bar after the OR completes, same as the other entry modes.
    """
    open_price = float(or_bars["open"].iloc[0])
    offset = params.strangle_rho * atr_prior
    upper = open_price + offset
    lower = open_price - offset

    for idx, (ts, row) in enumerate(post_or_bars.iterrows()):
        open_, high, low = float(row["open"]), float(row["high"]), float(row["low"])
        hit_long = high >= upper
        hit_short = low <= lower
        if hit_long and hit_short:
            return None  # ambiguous same-bar double fill -> no trade (conservative)
        if hit_long:
            trigger = max(upper, open_)  # gapped through: resting order fills at the worse of {level, bar open}
            fill = _fill_price(trigger, params.tick_size, params.slippage_ticks, "buy")
            return "long", ts, fill, idx
        if hit_short:
            trigger = min(lower, open_)
            fill = _fill_price(trigger, params.tick_size, params.slippage_ticks, "sell")
            return "short", ts, fill, idx
    return None


def _resolve_stop(
    *,
    direction: Direction,
    entry_price: float,
    or_high: float,
    or_low: float,
    atr_prior: float,
    params: ORBParams,
) -> float:
    if params.stop_mode == "or_opposite":
        return or_low if direction == "long" else or_high
    if params.stop_mode == "atr_frac":
        offset = params.stop_atr_frac * atr_prior
        return entry_price - offset if direction == "long" else entry_price + offset
    raise ValueError(f"unknown stop_mode: {params.stop_mode}")


def _favorable_excursion_r(direction: Direction, entry_price: float, close: float, risk: float) -> float:
    """Favorable excursion in R terms from a completed bar's close (no wicks -- close-basis only)."""
    raw = (close - entry_price) if direction == "long" else (entry_price - close)
    return raw / risk


def _walk_to_exit(
    *,
    direction: Direction,
    entry_price: float,
    entry_ts: pd.Timestamp,
    stop_price: float,
    target_price: float | None,
    risk: float,
    remaining_bars: pd.DataFrame,
    session_bars: pd.DataFrame,
    params: ORBParams,
) -> tuple[pd.Timestamp, float, ExitReason, float | None]:
    """Walk forward bar-by-bar from the entry bar.

    Returns (exit_ts, exit_price, exit_reason, partial_exit_r), where the
    first three describe the RUNNER's (or the full position's, if no partial
    ever fired) terminal exit, and `partial_exit_r` is the GROSS R-level
    (no-friction, same convention as `_favorable_excursion_r`/MFE
    throughout this module) a partial-profit fill fired at -- None if the
    overlay is off, never armed, or was pre-empted by a same-bar stop/target
    before it could fire (see module docstring). The caller (`_simulate_session`)
    uses this to compute the size-weighted blended r_multiple; see that
    function for the blend arithmetic.

    Conservative intra-bar rule: if a bar's high/low range touches both the
    stop and the target, the stop wins (worst-case ordering assumed). The
    optional overlays (hold_into_close, vwap_trail_after_r, time_stop_minutes,
    partial_exit_r; see module docstring) are evaluated on a completed-bar
    basis and never override stop/target within the same bar -- a market
    exit they schedule on bar t always fills at bar t+1's open, and if bar
    t+1 also touches the stop or target, stop/target wins (stop-first on
    conflict, matching the existing convention). A same-bar conflict between
    the pending partial and stop/target closes the FULL remaining position
    at the stop/target price; the partial never independently fires in that
    case (partial_exit_r stays None).
    """
    last_ts = remaining_bars.index[-1]
    last_close = float(remaining_bars["close"].iloc[-1])
    exit_side: OrderSide = "sell" if direction == "long" else "buy"

    # VWAP running state, seeded from session bars strictly before the entry bar (the
    # entry bar itself is completed by the time the *next* bar is being decided upon,
    # so it enters the running sums at the end of its own iteration below, same as any
    # other bar -- see the "completed bars only" contract in the module docstring).
    entry_bar_pos = session_bars.index.get_loc(remaining_bars.index[0])
    pre_entry_bars = session_bars.iloc[:entry_bar_pos]
    typical_pre = (pre_entry_bars["high"] + pre_entry_bars["low"] + pre_entry_bars["close"]) / 3.0
    vwap_num = float((typical_pre * pre_entry_bars["volume"]).sum())
    vwap_den = float(pre_entry_bars["volume"].sum())

    target_cancelled = False
    hold_into_close_decided = False
    vwap_trail_armed = False
    mfe_r = float("-inf")
    time_stop_deadline = entry_ts + timedelta(minutes=params.time_stop_minutes) if params.time_stop_minutes else None
    pending_exit_reason: ExitReason | None = None
    # partial_exit_r overlay state: `partial_pending` arms when a completed bar's close
    # first reaches +partial_exit_r; `partial_fired_r` records the R-level actually filled
    # at (set once, never re-armed -- only one partial per trade, per spec). Kept separate
    # from `pending_exit_reason` because the partial fill does not end the walk -- the
    # runner keeps going under the same loop afterward.
    partial_pending = False
    partial_fired_r: float | None = None

    for ts, row in remaining_bars.iterrows():
        open_, high, low, close = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

        # 1) A market exit scheduled on the prior bar fills at this bar's open, UNLESS
        # this bar's own stop/target trigger first (stop takes precedence on conflict).
        # The pending partial fill uses the identical rule: it fills at this bar's open
        # unless stop/target fires first, in which case the FULL remaining position exits
        # at stop/target and the partial is dropped (never independently applied).
        # A pending partial and a pending runner exit (vwap_trail/time_stop) can be
        # scheduled for the SAME bar (e.g. partial armed on bar t-1's close, and the
        # vwap trail/time stop also scheduled on bar t-1) -- both must fill on THIS same
        # bar's open, not one bar apart (reviewer fix, Finding 2: this used to be an
        # elif, which silently deferred the runner's exit to the following bar).
        if pending_exit_reason is not None or partial_pending:
            stop_hit_open_bar = low <= stop_price if direction == "long" else high >= stop_price
            target_hit_open_bar = (
                (high >= target_price if direction == "long" else low <= target_price)
                if target_price is not None and not target_cancelled
                else False
            )
            if not stop_hit_open_bar and not target_hit_open_bar:
                if partial_pending:
                    partial_fill_price = _fill_price(open_, params.tick_size, params.slippage_ticks, exit_side)
                    partial_fired_r = _favorable_excursion_r(direction, entry_price, partial_fill_price, risk)
                    partial_pending = False
                    # Do not return yet -- if a runner exit is ALSO pending for this same
                    # bar, it must fill here too (checked immediately below), not be
                    # pushed to the next iteration.
                if pending_exit_reason is not None:
                    fill = _fill_price(open_, params.tick_size, params.slippage_ticks, exit_side)
                    return ts, fill, pending_exit_reason, partial_fired_r
            # else: fall through, stop/target evaluation below wins this bar (full position).

        # 2) hold_into_close: decide once, at the first bar whose ET clock time is
        # >= 15:30, using that bar's OPEN (known at decision time).
        if params.hold_into_close and not hold_into_close_decided:
            ts_et = ts.tz_convert(ET) if ts.tzinfo is not None else ts.tz_localize(ET)
            if ts_et.timetz() >= HOLD_INTO_CLOSE_ET_TIME:
                hold_into_close_decided = True
                unrealized = (open_ - entry_price) if direction == "long" else (entry_price - open_)
                if unrealized > 0:
                    target_cancelled = True

        # 3) Stop / target, stop-first on same-bar conflict (existing conservative rule).
        # A same-bar hit here always closes the FULL remaining position (runner AND any
        # still-pending partial, per the same-bar-conflict rule in the module docstring).
        stop_hit = low <= stop_price if direction == "long" else high >= stop_price
        target_hit = (
            (high >= target_price if direction == "long" else low <= target_price)
            if target_price is not None and not target_cancelled
            else False
        )
        if stop_hit:
            fill = _fill_price(stop_price, params.tick_size, params.slippage_ticks, exit_side)
            return ts, fill, "stop", partial_fired_r if not partial_pending else None
        if target_hit:
            fill = _fill_price(target_price, params.tick_size, params.slippage_ticks, exit_side)
            return ts, fill, "target", partial_fired_r if not partial_pending else None

        # 4) Update completed-bar state using THIS bar's close, then schedule any
        # overlay-driven market exit for the NEXT bar's open.
        mfe_r = max(mfe_r, _favorable_excursion_r(direction, entry_price, close, risk))

        if params.vwap_trail_after_r is not None and not vwap_trail_armed and mfe_r >= params.vwap_trail_after_r:
            vwap_trail_armed = True

        if vwap_trail_armed and vwap_den > 0:
            vwap = vwap_num / vwap_den
            vwap_breach = close < vwap if direction == "long" else close > vwap
            if vwap_breach:
                pending_exit_reason = "vwap_trail"

        if (
            pending_exit_reason is None
            and time_stop_deadline is not None
            and mfe_r < 1.0
            and ts >= time_stop_deadline
        ):
            pending_exit_reason = "time_stop"

        if (
            params.partial_exit_r is not None
            and partial_fired_r is None
            and not partial_pending
            and mfe_r >= params.partial_exit_r
        ):
            partial_pending = True

        # This bar is now complete: fold it into the VWAP running sums so it counts
        # toward the "completed bars" available to the NEXT bar's decision.
        typical = (high + low + close) / 3.0
        vwap_num += typical * float(row["volume"])
        vwap_den += float(row["volume"])

    # Mandatory flat by session close: exit at close of last RTH bar (no further slippage
    # assumed at forced flat). A still-pending partial with no next bar to fill at is
    # dropped (matches the existing "overlay breach on the last bar" EoD fallthrough).
    return last_ts, last_close, "eod", partial_fired_r if not partial_pending else None
