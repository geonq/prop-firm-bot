"""Fake-transport tests for src/live/projectx.py -- NO real network calls.

`FakeTransport` records every call and returns pre-scripted responses keyed
by (path,) in call order, mirroring the response envelopes documented on
https://gateway.docs.projectx.com (see src/live/projectx.py module
docstring for the citation of every endpoint/schema used here).
"""

from __future__ import annotations

import pytest

from src.live.projectx import (
    BASE_URL,
    ORDER_SIDE_ASK,
    ORDER_SIDE_BID,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_OPEN,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    POSITION_TYPE_LONG,
    ProjectXClient,
    ProjectXError,
    RateLimiter,
    TransportResponse,
)


class FakeTransport:
    """Scripted transport: queue of (status_code, body) per call, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []
        self._queue: list[TransportResponse] = []

    def queue_response(self, status_code: int, body: dict) -> None:
        self._queue.append(TransportResponse(status_code=status_code, body=body))

    def post(self, path: str, *, json: dict, headers: dict) -> TransportResponse:
        self.calls.append((path, json, headers))
        if not self._queue:
            raise AssertionError(f"FakeTransport: no scripted response queued for POST {path}")
        return self._queue.pop(0)


def _client() -> tuple[ProjectXClient, FakeTransport]:
    transport = FakeTransport()
    # sleep=no-op: the client's own rate limiter (Fix 8) must never cause a
    # REAL sleep in tests -- fast synthetic polling loops elsewhere in this
    # suite can legitimately fire well over 200 requests within a fraction
    # of a real second, and without this the limiter would block on a real
    # time.sleep() once that threshold is crossed.
    client = ProjectXClient(transport, username="testuser", api_key="testkey", sleep=lambda s: None)
    return client, transport


def _ok(body: dict) -> dict:
    return {"success": True, "errorCode": 0, "errorMessage": None, **body}


def _fail(error_code: int = 1, error_message: str = "failed") -> dict:
    return {"success": False, "errorCode": error_code, "errorMessage": error_message}


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def test_login_sets_token_and_uses_correct_endpoint_no_auth_header():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "abc123"}))

    token = client.login()

    assert token == "abc123"
    assert client.token == "abc123"
    path, payload, headers = transport.calls[0]
    assert path == "/api/Auth/loginKey"
    assert payload == {"userName": "testuser", "apiKey": "testkey"}
    # login itself must not require a prior token (auth=False path)
    assert "Authorization" not in headers


def test_subsequent_calls_use_bearer_auth_header():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "abc123"}))
    client.login()

    transport.queue_response(200, _ok({"accounts": []}))
    client.search_accounts()

    _, _, headers = transport.calls[1]
    assert headers["Authorization"] == "Bearer abc123"


def test_calling_before_login_raises():
    client, _ = _client()
    with pytest.raises(ProjectXError, match="not authenticated"):
        client.search_accounts()


def test_validate_session_updates_token():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "abc123"}))
    client.login()
    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "newToken": "def456"})

    new_token = client.validate_session()

    assert new_token == "def456"
    assert client.token == "def456"
    path, payload, _ = transport.calls[1]
    assert path == "/api/Auth/validate"


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


def test_api_failure_raises_projectx_error_with_code_and_message():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "t"}))
    client.login()
    transport.queue_response(200, _fail(error_code=7, error_message="account not found"))

    with pytest.raises(ProjectXError) as exc_info:
        client.search_accounts()
    assert exc_info.value.error_code == 7
    assert exc_info.value.error_message == "account not found"


def test_http_429_raises_rate_limited_error():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "t"}))
    client.login()
    transport.queue_response(429, {})

    with pytest.raises(ProjectXError, match="429"):
        client.search_accounts()


def test_http_500_raises():
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "t"}))
    client.login()
    transport.queue_response(500, {"success": False})

    with pytest.raises(ProjectXError, match="500"):
        client.search_accounts()


# ---------------------------------------------------------------------------
# account / contracts
# ---------------------------------------------------------------------------


def _authed_client() -> tuple[ProjectXClient, FakeTransport]:
    client, transport = _client()
    transport.queue_response(200, _ok({"token": "t"}))
    client.login()
    return client, transport


def test_search_accounts_parses_response():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "accounts": [
                    {"id": 1, "name": "TEST_ACCOUNT_1", "canTrade": True, "isVisible": True, "balance": 50000.0}
                ]
            }
        ),
    )
    accounts = client.search_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == 1
    assert accounts[0].can_trade is True
    assert accounts[0].balance == 50000.0

    path, payload, _ = transport.calls[-1]
    assert path == "/api/Account/search"
    assert payload == {"onlyActiveAccounts": True}


def test_search_contracts_parses_response():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "contracts": [
                    {
                        "id": "CON.F.US.MNQ.U25",
                        "name": "MNQU5",
                        "description": "Micro E-mini Nasdaq-100: September 2025",
                        "tickSize": 0.25,
                        "tickValue": 0.5,
                        "activeContract": True,
                        "symbolId": "F.US.MNQ",
                    }
                ]
            }
        ),
    )
    contracts = client.search_contracts("MNQ", live=False)
    assert len(contracts) == 1
    assert contracts[0].id == "CON.F.US.MNQ.U25"
    assert contracts[0].tick_size == 0.25

    path, payload, _ = transport.calls[-1]
    assert path == "/api/Contract/search"
    assert payload == {"searchText": "MNQ", "live": False}


def test_resolve_front_contract_picks_the_single_active_match():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "contracts": [
                    {
                        "id": "CON.F.US.MNQ.U25",
                        "name": "MNQU5",
                        "description": "active front",
                        "tickSize": 0.25,
                        "tickValue": 0.5,
                        "activeContract": True,
                        "symbolId": "F.US.MNQ",
                    },
                    {
                        "id": "CON.F.US.MNQ.Z25",
                        "name": "MNQZ5",
                        "description": "not yet active",
                        "tickSize": 0.25,
                        "tickValue": 0.5,
                        "activeContract": False,
                        "symbolId": "F.US.MNQ",
                    },
                ]
            }
        ),
    )
    contract = client.resolve_front_contract("MNQ")
    assert contract.id == "CON.F.US.MNQ.U25"


def test_resolve_front_contract_raises_on_no_match():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({"contracts": []}))
    with pytest.raises(ProjectXError, match="no active contract"):
        client.resolve_front_contract("MNQ")


def test_resolve_front_contract_raises_on_ambiguous_match():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "contracts": [
                    {
                        "id": "CON.F.US.MNQ.U25",
                        "name": "MNQU5",
                        "description": "a",
                        "tickSize": 0.25,
                        "tickValue": 0.5,
                        "activeContract": True,
                        "symbolId": "F.US.MNQ",
                    },
                    {
                        "id": "CON.F.US.MNQ.Z25",
                        "name": "MNQZ5",
                        "description": "b",
                        "tickSize": 0.25,
                        "tickValue": 0.5,
                        "activeContract": True,
                        "symbolId": "F.US.MNQ",
                    },
                ]
            }
        ),
    )
    with pytest.raises(ProjectXError, match="ambiguous"):
        client.resolve_front_contract("MNQ")


# ---------------------------------------------------------------------------
# bars
# ---------------------------------------------------------------------------


def test_retrieve_bars_sends_correct_payload_and_parses_response():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "bars": [
                    {"t": "2026-07-18T13:35:00Z", "o": 20000.0, "h": 20005.0, "l": 19998.0, "c": 20002.0, "v": 150},
                ]
            }
        ),
    )
    bars = client.retrieve_bars(
        "CON.F.US.MNQ.U25", start_time="2026-07-18T13:30:00Z", end_time="2026-07-18T13:40:00Z", limit=10
    )
    assert len(bars) == 1
    assert bars[0].o == 20000.0
    assert bars[0].v == 150

    path, payload, _ = transport.calls[-1]
    assert path == "/api/History/retrieveBars"
    assert payload["unit"] == 2  # BAR_UNIT_MINUTE
    assert payload["unitNumber"] == 1
    assert payload["includePartialBar"] is False


# ---------------------------------------------------------------------------
# orders
# ---------------------------------------------------------------------------


def test_place_order_sends_full_payload_and_returns_order_id():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({"orderId": 9056}))

    order_id = client.place_order(
        account_id=465,
        contract_id="CON.F.US.MNQ.U25",
        type=ORDER_TYPE_MARKET,
        side=ORDER_SIDE_BID,
        size=3,
        custom_tag="entry-2026-07-18",
    )
    assert order_id == 9056

    path, payload, _ = transport.calls[-1]
    assert path == "/api/Order/place"
    assert payload["accountId"] == 465
    assert payload["type"] == ORDER_TYPE_MARKET
    assert payload["side"] == ORDER_SIDE_BID
    assert payload["size"] == 3
    assert payload["customTag"] == "entry-2026-07-18"
    assert payload["stopLossBracket"] is None


def test_place_order_with_stop_price():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({"orderId": 9057}))

    client.place_order(
        account_id=465, contract_id="CON.F.US.MNQ.U25", type=ORDER_TYPE_STOP, side=ORDER_SIDE_ASK, size=3, stop_price=19980.0
    )
    _, payload, _ = transport.calls[-1]
    assert payload["stopPrice"] == 19980.0
    assert payload["type"] == ORDER_TYPE_STOP


def test_cancel_order_sends_correct_payload():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({}))
    client.cancel_order(account_id=465, order_id=9056)
    path, payload, _ = transport.calls[-1]
    assert path == "/api/Order/cancel"
    assert payload == {"accountId": 465, "orderId": 9056}


def test_modify_order_sends_correct_payload():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({}))
    client.modify_order(account_id=465, order_id=9056, stop_price=19975.0)
    path, payload, _ = transport.calls[-1]
    assert path == "/api/Order/modify"
    assert payload["stopPrice"] == 19975.0
    assert payload["size"] is None


def test_search_orders_parses_status_and_fill_fields():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "orders": [
                    {
                        "id": 9056,
                        "accountId": 465,
                        "contractId": "CON.F.US.MNQ.U25",
                        "symbolId": "F.US.MNQ",
                        "creationTimestamp": "2026-07-18T13:35:00Z",
                        "updateTimestamp": "2026-07-18T13:35:01Z",
                        "status": ORDER_STATUS_FILLED,
                        "type": ORDER_TYPE_MARKET,
                        "side": ORDER_SIDE_BID,
                        "size": 3,
                        "limitPrice": None,
                        "stopPrice": None,
                        "fillVolume": 3,
                        "filledPrice": 20001.0,
                        "customTag": "entry-2026-07-18",
                    }
                ]
            }
        ),
    )
    orders = client.search_orders(account_id=465, start_timestamp="2026-07-18T00:00:00Z")
    assert len(orders) == 1
    assert orders[0].is_filled is True
    assert orders[0].is_open is False
    assert orders[0].is_terminal is True
    assert orders[0].filled_price == 20001.0


def test_order_record_is_open_and_is_terminal_semantics():
    from src.live.projectx import OrderRecord

    open_order = OrderRecord.from_dict(
        {
            "id": 1,
            "accountId": 1,
            "contractId": "X",
            "status": ORDER_STATUS_OPEN,
            "type": ORDER_TYPE_MARKET,
            "side": ORDER_SIDE_BID,
            "size": 1,
        }
    )
    assert open_order.is_open is True
    assert open_order.is_terminal is False

    cancelled_order = OrderRecord.from_dict(
        {
            "id": 2,
            "accountId": 1,
            "contractId": "X",
            "status": ORDER_STATUS_CANCELLED,
            "type": ORDER_TYPE_MARKET,
            "side": ORDER_SIDE_BID,
            "size": 1,
        }
    )
    assert cancelled_order.is_open is False
    assert cancelled_order.is_terminal is True


def test_search_open_orders_sends_correct_payload():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({"orders": []}))
    client.search_open_orders(account_id=465)
    path, payload, _ = transport.calls[-1]
    assert path == "/api/Order/searchOpen"
    assert payload == {"accountId": 465}


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------


def test_search_open_positions_parses_response():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "positions": [
                    {
                        "id": 1,
                        "accountId": 465,
                        "contractId": "CON.F.US.MNQ.U25",
                        "creationTimestamp": "2026-07-18T13:35:00Z",
                        "type": POSITION_TYPE_LONG,
                        "size": 3,
                        "averagePrice": 20001.0,
                    }
                ]
            }
        ),
    )
    positions = client.search_open_positions(account_id=465)
    assert len(positions) == 1
    assert positions[0].type == POSITION_TYPE_LONG
    assert positions[0].size == 3


def test_close_position_sends_correct_payload():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({}))
    client.close_position(account_id=465, contract_id="CON.F.US.MNQ.U25")
    path, payload, _ = transport.calls[-1]
    assert path == "/api/Position/closeContract"
    assert payload == {"accountId": 465, "contractId": "CON.F.US.MNQ.U25"}


def test_partial_close_position_sends_correct_payload():
    client, transport = _authed_client()
    transport.queue_response(200, _ok({}))
    client.partial_close_position(account_id=465, contract_id="CON.F.US.MNQ.U25", size=1)
    path, payload, _ = transport.calls[-1]
    assert path == "/api/Position/partialCloseContract"
    assert payload == {"accountId": 465, "contractId": "CON.F.US.MNQ.U25", "size": 1}


# ---------------------------------------------------------------------------
# trades
# ---------------------------------------------------------------------------


def test_search_trades_returns_raw_dicts():
    client, transport = _authed_client()
    transport.queue_response(
        200,
        _ok(
            {
                "trades": [
                    {
                        "id": 1,
                        "accountId": 465,
                        "contractId": "CON.F.US.MNQ.U25",
                        "creationTimestamp": "2026-07-18T13:35:01Z",
                        "price": 20001.0,
                        "profitAndLoss": None,
                        "fees": 1.48,
                        "side": ORDER_SIDE_BID,
                        "size": 3,
                        "voided": False,
                        "orderId": 9056,
                    }
                ]
            }
        ),
    )
    trades = client.search_trades(account_id=465, start_timestamp="2026-07-18T00:00:00Z")
    assert len(trades) == 1
    assert trades[0]["price"] == 20001.0


# ---------------------------------------------------------------------------
# base URL / rate limiter
# ---------------------------------------------------------------------------


def test_base_url_is_topstepx():
    assert BASE_URL == "https://api.topstepx.com"


def test_rate_limiter_allows_under_limit_without_sleeping():
    limiter = RateLimiter(max_requests=3, per_seconds=10.0)
    sleep_calls = []
    for i in range(3):
        limiter.acquire(now=float(i), sleep=sleep_calls.append)
    assert sleep_calls == []


def test_rate_limiter_sleeps_when_over_limit():
    limiter = RateLimiter(max_requests=2, per_seconds=10.0)
    sleep_calls = []
    limiter.acquire(now=0.0, sleep=sleep_calls.append)
    limiter.acquire(now=1.0, sleep=sleep_calls.append)
    # third request within the window -> must wait until the first ages out (t=10.0)
    limiter.acquire(now=2.0, sleep=sleep_calls.append)
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(8.0)  # (0.0 + 10.0) - 2.0


# ---------------------------------------------------------------------------
# FIX 8 (reviewer, 2026-07-19, COSMETIC): RateLimiter must actually be WIRED
# into ProjectXClient, not dead code -- these tests prove _post() routes
# through the client's own limiter instances (a fake `sleep` catches the
# limiter tripping without a real wall-clock wait).
# ---------------------------------------------------------------------------


def test_client_post_uses_default_limiter_and_trips_it():
    transport = FakeTransport()
    sleep_calls = []
    client = ProjectXClient(transport, username="u", api_key="k", sleep=sleep_calls.append)
    client._default_limiter = RateLimiter(max_requests=2, per_seconds=60.0)
    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "token": "t"})
    client.login()  # auth=False path still goes through _post -> still rate limited

    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "accounts": []})
    client.search_accounts()
    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "accounts": []})
    client.search_accounts()  # this is the 3rd call against a max_requests=2 limiter -> must trip

    assert len(sleep_calls) == 1


def test_client_post_uses_separate_limiter_for_retrieve_bars():
    """retrieveBars must use its OWN (stricter) limiter, distinct from the
    default one used by every other endpoint -- exhausting the default
    limiter must not affect the retrieveBars limiter's own budget, and
    vice versa.
    """
    transport = FakeTransport()
    sleep_calls = []
    client = ProjectXClient(transport, username="u", api_key="k", sleep=sleep_calls.append)
    client._retrieve_bars_limiter = RateLimiter(max_requests=1, per_seconds=60.0)
    client._default_limiter = RateLimiter(max_requests=100, per_seconds=60.0)  # generous, should never trip here

    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "token": "t"})
    client.login()

    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "bars": []})
    client.retrieve_bars("CON.F.US.MNQ.U25", start_time="2026-01-01T00:00:00Z", end_time="2026-01-01T00:01:00Z")
    assert sleep_calls == []  # first retrieveBars call, under the limit of 1

    transport.queue_response(200, {"success": True, "errorCode": 0, "errorMessage": None, "bars": []})
    client.retrieve_bars("CON.F.US.MNQ.U25", start_time="2026-01-01T00:01:00Z", end_time="2026-01-01T00:02:00Z")
    assert len(sleep_calls) == 1  # second call trips the 1-request retrieveBars limiter
