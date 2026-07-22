from __future__ import annotations

from pathlib import Path

from src.ops.control import ControlStore
from src.ops.supervisor import Supervisor


class _Process:
    pid = 4321

    def __init__(self) -> None:
        self.code = None

    def poll(self):
        return self.code


def test_supervisor_launches_one_runner_and_acknowledges_stop(tmp_path: Path) -> None:
    store = ControlStore(tmp_path)
    store.request("paper", actor="test")
    launched: list[list[str]] = []
    process = _Process()

    supervisor = Supervisor(
        state_dir=tmp_path,
        trading_state_dir=tmp_path / "trading",
        launcher=lambda command: launched.append(command) or process,
        account_poll=lambda: None,
    )

    assert supervisor.tick() is True
    assert len(launched) == 1
    assert "--control-dir" in launched[0]
    assert supervisor.tick() is True
    assert len(launched) == 1

    store.request("stopped", actor="test")
    process.code = 0
    assert supervisor.tick() is False
    runtime = supervisor.runtime.load()
    assert runtime["actual_mode"] == "stopped"
    assert runtime["broker_flat_confirmed"] is True
