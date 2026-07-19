"""Tests for src/live/live_broker.py::LiveBroker -- OCO state machine, fake transport only.

Reuses the FakeTransport pattern from tests/test_projectx.py (no real
network calls). Drives LiveBroker through: entry fill -> bracket placement,
OCO polling (either leg fills -> sibling cancelled), flatten/EoD, restart
reconciliation (adopt an existing position, never double-enter), and
partial-fill / entry-timeout edge cases.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.live.live_broker import LiveBroker, LiveBrokerError
from src.live.projectx import (
    ORDER_SIDE_ASK,
    ORDER_SIDE_BID,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_OPEN,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    POSITION_TYPE_LONG,
    POSITION_TYPE_SHORT,
    ProjectXClient,
    TransportResponse,
)


class ScriptedTransport:
    """FakeTransport variant keyed by path -> queue, since LiveBroker interleaves
    calls to different endpoints (unlike the linear ProjectXClient tests).

    Once a path's queue is exhausted, the LAST response queued for that path
    is repeated indefinitely (rather than raising) -- this matters for
    polling-loop tests (e.g. entry-fill timeout) where `sleep` is stubbed to
    a no-op and the loop can iterate far more times than any fixed number of
    pre-seeded responses would cover; repeating "still open" is exactly the
    real-world behavior being simulated (the exchange keeps saying "still
    open" until the deadline is reached).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._queues: dict[str, list[TransportResponse]] = {}
        self._last: dict[str, TransportResponse] = {}

    def queue(self, path: str, status_code: int, body: dict) -> None:
        self._queues.setdefault(path, []).append(TransportResponse(status_code=status_code, body=body))

    def post(self, path: str, *, json: dict, headers: dict) -> TransportResponse:
        self.calls.append((path, json))
        q = self._queues.get(path)
        if q:
            response = q.pop(0)
            self._last[path] = response
            return response
        if path in self._last:
            return self._last[path]
        raise AssertionError(f"ScriptedTransport: no scripted response left for POST {path}, payload={json}")


def _ok(body: dict) -> dict:
    return {"success": True, "errorCode": 0, "errorMessage": None, **body}


def _events() -> tuple[list[tuple[str, dict]], callable]:
    log: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        log.append((event_type, payload))

    return log, on_event


def _client_and_transport() -> tuple[ProjectXClient, ScriptedTransport]:
    transport = ScriptedTransport()
    transport.queue("/api/Auth/loginKey", 200, _ok({"token": "t"}))
    # sleep=no-op: see tests/test_projectx.py::_client for why this matters --
    # this file's own fast timeout-polling tests (e.g.
    # test_place_bracket_raises_if_entry_never_fills) fire far more than 200
    # requests within a fraction of a real second.
    client = ProjectXClient(transport, username="u", api_key="k", sleep=lambda s: None)
    client.login()
    return client, transport


def _order_dict(*, id, status, type, side, size, stop_price=None, limit_price=None, fill_volume=0, filled_price=None):
    return {
        "id": id,
        "accountId": 465,
        "contractId": "CON.F.US.MNQ.U25",
        "symbolId": "F.US.MNQ",
        "creationTimestamp": "2026-07-18T13:35:00Z",
        "updateTimestamp": "2026-07-18T13:35:01Z",
        "status": status,
        "type": type,
        "side": side,
        "size": size,
        "limitPrice": limit_price,
        "stopPrice": stop_price,
        "fillVolume": fill_volume,
        "filledPrice": filled_price,
        "customTag": "orb6b-2026-07-18-abc12345",
    }


def _no_sleep(_seconds: float) -> None:
    pass


# ---------------------------------------------------------------------------
# entry + bracket placement
# ---------------------------------------------------------------------------


def test_place_bracket_places_market_entry_then_stop_and_target():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )

    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))  # entry
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=3, fill_volume=3, filled_price=20001.5)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))  # stop
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))  # target

    snapshot = broker.place_bracket(
        session_date=date(2026, 7, 18),
        direction="long",
        entry_price=20000.0,  # modeled
        stop_price=19985.0,
        target_price=20060.0,
        contracts=3,
        entry_ts="2026-07-18T09:35:00-04:00",
    )

    assert snapshot.entry_price == 20001.5  # REAL fill, not the modeled 20000.0
    assert snapshot.contracts == 3
    assert snapshot.stop_price == 19985.0
    assert snapshot.target_price == 20060.0

    # entry, stop, target placed in that order
    place_calls = [c for c in transport.calls if c[0] == "/api/Order/place"]
    assert len(place_calls) == 3
    assert place_calls[0][1]["type"] == ORDER_TYPE_MARKET
    assert place_calls[1][1]["type"] == ORDER_TYPE_STOP
    assert place_calls[1][1]["stopPrice"] == 19985.0
    assert place_calls[2][1]["type"] == ORDER_TYPE_LIMIT
    assert place_calls[2][1]["limitPrice"] == 20060.0

    event_types = [e for e, _ in log]
    assert "LiveOrderPlaced" in event_types
    assert "LiveOrderFilled" in event_types
    fill_event = next(p for e, p in log if e == "LiveOrderFilled")
    assert fill_event["slippage_vs_model"] == pytest.approx(1.5)  # real 20001.5 vs modeled 20000.0, long


