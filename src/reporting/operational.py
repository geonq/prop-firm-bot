from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from datetime import date
from pathlib import Path

from src.ops.control import ControlStore
from src.ops.runtime import RuntimeStore


def _trade_stats(path: Path) -> tuple[int, float, int, float]:
    if not path.is_file():
        return 0, 0.0, 0, 0.0
    today = date.today().isoformat()
    month = today[:7]
    today_count = month_count = 0
    today_pnl = month_pnl = 0.0
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            session = str(row.get("session_date") or "")
            pnl = float(row.get("net_pnl_usd") or row.get("pnl_usd") or 0.0)
            if session.startswith(month):
                month_count += 1
                month_pnl += pnl
            if session == today:
                today_count += 1
                today_pnl += pnl
    return today_count, today_pnl, month_count, month_pnl


def _recovery_task_state() -> str:
    if os.name != "nt":
        return "unavailable"
    try:
        proc = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", "ORBTradingSupervisorWatchdog", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 - report boundary
        return f"unavailable ({type(exc).__name__})"
    if proc.returncode != 0:
        return "not installed"
    try:
        row = next(csv.reader(proc.stdout.splitlines()))
        return row[2] if len(row) > 2 else "installed"
    except (StopIteration, csv.Error):
        return "installed (state unreadable)"


def build_operational_report(*, state_dir: Path, control_dir: Path) -> str:
    control = ControlStore(control_dir).load()
    runtime = RuntimeStore(control_dir).load()
    today_count, today_pnl, month_count, month_pnl = _trade_stats(Path(state_dir) / "trades.csv")
    accounts_path = Path(state_dir) / "monitor" / "accounts.json"
    account_count = 0
    last_discovery = "unavailable"
    if accounts_path.is_file():
        try:
            raw = json.loads(accounts_path.read_text(encoding="utf-8"))
            account_count = len(raw.get("accounts", {}))
            last_discovery = str(raw.get("observed_at") or "unavailable")
        except (OSError, json.JSONDecodeError):
            last_discovery = "corrupt snapshot (fail closed)"
    broker_reconciliation = runtime.get("broker_reconciled_at") or "unavailable"
    next_action = runtime.get("last_error") or (
        "configure ProjectX credentials and run paper acceptance" if control["activation_gate"] == "unconfigured" else "none"
    )
    return "\n".join(
        [
            "Trading operations dashboard",
            f"Trading mode: {control['requested_mode']}",
            f"Actual mode: {runtime.get('actual_mode', 'stopped')}",
            f"Activation gate: {control['activation_gate']}",
            f"Supervisor heartbeat: {runtime.get('heartbeat_at') or 'unavailable'}",
            f"Recovery task: {_recovery_task_state()}",
            f"Broker reconciliation: {broker_reconciliation}",
            f"Accounts discovered: {account_count}; last discovery: {last_discovery}",
            f"Today: {today_count} trades, net PnL ${today_pnl:.2f}",
            f"Month: {month_count} trades, net PnL ${month_pnl:.2f}",
            f"Next operator action: {next_action}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render trading operational dashboard")
    parser.add_argument("--state-dir", type=Path, default=Path("LiveState"))
    parser.add_argument("--control-dir", type=Path, default=Path("LiveState/control"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_operational_report(state_dir=args.state_dir, control_dir=args.control_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
