from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from src.ops.service import TradingService

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROL_DIR = ROOT / "LiveState" / "control"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed trading supervisor control")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_CONTROL_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--mode", choices=("paper", "live"), default=os.environ.get("TRADING_MODE", "paper"))
    start.add_argument("--actor", default="cli")
    stop = sub.add_parser("stop")
    stop.add_argument("--actor", default="cli")
    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None, *, service: Any | None = None) -> int:
    args = _parser().parse_args(argv)
    service = service or TradingService(args.state_dir)
    if args.command == "start":
        receipt = service.start(mode=args.mode, actor=args.actor)
    elif args.command == "stop":
        receipt = service.stop(actor=args.actor)
    else:
        receipt = service.status()
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0 if receipt.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
