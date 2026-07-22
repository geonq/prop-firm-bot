from __future__ import annotations

from pathlib import Path

from src.ops.service import TradingService


class _Preflight:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.checks = [("auth", ok, "ok" if ok else "missing credentials")]


def test_start_fails_closed_when_preflight_fails(tmp_path: Path) -> None:
    launched: list[list[str]] = []
    service = TradingService(
        tmp_path,
        preflight=lambda: _Preflight(False),
        launcher=lambda command: launched.append(command) or 123,
    )

    receipt = service.start(mode="paper", actor="telegram:1")

    assert receipt["ok"] is False
    assert receipt["state"] == "stopped"
    assert "missing credentials" in receipt["detail"]
    assert launched == []


def test_start_launches_supervisor_after_preflight_and_is_idempotent(tmp_path: Path) -> None:
    launched: list[list[str]] = []
    service = TradingService(
        tmp_path,
        preflight=lambda: _Preflight(True),
        launcher=lambda command: launched.append(command) or 321,
        process_alive=lambda pid: pid == 321,
    )

    first = service.start(mode="paper", actor="telegram:1")
    second = service.start(mode="paper", actor="telegram:1")

    assert first["ok"] is True
    assert first["pid"] == 321
    assert second["already_running"] is True
    assert len(launched) == 1


def test_start_rejects_mode_switch_while_supervisor_is_running(tmp_path: Path) -> None:
    launched: list[list[str]] = []
    service = TradingService(
        tmp_path,
        preflight=lambda: _Preflight(True),
        launcher=lambda command: launched.append(command) or 321,
        process_alive=lambda pid: pid == 321,
    )
    service.control.activation_path.parent.mkdir(parents=True, exist_ok=True)
    service.control.activation_path.write_text(
        '{"approved": true, "paper_acceptance": true, "approved_by": "geonq"}',
        encoding="utf-8",
    )

    assert service.start(mode="paper", actor="telegram:1")["ok"] is True
    switched = service.start(mode="live", actor="telegram:1")

    assert switched["ok"] is False
    assert switched["state"] == "paper"
    assert "stop" in switched["detail"].lower()
    assert len(launched) == 1


def test_stop_is_requested_even_if_supervisor_is_absent(tmp_path: Path) -> None:
    service = TradingService(tmp_path, preflight=lambda: _Preflight(True), launcher=lambda command: 1)

    receipt = service.stop(actor="telegram:1")

    assert receipt["ok"] is True
    assert receipt["state"] == "stopped"
    assert receipt["already_stopped"] is True
