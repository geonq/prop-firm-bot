"""Tests for src/live/live_runner.py::run_preflight -- specifically the bar
timestamp convention check (reviewer Fix 5, 2026-07-19, MEDIUM). Driven
entirely through a fake transport -- no real network, no real credentials.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.live.live_runner import run_preflight
from src.live.projectx import ProjectXClient, TransportResponse


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


def _bar_dict(t: str, *, o=100.0, h=100.5, l=99.5, c=100.2, v=10) -> dict:
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_bar_timestamp_convention_check_prints_bars_and_wall_clock(monkeypatch):
    monkeypatch.setenv("PROJECTX_USERNAME", "u")
    monkeypatch.setenv("PROJECTX_API_KEY", "k")
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    # "bars fetch (smoke)" check consumes one retrieveBars response first.
    transport.queue("/api/History/retrieveBars", 200, _ok({"bars": [_bar_dict("2026-07-20T13:35:00Z")]}))
    # The dedicated bar-timestamp-convention check consumes a second one,
    # with 3 bars (reviewer Fix 5 spec: "last ~3 one-minute bars").
    transport.queue(
        "/api/History/retrieveBars",
        200,
        _ok(
            {
                "bars": [
                    _bar_dict("2026-07-20T13:33:00Z", c=100.1),
                    _bar_dict("2026-07-20T13:34:00Z", c=100.2),
                    _bar_dict("2026-07-20T13:35:00Z", c=100.3),
                ]
            }
        ),
    )

    result = run_preflight(client_factory=_client_factory(transport))

    names = [name for name, _passed, _detail in result.checks]
    assert "bar timestamp convention (manual confirmation required)" in names

    detail = next(detail for name, _passed, detail in result.checks if name == "bar timestamp convention (manual confirmation required)")
    # All 3 fetched bar timestamps must appear in the printed detail.
    assert "13:33:00" in detail
    assert "13:34:00" in detail
    assert "13:35:00" in detail
    # The current wall clock must be printed alongside them for comparison.
    assert "current wall clock (ET)" in detail
    # The explicit go/no-go instruction must be present.
    assert "STOP, do NOT go live" in detail
    assert "open" in detail.lower()


def test_bar_timestamp_convention_check_reports_no_bars_outside_rth(monkeypatch):
    monkeypatch.setenv("PROJECTX_USERNAME", "u")
    monkeypatch.setenv("PROJECTX_API_KEY", "k")
    transport = ScriptedTransport()
    _setup_auth_account_contract(transport)

    transport.queue("/api/History/retrieveBars", 200, _ok({"bars": []}))  # smoke check: empty
    transport.queue("/api/History/retrieveBars", 200, _ok({"bars": []}))  # convention check: empty

    result = run_preflight(client_factory=_client_factory(transport))

    detail = next(detail for name, _passed, detail in result.checks if name == "bar timestamp convention (manual confirmation required)")
    assert "no bars returned" in detail
    # An empty-bars result is a benign "can't check right now," not a
    # preflight failure -- the check function returns a string, not a raise,
    # so it is still recorded as passed=True (informational).
    passed = next(passed for name, passed, _detail in result.checks if name == "bar timestamp convention (manual confirmation required)")
    assert passed is True
