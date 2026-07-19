"""Incremental, bar-driven ORB state machine for FROZEN_PARAMS only.

Consumes completed 1-minute bars one at a time (via `on_bar`) and never
accesses a bar past the one it is currently processing. This is a
deliberately independent re-implementation of the decision logic in
src/backtest/orb.py's `_resolve_first_candle_entry` / `_resolve_stop` /
`_walk_to_exit` for the exact overlay combination FROZEN_PARAMS uses
(first_candle entry, or_opposite stop, fixed R target, time_stop_minutes
armed, hold_into_close/vwap_trail/partial_exit all OFF) — it must NOT call
into src/backtest/orb.py's session-level functions, because the whole point
of tests/test_live_parity.py is comparing two structurally different
traversal styles (full-session vectorized-ish walk vs. true one-bar-at-a-time
state machine) and proving they agree. Only tiny pure helpers (`_fill_price`,
doji check) are shared/ported.

Fidelity notes (must match src/backtest/orb.py exactly for parity):
- OR window: first `or_minutes` bars of the session (bar clock time, not a
  fixed 09:30-09:35 assumption baked in — matches `or_bars = bars_today.loc[
  bars_today.index < or_end]` where `or_end = first_bar_ts + or_minutes`).
- Doji skip uses the OR window's open/close/high/low exactly as
  `_resolve_first_candle_entry` computes them (body/range vs. doji_threshold).
- Entry fills at the FIRST post-OR bar's open, adverse-slipped via
  `_fill_price` (identical helper, ported verbatim below).
- Stop = opposite OR extreme (or_opposite only; atr_frac/strangle are out of
  scope for FROZEN_PARAMS and this engine does not implement them).
  Target = entry +/- target_r * risk.
- Exit walk starts on the ENTRY bar itself (mirrors `remaining_bars` in
  `_walk_to_exit`, which begins at `post_or_bars.iloc[entry_bar_idx:]` — for
  first_candle entry_bar_idx=0, so the entry bar is itself in-scope for a
  same-bar stop/target).
- Same-bar precedence: a bar with both stop and target touched resolves
  stop-first (matches `_walk_to_exit` step 3: `if stop_hit: ... if
  target_hit: ...` — stop checked and returned before target is ever
  evaluated).
- A pending overlay-driven exit (only `time_stop` is reachable under
  FROZEN_PARAMS) fills at the NEXT bar's open, UNLESS that next bar's own
  stop/target triggers first (checked BEFORE the pending-exit fill, matching
  `_walk_to_exit` step 1 running before step 3 within the same iteration).
  `time_stop` itself arms on a completed-bar-close basis: if MFE (favorable
  excursion, close-basis) has not reached +1R by `time_stop_minutes` after
  the entry timestamp, the exit arms and fills at the following bar's open.
- Mandatory end-of-session flat: if no exit has fired by the session's last
  RTH bar, flatten at that bar's close, exit_reason="eod" (no further
  slippage, matching `_walk_to_exit`'s final fallthrough).
- Max 1 trade per session (day). Once a trade is opened for a session_date,
  no further entries are evaluated that day, mirroring the backtester's
  one-trade-per-session design (each session produces at most one Trade).

This module performs no I/O. It emits `EngineEvent`s (order intents / fills /
session-state notes); `src/live/runner.py` is responsible for wiring a
`BarFeed` into `on_bar` and a `Broker` to actually place/fill orders based on
the intents this engine emits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from src.live.feed import Bar

Direction = Literal["long", "short"]
ExitReason = Literal["stop", "target", "eod", "time_stop"]
OrderSide = Literal["buy", "sell"]


def fill_price(trigger: float, tick_size: float, slippage_ticks: float, side: OrderSide) -> float:
    """Ported verbatim from src.backtest.orb._fill_price (same adverse-slippage convention).

    Kept as a standalone copy rather than an import so this module's
    decision logic has zero runtime dependency on src/backtest/orb.py's
    session-level traversal functions (see module docstring) — this helper
    is pure arithmetic, not a traversal, so duplication here is deliberate
    and cheap to keep in sync (single line, covered by parity tests).
    """
    offset = tick_size * slippage_ticks
    return trigger + offset if side == "buy" else trigger - offset


def favorable_excursion_r(direction: Direction, entry_price: float, close: float, risk: float) -> float:
    """Ported verbatim from src.backtest.orb._favorable_excursion_r."""
    raw = (close - entry_price) if direction == "long" else (entry_price - close)
    return raw / risk


@dataclass(frozen=True)
class EntryIntent:
    """Emitted once the OR window is complete and a non-doji first-candle direction is known.

    Fires on the bar immediately after the OR window closes; the engine
    expects the broker to fill at that bar's open (see `fill_price` applied
    inside `on_bar`), matching `_resolve_first_candle_entry`.
    """

    session_date: date
    direction: Direction
    signal_ts: object  # pd.Timestamp of the OR-completion bar that produced the signal


@dataclass(frozen=True)
class TradeOpened:
    session_date: date
    direction: Direction
    entry_ts: object
    entry_price: float
    stop_price: float
    target_price: float | None
    risk_points: float


@dataclass(frozen=True)
class TradeClosed:
    session_date: date
    direction: Direction
    entry_ts: object
    entry_price: float
    exit_ts: object
    exit_price: float
    exit_reason: ExitReason
    risk_points: float

    @property
    def r_multiple_gross(self) -> float:
        """Gross R (no friction) — mirrors _favorable_excursion_r at the exit price.

        The backtester's Trade.r_multiple is friction-adjusted (see
        _simulate_session); this engine performs no dollar/friction
        accounting itself (that's PaperBroker's job), so this property is
        the pre-friction R only, used by tests and journaling.
        """
        raw = (self.exit_price - self.entry_price) if self.direction == "long" else (self.entry_price - self.exit_price)
        return raw / self.risk_points


@dataclass(frozen=True)
class NoTradeToday:
    """Emitted when the OR window completes but no trade is taken (doji skip)."""

    session_date: date
    reason: str


EngineEvent = EntryIntent | TradeOpened | TradeClosed | NoTradeToday


@dataclass
class _SessionState:
    session_date: date
    or_minutes: int
    or_end_ts: object | None = None  # set once the first bar of the session is seen
    or_open: float | None = None
    or_high: float = float("-inf")
    or_low: float = float("inf")
    or_close: float | None = None
    or_bars_seen: int = 0
    or_complete: bool = False
    trade_taken: bool = False  # max 1 trade/day guard
    no_trade_reason: str | None = None

    # Open-position state (None if flat)
    direction: Direction | None = None
    entry_ts: object | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    risk_points: float | None = None
    mfe_r: float = float("-inf")
    time_stop_deadline: object | None = None
    pending_exit_reason: ExitReason | None = None
    entry_bar_pending: bool = False  # True on the bar the engine expects the broker to fill entry
    entry_signal_direction: Direction | None = None


@dataclass
class ORBLiveEngine:
    """Bar-driven state machine. Call `on_bar(bar)` once per completed bar, in order.

    Only supports the exact overlay combination FROZEN_PARAMS uses:
    entry_mode="first_candle", stop_mode="or_opposite", target_r set,
    time_stop_minutes set, hold_into_close=False, vwap_trail_after_r=None,
    partial_exit_r=None. Raises on construction if given a params object
    outside that support surface, so a future param change fails loud
    instead of silently diverging from the backtester.
    """

    or_minutes: int
    doji_threshold: float
    target_r: float
    time_stop_minutes: int
    tick_size: float
    slippage_ticks: float

    _state: _SessionState | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_params(cls, params) -> "ORBLiveEngine":
        unsupported = (
            params.entry_mode != "first_candle"
            or params.stop_mode != "or_opposite"
            or params.target_r is None
            or params.hold_into_close
            or params.vwap_trail_after_r is not None
            or params.partial_exit_r is not None
        )
        if unsupported:
            raise ValueError(
                "ORBLiveEngine only supports the FROZEN_PARAMS overlay combination "
                "(first_candle/or_opposite/target_r set/no hold_into_close/no vwap_trail/"
                "no partial_exit). Got an unsupported ORBParams combination."
            )
        return cls(
            or_minutes=params.or_minutes,
            doji_threshold=params.doji_threshold,
            target_r=params.target_r,
            time_stop_minutes=params.time_stop_minutes or 0,
            tick_size=params.tick_size,
            slippage_ticks=params.slippage_ticks,
        )

    def restore_session(
        self,
        *,
        session_date: date,
        trade_taken: bool,
        direction: Direction | None = None,
        entry_ts=None,
        entry_price: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
        risk_points: float | None = None,
    ) -> None:
        """Seed session state on startup from a persisted RunnerState (restart recovery).

        Two cases the runner needs (see src/live/runner.py RunnerState):
        1. `trade_taken=True`, `direction=None` — a trade already completed
           (or was skipped for 0 contracts) earlier today; the engine must
           not evaluate the OR window again and must ignore the rest of
           today's bars.
        2. `trade_taken=True`, `direction` set — a trade is still OPEN from
           before the restart; the engine resumes managing it (stop/target/
           time_stop) from the restored entry/stop/target/risk without
           re-deciding entry.

        Must be called BEFORE the first `on_bar` of the session being
        restored into; the OR window itself is not replayed (its outcome —
        take-or-skip — is already known from the persisted state), so
        `or_complete` is set True unconditionally here.

        `time_stop_deadline` is NOT a caller-supplied parameter (reviewer
        Fix 1, 2026-07-18: the original signature accepted it as an optional
        kwarg the runner never actually passed, so every restored position
        silently lost its time-stop and could only exit via stop/target/eod
        — a live-money bug). It is always DERIVED here from `entry_ts +
        time_stop_minutes`, using this engine's own `time_stop_minutes`,
        exactly as `_fill_entry` computes it for a freshly-opened position.
        `PositionSnapshot` already persists `entry_ts`, so no new persisted
        field is needed.

        `mfe_r` (favorable excursion, close-basis) is NOT persisted anywhere
        (`PositionSnapshot` has no field for it) and is reset to -inf on
        restore, same as before. This is a deliberately CONSERVATIVE choice,
        not a full fix: the engine will only re-accumulate MFE from bars it
        sees AFTER the restart, so if the real pre-restart MFE had already
        reached +1R, restored `mfe_r` under-reports it and the time-stop can
        arm and fire even though the actual trade had already earned its
        exemption. That is safe in the "wrong direction" for money (it can
        cause an early exit on a trade that technically shouldn't time-stop,
        never the reverse — it can never SUPPRESS a time-stop that should
        fire, since under-reporting MFE only makes the `mfe_r < 1.0` arming
        condition MORE likely to hold, not less). Getting this fully right
        would require persisting the running MFE in `PositionSnapshot` and
        is left as a follow-up if the conservative bias proves costly in
        practice.
        """
        state = _SessionState(session_date=session_date, or_minutes=self.or_minutes)
        state.or_complete = True
        state.trade_taken = trade_taken
        if direction is not None:
            state.direction = direction
            state.entry_ts = entry_ts
            state.entry_price = entry_price
            state.stop_price = stop_price
            state.target_price = target_price
            state.risk_points = risk_points
            state.mfe_r = float("-inf")
            state.time_stop_deadline = (
                entry_ts + timedelta(minutes=self.time_stop_minutes)
                if entry_ts is not None and self.time_stop_minutes
                else None
            )
        self._state = state

    def on_bar(self, bar: Bar) -> list[EngineEvent]:
        """Process one completed bar. Returns zero or more events for this bar."""
        events: list[EngineEvent] = []
        state = self._state
        if state is None or state.session_date != bar.session_date:
            state = _SessionState(session_date=bar.session_date, or_minutes=self.or_minutes)
            self._state = state

        if state.trade_taken and state.direction is None and state.or_complete:
            # Restored (or already-completed) "no more trades today" state: ignore
            # remaining bars for this session entirely (matches max-1-trade/day).
            return events

        if not state.or_complete:
            events.extend(self._process_or_bar(state, bar))
            return events

        if state.entry_bar_pending:
            events.extend(self._fill_entry(state, bar))
            # The entry bar is also the first bar eligible for stop/target/time-stop
            # checks (mirrors _walk_to_exit's remaining_bars starting at entry_bar_idx).
            events.extend(self._process_position_bar(state, bar))
            return events

        if state.direction is not None:
            events.extend(self._process_position_bar(state, bar))

        return events

    def _process_or_bar(self, state: _SessionState, bar: Bar) -> list[EngineEvent]:
        if state.or_end_ts is None:
            state.or_end_ts = bar.ts + timedelta(minutes=state.or_minutes)
            state.or_open = bar.open

        if bar.ts < state.or_end_ts:
            state.or_high = max(state.or_high, bar.high)
            state.or_low = min(state.or_low, bar.low)
            state.or_close = bar.close
            state.or_bars_seen += 1
            return []

        # This bar is the first bar at/after the OR window close: OR is now complete,
        # and (for first_candle mode) this bar is also the entry-decision bar whose
        # OPEN fills the trade.
        state.or_complete = True
        or_range = state.or_high - state.or_low
        body = abs(state.or_close - state.or_open)
        is_doji = or_range <= 0 or (body / or_range) < self.doji_threshold
        if is_doji:
            state.no_trade_reason = "doji"
            return [NoTradeToday(session_date=state.session_date, reason="doji")]

        direction: Direction = "long" if state.or_close > state.or_open else "short"
        state.entry_signal_direction = direction
        state.entry_bar_pending = True
        events: list[EngineEvent] = [
            EntryIntent(session_date=state.session_date, direction=direction, signal_ts=bar.ts)
        ]
        events.extend(self._fill_entry(state, bar))
        events.extend(self._process_position_bar(state, bar))
        return events

    def _fill_entry(self, state: _SessionState, bar: Bar) -> list[EngineEvent]:
        if not state.entry_bar_pending:
            return []
        direction = state.entry_signal_direction
        assert direction is not None
        entry_side: OrderSide = "buy" if direction == "long" else "sell"
        entry_price = fill_price(bar.open, self.tick_size, self.slippage_ticks, entry_side)
        stop_price = state.or_low if direction == "long" else state.or_high
        risk = abs(entry_price - stop_price)

        state.entry_bar_pending = False
        if risk <= 0:
            # Degenerate risk (entry == stop after slippage): no trade, matches
            # _simulate_session's `if risk <= 0: return None`.
            state.direction = None
            state.no_trade_reason = "zero_risk"
            return [NoTradeToday(session_date=state.session_date, reason="zero_risk")]

        target_price = entry_price + self.target_r * risk if direction == "long" else entry_price - self.target_r * risk

        state.direction = direction
        state.entry_ts = bar.ts
        state.entry_price = entry_price
        state.stop_price = stop_price
        state.target_price = target_price
        state.risk_points = risk
        state.mfe_r = float("-inf")
        state.time_stop_deadline = (
            bar.ts + timedelta(minutes=self.time_stop_minutes) if self.time_stop_minutes else None
        )
        state.pending_exit_reason = None
        state.trade_taken = True

        return [
            TradeOpened(
                session_date=state.session_date,
                direction=direction,
                entry_ts=bar.ts,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                risk_points=risk,
            )
        ]

    def _process_position_bar(self, state: _SessionState, bar: Bar) -> list[EngineEvent]:
        if state.direction is None:
            return []
        direction = state.direction
        exit_side: OrderSide = "sell" if direction == "long" else "buy"

        # 1) A pending overlay exit (time_stop only, under FROZEN_PARAMS) fills at
        # THIS bar's open, unless this bar's own stop/target fires first.
        if state.pending_exit_reason is not None:
            stop_hit_open_bar = bar.low <= state.stop_price if direction == "long" else bar.high >= state.stop_price
            target_hit_open_bar = (
                (bar.high >= state.target_price if direction == "long" else bar.low <= state.target_price)
                if state.target_price is not None
                else False
            )
            if not stop_hit_open_bar and not target_hit_open_bar:
                fill = fill_price(bar.open, self.tick_size, self.slippage_ticks, exit_side)
                reason = state.pending_exit_reason
                event = self._close_trade(state, exit_ts=bar.ts, exit_price=fill, reason=reason)
                return [event]
            # else: fall through, stop/target evaluation below wins this bar.

        # 2) Stop / target, stop-first on same-bar conflict.
        stop_hit = bar.low <= state.stop_price if direction == "long" else bar.high >= state.stop_price
        target_hit = (
            (bar.high >= state.target_price if direction == "long" else bar.low <= state.target_price)
            if state.target_price is not None
            else False
        )
        if stop_hit:
            fill = fill_price(state.stop_price, self.tick_size, self.slippage_ticks, exit_side)
            return [self._close_trade(state, exit_ts=bar.ts, exit_price=fill, reason="stop")]
        if target_hit:
            fill = fill_price(state.target_price, self.tick_size, self.slippage_ticks, exit_side)
            return [self._close_trade(state, exit_ts=bar.ts, exit_price=fill, reason="target")]

        # 3) Completed-bar state update (close-basis MFE), then arm time_stop for the
        # NEXT bar if not yet reached +1R by the deadline.
        state.mfe_r = max(state.mfe_r, favorable_excursion_r(direction, state.entry_price, bar.close, state.risk_points))
        if (
            state.pending_exit_reason is None
            and state.time_stop_deadline is not None
            and state.mfe_r < 1.0
            and bar.ts >= state.time_stop_deadline
        ):
            state.pending_exit_reason = "time_stop"

        return []

    def on_session_end(self, last_bar: Bar) -> list[EngineEvent]:
        """Call after the last RTH bar of a session has been passed to `on_bar`.

        Mandatory flat: if still in a position, close at `last_bar.close`
        with exit_reason="eod" (no further slippage), matching
        `_walk_to_exit`'s final fallthrough. No-op if already flat.
        """
        state = self._state
        if state is None or state.session_date != last_bar.session_date or state.direction is None:
            return []
        event = self._close_trade(state, exit_ts=last_bar.ts, exit_price=last_bar.close, reason="eod")
        return [event]

    def _close_trade(self, state: _SessionState, *, exit_ts, exit_price: float, reason: ExitReason) -> TradeClosed:
        event = TradeClosed(
            session_date=state.session_date,
            direction=state.direction,
            entry_ts=state.entry_ts,
            entry_price=state.entry_price,
            exit_ts=exit_ts,
            exit_price=exit_price,
            exit_reason=reason,
            risk_points=state.risk_points,
        )
        state.direction = None
        state.pending_exit_reason = None
        return event