def test_place_bracket_short_direction_uses_correct_sides():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 2001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=2001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_ASK, size=2, fill_volume=2, filled_price=19999.0)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 2002}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 2003}))

    broker.place_bracket(
        session_date=date(2026, 7, 18), direction="short", entry_price=20000.0, stop_price=20015.0,
        target_price=19940.0, contracts=2, entry_ts="ts",
    )
    place_calls = [c for c in transport.calls if c[0] == "/api/Order/place"]
    assert place_calls[0][1]["side"] == ORDER_SIDE_ASK  # short entry = sell
    assert place_calls[1][1]["side"] == ORDER_SIDE_BID  # exit of a short = buy
    assert place_calls[2][1]["side"] == ORDER_SIDE_BID


def test_place_bracket_raises_when_already_in_position():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=1, fill_volume=1, filled_price=20000.0)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 2}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 3}))
    broker.place_bracket(
        session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19990.0,
        target_price=20040.0, contracts=1, entry_ts="ts",
    )
    with pytest.raises(LiveBrokerError, match="already has an open position"):
        broker.place_bracket(
            session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19990.0,
            target_price=20040.0, contracts=1, entry_ts="ts",
        )


def test_place_bracket_raises_if_entry_never_fills():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event,
        sleep=_no_sleep, entry_fill_timeout_seconds=0.01, poll_interval_seconds=0.001,
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1}))
    # order stays OPEN forever -- searchOpen always returns it as open, never
    # filled (ScriptedTransport repeats the last queued response once exhausted).
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=1)]}),
    )
    with pytest.raises(LiveBrokerError, match="did not fill"):
        broker.place_bracket(
            session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19990.0,
            target_price=20040.0, contracts=1, entry_ts="ts",
        )


# ---------------------------------------------------------------------------
# FIX 4 (reviewer, 2026-07-19, HIGH): a partial entry fill that never
# reaches FILLED before the poll timeout must be PROTECTED (stop+target
# sized to the actual filled quantity), never raise leaving contracts
# unprotected.
# ---------------------------------------------------------------------------


def test_place_bracket_protects_partial_fill_instead_of_raising():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event,
        sleep=_no_sleep, entry_fill_timeout_seconds=0.01, poll_interval_seconds=0.001,
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))  # entry, requested size=5
    # Order stays OPEN forever (never reaches FILLED) but 2 of the 5
    # requested contracts DID fill -- ScriptedTransport repeats this
    # response once exhausted, simulating "still partially filled, hung."
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=5, fill_volume=2, filled_price=20000.5)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))  # stop
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))  # target

    snapshot = broker.place_bracket(
        session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19985.0,
        target_price=20060.0, contracts=5, entry_ts="ts",
    )

    # Protected at the ACTUAL filled quantity, not the originally requested size.
    assert snapshot.contracts == 2
    assert snapshot.entry_price == 20000.5
    assert broker.position is not None
    assert broker.position.contracts == 2

    # Stop and target orders were placed sized to the filled quantity (2), not 5.
    place_calls = [c for c in transport.calls if c[0] == "/api/Order/place"]
    assert len(place_calls) == 3  # entry, stop, target
    stop_call = place_calls[1][1]
    target_call = place_calls[2][1]
    assert stop_call["size"] == 2
    assert target_call["size"] == 2

    assert any(e == "PartialFill" for e, _ in log)
    partial_event = next(p for e, p in log if e == "PartialFill")
    assert partial_event["requested_size"] == 5
    assert partial_event["filled_size"] == 2


def test_place_bracket_raises_when_truly_zero_fill_not_partial():
    """Sanity: the genuinely-safe case (nothing filled at all) must still raise,
    same as before -- Fix 4 only changes behavior when fillVolume > 0.
    """
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event,
        sleep=_no_sleep, entry_fill_timeout_seconds=0.01, poll_interval_seconds=0.001,
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=5, fill_volume=0)]}),
    )
    with pytest.raises(LiveBrokerError, match="did not fill"):
        broker.place_bracket(
            session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19985.0,
            target_price=20060.0, contracts=5, entry_ts="ts",
        )
    assert broker.position is None


