from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from src.ops.control import ControlStore
from src.ops.runtime import RuntimeStore


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...


def _spawn(command: list[str]) -> ProcessLike:
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(command, creationflags=flags)


class Supervisor:
    def __init__(
        self,
        *,
        state_dir: Path,
        trading_state_dir: Path,
        launcher: Callable[[list[str]], ProcessLike] = _spawn,
        account_poll: Callable[[], None] = lambda: None,
    ) -> None:
        self.state_dir = state_dir
        self.trading_state_dir = trading_state_dir
        self.control = ControlStore(state_dir)
        self.runtime = RuntimeStore(state_dir)
        self.launcher = launcher
        self.account_poll = account_poll
        self.process: ProcessLike | None = None
        self._last_launch_date: date | None = None
        self._last_account_poll = 0.0

    def _command(self, mode: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "src.live.runner",
            "--mode",
            mode,
            "--auto",
            "--state-dir",
            str(self.trading_state_dir),
            "--control-dir",
            str(self.state_dir),
        ]

    def tick(self) -> bool:
        now = time.monotonic()
        if now - self._last_account_poll >= 60:
            try:
                self.account_poll()
            except Exception as exc:  # noqa: BLE001 - monitoring cannot crash control plane
                self.runtime.update(last_error=f"account monitor: {type(exc).__name__}: {exc}")
            self._last_account_poll = now

        desired = self.control.load()["requested_mode"]
        code = self.process.poll() if self.process is not None else None
        if self.process is not None and code is not None:
            prior_pid = self.process.pid
            self.process = None
            self.runtime.update(
                runner_pid=None,
                runner_exit_code=code,
                runner_exited_at=datetime.now(timezone.utc).isoformat(),
                last_error=None if code == 0 else f"runner {prior_pid} exited with code {code}",
            )

        if desired == "stopped":
            if self.process is not None:
                self.runtime.update(actual_mode="stopping", broker_flat_confirmed=False)
                return True
            last_code = self.runtime.load().get("runner_exit_code")
            flat = last_code in (None, 0)
            self.runtime.update(
                actual_mode="stopped",
                broker_flat_confirmed=flat,
                heartbeat_at=datetime.now(timezone.utc).isoformat(),
            )
            return False

        if self.process is None and self._last_launch_date != date.today():
            self.process = self.launcher(self._command(desired))
            self._last_launch_date = date.today()
            self.runtime.update(
                actual_mode=desired,
                runner_pid=self.process.pid,
                runner_exit_code=None,
                broker_flat_confirmed=False,
                last_error=None,
            )

        self.runtime.update(
            actual_mode=desired if self.process is not None else f"{desired}_completed_today",
            heartbeat_at=datetime.now(timezone.utc).isoformat(),
        )
        return True

    def run(self, interval_seconds: float = 2.0) -> int:
        self.runtime.update(supervisor_pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat())
        while self.tick():
            time.sleep(interval_seconds)
        self.runtime.update(supervisor_pid=None, heartbeat_at=datetime.now(timezone.utc).isoformat())
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading lifecycle supervisor")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--trading-state-dir", type=Path, default=Path("LiveState"))
    args = parser.parse_args(argv)
    from src.monitor.service import AccountPollingService

    account_monitor = AccountPollingService(args.trading_state_dir)
    return Supervisor(
        state_dir=args.state_dir,
        trading_state_dir=args.trading_state_dir,
        account_poll=account_monitor.poll,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
