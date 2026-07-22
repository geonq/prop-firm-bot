from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from src.ops.control import ControlStore
from src.ops.runtime import RuntimeStore


def _process_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _launch(command: list[str]) -> int:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    kwargs: dict[str, Any] = {"cwd": str(Path(__file__).resolve().parents[2]), "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        kwargs["close_fds"] = True
    proc = subprocess.Popen(command, **kwargs)
    return int(proc.pid)


class TradingService:
    """Command-facing desired-state service. It never places orders itself."""

    def __init__(
        self,
        state_dir: Path,
        *,
        preflight: Callable[[], Any] | None = None,
        launcher: Callable[[list[str]], int] = _launch,
        process_alive: Callable[[int | None], bool] = _process_alive,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.control = ControlStore(self.state_dir)
        self.runtime = RuntimeStore(self.state_dir)
        if preflight is None:
            from src.live.live_runner import run_preflight

            preflight = run_preflight
        self.preflight = preflight
        self.launcher = launcher
        self.process_alive = process_alive

    def status(self) -> dict[str, Any]:
        control = self.control.load()
        runtime = self.runtime.load()
        supervisor_alive = self.process_alive(runtime.get("supervisor_pid"))
        runner_alive = self.process_alive(runtime.get("runner_pid"))
        return {
            "ok": True,
            "state": control["requested_mode"],
            "activation_gate": control["activation_gate"],
            "generation": control["generation"],
            "supervisor_alive": supervisor_alive,
            "runner_alive": runner_alive,
            "supervisor_pid": runtime.get("supervisor_pid"),
            "runner_pid": runtime.get("runner_pid"),
            "actual_mode": runtime.get("actual_mode", "stopped"),
            "heartbeat_at": runtime.get("heartbeat_at"),
            "last_error": runtime.get("last_error") or control.get("last_error"),
            "stop_ack_generation": runtime.get("stop_ack_generation", 0),
        }

    def start(self, *, mode: str, actor: str) -> dict[str, Any]:
        existing = self.status()
        if existing["supervisor_alive"]:
            if existing["state"] == mode:
                return {**existing, "already_running": True, "detail": "trading supervisor already owns this requested mode"}
            return {
                **existing,
                "ok": False,
                "detail": "stop the active supervisor and confirm it stopped before switching trading modes",
            }

        preflight = self.preflight()
        if not bool(preflight.ok):
            failures = [f"{name}: {detail}" for name, passed, detail in preflight.checks if not passed]
            stopped = self.control.request("stopped", actor=actor)
            return {"ok": False, "state": stopped["requested_mode"], "detail": "; ".join(failures) or "preflight failed"}

        requested = self.control.request(mode, actor=actor)
        if requested["requested_mode"] != mode:
            return {"ok": False, "state": requested["requested_mode"], "detail": requested.get("last_error") or "activation gate refused request"}

        command = [sys.executable, "-m", "src.ops.supervisor", "--state-dir", str(self.state_dir)]
        pid = self.launcher(command)
        self.runtime.write(supervisor_pid=pid, actual_mode="starting", last_error=None)
        return {"ok": True, "state": mode, "pid": pid, "already_running": False, "detail": "supervisor launched after successful preflight"}

    def stop(self, *, actor: str) -> dict[str, Any]:
        before = self.status()
        state = self.control.request("stopped", actor=actor)
        return {
            "ok": True,
            "state": state["requested_mode"],
            "generation": state["generation"],
            "already_stopped": not before["supervisor_alive"] and not before["runner_alive"],
            "detail": "cooperative stop requested; success means intent recorded, not broker-flat confirmation",
        }