# ---------------------------------------------------------------------------
# OCO polling
# ---------------------------------------------------------------------------


def _broker_with_open_position(transport, client, on_event) -> LiveBroker:
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=ORDER_SIDE_BID, size=3, fill_volume=3, filled_price=20000.0)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))  # stop
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))  # target
    broker.place_bracket(
        session_date=date(2026, 7, 18), direction="long", entry_price=20000.0, stop_price=19985.0,
        target_price=20060.0, contracts=3, entry_ts="ts",
    )
    return broker


def test_poll_oco_stop_fills_cancels_target():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    # stop (1002) now filled, target (1003) still open
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok(
            {
                "orders": [
                    _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0),
                ]
            }
        ),
    )
    # _order_status(1002) misses in searchOpen -> falls back to full search
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19985.0, fill_volume=3, filled_price=19984.75)]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))

    result = broker.poll_oco()
    assert result == "stop"

    cancel_calls = [c for c in transport.calls if c[0] == "/api/Order/cancel"]
    assert len(cancel_calls) == 1
    assert cancel_calls[0][1]["orderId"] == 1003  # target cancelled, not the filled stop

    # payload now also carries an "attempt" field (reviewer Fix 2, 2026-07-19
    # cancel-retry policy) -- check the fields that matter, not an exact dict match.
    cancelled_events = [p for e, p in log if e == "LiveOrderCancelled"]
    assert any(p["order_id"] == 1003 and p["reason"] == "oco_sibling_filled" for p in cancelled_events)


def test_poll_oco_target_fills_cancels_stop():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19985.0)]}),
    )
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0, fill_volume=3, filled_price=20060.0)]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))

    result = broker.poll_oco()
    assert result == "target"
    cancel_calls = [c for c in transport.calls if c[0] == "/api/Order/cancel"]
    assert cancel_calls[0][1]["orderId"] == 1002


def test_poll_oco_neither_filled_returns_none():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok(
            {
                "orders": [
                    _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19985.0),
                    _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0),
                ]
            }
        ),
    )
    assert broker.poll_oco() is None


def test_poll_oco_when_flat_returns_none_without_calling_api():
    client, transport = _client_and_transport()
    calls_before = len(transport.calls)  # login() already made one call
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    assert broker.poll_oco() is None
    assert len(transport.calls) == calls_before  # no NEW calls made while flat


# ---------------------------------------------------------------------------
# flatten / close
# ---------------------------------------------------------------------------


def test_close_position_cancels_working_orders_and_closes():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel stop
    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel target
    # Fix 7 (2026-07-19, DOC): close_position now checks searchOpen before
    # closeContract -- still open here, so closeContract proceeds normally.
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 20000.0}]}),
    )
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue("/api/Trade/search", 200, _ok({"trades": []}))  # no real fill found -> fallback

    trade = broker.close_position(exit_ts="2026-07-18T11:35:00-04:00", exit_price=20010.0, exit_reason="time_stop")

    assert trade.exit_reason == "time_stop"
    assert trade.exit_price == 20010.0  # fallback to modeled since Trade/search returned nothing
    assert trade.contracts == 3
    assert broker.position is None

    close_calls = [c for c in transport.calls if c[0] == "/api/Position/closeContract"]
    assert len(close_calls) == 1
    assert close_calls[0][1] == {"accountId": 465, "contractId": "CON.F.US.MNQ.U25"}


def test_close_position_skips_close_contract_when_already_flat():
    """Reviewer Fix 7 (2026-07-19, DOC): if searchOpen shows no open position
    for this contract (e.g. the exchange already flattened it via some other
    path -- an OCO race, a manual intervention, etc), close_position must
    NOT call closeContract at all (its behavior on an already-flat contract
    is UNVERIFIED -- see src/live/projectx.py module docstring) -- it treats
    already-flat as a successful close. No /api/Position/closeContract
    response is queued at all here -- if the guard were absent or broken,
    this would fail with "no scripted response left for POST
    /api/Position/closeContract".
    """
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel stop
    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel target
    transport.queue("/api/Position/searchOpen", 200, _ok({"positions": []}))  # already flat
    transport.queue("/api/Trade/search", 200, _ok({"trades": []}))

    trade = broker.close_position(exit_ts="2026-07-18T11:35:00-04:00", exit_price=20010.0, exit_reason="time_stop")

    assert trade.exit_reason == "time_stop"
    assert trade.contracts == 3
    assert broker.position is None
    close_calls = [c for c in transport.calls if c[0] == "/api/Position/closeContract"]
    assert len(close_calls) == 0


