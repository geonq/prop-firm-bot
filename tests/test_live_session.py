"""End-to-end tests for src/live/live_runner.py::run_live_or_paper_session,
driven entirely through fake transports/feeds -- no real network, no real
credentials, no real clock waiting.

Covers: paper-mode entry+exit over a real-shaped session, live-mode
entry+exit via LiveBroker (with OCO), restart recovery in both modes (paper
via state.json, live via broker.reconcile() as the authoritative source),
and the "exchange wins over stale local state" fix.

Both `client_factory` and `feed_factory` are injected (see
src/live/live_runner.py's own docstring) -- this drives the REAL session
loop, REAL PaperBroker/LiveBroker, REAL engine, with only the transport and
the bar clock faked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.live.live_runner import run_live_or_paper_session
from src.live.projectx import (
    ORDER_STATUS_FILLED,
    ORDER_STATUS_OPEN,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    ProjectXClient,
    TransportResponse,
)
from src.live.feed import Bar, ET
from src.live.config import FROZEN_PARAMS
from src.live.engine import ORBLiveEngine

ET_TZ = ZoneInfo("America/New_York")


def test_engine_opens_immediately_after_final_or_bar_without_waiting_for_0935_close():
    """A completed-bar live feed receives 09:34 near 09:35:02.

    The signal is fully known then, so waiting for the completed 09:35 bar would
    defer the order until roughly 09:36 and then model a retroactive 09:35-open
    fill. The engine must instead emit the entry from the final OR bar, using
    its close as the contemporaneous paper reference and 09:35 as entry time.
    """
    d = date(2026, 7, 20)
    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)
    all_events = []
    for minute, close in enumerate([100.0, 100.25, 100.5, 100.75, 101.0], start=30):
        all_events.extend(
            engine.on_bar(
                Bar(
                    ts=_minute(d, 9, minute),
                    session_date=d,
                    open=100.0,
                    high=max(101.25, close),
                    low=99.5,
                    close=close,
                    volume=10,
                )
            )
        )

    opened = [event for event in all_events if type(event).__name__ == "TradeOpened"]
    assert len(opened) == 1
    assert opened[0].entry_ts == _minute(d, 9, 35)
    assert opened[0].entry_price == pytest.approx(101.25)  # 09:34 close + one adverse tick


class ScriptedTransport:
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


def _client_factory(transport: ScriptedTransport):
    def factory() -> ProjectXClient:
        # sleep=no-op: see tests/test_projectx.py::_client for why the
        # client's own rate limiter (Fix 8) must never cause a real sleep here.
        return ProjectXClient(transport, username="u", api_key="k", sleep=lambda s: None)

    return factory


def _setup_auth_account_contract(transport: ScriptedTransport, *, account_id: int = 465, contract_id: str = "CON.F.US.MNQ.U25") -> None:
    transport.queue("/api/Auth/loginKey", 200, _ok({"token": "t"}))
    transport.queue("/api/Account/search", 200, _ok({"accounts": [{"id": account_id, "name": "PRACTICEACCT", "canTrade": True, "isVisible": True}]}))
    transport.queue(
        "/api/Contract/search",
        200,
        _ok({"contracts": [{"id": contract_id, "name": "MNQU5", "description": "d", "tickSize": 0.25, "tickValue": 0.5, "activeContract": True, "symbolId": "F.US.MNQ"}]}),
    )


def _minute(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=ET_TZ)


class ScriptedBarFeed:
    """A minimal, already-built BarFeed-protocol object: yields a fixed list
    of Bar objects in order, with no wall-clock waiting -- used via
    `feed_factory` injection so tests never depend on real time passing.
    """

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars
        self._max_ts = None

    @property
    def max_timestamp_served(self):
        return self._max_ts

    def __iter__(self):
        for b in self._bars:
            self._max_ts = b.ts
            yield b


class ScriptedBarFeedWithWaitTicks:
    """Like `ScriptedBarFeed`, but calls a caller-supplied `on_wait_tick`
    hook a fixed number of times BEFORE yielding each bar -- models the real
    `LiveBarFeed._wait_until` calling `on_wait_tick` roughly once per second
    while waiting for the next minute's bar (reviewer Fix 6, 2026-07-19,
    OPS). `ticks_before_bar[i]` is how many times `on_wait_tick` fires
    immediately before `bars[i]` is yielded (0 if omitted / list too short).
    """

    def __init__(self, bars: list[Bar], on_wait_tick, ticks_before_bar: list[int] | None = None) -> None:
        self._bars = bars
        self._on_wait_tick = on_wait_tick
        self._ticks_before_bar = ticks_before_bar or []
        self._max_ts = None

    @property
    def max_timestamp_served(self):
        return self._max_ts

    def __iter__(self):
        for i, b in enumerate(self._bars):
            ticks = self._ticks_before_bar[i] if i < len(self._ticks_before_bar) else 0
            for _ in range(ticks):
                self._on_wait_tick()
            self._max_ts = b.ts
            yield b


def _bar(d: date, hh: int, mm: int, *, o, h, l, c, v=10.0) -> Bar:
    return Bar(ts=pd_timestamp(d, hh, mm), session_date=d, open=o, high=h, low=l, close=c, volume=v)


def pd_timestamp(d: date, hh: int, mm: int):
    import pandas as pd

    return pd.Timestamp(_minute(d, hh, mm))


def _long_session_bars_target_exit(d: date) -> list[Bar]:
    """OR window (5 bars, 09:30-09:34) bullish -> long entry at 09:35 open
    (100.5 + 1 tick adverse slippage = 100.75). Stop = or_low (99.5) ->
    risk = 100.75 - 99.5 = 1.25. Target = entry + 4*risk = 105.75. Bar at
    09:36 spikes to high=106.5, well past target. These exact figures were
    verified by running the real ORBLiveEngine over this bar sequence
    directly (not hand-computed and hoped to match) before being encoded
    here, after an earlier hand-computed guess (risk=1.0, target~104.5)
    turned out wrong and made this test fail against the real engine.
    """
    bars = [
        _bar(d, 9, 30, o=100.0, h=100.2, l=99.9, c=100.1),
        _bar(d, 9, 31, o=100.1, h=101.0, l=100.0, c=100.8),
        _bar(d, 9, 32, o=100.8, h=100.9, l=99.5, c=100.0),
        _bar(d, 9, 33, o=100.0, h=100.3, l=99.8, c=100.2),
        _bar(d, 9, 34, o=100.2, h=100.6, l=100.1, c=100.5),
        _bar(d, 9, 35, o=100.5, h=100.6, l=100.4, c=100.5),  # entry bar
        _bar(d, 9, 36, o=106.0, h=106.5, l=105.9, c=106.2),  # target (105.75) hit
    ]
    return bars


def test_paper_mode_full_session_entry_and_target_exit(tmp_path):
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    trades = run_live_or_paper_session(
        mode="paper", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed(bars),
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.direction == "long"
    assert trade.exit_reason == "target"
    assert trade.entry_price == pytest.approx(100.75)  # entry_bar open (100.5) + 1 tick (0.25) adverse slippage

    csv_text = (tmp_path / "trades.csv").read_text()
    assert "long" in csv_text
    assert "target" in csv_text


def test_paper_mode_restart_mid_session_does_not_double_enter(tmp_path):
    """Simulates a crash WHILE a position is open: state.json is written
    directly to represent "process 1 opened a position and then died before
    it could exit" (run_live_or_paper_session's own EoD-flatten semantics
    make it impossible to observe this state through a truncated
    ScriptedBarFeed alone -- the loop always calls on_session_end() once its
    feed is exhausted, which is CORRECT behavior for a real LiveBarFeed
    reaching the true end of its polling window, but means a deliberately
    truncated fake feed doesn't actually model "the process died", it
    models "the session legitimately ended early"). Writing state.json
    directly is the more honest way to set up this precondition.
    """
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)

    from src.live.broker import PositionSnapshot
    from src.live.runner import RunnerState

    pos = PositionSnapshot(
        session_date=d, direction="long", entry_ts="2026-07-20 09:35:00-04:00", entry_price=100.75,
        stop_price=99.5, target_price=105.75, contracts=1, risk_points=1.25,
    )
    runner_state = RunnerState(tmp_path / "state.json")
    runner_state.roll_to_session(d)
    runner_state.trade_taken = True
    runner_state.position = pos
    runner_state.save()

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["trade_taken"] is True
    assert state["position"] is not None
    assert state["position"]["direction"] == "long"

    # "Restart": run_live_or_paper_session picks up from this persisted
    # state -- feed it just the remaining bar (the target-hit bar) as if
    # the process had just been restarted partway through the session.
    transport2 = ScriptedTransport()
    _setup_auth_account_contract(transport2)
    remaining_bars = bars[6:]  # just the target-hit bar
    trades = run_live_or_paper_session(
        mode="paper", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport2),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed(remaining_bars),
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "target"

    csv_rows = (tmp_path / "trades.csv").read_text().strip().splitlines()
    assert len(csv_rows) == 2  # header + exactly ONE trade row, no duplicate entry


def _order_dict(*, id, status, type, side, size, stop_price=None, limit_price=None, fill_volume=0, filled_price=None, tag="orb6b-2026-07-20-abc"):
    return {
        "id": id, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "symbolId": "F.US.MNQ",
        "creationTimestamp": "2026-07-20T13:35:00Z", "updateTimestamp": "2026-07-20T13:35:01Z",
        "status": status, "type": type, "side": side, "size": size,
        "limitPrice": limit_price, "stopPrice": stop_price, "fillVolume": fill_volume,
        "filledPrice": filled_price, "customTag": tag,
    }


def test_live_mode_full_session_entry_and_target_exit_via_oco(tmp_path):
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    # reconcile() at session start: flat.
    transport.queue("/api/Position/searchOpen", 200, _ok({"positions": []}))

    # entry market order
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=0, size=400, fill_volume=400, filled_price=100.75)]}),
    )
    # stop + target working orders
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))

    # OCO polls on subsequent bars: both open until the target bar, when target fills.
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=400, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=400, limit_price=104.5),
        ]}),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=400, stop_price=99.5)]}),
    )
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_LIMIT, side=1, size=400, limit_price=104.5, fill_volume=400, filled_price=104.5)]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel the stop

    # close_position after OCO detects the target fill (bar.ts, bar.close as modeled fallback)
    transport.queue("/api/Order/cancel", 200, _ok({}))  # close_position also tries to cancel both (stop already gone, target already filled -- safe_cancel tolerates failure)
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue("/api/Trade/search", 200, _ok({"trades": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "price": 104.5, "profitAndLoss": None, "fees": 1.48, "side": 1, "size": 400, "voided": False, "orderId": 1003}]}))

    trades = run_live_or_paper_session(
        mode="live", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed(bars),
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "target"
    assert trades[0].contracts == 400


def test_live_mode_oco_fill_detected_between_bars_via_wait_tick(tmp_path):
    """Reviewer Fix 6 (2026-07-19, OPS): a real stop/target fill must be
    detected via the ~10s between-bar poll (on_wait_tick), not only once per
    bar. This feeds ONLY the entry bar (09:35) through ScriptedBarFeedWithWaitTicks,
    which fires on_wait_tick 10 times before the next bar (09:36) is yielded
    -- exactly enough to cross OCO_WAIT_TICK_POLL_EVERY=10 once. The target-
    fill transport response is queued for THAT poll call, with only a single
    flat/no-op searchOpen queued for the subsequent per-bar poll (proving it
    sees broker.position is already None and does nothing) -- if fix 6's
    wiring were absent (on_wait_tick never called, or never actually calling
    poll_oco), this test would fail with "no scripted response left for
    POST /api/Order/searchOpen" or with 0 trades recorded, since there'd be
    no OTHER path to detect the fill before session end.
    """
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)
    entry_bars = bars[:6]  # through the 09:35 entry bar only
    next_bar = bars[6]  # 09:36 -- yielded AFTER the wait-ticks, itself flat/uneventful for OCO purposes
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    # reconcile() at session start: flat.
    transport.queue("/api/Position/searchOpen", 200, _ok({"positions": []}))

    # entry market order
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=0, size=400, fill_volume=400, filled_price=100.75)]}),
    )
    # stop + target working orders
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))

    # NOTE: the per-bar OCO poll (live_runner.py's block right before
    # engine.on_bar) does NOT run on the entry bar itself -- broker.position
    # is still None at that point in the SAME iteration that places the
    # bracket (TradeOpened is handled later, after that poll check). So the
    # FIRST searchOpen consumed after the bracket is placed is the WAIT-TICK
    # poll (10th tick, between the entry bar and next_bar) -- this is the
    # response under test: the target-filled result.
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=400, stop_price=99.5)]}),
    )
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_LIMIT, side=1, size=400, limit_price=104.5, fill_volume=400, filled_price=104.5)]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))  # cancel the stop (sibling of the filled target)

    # close_position() called from the wait-tick handler.
    transport.queue("/api/Order/cancel", 200, _ok({}))  # safe_cancel tolerates the stop already being gone
    transport.queue("/api/Order/cancel", 200, _ok({}))  # target already filled, also tolerated
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue("/api/Trade/search", 200, _ok({"trades": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "price": 104.5, "profitAndLoss": None, "fees": 1.48, "side": 1, "size": 400, "voided": False, "orderId": 1003}]}))

    # NOTE: next_bar (09:36) is still yielded after this (a real LiveBarFeed
    # always yields the bar it was waiting for), and its own per-bar OCO
    # poll check runs too -- but by then broker.position is already None
    # (closed by the wait-tick above), so that check short-circuits with NO
    # transport call at all. No searchOpen is queued for it -- if fix 6's
    # wait-tick close did NOT happen first, this test would fail with "no
    # scripted response left for POST /api/Order/searchOpen" right there.

    def _feed_factory(client, contract_id, session_date, journal, on_wait_tick=None):
        assert on_wait_tick is not None  # this IS the thing fix 6 wires up -- must not be dropped
        return ScriptedBarFeedWithWaitTicks(
            entry_bars + [next_bar], on_wait_tick, ticks_before_bar=[0, 0, 0, 0, 0, 0, 10]
        )

    trades = run_live_or_paper_session(
        mode="live", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=_feed_factory,
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "target"
    assert trades[0].contracts == 400
    # exit_ts came from the wait-tick's own datetime.now(ET) fallback (no bar
    # available at that moment), NOT from next_bar.ts (09:36) -- proving the
    # close happened BEFORE the next bar was even yielded, i.e. strictly
    # between bars via on_wait_tick, not via the per-bar poll.
    assert str(bars[6].ts) not in trades[0].exit_ts


def test_live_mode_wait_tick_does_not_poll_oco_before_the_tenth_tick(tmp_path):
    """The wait-tick OCO poll (fix 6) only actually calls the API every
    ~10th tick, not every tick -- otherwise it would trivially blow through
    the general rate limit / hammer the API every second. This feeds ONLY 9
    wait-ticks (one short of OCO_WAIT_TICK_POLL_EVERY=10) before the next
    bar -- no searchOpen response is queued for a wait-tick poll at all, so
    if the throttle were broken (polling every tick, or off-by-one), this
    would fail with "no scripted response left for POST
    /api/Order/searchOpen" raised from inside the 9th on_wait_tick call,
    instead of cleanly reaching and consuming next_bar's own per-bar poll.
    """
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)
    entry_bars = bars[:6]
    next_bar = bars[6]
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    transport.queue("/api/Position/searchOpen", 200, _ok({"positions": []}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1001}))
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1001, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_MARKET, side=0, size=400, fill_volume=400, filled_price=100.75)]}),
    )
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1002}))
    transport.queue("/api/Order/place", 200, _ok({"orderId": 1003}))

    # Only ONE searchOpen queued for the rest of the test -- next_bar's own
    # per-bar poll (target filled there instead, just to reach a clean exit).
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [_order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=400, stop_price=99.5)]}),
    )
    transport.queue(
        "/api/Order/search",
        200,
        _ok({"orders": [_order_dict(id=1003, status=ORDER_STATUS_FILLED, type=ORDER_TYPE_LIMIT, side=1, size=400, limit_price=104.5, fill_volume=400, filled_price=104.5)]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue("/api/Trade/search", 200, _ok({"trades": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "price": 104.5, "profitAndLoss": None, "fees": 1.48, "side": 1, "size": 400, "voided": False, "orderId": 1003}]}))

    def _feed_factory(client, contract_id, session_date, journal, on_wait_tick=None):
        return ScriptedBarFeedWithWaitTicks(
            entry_bars + [next_bar], on_wait_tick, ticks_before_bar=[0, 0, 0, 0, 0, 0, 9]
        )

    trades = run_live_or_paper_session(
        mode="live", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=_feed_factory,
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "target"
    # Entry is now emitted immediately after the completed 09:34 OR bar, so
    # the first post-entry per-bar OCO poll occurs on the 09:35 bar. The nine
    # wait ticks still must not consume the sole queued searchOpen response.
    assert trades[0].exit_ts == str(entry_bars[-1].ts)


def test_paper_mode_wait_ticks_never_poll_oco(tmp_path):
    """`on_wait_tick` must be a no-op in --mode paper (there is no real
    exchange/OCO to poll -- PaperBroker isn't even a LiveBroker instance).
    Feeds many wait-ticks (well past the fix-6 threshold) with NO
    searchOpen/Order endpoints queued at all beyond setup -- if paper mode
    accidentally called broker.poll_oco() (which doesn't exist on
    PaperBroker), this would raise AttributeError; if it were live-mode-gated
    incorrectly and somehow tried an HTTP call, it would fail with "no
    scripted response left."
    """
    d = date(2026, 7, 20)
    bars = _long_session_bars_target_exit(d)
    entry_bars = bars[:6]
    next_bar = bars[6]
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    def _feed_factory(client, contract_id, session_date, journal, on_wait_tick=None):
        return ScriptedBarFeedWithWaitTicks(
            entry_bars + [next_bar], on_wait_tick, ticks_before_bar=[0, 0, 0, 0, 0, 0, 25]
        )

    trades = run_live_or_paper_session(
        mode="paper", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=_feed_factory,
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "target"


def test_live_mode_reconcile_adopts_position_and_never_double_enters(tmp_path):
    """The core idempotency guarantee for --mode live: even if state.json is
    missing/stale, a real open position on the exchange is discovered via
    reconcile() and adopted -- no second entry is ever placed.
    """
    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 100.75}]}),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    # No state.json exists at all (simulating a fresh/corrupted local state) --
    # only ONE bar fed (a flat, uneventful bar) so the session ends via
    # on_session_end -> EoD flatten of the adopted position.
    flat_bar = _bar(d, 11, 39, o=101.0, h=101.1, l=100.9, c=101.0)
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 200, _ok({}))
    transport.queue("/api/Trade/search", 200, _ok({"trades": []}))

    trades = run_live_or_paper_session(
        mode="live", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed([flat_bar]),
    )
    assert len(trades) == 1
    assert trades[0].contracts == 3
    assert trades[0].entry_price == 100.75  # adopted from the real exchange position, never re-entered

    place_calls = [c for c in transport.calls if c[0] == "/api/Order/place"]
    assert place_calls == []  # NO entry order was ever placed this run

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["trade_taken"] is True


# ---------------------------------------------------------------------------
# FIX 3 (reviewer, 2026-07-19, CRITICAL): if the EoD/error-path flatten
# itself fails (Position/closeContract keeps raising), the session must
# still journal FlattenOnError FIRST (unconditionally), retry the flatten
# with backoff, and if every attempt fails, journal a NakedPositionAlarm and
# write the daily report with the alarm prominent -- the original bug let a
# re-raising close_position() call inside the exception handler prevent
# FlattenOnError from EVER being journaled.
# ---------------------------------------------------------------------------


def test_flatten_failure_journals_flatten_on_error_and_naked_position_alarm(tmp_path):
    """closeContract ALWAYS raises -> journal contains FlattenOnError +
    NakedPositionAlarm, report file written, nonzero result (via
    SessionErrored propagating out of run_live_or_paper_session).
    """
    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    # Adopt an already-open position via reconcile() (fast path to "position
    # open", same pattern as test_live_mode_reconcile_adopts_position...).
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 100.75}]}),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    flat_bar = _bar(d, 11, 39, o=101.0, h=101.1, l=100.9, c=101.0)
    # OCO poll on the flat bar: both still open.
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    # EoD close_position(): cancels succeed (not what's under test here),
    # but Position/closeContract ALWAYS fails -- this is what should surface
    # as an unhandled exception inside the try block, caught by the
    # exception handler under test.
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 500, {"success": False})

    with pytest.raises(Exception):  # SessionErrored, imported below for the type-specific assertion
        run_live_or_paper_session(
            mode="live", session_date=d, state_dir=tmp_path,
            client_factory=_client_factory(transport),
            feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed([flat_bar]),
            sleep=lambda s: None,
        )

    events_text = (tmp_path / "events.jsonl").read_text()
    assert "FlattenOnError" in events_text
    assert "NakedPositionAlarm" in events_text

    # FlattenOnError must appear BEFORE NakedPositionAlarm in the journal --
    # the whole point of Fix 3 is that FlattenOnError is written FIRST,
    # unconditionally, not after (or instead of) the retry outcome.
    flatten_on_error_line = next(i for i, line in enumerate(events_text.splitlines()) if "FlattenOnError" in line and "Retry" not in line)
    naked_alarm_line = next(i for i, line in enumerate(events_text.splitlines()) if "NakedPositionAlarm" in line)
    assert flatten_on_error_line < naked_alarm_line

    from src.live.report import write_daily_report

    report_path = write_daily_report(session_date=d, state_dir=tmp_path)
    report_text = report_path.read_text()
    assert "NakedPositionAlarm" in report_text
    assert "ALARM" in report_text


def test_flatten_failure_raises_session_errored_with_flattened_false(tmp_path):
    from src.live.live_runner import SessionErrored

    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 100.75}]}),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    flat_bar = _bar(d, 11, 39, o=101.0, h=101.1, l=100.9, c=101.0)
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 500, {"success": False})

    with pytest.raises(SessionErrored) as exc_info:
        run_live_or_paper_session(
            mode="live", session_date=d, state_dir=tmp_path,
            client_factory=_client_factory(transport),
            feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed([flat_bar]),
            sleep=lambda s: None,
        )
    assert exc_info.value.flattened is False


def test_run_auto_writes_report_and_exits_nonzero_when_flatten_fails(tmp_path):
    """The run_auto-level guarantee: even when the session raises SessionErrored,
    the daily report is still written (via the try/finally in _run_auto_locked)
    and the process exit code is nonzero.
    """
    from src.live.live_runner import _run_auto_locked

    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)
    transport.queue(
        "/api/Position/searchOpen",
        200,
        _ok({"positions": [{"id": 1, "accountId": 465, "contractId": "CON.F.US.MNQ.U25", "creationTimestamp": "ts", "type": 1, "size": 3, "averagePrice": 100.75}]}),
    )
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    flat_bar = _bar(d, 11, 39, o=101.0, h=101.1, l=100.9, c=101.0)
    transport.queue(
        "/api/Order/searchOpen",
        200,
        _ok({"orders": [
            _order_dict(id=1002, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_STOP, side=1, size=3, stop_price=99.5),
            _order_dict(id=1003, status=ORDER_STATUS_OPEN, type=ORDER_TYPE_LIMIT, side=1, size=3, limit_price=104.5),
        ]}),
    )
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Order/cancel", 200, _ok({}))
    transport.queue("/api/Position/closeContract", 500, {"success": False})

    exit_code = _run_auto_locked(
        mode="live", state_dir=tmp_path, risk_per_trade_usd=400.0, max_contracts=20, daily_loss_cap_usd=600.0,
        account_name_hint=None, now_fn=lambda: datetime(2026, 7, 20, 9, 30, tzinfo=ET_TZ), sleep_fn=lambda s: None,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed([flat_bar]),
        today=d,
    )
    assert exit_code == 1
    report_path = tmp_path / "reports" / f"{d.isoformat()}.md"
    assert report_path.exists()
    assert "NakedPositionAlarm" in report_path.read_text()


def test_paper_mode_doji_produces_no_trade(tmp_path):
    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)
    # OR window (5 bars, 09:30-09:34) with a tiny body relative to range ->
    # doji, skip. The doji/direction DECISION doesn't fire until the first
    # POST-OR bar (09:35 -- see src/live/engine.py::_process_or_bar), so a
    # 6th bar must be present for the engine to ever emit NoTradeToday; its
    # own OHLC is irrelevant to the doji check itself (that only reads the
    # OR window's own open/close/high/low from the first 5 bars).
    doji_bars = [
        _bar(d, 9, 30, o=100.0, h=100.5, l=99.5, c=100.05),
        _bar(d, 9, 31, o=100.05, h=100.4, l=99.6, c=100.02),
        _bar(d, 9, 32, o=100.02, h=100.3, l=99.7, c=100.03),
        _bar(d, 9, 33, o=100.03, h=100.2, l=99.8, c=100.01),
        _bar(d, 9, 34, o=100.01, h=100.1, l=99.9, c=100.0),
        _bar(d, 9, 35, o=100.0, h=100.05, l=99.95, c=100.0),
    ]
    trades = run_live_or_paper_session(
        mode="paper", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed(doji_bars),
    )
    assert trades == []
    events_text = (tmp_path / "events.jsonl").read_text()
    assert "NoTradeToday" in events_text


def test_cooperative_stop_before_first_bar_acknowledges_without_entry(tmp_path):
    d = date(2026, 7, 20)
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)
    bars = [_bar(d, 9, 30, o=100.0, h=101.0, l=99.0, c=100.5)]

    trades = run_live_or_paper_session(
        mode="paper", session_date=d, state_dir=tmp_path,
        client_factory=_client_factory(transport),
        feed_factory=lambda client, contract_id, session_date, journal, on_wait_tick=None: ScriptedBarFeed(bars),
        stop_requested=lambda: True,
    )

    assert trades == []
    assert "CooperativeStopAcknowledged" in (tmp_path / "events.jsonl").read_text()
