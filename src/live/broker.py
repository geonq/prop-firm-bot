"""Broker abstraction: places brackets, flattens, reports position state.

`PaperBroker` fills using the same convention the backtester uses (adverse
`_fill_price`/slippage on entry; stop/target fill at the triggered level with
the same adverse-slippage tick offset; eod flat fills at the bar close with
no extra slippage). A future Phase 6B `ProjectXBroker` (TopstepX/ProjectX
REST + WS adapter) would implement the same `Broker` protocol so
src/live/runner.py never needs to know which one it's driving.

This module performs no strategy logic — it only reacts to events emitted by
src/live/engine.py and reports fills/positions back to the runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

Direction = Literal["long", "short"]


@dataclass
class PositionSnapshot:
    """Serializable open-position state (for LiveState/state.json round-tripping)."""

    session_date: date
    direction: Direction
    entry_ts: str  # ISO timestamp string
    entry_price: float
    stop_price: float
    target_price: float | None
    contracts: int
    risk_points: float

    def to_dict(self) -> dict:
        return {
            "session_date": self.session_date.isoformat(),
            "direction": self.direction,
            "entry_ts": self.entry_ts,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "contracts": self.contracts,
            "risk_points": self.risk_points,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PositionSnapshot":
        from datetime import date as _date

        return cls(
            session_date=_date.fromisoformat(d["session_date"]),
            direction=d["direction"],
            entry_ts=d["entry_ts"],
            entry_price=d["entry_price"],
            stop_price=d["stop_price"],
            target_price=d["target_price"],
            contracts=d["contracts"],
            risk_points=d["risk_points"],
        )


@dataclass
class FilledTrade:
    """One completed round-trip, with dollar P&L computed at the actual filled contract count."""

    session_date: date
    direction: Direction
    entry_ts: object
    entry_price: float
    exit_ts: object
    exit_price: float
    exit_reason: str
    contracts: int
    risk_points: float
    point_value: float

    @property
    def pnl_points(self) -> float:
        return (self.exit_price - self.entry_price) if self.direction == "long" else (self.entry_price - self.exit_price)

    @property
    def r_multiple(self) -> float:
        return self.pnl_points / self.risk_points

    @property
    def pnl_usd(self) -> float:
        return self.pnl_points * self.point_value * self.contracts


class Broker(Protocol):
    """Minimal broker surface the runner drives."""

    def place_bracket(
        self,
        *,
        session_date: date,
        direction: Direction,
        entry_price: float,
        stop_price: float,
        target_price: float | None,
        contracts: int,
        entry_ts,
        target_r: float | None = None,
    ) -> PositionSnapshot: ...

    def close_position(self, *, exit_ts, exit_price: float, exit_reason: str) -> FilledTrade: ...

    def flatten(self, *, exit_ts, exit_price: float, exit_reason: str) -> FilledTrade | None: ...

    @property
    def position(self) -> PositionSnapshot | None: ...


@dataclass
class PaperBroker:
    """Simulated fills using the backtester's fill-price convention.

    Entry/exit prices are passed in ALREADY adverse-slipped by the caller
    (src/live/engine.py computes fills via its own `fill_price`, ported from
    src.backtest.orb._fill_price) — PaperBroker does not re-apply slippage,
    it only tracks position state and turns a fill pair into a `FilledTrade`
    with dollar P&L at the actual contract count.
    """

    point_value: float
    _position: PositionSnapshot | None = field(default=None, init=False, repr=False)

    @property
    def position(self) -> PositionSnapshot | None:
        return self._position

    def place_bracket(
        self,
        *,
        session_date: date,
        direction: Direction,
        entry_price: float,
        stop_price: float,
        target_price: float | None,
        contracts: int,
        entry_ts,
        target_r: float | None = None,
    ) -> PositionSnapshot:
        if self._position is not None:
            raise RuntimeError("PaperBroker already has an open position; flatten before opening a new one")
        risk_points = abs(entry_price - stop_price)
        snapshot = PositionSnapshot(
            session_date=session_date,
            direction=direction,
            entry_ts=str(entry_ts),
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            contracts=contracts,
            risk_points=risk_points,
        )
        self._position = snapshot
        return snapshot

    def close_position(self, *, exit_ts, exit_price: float, exit_reason: str) -> FilledTrade:
        if self._position is None:
            raise RuntimeError("PaperBroker has no open position to close")
        pos = self._position
        trade = FilledTrade(
            session_date=pos.session_date,
            direction=pos.direction,
            entry_ts=pos.entry_ts,
            entry_price=pos.entry_price,
            exit_ts=str(exit_ts),
            exit_price=exit_price,
            exit_reason=exit_reason,
            contracts=pos.contracts,
            risk_points=pos.risk_points,
            point_value=self.point_value,
        )
        self._position = None
        return trade

    def flatten(self, *, exit_ts, exit_price: float, exit_reason: str = "flatten") -> FilledTrade | None:
        if self._position is None:
            return None
        return self.close_position(exit_ts=exit_ts, exit_price=exit_price, exit_reason=exit_reason)

    def unrealized_pnl_usd(self, mark_price: float) -> float:
        """Mark-to-market P&L of the open position at `mark_price` (e.g. a bar's close).

        Added for the runner's per-bar daily-loss kill switch (reviewer
        Fix 3, 2026-07-18): a stop/target check alone only reacts to prices
        the ENGINE decided to compare against the modeled stop, and a large
        overnight/intrabar gap can blow straight through that stop before
        the engine's own next decision point. This lets the runner mark the
        position to the bar it just saw, independent of engine/stop logic,
        so the daily-loss cap can act on real intrabar risk, not just
        realized P&L from completed exits. Returns 0.0 if flat.
        """
        if self._position is None:
            return 0.0
        pos = self._position
        pnl_points = (mark_price - pos.entry_price) if pos.direction == "long" else (pos.entry_price - mark_price)
        return pnl_points * self.point_value * pos.contracts