def test_close_position_uses_real_fill_price_from_trade_search():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    # Fix 7 (2026-07-19, DOC): close_position now checks searchOpen before
    # closeContract -- still open here, so closeContract proceeds normally.
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 20000.0}]}),
    )
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue(
        "/api/Trade/search",
        200,
        _ok(
            {
                "trades": [
                    {
                        "id": 1,
                        "accountId": 465,
                        "contractId": "CON.F.US.MNQ.U25",
                        "creationTimestamp": "2026-07-18T11:35:01Z",
                        "price": 20009.25,
                        "profitAndLoss": None,
                        "fees": 1.48,
                        "side": ORDER_SIDE_ASK,
                        "size": 3,
                        "voided": False,
                        "orderId": 9999,
                    }
                ]
            }
        ),
    )

    trade = broker.close_position(exit_ts="2026-07-18T11:35:00-04:00", exit_price=20010.0, exit_reason="time_stop")
    assert trade.exit_price == 20009.25  # REAL fill, not the modeled fallback


def test_flatten_returns_none_when_already_flat():
    client, _ = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    assert broker.flatten(exit_ts="ts", exit_price=1.0) is None


def test_close_position_raises_when_already_flat():
    client, _ = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    with pytest.raises(LiveBrokerError, match="no open position"):
        broker.close_position(exit_ts="ts", exit_price=1.0, exit_reason="eod")


# ---------------------------------------------------------------------------
# reconciliation (idempotent restart recovery)
# ---------------------------------------------------------------------------


def test_reconcile_returns_none_when_flat():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue("/api/Position/searchOpen", 200, _ok({"positions": []}))
    assert broker.reconcile() is None
    assert broker.position is None


def test_reconcile_adopts_existing_position_and_working_orders():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok(
            {
                "positions": [
                    {
                        "id": 1,
                        "accountId": 465,
                        "contractId": "CON.F.US.MNQ.U25",
                        "creationTimestamp": "2026-07-18T09:35:00Z",
                        "type": POSITION_TYPE_LONG,
                        "size": 3,
                        "averagePrice": 20000.0,
                    }
                ]
            }
        ),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok(
            {
                "orders": [
                    _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19985.0),
                    _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0),
                ]
            }
        ),
    )

    snapshot = broker.reconcile()
    assert snapshot is not None
    assert snapshot.direction == "long"
    assert snapshot.contracts == 3
    assert snapshot.entry_price == 20000.0
    assert snapshot.stop_price == 19985.0
    assert snapshot.target_price == 20060.0
    assert broker._working.stop_order_id == 1002
    assert broker._working.target_order_id == 1003
    assert any(e == "LiveBrokerReconcileAdopted" for e, _ in log)


def test_reconcile_then_place_bracket_raises_no_duplicate_entry():
    """The actual idempotency guarantee: after reconcile() adopts a position,
    a subsequent place_bracket() call (e.g. a naive runner that didn't check
    trade_taken) must be refused, never silently double-entered.
    """
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": POSITION_TYPE_SHORT, "size": 2, "averagePrice": 20000.0}]}),
    )
    transport.queue("/api/Order/searchOpen", 200, _ok({"orders": []}))
    broker.reconcile()

    with pytest.raises(LiveBrokerError, match="already has an open position"):
        broker.place_bracket(
            session_date=date(2026, 7, 18), direction="short", entry_price=20000.0, stop_price=20010.0,
            target_price=19970.0, contracts=2, entry_ts="ts",
        )


def test_reconcile_raises_on_ambiguous_multiple_positions():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok(
            {
                "positions": [
                    {"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": POSITION_TYPE_LONG, "size": 1, "averagePrice": 20000.0},
                    {"id": 2, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": POSITION_TYPE_LONG, "size": 1, "averagePrice": 20001.0},
                ]
            }
        ),
    )
    with pytest.raises(LiveBrokerError, match="refusing to guess"):
        broker.reconcile()


# ---------------------------------------------------------------------------
# unrealized_pnl_usd (mark-to-market, mirrors PaperBroker)
# ---------------------------------------------------------------------------


def test_unrealized_pnl_usd_matches_paper_broker_convention():
    client, transport = _client_and_transport()
    _, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)
    # long, entry 20000.0, 3 contracts, point_value=2.0
    assert broker.unrealized_pnl_usd(20010.0) == pytest.approx(10.0 * 2.0 * 3)
    assert broker.unrealized_pnl_usd(19990.0) == pytest.approx(-10.0 * 2.0 * 3)


