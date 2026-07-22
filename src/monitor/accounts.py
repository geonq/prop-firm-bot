from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.live.projectx import Account


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountEvent:
    transition_key: str
    kind: str
    account_id: int
    account_name: str
    evidence: str
    message: str
    details: dict[str, Any]
    observed_at: str


class AccountMonitor:
    """Persist ProjectX account observations and emit only factual transitions."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "accounts.json"

    def snapshot(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "initialized": False, "observed_at": None, "accounts": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw.get("accounts"), dict):
                raise ValueError("accounts is not an object")
            return raw
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"schema_version": 1, "initialized": False, "observed_at": None, "accounts": {}, "stale_reason": "corrupt snapshot"}

    def _write(self, payload: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, self.path)

    def observe(self, accounts: Iterable[Account]) -> list[AccountEvent]:
        previous = self.snapshot()
        observed_at = _now()
        current_accounts = {
            str(account.id): {
                "id": account.id,
                "name": account.name,
                "can_trade": account.can_trade,
                "is_visible": account.is_visible,
                "balance": account.balance,
            }
            for account in accounts
        }
        events: list[AccountEvent] = []
        old_accounts = previous.get("accounts", {})
        if previous.get("initialized"):
            for account_id in sorted(current_accounts.keys() - old_accounts.keys(), key=int):
                account = current_accounts[account_id]
                events.append(AccountEvent(
                    transition_key=f"account:{account_id}:new",
                    kind="new_account", account_id=account["id"], account_name=account["name"],
                    evidence="confirmed", message=f"New ProjectX account observed: {account['name']} ({account_id}).",
                    details={"account": account}, observed_at=observed_at,
                ))
            for account_id in sorted(old_accounts.keys() - current_accounts.keys(), key=int):
                account = old_accounts[account_id]
                events.append(AccountEvent(
                    transition_key=f"account:{account_id}:removed:{previous.get('observed_at')}",
                    kind="removed_or_hidden", account_id=int(account_id), account_name=account.get("name", ""),
                    evidence="confirmed", message=f"Account {account.get('name', account_id)} is no longer returned; reason unknown.",
                    details={"previous_account": account}, observed_at=observed_at,
                ))
            for account_id in sorted(current_accounts.keys() & old_accounts.keys(), key=int):
                old = old_accounts[account_id]
                new = current_accounts[account_id]
                if bool(old.get("can_trade")) != bool(new.get("can_trade")):
                    events.append(AccountEvent(
                        transition_key=f"account:{account_id}:can_trade:{int(bool(new['can_trade']))}:{observed_at}",
                        kind="tradability_changed", account_id=int(account_id), account_name=new["name"],
                        evidence="confirmed",
                        message=f"Account {new['name']} tradability changed to canTrade={new['can_trade']}; ProjectX does not expose the reason.",
                        details={"old": bool(old.get("can_trade")), "new": bool(new["can_trade"])}, observed_at=observed_at,
                    ))
        payload = {"schema_version": 1, "initialized": True, "observed_at": observed_at, "accounts": current_accounts}
        self._write(payload)
        return events

    @staticmethod
    def event_payload(event: AccountEvent) -> dict[str, Any]:
        return asdict(event)
