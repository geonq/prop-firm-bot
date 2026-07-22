from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_MODES = {"stopped", "paper", "live"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ControlStore:
    """Atomic fail-closed desired-state store.

    This file expresses operator intent only. Broker reconciliation remains the
    authority for whether an account is actually flat.
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "control.json"
        self.activation_path = self.state_dir / "live_activation.json"

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "requested_mode": "stopped",
            "generation": 0,
            "activation_gate": "unconfigured",
            "requested_at": None,
            "requested_by": None,
            "last_error": None,
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.default()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("requested_mode") not in VALID_MODES:
                raise ValueError("invalid schema or requested_mode")
            state = self.default()
            state.update(raw)
            state["generation"] = max(0, int(state["generation"]))
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            evidence = self.state_dir / f"control.corrupt.{stamp}.json"
            try:
                os.replace(self.path, evidence)
            except OSError:
                pass
            state = self.default()
            state["last_error"] = f"corrupt control state: {type(exc).__name__}: {exc}"
            return state

    def _write(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_dir / "control.json.tmp"
        encoded = json.dumps(state, indent=2, sort_keys=True) + "\n"
        with temp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, self.path)

    def _live_activation_valid(self) -> bool:
        try:
            raw = json.loads(self.activation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            isinstance(raw, dict)
            and raw.get("approved") is True
            and raw.get("paper_acceptance") is True
            and isinstance(raw.get("approved_by"), str)
            and bool(raw["approved_by"].strip())
        )

    def request(self, mode: str, *, actor: str) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError(f"unsupported requested mode: {mode}")
        current = self.load()
        next_state = dict(current)
        next_state["generation"] = int(current["generation"]) + 1
        next_state["requested_at"] = _utcnow()
        next_state["requested_by"] = actor
        next_state["last_error"] = None

        if mode == "live" and not self._live_activation_valid():
            next_state["requested_mode"] = "stopped"
            next_state["activation_gate"] = "live_locked"
            next_state["last_error"] = "live activation artifact is missing or invalid; refusing live request"
        else:
            next_state["requested_mode"] = mode
            if mode == "paper":
                next_state["activation_gate"] = "paper_ready"
            elif mode == "live":
                next_state["activation_gate"] = "live_armed"
        self._write(next_state)
        return next_state