def test_unrealized_pnl_usd_zero_when_flat():
    client, _ = _client_and_transport()
    _, on_event = _events()
    broker = LiveBroker(
        client=client, account_id=465, contract_id="CON.F.US.MNQ.U25", point_value=2.0, on_event=on_event, sleep=_no_sleep
    )
    assert broker.unrealized_pnl_usd(20000.0) == 0.0


# ---------------------------------------------------------------------------
# FIX 2 (reviewer, 2026-07-19, CRITICAL): _safe_cancel retries with backoff;
# on exhausted retries it must journal a distinct NakedOrderAlarm event and
# RAISE (never silently swallow), so a flat-position-with-naked-resting-order
# can never look like a cleanly-completed exit.
# ---------------------------------------------------------------------------


def test_safe_cancel_retries_before_giving_up():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    # cancel ALWAYS fails (repeated by ScriptedTransport once exhausted);
    # searchOpen keeps reporting the target order as still OPEN (not
    # terminal) so the benign-race short-circuit never applies.
    transport.queue("/api/Order/cancel", 500, {"success": False})
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0)]}),
    )

    from src.live.live_broker import NakedOrderError, CANCEL_RETRY_ATTEMPTS

    with pytest.raises(NakedOrderError) as exc_info:
        broker._safe_cancel(1003, reason="test_reason")

    assert exc_info.value.order_id == 1003
    assert exc_info.value.reason == "test_reason"

    cancel_attempts = [c for c in transport.calls if c[0] == "/api/Order/cancel"]
    assert len(cancel_attempts) == CANCEL_RETRY_ATTEMPTS  # actually retried, not a single shot

    failed_events = [p for e, p in log if e == "LiveOrderCancelFailed"]
    assert len(failed_events) == CANCEL_RETRY_ATTEMPTS

    naked_alarms = [p for e, p in log if e == "NakedOrderAlarm"]
    assert len(naked_alarms) == 1
    assert naked_alarms[0]["order_id"] == 1003


def test_safe_cancel_backs_off_using_injected_sleep_not_real_time():
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)
    broker.sleep = lambda s: log.append(("sleep", {"seconds": s}))  # capture instead of no-op

    transport.queue("/api/Order/cancel", 500, {"success": False})
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0)]}),
    )

    from src.live.live_broker import NakedOrderError, CANCEL_RETRY_BACKOFF_SECONDS

    with pytest.raises(NakedOrderError):
        broker._safe_cancel(1003, reason="test_reason")

    sleep_calls = [p["seconds"] for e, p in log if e == "sleep"]
    assert sleep_calls == list(CANCEL_RETRY_BACKOFF_SECONDS[:-1])  # one fewer sleep than attempts (no sleep after the last)


def test_safe_cancel_benign_race_does_not_alarm_when_order_already_terminal():
    """If the cancel fails but the order turns out to have ALREADY reached a
    terminal state (e.g. it filled in the race window), this is NOT a naked
    order -- there is nothing resting -- and must not alarm/raise.
    """
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue("/api/Order/cancel", 500, {"success": False})
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": []}),  # not in the open list anymore
    )
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_LIMIT, side=ORDER_SIDE_ASK, size=3, limit_price=20060.0, fill_volume=3, filled_price=20060.0)]}),
    )

    broker._safe_cancel(1003, reason="test_reason")  # must NOT raise

    assert not any(e == "NakedOrderAlarm" for e, _ in log)
    assert any(e == "LiveOrderCancelBenignRace" for e, _ in log)
    cancel_attempts = [c for c in transport.calls if c[0] == "/api/Order/cancel"]
    assert len(cancel_attempts) == 1  # stopped retrying once the benign race was confirmed


def test_close_position_propagates_naked_order_error_when_cancel_exhausts_retries():
    """The 'same policy for the re-cancel in close_position' clause: a
    close_position() call whose stop-cancel fails permanently must propagate
    NakedOrderError (via _safe_cancel), not silently proceed to
    Position/closeContract as if nothing happened.
    """
    client, transport = _client_and_transport()
    log, on_event = _events()
    broker = _broker_with_open_position(transport, client, on_event)

    transport.queue("/api/Order/cancel", 500, {"success": False})
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19985.0)]}),
    )

    from src.live.live_broker import NakedOrderError

    with pytest.raises(NakedOrderError):
        broker.close_position(exit_ts="ts", exit_price=20010.0, exit_reason="time_stop")

    # Position/closeContract must never have been called -- we don't get to
    # pretend the position is flat when a working order might still be resting.
    close_calls = [c for c in transport.calls if c[0] == "/api/Position/closeContract"]
    assert close_calls == []
    assert broker.position is not None  # still tracked as open -- NOT silently cleared
