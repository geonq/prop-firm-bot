"""LiveBroker: Broker implementation over the real ProjectX Gateway API.

Design decisions (see src/live/projectx.py module docstring for the
UNVERIFIED note this responds to):

- Entry is a plain MARKET order (`Order/place`, type=Market). The engine's
  `entry_price` (from `src/live/engine.py`'s modeled fill) is used ONLY to
  compute the modeled-vs-real slippage delta for the daily report; the
  ACTUAL position is sized/priced from whatever the exchange fills.
- Stop and target are placed as SEPARATE exchange-resident working orders
  AFTER the entry fills (Stop order + Limit order), not via
  `stopLossBracket`/`takeProfitBracket` on the entry order. Reason
  (documented in projectx.py): the docs describe the bracket fields' TYPE
  enum but never state whether TopstepX actually auto-cancels the sibling
  order server-side when one leg fills -- that is exactly the kind of
  behavior this task's ground rules forbid guessing. Placing two ordinary
  working orders and having THIS module manage the OCO relationship
  (poll -> detect one filled -> cancel the other) is the documented,
  defensive interpretation of the spec's own fallback clause: "if the API
  has no native OCO/bracket, the runner manages OCO."
- Time-stop / EoD flatten: cancel BOTH working orders (whichever is still
  open), then `Position/closeContract` for the full remaining size.
- ENTRY partial fills (reviewer Fix 4, 2026-07-19, HIGH -- this bullet was
  previously inaccurate; it claimed exit-side (stop/target) partial-fill
  handling that was never actually implemented): `_await_fill` distinguishes
  three outcomes for the entry order -- fully filled, timed out with a
  PARTIAL fill (`fillVolume > 0` but never reached FILLED status), and
  timed out with no fill at all. Only the last case raises. A partial fill
  is protected: `place_bracket` places the stop and target sized to the
  ACTUAL filled quantity (`fill.fill_volume`, not the originally requested
  `contracts`), journals a distinct `PartialFill` event, and tracks the
  position at that filled size -- it never raises past a partial fill and
  leaves it unprotected. EXIT-side (stop/target) partial fills are NOT
  specially handled beyond this: if a stop or target itself fills only
  partially, `poll_oco` still treats a `FILLED` status as a full close (the
  documented UNVERIFIED gap in src/live/projectx.py's module docstring
  about exact fill-vs-partial-fill order-status semantics applies here);
  this is a real, currently-unclosed gap, not claimed as solved.
- Idempotent restart recovery: `reconcile()` queries `Position/searchOpen` +
  `Order/searchOpen` BEFORE any placement decision. If a position already
  exists for the resolved contract, this module adopts it (never places a
  second entry) and re-derives which of its own stop/target orders (if any
  are still open) belong to it via `customTag` (see `_ENTRY_TAG_PREFIX`
  below) -- this is what makes restart-after-crash safe.
- Every state transition (order placed, order filled, order cancelled,
  position closed, reconciliation outcome) is journaled via the
  `on_event` callback the runner supplies, using the same JSONL event log
  the rest of the runner already writes to (src/live/runner.py's
  TradeJournal.record_event) -- LiveBroker performs no I/O to a file
  itself; it only calls back.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Literal

from src.live.broker import FilledTrade, PositionSnapshot
from src.live.projectx import (
    ORDER_SIDE_ASK,
    ORDER_SIDE_BID,
    ORDER_STATUS_FILLED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    POSITION_TYPE_LONG,
    OrderRecord,
    PositionRecord,
    ProjectXClient,
    ProjectXError,
)

Direction = Literal["long", "short"]

_ENTRY_TAG_PREFIX = "orb6b-"  # customTag prefix so reconcile() can recognize this bot's own orders

# How long to poll for a market entry fill before giving up (seconds).
# Market orders on a liquid MNQ front contract should fill near-instantly;
# this is a safety bound, not a tuned latency expectation (real latency is
# UNVERIFIED -- see projectx.py module docstring).
DEFAULT_ENTRY_FILL_TIMEOUT_SECONDS = 15.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# Cancel-order retry policy (reviewer Fix 2, 2026-07-19, CRITICAL): a cancel
# that keeps failing after entry is the exact precondition for a NAKED
# resting order sitting on the exchange after this process believes the
# position is flat -- that order can fill later and open a fresh,
# unmanaged, unprotected position with nobody watching it. ~5 attempts over
# ~30s (via the injected `sleep` clock, so tests never wait in real time).
CANCEL_RETRY_ATTEMPTS = 5
CANCEL_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 15.0)  # sums to 30s over 5 attempts


class LiveBrokerError(RuntimeError):
    """Raised when LiveBroker cannot complete an order lifecycle safely."""


class NakedOrderError(LiveBrokerError):
    """Raised when a working order (stop or target) could not be cancelled
    after exhausting the retry budget -- the order may still be resting on
    the exchange with nothing tracking or managing it. This is deliberately
    a DISTINCT exception type from a generic LiveBrokerError so callers
    (src/live/live_runner.py) can recognize this specific failure mode and
    make sure the resulting alarm/nonzero-exit path is unambiguous.
    """

    def __init__(self, order_id: int, *, reason: str, last_error: str) -> None:
        super().__init__(
            f"failed to cancel order {order_id} (reason={reason!r}) after {CANCEL_RETRY_ATTEMPTS} attempts: "
            f"{last_error} -- this order may still be resting on the exchange, unmanaged"
        )
        self.order_id = order_id
        self.reason = reason
        self.last_error = last_error


@dataclass
class _WorkingOrders:
    stop_order_id: int | None = None
    target_order_id: int | None = None


@dataclass
class LiveBroker:
    """Broker protocol implementation over ProjectXClient. See module docstring."""

    client: ProjectXClient
    account_id: int
    contract_id: str
    point_value: float
    on_event: Callable[[str, dict], None]
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    entry_fill_timeout_seconds: float = DEFAULT_ENTRY_FILL_TIMEOUT_SECONDS
    sleep: Callable[[float], None] = time.sleep

    _position: PositionSnapshot | None = field(default=None, init=False, repr=False)
    _working: _WorkingOrders = field(default_factory=_WorkingOrders, init=False, repr=False)
    _entry_tag: str | None = field(default=None, init=False, repr=False)
    _last_partial_fill_record: OrderRecord | None = field(default=None, init=False, repr=False)

    @property
    def position(self) -> PositionSnapshot | None:
        return self._position

    # -- restart-recovery ----------------------------------------------------------

    def reconcile(self) -> PositionSnapshot | None:
        """Idempotent restart recovery: adopt an already-open position, never re-enter.

        Must be called before any `place_bracket` call on a fresh process.
        Returns the adopted `PositionSnapshot` (or None if flat). Any of
        this bot's own working orders still open for the account (tagged
        with `_ENTRY_TAG_PREFIX`) are re-attached as the tracked stop/target
        so a subsequent `flatten()` still cancels them correctly.
        """
        positions = self.client.search_open_positions(account_id=self.account_id)
        matching = [p for p in positions if p.contract_id == self.contract_id and p.size != 0]
        self.on_event(
            "LiveBrokerReconcile",
            {"open_positions_for_contract": len(matching), "account_id": self.account_id, "contract_id": self.contract_id},
        )
        if not matching:
            self._position = None
            self._working = _WorkingOrders()
            return None
        if len(matching) > 1:
            raise LiveBrokerError(
                f"reconcile(): {len(matching)} open positions for contract {self.contract_id} on "
                f"account {self.account_id} -- refusing to guess which one is ours; resolve manually"
            )
        pos = matching[0]
        direction: Direction = "long" if pos.type == POSITION_TYPE_LONG else "short"

        open_orders = self.client.search_open_orders(account_id=self.account_id)
        own_open = [o for o in open_orders if o.contract_id == self.contract_id and (o.custom_tag or "").startswith(_ENTRY_TAG_PREFIX)]
        stop_order = next((o for o in own_open if o.type == ORDER_TYPE_STOP), None)
        target_order = next((o for o in own_open if o.type == ORDER_TYPE_LIMIT), None)
        self._working = _WorkingOrders(
            stop_order_id=stop_order.id if stop_order else None,
            target_order_id=target_order.id if target_order else None,
        )
        self._entry_tag = (stop_order.custom_tag if stop_order else target_order.custom_tag if target_order else None)

        # risk_points is unrecoverable from the exchange alone (the exchange
        # doesn't record "what was the modeled OR stop distance") -- best
        # available reconstruction is the stop order's own stopPrice vs the
        # position's averagePrice, which IS what the exchange knows.
        risk_points = abs(pos.average_price - stop_order.stop_price) if stop_order and stop_order.stop_price else float("nan")

        # entry_ts for a RECONCILED position comes from the position's own
        # creationTimestamp (doc-cited field, src/live/projectx.py
        # PositionRecord) when the exchange provides it -- this is what lets
        # a restored position's time-stop deadline (entry_ts +
        # time_stop_minutes, computed by src.live.engine.restore_session)
        # be correct after a restart, not just "unknown." Only falls back to
        # a placeholder if the exchange genuinely omitted it (defensive;
        # not expected in practice per the doc-cited schema, which always
        # includes creationTimestamp).
        entry_ts = pos.creation_timestamp or "unknown-reconciled"

        snapshot = PositionSnapshot(
            session_date=date.today(),
            direction=direction,
            entry_ts=entry_ts,
            entry_price=pos.average_price,
            stop_price=stop_order.stop_price if stop_order else float("nan"),
            target_price=target_order.limit_price if target_order else None,
            contracts=abs(pos.size),
            risk_points=risk_points,
        )
        self._position = snapshot
        self.on_event(
            "LiveBrokerReconcileAdopted",
            {
                "direction": direction,
                "contracts": abs(pos.size),
                "average_price": pos.average_price,
                "stop_order_id": self._working.stop_order_id,
                "target_order_id": self._working.target_order_id,
            },
        )
        return snapshot

    # -- entry ----------------------------------------------------------

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
        """Market entry, polled to fill, then exchange-resident stop + target working orders.

        `entry_price` is the ENGINE's modeled fill (used only for the
        modeled-vs-real slippage delta the caller can compute from the
        returned snapshot's actual `entry_price` vs this argument) -- the
        snapshot returned here carries the REAL fill price, not this one.
        """
        if self._position is not None:
            raise LiveBrokerError("LiveBroker already has an open position; flatten before opening a new one")

        tag = f"{_ENTRY_TAG_PREFIX}{session_date.isoformat()}-{uuid.uuid4().hex[:8]}"
        self._entry_tag = tag
        side = ORDER_SIDE_BID if direction == "long" else ORDER_SIDE_ASK

        entry_order_id = self.client.place_order(
            account_id=self.account_id,
            contract_id=self.contract_id,
            type=ORDER_TYPE_MARKET,
            side=side,
            size=contracts,
            custom_tag=tag,
        )
        self.on_event(
            "LiveOrderPlaced",
            {"role": "entry", "order_id": entry_order_id, "direction": direction, "contracts": contracts, "modeled_entry_price": entry_price},
        )

        fill = self._await_fill(entry_order_id, expected_size=contracts)
        if fill is None:
            # Reviewer Fix 4 (2026-07-19, HIGH): a timeout with NO fill at
            # all is genuinely safe to raise on (nothing is exposed). But a
            # timeout with a PARTIAL fill (_last_partial_fill_record set)
            # means real contracts ARE open on the exchange right now --
            # raising here without protecting them would leave that
            # quantity naked (no stop, no target, self._position never
            # set, so even the runner's error-path flatten guard would
            # find nothing to flatten). Must fall through to protect
            # whatever DID fill, never raise past it.
            partial = self._last_partial_fill_record
            if partial is None or not (partial.fill_volume or 0) > 0:
                raise LiveBrokerError(
                    f"entry order {entry_order_id} did not fill within {self.entry_fill_timeout_seconds}s "
                    "-- refusing to place stop/target for an unconfirmed position"
                )
            fill = partial
            self.on_event(
                "PartialFill",
                {
                    "role": "entry", "order_id": entry_order_id, "requested_size": contracts,
                    "filled_size": fill.fill_volume, "filled_price": fill.filled_price,
                    "message": "entry order partially filled before timing out -- protecting the filled quantity, "
                    "not the originally requested size",
                },
            )
        real_entry_price = fill.filled_price
        filled_contracts = fill.fill_volume or contracts
        self.on_event(
            "LiveOrderFilled",
            {"role": "entry", "order_id": entry_order_id, "filled_price": real_entry_price, "filled_size": filled_contracts,
             "modeled_entry_price": entry_price, "slippage_vs_model": (
                 (real_entry_price - entry_price) if direction == "long" else (entry_price - real_entry_price)
             )},
        )

        # The OR stop remains fixed, but preserve the configured R multiple
        # against the exchange-confirmed fill rather than the modeled quote.
        if target_price is not None and target_r is not None:
            actual_risk = abs(real_entry_price - stop_price)
            target_price = (
                real_entry_price + target_r * actual_risk
                if direction == "long"
                else real_entry_price - target_r * actual_risk
            )

        exit_side = ORDER_SIDE_ASK if direction == "long" else ORDER_SIDE_BID
        stop_order_id = self.client.place_order(
            account_id=self.account_id,
            contract_id=self.contract_id,
            type=ORDER_TYPE_STOP,
            side=exit_side,
            size=filled_contracts,
            stop_price=stop_price,
            custom_tag=tag,
        )
        self.on_event("LiveOrderPlaced", {"role": "stop", "order_id": stop_order_id, "stop_price": stop_price})

        target_order_id = None
        if target_price is not None:
            target_order_id = self.client.place_order(
                account_id=self.account_id,
                contract_id=self.contract_id,
                type=ORDER_TYPE_LIMIT,
                side=exit_side,
                size=filled_contracts,
                limit_price=target_price,
                custom_tag=tag,
            )
            self.on_event("LiveOrderPlaced", {"role": "target", "order_id": target_order_id, "target_price": target_price})

        self._working = _WorkingOrders(stop_order_id=stop_order_id, target_order_id=target_order_id)
        risk_points = abs(real_entry_price - stop_price)
        snapshot = PositionSnapshot(
            session_date=session_date,
            direction=direction,
            entry_ts=str(entry_ts),
            entry_price=real_entry_price,
            stop_price=stop_price,
            target_price=target_price,
            contracts=filled_contracts,
            risk_points=risk_points,
        )
        self._position = snapshot
        return snapshot

    # -- OCO polling ----------------------------------------------------------

    def poll_oco(self) -> str | None:
        """Check whether the stop or target has filled; cancel the sibling if so.

        Returns "stop", "target", or None (still both open / already flat).
        Callers (the runner) should call this once per bar tick while a
        position is open, in addition to the engine's own modeled
        stop/target logic -- the engine tells the runner WHEN it modeled an
        exit; this method tells the runner what the EXCHANGE actually did,
        which is the source of truth for `close_position()`'s exit price
        when this returns non-None.

        Fetches the account's open-order list ONCE per call (not once per
        leg) and checks both tracked order ids against that single
        snapshot -- an id present in the open list is still open by
        definition; an id ABSENT from it has transitioned to some terminal
        state (filled/cancelled/rejected/expired), which only THEN requires
        a fallback to the full order-search endpoint to learn which.
        """
        if self._position is None:
            return None
        stop_id = self._working.stop_order_id
        target_id = self._working.target_order_id

        open_orders = self.client.search_open_orders(account_id=self.account_id)
        open_by_id = {o.id: o for o in open_orders}

        stop_status = self._resolve_status(stop_id, open_by_id) if stop_id else None
        target_status = self._resolve_status(target_id, open_by_id) if target_id else None

        if stop_status is not None and stop_status.status == ORDER_STATUS_FILLED:
            if target_id is not None:
                self._safe_cancel(target_id, reason="oco_sibling_filled")
            return "stop"
        if target_status is not None and target_status.status == ORDER_STATUS_FILLED:
            if stop_id is not None:
                self._safe_cancel(stop_id, reason="oco_sibling_filled")
            return "target"
        return None

    def _resolve_status(self, order_id: int, open_by_id: dict[int, OrderRecord]) -> OrderRecord | None:
        if order_id in open_by_id:
            return open_by_id[order_id]
        # Not in the OPEN snapshot -- either filled, cancelled, or rejected;
        # look it up via full search to learn which.
        from datetime import UTC, datetime, timedelta

        window_start = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
        recent = self.client.search_orders(account_id=self.account_id, start_timestamp=window_start)
        for o in recent:
            if o.id == order_id:
                return o
        return None

    def _safe_cancel(self, order_id: int, *, reason: str) -> None:
        """Cancel `order_id`, retrying with backoff on failure (reviewer Fix 2,
        2026-07-19, CRITICAL). Raises `NakedOrderError` if every attempt
        fails AND the order is confirmed still open on the exchange after
        the retry budget is exhausted -- callers must NOT swallow this;
        propagating it is what turns "a cancel silently failed" into "the
        session is marked errored, not cleanly done" (see
        src/live/live_runner.py's handling of this exception).

        A cancel failure where the order turns out to have ALREADY reached
        a terminal state (filled/cancelled/expired/rejected) by the time we
        check is treated as benign, not an alarm -- that is the expected
        race between "we decided to cancel the sibling" and "the sibling
        itself just filled/expired," and there is no naked order in that
        case (the order is gone, not resting).
        """
        last_error = ""
        for attempt in range(CANCEL_RETRY_ATTEMPTS):
            try:
                self.client.cancel_order(account_id=self.account_id, order_id=order_id)
                self.on_event("LiveOrderCancelled", {"order_id": order_id, "reason": reason, "attempt": attempt + 1})
                return
            except ProjectXError as exc:
                last_error = str(exc)
                self.on_event(
                    "LiveOrderCancelFailed",
                    {"order_id": order_id, "reason": reason, "error": last_error, "attempt": attempt + 1, "max_attempts": CANCEL_RETRY_ATTEMPTS},
                )
                # Check whether the order is ALREADY terminal (benign race --
                # e.g. it filled or expired between our status check and this
                # cancel call) before burning the rest of the retry budget on
                # an order that no longer needs cancelling at all.
                status = self._single_order_status(order_id)
                if status is not None and status.is_terminal:
                    self.on_event(
                        "LiveOrderCancelBenignRace",
                        {"order_id": order_id, "reason": reason, "resolved_status": status.status},
                    )
                    return
                if attempt < CANCEL_RETRY_ATTEMPTS - 1:
                    self.sleep(CANCEL_RETRY_BACKOFF_SECONDS[attempt])

        # Exhausted every retry AND the order is still open (or its status
        # couldn't even be confirmed) -- this IS the naked-order case.
        self.on_event(
            "NakedOrderAlarm",
            {
                "order_id": order_id,
                "reason": reason,
                "attempts": CANCEL_RETRY_ATTEMPTS,
                "last_error": last_error,
                "message": "cancel failed after exhausting retries; order may still be resting on the exchange, unmanaged",
            },
        )
        raise NakedOrderError(order_id, reason=reason, last_error=last_error)

    # -- exit ----------------------------------------------------------

    def close_position(self, *, exit_ts, exit_price: float, exit_reason: str) -> FilledTrade:
        """Cancel any remaining working order(s), then flatten via Position/closeContract.

        `exit_price` from the caller is the MODELED exit (engine's
        time_stop/eod fill) and is used as a fallback only if this method
        cannot determine a real fill price (e.g. an OCO leg already handled
        the exit via `poll_oco()` -- in that case the runner should prefer
        that fill's real price when journaling, which happens at the
        runner layer, not here; `close_position` always reports what IT
        did on THIS call).
        """
        if self._position is None:
            raise LiveBrokerError("LiveBroker has no open position to close")
        pos = self._position
        if self._working.stop_order_id is not None:
            self._safe_cancel(self._working.stop_order_id, reason=exit_reason)
        if self._working.target_order_id is not None:
            self._safe_cancel(self._working.target_order_id, reason=exit_reason)

        # Reviewer Fix 7 (2026-07-19, DOC): closeContract's behavior when
        # called against an already-flat contract is UNVERIFIED (see
        # src/live/projectx.py module docstring) -- rather than depend on
        # whatever it actually does in that case, check searchOpen FIRST and
        # skip the call entirely if the account is already flat for this
        # contract (e.g. both legs of the OCO raced and the exchange beat us
        # to flattening between our last poll and this call). Already-flat
        # is treated as a successful close, not an error.
        open_positions = self.client.search_open_positions(account_id=self.account_id)
        already_flat = not any(p.contract_id == self.contract_id and p.size != 0 for p in open_positions)
        if already_flat:
            self.on_event(
                "LiveCloseAlreadyFlat",
                {"reason": exit_reason, "contracts": pos.contracts, "message": "searchOpen showed no open position for this contract -- skipped closeContract"},
            )
        else:
            self.client.close_position(account_id=self.account_id, contract_id=self.contract_id)
        self.on_event("LivePositionClosed", {"reason": exit_reason, "contracts": pos.contracts, "modeled_exit_price": exit_price})

        real_exit_price = self._resolve_real_exit_price(fallback=exit_price)
        trade = FilledTrade(
            session_date=pos.session_date,
            direction=pos.direction,
            entry_ts=pos.entry_ts,
            entry_price=pos.entry_price,
            exit_ts=str(exit_ts),
            exit_price=real_exit_price,
            exit_reason=exit_reason,
            contracts=pos.contracts,
            risk_points=pos.risk_points,
            point_value=self.point_value,
        )
        self._position = None
        self._working = _WorkingOrders()
        return trade

    def _resolve_real_exit_price(self, *, fallback: float) -> float:
        """Best-effort real exit price from the most recent trade fill, else fallback.

        `Position/closeContract` (doc-cited) returns only success/error, no
        fill price -- the real price must come from `Trade/search`. This is
        UNVERIFIED-in-practice (no credentials to confirm timing of when a
        just-closed trade appears in that search), so a failure here falls
        back to the caller's modeled price rather than raising -- a
        reporting-accuracy gap, never a trading-safety one (the position is
        already flat by the time this runs).
        """
        from datetime import UTC, datetime, timedelta

        try:
            window_start = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            trades = self.client.search_trades(account_id=self.account_id, start_timestamp=window_start)
            contract_trades = [t for t in trades if t.get("contractId") == self.contract_id]
            if contract_trades:
                return float(contract_trades[-1]["price"])
        except ProjectXError:
            pass
        return fallback

    def flatten(self, *, exit_ts, exit_price: float, exit_reason: str = "flatten") -> FilledTrade | None:
        if self._position is None:
            return None
        return self.close_position(exit_ts=exit_ts, exit_price=exit_price, exit_reason=exit_reason)

    def unrealized_pnl_usd(self, mark_price: float) -> float:
        """Mark-to-market P&L at `mark_price`, same convention as PaperBroker."""
        if self._position is None:
            return 0.0
        pos = self._position
        pnl_points = (mark_price - pos.entry_price) if pos.direction == "long" else (pos.entry_price - mark_price)
        return pnl_points * self.point_value * pos.contracts

    # -- polling helpers ----------------------------------------------------------

    def _single_order_status(self, order_id: int) -> OrderRecord | None:
        """Convenience wrapper for callers checking exactly one order (e.g. entry-fill
        polling), which don't have a pre-fetched open-orders snapshot to reuse.
        """
        open_orders = self.client.search_open_orders(account_id=self.account_id)
        return self._resolve_status(order_id, {o.id: o for o in open_orders})

    def _await_fill(self, order_id: int, *, expected_size: int) -> OrderRecord | None:
        """Polls until the order is fully filled. Returns the terminal
        OrderRecord if fully filled, or None if the timeout was reached
        with NO fill at all (fillVolume in (None, 0)) -- callers must check
        `_last_partial_fill_record` (reviewer Fix 4, 2026-07-19, HIGH) for
        the partial-fill case, which is DISTINCT from "no fill": a timeout
        with fillVolume > 0 is not represented by this method's None return
        anymore, because the original version conflated "nothing filled"
        and "partially filled, still working" into the same None result --
        that left a real, live position (whatever quantity DID fill)
        completely unprotected (no stop, no target, self._position never
        set) whenever a market order filled partially and then hung.
        """
        self._last_partial_fill_record = None
        deadline = time.monotonic() + self.entry_fill_timeout_seconds
        while time.monotonic() < deadline:
            record = self._single_order_status(order_id)
            if record is not None and record.is_filled:
                return record
            if record is not None and record.status not in (None,) and record.is_terminal and not record.is_filled:
                fill_volume = record.fill_volume or 0
                if fill_volume > 0:
                    # Terminal (e.g. cancelled/expired/rejected mid-fill) but
                    # SOME quantity did fill -- this is the partial-fill case,
                    # not "nothing filled." Record it for place_bracket to act on.
                    self._last_partial_fill_record = record
                    return None
                raise LiveBrokerError(f"entry order {order_id} reached terminal non-filled status={record.status}")
            if record is not None and (record.fill_volume or 0) > 0:
                # Still OPEN (not yet terminal) but already partially filled --
                # remember the best partial seen so far in case we time out
                # before it ever reaches a terminal state.
                self._last_partial_fill_record = record
            self.sleep(self.poll_interval_seconds)
        return None
