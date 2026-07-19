"""ProjectX Gateway API client (TopstepX platform) for Phase 6B live trading.

EVERY endpoint below is cited to a fetched official doc page
(gateway.docs.projectx.com, fetched 2026-07-18). No endpoint, field, or enum
in this module was guessed — where the docs did not state something
explicitly, it is called out as UNVERIFIED / INFERRED below and in the
relevant docstring, per the Phase 6B ground rule ("no hallucinated APIs").

Base URLs (from https://gateway.docs.projectx.com/docs/getting-started/connection-urls/,
TopstepX platform selected):
    REST:      https://api.topstepx.com
    SignalR user hub:   https://rtc.topstepx.com/hubs/user     (NOT used -- see below)
    SignalR market hub: https://rtc.topstepx.com/hubs/market   (NOT used -- see below)
This client is REST-polling only. The spec (Tasks/todo.md "Phase 6B") explicitly
defers SignalR: "once-a-day strategy does not need it." The hub URLs are recorded
here for completeness/future reference only; nothing in this module opens a
WebSocket connection.

Endpoints implemented, each cited:
- POST /api/Auth/loginKey    -- https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-api-key/
  Request:  {"userName": str, "apiKey": str}
  Response: {"token": str, "success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Auth/validate    -- https://gateway.docs.projectx.com/docs/getting-started/validate-session/
  No request body (session token sent via header, see AUTH HEADER note below).
  Response: {"success": bool, "errorCode": int, "errorMessage": str|null, "newToken": str}
  Session tokens are valid 24h; call this to refresh before they expire.
- POST /api/Account/search   -- https://gateway.docs.projectx.com/docs/api-reference/account/search-accounts/
  Request:  {"onlyActiveAccounts": bool}
  Response: {"accounts": [{"id": int, "name": str, "balance": number, "canTrade": bool,
              "isVisible": bool}], "success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Contract/search  -- https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts/
  Request:  {"searchText": str, "live": bool}
  Response: {"contracts": [{"id": str, "name": str, "description": str, "tickSize": number,
              "tickValue": number, "activeContract": bool, "symbolId": str}], "success": bool,
              "errorCode": int, "errorMessage": str|null}
  Doc note: "returns up to 20 contracts at a time."
- POST /api/Contract/searchById -- https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts-by-id/
  Request:  {"contractId": str}
  Response: {"contract": {...same shape as one contract above...}, "success": bool,
              "errorCode": int, "errorMessage": str|null}
- POST /api/Contract/available -- https://gateway.docs.projectx.com/docs/api-reference/market-data/available-contracts/
  Request:  {"live": bool}
  Response: {"contracts": [...], "success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/History/retrieveBars -- https://gateway.docs.projectx.com/docs/api-reference/market-data/retrieve-bars/
  Request:  {"contractId": str, "live": bool, "startTime": iso-datetime, "endTime": iso-datetime,
              "unit": int (1=Second,2=Minute,3=Hour,4=Day,5=Week,6=Month), "unitNumber": int,
              "limit": int, "includePartialBar": bool}
  Response: {"bars": [{"t": iso-datetime, "o": number, "h": number, "l": number, "c": number,
              "v": int}], "success": bool, "errorCode": int, "errorMessage": str|null}
  Doc notes: max 20,000 bars/request; rate limit 50 requests/30s (stricter than the 200/60s
  default for all other endpoints) -- see RATE LIMITS below.
- POST /api/Order/place      -- https://gateway.docs.projectx.com/docs/api-reference/order/order-place/
  Request:  {"accountId": int, "contractId": str, "type": int (OrderType enum below), "side": int
              (0=Bid/buy, 1=Ask/sell), "size": int, "limitPrice": number|null, "stopPrice":
              number|null, "trailPrice": number|null, "customTag": str|null (must be unique per
              account), "stopLossBracket": {"ticks": int, "type": int}|null, "takeProfitBracket":
              {"ticks": int, "type": int}|null}
  Response: {"orderId": int, "success": bool, "errorCode": int, "errorMessage": str|null}
  stopLossBracket.type / takeProfitBracket.type use the SAME OrderType enum as the top-level
  "type" field (doc-confirmed, same page).
- POST /api/Order/cancel     -- https://gateway.docs.projectx.com/docs/api-reference/order/order-cancel/
  Request:  {"accountId": int, "orderId": int}
  Response: {"success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Order/modify     -- https://gateway.docs.projectx.com/docs/api-reference/order/order-modify/
  Request:  {"accountId": int, "orderId": int, "size": int|null, "limitPrice": number|null,
              "stopPrice": number|null, "trailPrice": number|null}
  Response: {"success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Order/search     -- https://gateway.docs.projectx.com/docs/api-reference/order/order-search/
  Request:  {"accountId": int, "startTimestamp": iso-datetime, "endTimestamp": iso-datetime|null}
  Response: {"orders": [{"id": int, "accountId": int, "contractId": str, "symbolId": str,
              "creationTimestamp": iso-datetime, "updateTimestamp": iso-datetime, "status": int
              (OrderStatus enum below), "type": int, "side": int, "size": int, "limitPrice":
              number|null, "stopPrice": number|null, "fillVolume": int, "filledPrice": number,
              "customTag": str|null}], "success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Order/searchOpen -- https://gateway.docs.projectx.com/docs/api-reference/order/order-search-open/
  Request:  {"accountId": int}
  Response: {"orders": [...same shape as above, filtered to open orders...], "success": bool,
              "errorCode": int, "errorMessage": str|null}
- POST /api/Position/searchOpen -- https://gateway.docs.projectx.com/docs/api-reference/positions/search-open-positions/
  Request:  {"accountId": int}
  Response: {"positions": [{"id": int, "accountId": int, "contractId": str, "creationTimestamp":
              iso-datetime, "type": int (PositionType enum below), "size": int, "averagePrice":
              number}], "success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Position/closeContract -- https://gateway.docs.projectx.com/docs/api-reference/positions/close-positions/
  Request:  {"accountId": int, "contractId": str}
  Response: {"success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Position/partialCloseContract -- https://gateway.docs.projectx.com/docs/api-reference/positions/close-positions-partial/
  Request:  {"accountId": int, "contractId": str, "size": int}
  Response: {"success": bool, "errorCode": int, "errorMessage": str|null}
- POST /api/Trade/search     -- https://gateway.docs.projectx.com/docs/api-reference/trade/trade-search/
  Request:  {"accountId": int, "startTimestamp": iso-datetime, "endTimestamp": iso-datetime|null}
  Response: {"trades": [{"id": int, "accountId": int, "contractId": str, "creationTimestamp":
              iso-datetime, "price": number, "profitAndLoss": number|null, "fees": number, "side":
              int, "size": int, "voided": bool, "orderId": int}], "success": bool, "errorCode":
              int, "errorMessage": str|null}

Enums (from https://gateway.docs.projectx.com/docs/realtime/ -- these are NOT documented on
the REST reference pages themselves; the realtime page is the only place the Gateway docs
publish the C# enum source. Cited from that page, not guessed):
    OrderStatus: None=0, Open=1, Filled=2, Cancelled=3, Expired=4, Rejected=5, Pending=6
    PositionType: Undefined=0, Long=1, Short=2
    OrderType (from order-place page): Limit=1, Market=2, Stop=4, TrailingStop=5, JoinBid=6,
        JoinAsk=7 (note: 3 is not documented/assigned to anything)
    OrderSide (from order-place page): Bid=0 (buy), Ask=1 (sell)

RATE LIMITS (https://gateway.docs.projectx.com/docs/getting-started/rate-limits/):
    POST /api/History/retrieveBars: 50 requests / 30 seconds
    All other endpoints: 200 requests / 60 seconds
    Exceeding either returns HTTP 429.

AUTH HEADER -- ***INFERRED, NOT DIRECTLY DOC-CITED***: no fetched page states the exact header
name/format for attaching the session token to subsequent REST calls. The docs state only "We
utilize JSON Web Tokens to authenticate all requests sent to the API"
(authenticate-api-key page) and, for the SignalR hubs, show the token passed via
`accessTokenFactory` or an `?access_token=` query param (realtime page) -- neither of which is
the REST convention. This client uses the universal JWT-bearer convention
(`Authorization: Bearer <token>`) as the only documented-adjacent inference available; this
MUST be confirmed empirically the first time real credentials exist (see --preflight in
src/live/runner.py) and is flagged again there.

loginApp (https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-as-application/)
is a SEPARATE auth flow for third-party/ISV applications acting on behalf of a firm (requires
admin username/password/appId/verifyKey) -- explicitly NOT what an individual trader on their
own account uses. This client only implements loginKey.

UNVERIFIED (cannot be confirmed without real credentials -- see also src/live/live_broker.py
and RUNBOOK_LIVE.md "What cannot be verified without credentials"):
- The exact Authorization header format (see AUTH HEADER above).
- Whether MNQ's actual contractId search text/pattern resolves cleanly via Contract/search
  (e.g. "MNQ") to the correct FRONT-MONTH contract, or whether disambiguation against multiple
  returned contracts is needed. resolve_front_contract() below picks the contract whose `name`
  starts with "MNQ" and is `activeContract=True`; this is a reasonable reading of the documented
  schema, not a doc-confirmed guarantee that exactly one such contract is ever returned.
- Actual latency of the loginKey -> Account/search -> Contract/search -> Order/place round trip
  from the runner's real network path.
- Whether stopLossBracket/takeProfitBracket actually create true exchange-resident OCO orders
  that TopstepX cancels-on-fill server-side, or whether the runner must manage OCO itself by
  polling and cancelling the sibling order (src/live/live_broker.py assumes the latter -- the
  safer, more defensive assumption -- and documents why there).
- retrieveBars bar-timestamp convention (reviewer Fix 5, 2026-07-19, MEDIUM): the docs (retrieve-
  bars page cited above) document the `t` field only as "iso-datetime" with no statement of
  whether it labels the OPEN or the CLOSE of the bar's interval. This client and src/live/feed.py
  assume OPEN-labeled (matching this project's backtest/replay convention throughout
  src/backtest and src/pipeline) but this is UNCONFIRMED against the real API. Getting this wrong
  would silently shift every bar's effective timestamp by one bar-width (1 minute), which shifts
  the OR window, the entry bar, and the time-stop deadline by the same amount without raising any
  error. --preflight (see run_preflight in src/live/runner.py) now fetches the last ~3 one-minute
  bars and prints each bar's `t` against the current wall-clock minute specifically so this can be
  eyeballed before go-live -- see that function's docstring for what to do if the bars look
  close-labeled instead (report back, do not go live).
- closeContract behavior on an already-flat position (reviewer Fix 7, 2026-07-19, DOC): the
  close-positions page cited above documents only the success-case response shape
  ({"success": bool, ...}); it does not state what closeContract returns when called against a
  contract with NO open position (e.g. a redundant flatten call, or a race where the position
  closed between our own searchOpen check and this call) -- whether it is a silent no-op success,
  a non-success errorCode, or something else is UNVERIFIED. src/live/live_broker.py's flatten
  path checks Position/searchOpen FIRST and treats an already-flat account as success without
  ever calling closeContract, specifically to avoid depending on this unconfirmed behavior.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

BASE_URL = "https://api.topstepx.com"  # doc-confirmed, see module docstring

# OrderType enum (doc-confirmed, order-place page)
ORDER_TYPE_LIMIT = 1
ORDER_TYPE_MARKET = 2
ORDER_TYPE_STOP = 4
ORDER_TYPE_TRAILING_STOP = 5
ORDER_TYPE_JOIN_BID = 6
ORDER_TYPE_JOIN_ASK = 7

# OrderSide enum (doc-confirmed, order-place page)
ORDER_SIDE_BID = 0  # buy
ORDER_SIDE_ASK = 1  # sell

# OrderStatus enum (doc-confirmed, realtime page -- see module docstring)
ORDER_STATUS_NONE = 0
ORDER_STATUS_OPEN = 1
ORDER_STATUS_FILLED = 2
ORDER_STATUS_CANCELLED = 3
ORDER_STATUS_EXPIRED = 4
ORDER_STATUS_REJECTED = 5
ORDER_STATUS_PENDING = 6

# PositionType enum (doc-confirmed, realtime page -- see module docstring)
POSITION_TYPE_UNDEFINED = 0
POSITION_TYPE_LONG = 1
POSITION_TYPE_SHORT = 2

# BarUnit enum (doc-confirmed, retrieve-bars page)
BAR_UNIT_SECOND = 1
BAR_UNIT_MINUTE = 2
BAR_UNIT_HOUR = 3
BAR_UNIT_DAY = 4
BAR_UNIT_WEEK = 5
BAR_UNIT_MONTH = 6

# Rate limits (doc-confirmed, rate-limits page)
RETRIEVE_BARS_RATE_LIMIT = (50, 30.0)  # (requests, per_seconds)
DEFAULT_RATE_LIMIT = (200, 60.0)


class ProjectXError(RuntimeError):
    """Raised when the API responds with success=false or a non-2xx HTTP status.

    Carries `error_code`/`error_message` from the response body when present
    (every documented response envelope has `errorCode`/`errorMessage`), so
    callers can log/journal the real reason without re-parsing the response.
    """

    def __init__(self, message: str, *, error_code: int | None = None, error_message: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_message = error_message


class Transport(Protocol):
    """Thin HTTP transport interface -- the ONLY thing that touches the network.

    Every test in tests/test_projectx.py drives `ProjectXClient` through a
    fake implementation of this protocol (`FakeTransport` in the test file),
    so no test in this repo ever makes a real network call. A real
    implementation (`RequestsTransport`, below) is used at runtime only.
    """

    def post(self, path: str, *, json: dict, headers: dict[str, str]) -> "TransportResponse": ...


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: dict[str, Any]


class RequestsTransport:
    """Real HTTP transport using the `requests` library. Never used in tests."""

    def __init__(self, *, base_url: str = BASE_URL, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def post(self, path: str, *, json: dict, headers: dict[str, str]) -> TransportResponse:
        import requests  # imported lazily so importing this module never requires `requests`

        resp = requests.post(f"{self.base_url}{path}", json=json, headers=headers, timeout=self.timeout_seconds)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return TransportResponse(status_code=resp.status_code, body=body)


@dataclass(frozen=True)
class Contract:
    id: str
    name: str
    description: str
    tick_size: float
    tick_value: float
    active_contract: bool
    symbol_id: str

    @classmethod
    def from_dict(cls, d: dict) -> "Contract":
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            tick_size=float(d["tickSize"]),
            tick_value=float(d["tickValue"]),
            active_contract=bool(d.get("activeContract", False)),
            symbol_id=d.get("symbolId", ""),
        )


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    can_trade: bool
    is_visible: bool
    balance: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            can_trade=bool(d.get("canTrade", False)),
            is_visible=bool(d.get("isVisible", True)),
            balance=d.get("balance"),
        )


@dataclass(frozen=True)
class Bar:
    """Raw bar from retrieveBars, before any conversion to src.live.feed.Bar."""

    t: str  # ISO datetime string, as returned by the API
    o: float
    h: float
    l: float
    c: float
    v: int

    @classmethod
    def from_dict(cls, d: dict) -> "Bar":
        return cls(t=d["t"], o=float(d["o"]), h=float(d["h"]), l=float(d["l"]), c=float(d["c"]), v=int(d["v"]))


@dataclass(frozen=True)
class OrderRecord:
    id: int
    account_id: int
    contract_id: str
    status: int
    type: int
    side: int
    size: int
    limit_price: float | None
    stop_price: float | None
    fill_volume: int | None
    filled_price: float | None
    custom_tag: str | None

    @classmethod
    def from_dict(cls, d: dict) -> "OrderRecord":
        return cls(
            id=d["id"],
            account_id=d["accountId"],
            contract_id=d["contractId"],
            status=d["status"],
            type=d["type"],
            side=d["side"],
            size=d["size"],
            limit_price=d.get("limitPrice"),
            stop_price=d.get("stopPrice"),
            fill_volume=d.get("fillVolume"),
            filled_price=d.get("filledPrice"),
            custom_tag=d.get("customTag"),
        )

    @property
    def is_open(self) -> bool:
        return self.status == ORDER_STATUS_OPEN

    @property
    def is_filled(self) -> bool:
        return self.status == ORDER_STATUS_FILLED

    @property
    def is_terminal(self) -> bool:
        """True once the order can no longer transition (filled/cancelled/expired/rejected)."""
        return self.status in (ORDER_STATUS_FILLED, ORDER_STATUS_CANCELLED, ORDER_STATUS_EXPIRED, ORDER_STATUS_REJECTED)


@dataclass(frozen=True)
class PositionRecord:
    id: int
    account_id: int
    contract_id: str
    type: int
    size: int
    average_price: float
    creation_timestamp: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "PositionRecord":
        return cls(
            id=d["id"],
            account_id=d["accountId"],
            contract_id=d["contractId"],
            type=d["type"],
            size=d["size"],
            average_price=float(d["averagePrice"]),
            creation_timestamp=d.get("creationTimestamp"),
        )


class ProjectXClient:
    """Thin, doc-cited wrapper over the ProjectX Gateway REST API. See module docstring.

    Client-side rate limiting (reviewer Fix 8, 2026-07-19, COSMETIC -- was
    dead code before this): TWO `RateLimiter` instances, one for
    `/api/History/retrieveBars` (doc-stated 50 requests/30s, stricter) and
    one for every other endpoint (doc-stated 200 requests/60s). `_post`
    acquires the appropriate one before every request, so normal client
    usage stays under the documented caps without relying solely on the
    server's own 429 response (which `_post` still handles as a hard
    error either way -- this is a courtesy, not a substitute).
    """

    def __init__(self, transport: Transport, *, username: str, api_key: str, sleep: Callable[[float], None] = time.sleep) -> None:
        self._transport = transport
        self._username = username
        self._api_key = api_key
        self._token: str | None = None
        self._sleep = sleep
        self._retrieve_bars_limiter = RateLimiter(*RETRIEVE_BARS_RATE_LIMIT)
        self._default_limiter = RateLimiter(*DEFAULT_RATE_LIMIT)

    # -- internal ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            raise ProjectXError("not authenticated -- call login() first")
        # See module docstring "AUTH HEADER" note: Bearer-token convention is
        # an inference from JWT usage, not a directly-cited doc example.
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict, *, auth: bool = True) -> dict:
        limiter = self._retrieve_bars_limiter if path == "/api/History/retrieveBars" else self._default_limiter
        limiter.acquire(sleep=self._sleep)

        headers = self._headers() if auth else {"Content-Type": "application/json"}
        resp = self._transport.post(path, json=payload, headers=headers)
        if resp.status_code == 429:
            raise ProjectXError(f"{path}: HTTP 429 rate limited")
        if resp.status_code >= 400:
            raise ProjectXError(f"{path}: HTTP {resp.status_code}: {resp.body}")
        body = resp.body
        if not body.get("success", False):
            raise ProjectXError(
                f"{path}: API reported failure",
                error_code=body.get("errorCode"),
                error_message=body.get("errorMessage"),
            )
        return body

    # -- auth ----------------------------------------------------------

    def login(self) -> str:
        """POST /api/Auth/loginKey. Sets and returns the session token."""
        body = self._post("/api/Auth/loginKey", {"userName": self._username, "apiKey": self._api_key}, auth=False)
        self._token = body["token"]
        return self._token

    def validate_session(self) -> str:
        """POST /api/Auth/validate. Refreshes the token (valid 24h); returns the new token."""
        body = self._post("/api/Auth/validate", {})
        self._token = body["newToken"]
        return self._token

    @property
    def token(self) -> str | None:
        return self._token

    # -- account ----------------------------------------------------------

    def search_accounts(self, *, only_active: bool = True) -> list[Account]:
        """POST /api/Account/search."""
        body = self._post("/api/Account/search", {"onlyActiveAccounts": only_active})
        return [Account.from_dict(a) for a in body.get("accounts", [])]

    # -- contracts ----------------------------------------------------------

    def search_contracts(self, search_text: str, *, live: bool = False) -> list[Contract]:
        """POST /api/Contract/search. Returns up to 20 contracts (doc-stated limit)."""
        body = self._post("/api/Contract/search", {"searchText": search_text, "live": live})
        return [Contract.from_dict(c) for c in body.get("contracts", [])]

    def search_contract_by_id(self, contract_id: str) -> Contract:
        """POST /api/Contract/searchById."""
        body = self._post("/api/Contract/searchById", {"contractId": contract_id})
        return Contract.from_dict(body["contract"])

    def available_contracts(self, *, live: bool = False) -> list[Contract]:
        """POST /api/Contract/available."""
        body = self._post("/api/Contract/available", {"live": live})
        return [Contract.from_dict(c) for c in body.get("contracts", [])]

    def resolve_front_contract(self, symbol_prefix: str, *, live: bool = False) -> Contract:
        """Resolve a tradable front-month contract by symbol prefix (e.g. "MNQ").

        UNVERIFIED (see module docstring): picks the FIRST contract from
        Contract/search whose `name` starts with `symbol_prefix` and whose
        `activeContract` flag is True. This is a reasonable reading of the
        documented schema (search-contracts page's example shows `name` as
        a short ticker like "6BU5", and `activeContract` as the obvious
        "is this the one actually tradable right now" signal), but has never
        been checked against a real MNQ response. If Contract/search returns
        multiple active MNQ-prefixed contracts (e.g. during a roll), this
        raises rather than silently guessing which one is the true front
        month -- --preflight (src/live/runner.py) surfaces exactly this
        raw list so a human can eyeball it before any live run.
        """
        contracts = self.search_contracts(symbol_prefix, live=live)
        active = [c for c in contracts if c.active_contract and c.name.upper().startswith(symbol_prefix.upper())]
        if not active:
            raise ProjectXError(
                f"no active contract found for symbol_prefix={symbol_prefix!r} "
                f"(got {len(contracts)} total results, none matched)"
            )
        if len(active) > 1:
            names = ", ".join(f"{c.id} ({c.name})" for c in active)
            raise ProjectXError(
                f"ambiguous front contract for symbol_prefix={symbol_prefix!r}: {len(active)} active "
                f"matches ({names}) -- resolve manually, do not guess which is the true front month"
            )
        return active[0]

    # -- bars ----------------------------------------------------------

    def retrieve_bars(
        self,
        contract_id: str,
        *,
        start_time: str,
        end_time: str,
        unit: int = BAR_UNIT_MINUTE,
        unit_number: int = 1,
        limit: int = 20,
        include_partial_bar: bool = False,
        live: bool = False,
    ) -> list[Bar]:
        """POST /api/History/retrieveBars. `start_time`/`end_time` are ISO-8601 strings.

        Doc-stated cap: 20,000 bars/request (not enforced client-side here --
        the live feed only ever asks for a handful of recent 1m bars).
        """
        body = self._post(
            "/api/History/retrieveBars",
            {
                "contractId": contract_id,
                "live": live,
                "startTime": start_time,
                "endTime": end_time,
                "unit": unit,
                "unitNumber": unit_number,
                "limit": limit,
                "includePartialBar": include_partial_bar,
            },
        )
        return [Bar.from_dict(b) for b in body.get("bars", [])]

    # -- orders ----------------------------------------------------------

    def place_order(
        self,
        *,
        account_id: int,
        contract_id: str,
        type: int,
        side: int,
        size: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
        trail_price: float | None = None,
        custom_tag: str | None = None,
        stop_loss_bracket: dict | None = None,
        take_profit_bracket: dict | None = None,
    ) -> int:
        """POST /api/Order/place. Returns the new orderId."""
        payload = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": type,
            "side": side,
            "size": size,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "trailPrice": trail_price,
            "customTag": custom_tag,
            "stopLossBracket": stop_loss_bracket,
            "takeProfitBracket": take_profit_bracket,
        }
        body = self._post("/api/Order/place", payload)
        return body["orderId"]

    def cancel_order(self, *, account_id: int, order_id: int) -> None:
        """POST /api/Order/cancel."""
        self._post("/api/Order/cancel", {"accountId": account_id, "orderId": order_id})

    def modify_order(
        self,
        *,
        account_id: int,
        order_id: int,
        size: int | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        trail_price: float | None = None,
    ) -> None:
        """POST /api/Order/modify."""
        self._post(
            "/api/Order/modify",
            {
                "accountId": account_id,
                "orderId": order_id,
                "size": size,
                "limitPrice": limit_price,
                "stopPrice": stop_price,
                "trailPrice": trail_price,
            },
        )

    def search_orders(self, *, account_id: int, start_timestamp: str, end_timestamp: str | None = None) -> list[OrderRecord]:
        """POST /api/Order/search."""
        body = self._post(
            "/api/Order/search",
            {"accountId": account_id, "startTimestamp": start_timestamp, "endTimestamp": end_timestamp},
        )
        return [OrderRecord.from_dict(o) for o in body.get("orders", [])]

    def search_open_orders(self, *, account_id: int) -> list[OrderRecord]:
        """POST /api/Order/searchOpen."""
        body = self._post("/api/Order/searchOpen", {"accountId": account_id})
        return [OrderRecord.from_dict(o) for o in body.get("orders", [])]

    # -- positions ----------------------------------------------------------

    def search_open_positions(self, *, account_id: int) -> list[PositionRecord]:
        """POST /api/Position/searchOpen."""
        body = self._post("/api/Position/searchOpen", {"accountId": account_id})
        return [PositionRecord.from_dict(p) for p in body.get("positions", [])]

    def close_position(self, *, account_id: int, contract_id: str) -> None:
        """POST /api/Position/closeContract. Flattens the ENTIRE open position for this contract."""
        self._post("/api/Position/closeContract", {"accountId": account_id, "contractId": contract_id})

    def partial_close_position(self, *, account_id: int, contract_id: str, size: int) -> None:
        """POST /api/Position/partialCloseContract."""
        self._post("/api/Position/partialCloseContract", {"accountId": account_id, "contractId": contract_id, "size": size})

    # -- trades ----------------------------------------------------------

    def search_trades(self, *, account_id: int, start_timestamp: str, end_timestamp: str | None = None) -> list[dict]:
        """POST /api/Trade/search. Returns raw dicts (fills/executions, for reconciliation reporting)."""
        body = self._post(
            "/api/Trade/search",
            {"accountId": account_id, "startTimestamp": start_timestamp, "endTimestamp": end_timestamp},
        )
        return body.get("trades", [])


class RateLimiter:
    """Simple client-side token-bucket-ish limiter to stay under the documented caps.

    Not a substitute for handling a real 429 (ProjectXError still propagates
    one if the server disagrees) -- this only reduces the chance of hitting
    one during normal polling. `retrieve_bars` calls should use
    `RETRIEVE_BARS_RATE_LIMIT`; everything else uses `DEFAULT_RATE_LIMIT`.
    """

    def __init__(self, max_requests: int, per_seconds: float) -> None:
        self.max_requests = max_requests
        self.per_seconds = per_seconds
        self._timestamps: list[float] = []

    def acquire(self, *, now: float | None = None, sleep=time.sleep) -> None:
        now = time.monotonic() if now is None else now
        cutoff = now - self.per_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) >= self.max_requests:
            wait = self._timestamps[0] + self.per_seconds - now
            if wait > 0:
                sleep(wait)
            now = time.monotonic() if now is None else now + wait
            cutoff = now - self.per_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
        self._timestamps.append(now)
