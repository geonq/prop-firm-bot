from __future__ import annotations

import json
from pathlib import Path

from src.ops.control import ControlStore


def test_missing_control_state_fails_closed_to_stopped(tmp_path: Path) -> None:
    state = ControlStore(tmp_path).load()

    assert state["requested_mode"] == "stopped"
    assert state["generation"] == 0
    assert state["activation_gate"] == "unconfigured"


def test_corrupt_control_state_fails_closed_and_preserves_evidence(tmp_path: Path) -> None:
    path = tmp_path / "control.json"
    path.write_text("{not-json", encoding="utf-8")

    state = ControlStore(tmp_path).load()

    assert state["requested_mode"] == "stopped"
    assert state["last_error"].startswith("corrupt control state:")
    assert list(tmp_path.glob("control.corrupt.*.json"))


def test_request_mode_is_atomic_and_increments_generation(tmp_path: Path) -> None:
    store = ControlStore(tmp_path)

    first = store.request("paper", actor="telegram:1")
    second = store.request("stopped", actor="telegram:1")

    assert first["generation"] == 1
    assert second["generation"] == 2
    assert second["requested_mode"] == "stopped"
    assert second["requested_by"] == "telegram:1"
    assert not (tmp_path / "control.json.tmp").exists()
    assert json.loads((tmp_path / "control.json").read_text(encoding="utf-8"))["generation"] == 2


def test_live_request_stays_locked_without_activation_artifact(tmp_path: Path) -> None:
    store = ControlStore(tmp_path)

    state = store.request("live", actor="test")

    assert state["requested_mode"] == "stopped"
    assert state["activation_gate"] == "live_locked"
    assert "activation" in state["last_error"]


def test_live_request_rejects_malformed_activation_artifact(tmp_path: Path) -> None:
    store = ControlStore(tmp_path)
    store.activation_path.parent.mkdir(parents=True, exist_ok=True)
    store.activation_path.write_text("{}", encoding="utf-8")

    state = store.request("live", actor="test")

    assert state["requested_mode"] == "stopped"
    assert state["activation_gate"] == "live_locked"
