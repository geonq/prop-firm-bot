from __future__ import annotations

import json
from pathlib import Path

from src.ops.cli import main


class _Service:
    def start(self, *, mode: str, actor: str):
        return {"ok": True, "state": mode, "actor": actor}

    def stop(self, *, actor: str):
        return {"ok": True, "state": "stopped", "actor": actor}

    def status(self):
        return {"ok": True, "state": "stopped"}


def test_cli_emits_one_json_receipt(capsys, tmp_path: Path) -> None:
    code = main(["--state-dir", str(tmp_path), "start", "--mode", "paper", "--actor", "telegram:1"], service=_Service())

    receipt = json.loads(capsys.readouterr().out)
    assert code == 0
    assert receipt == {"actor": "telegram:1", "ok": True, "state": "paper"}
