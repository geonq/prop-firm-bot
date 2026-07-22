from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = Path(state_dir) / "runtime.json"

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"supervisor_pid": None, "runner_pid": None, "heartbeat_at": None, "actual_mode": "stopped", "stop_ack_generation": 0}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {"supervisor_pid": None, "runner_pid": None, "heartbeat_at": None, "actual_mode": "unknown", "last_error": "corrupt runtime state"}

    def write(self, **updates: Any) -> dict[str, Any]:
        state = self.load()
        state.update(updates)
        state["heartbeat_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, self.path)
        return state

    def update(self, **updates: Any) -> dict[str, Any]:
        return self.write(**updates)
