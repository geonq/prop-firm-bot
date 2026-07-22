from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.live.env import load_projectx_credentials
from src.live.projectx import ProjectXClient, RequestsTransport
from src.monitor.accounts import AccountEvent, AccountMonitor
from src.monitor.outbox import Outbox


def _event_text(event: AccountEvent) -> str:
    return (
        f"{event.message}\n"
        f"account: {event.account_name or 'unknown'} ({event.account_id})\n"
        f"evidence: {event.evidence}\n"
        f"observed: {event.observed_at}\n"
        "This is a broker-observed transition; it is not a payout or rule-outcome claim."
    )


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.environ.get("TELEGRAM_CONTROLLER_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CONTROLLER_CHAT_ID") or os.environ.get("TELEGRAM_CONTROLLER_USER_ID")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> str:
        if not self.configured:
            raise RuntimeError("controller Telegram token/chat ID unavailable; notification retained in outbox")
        assert self.token and self.chat_id
        data = urllib.parse.urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/sendMessage", data=data, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - never persist a token-bearing request URL
            raise RuntimeError(f"Telegram notification request failed ({type(exc).__name__})") from None
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram rejected notification: {payload.get('description', 'unknown error')}")
        return str(payload["result"]["message_id"])


class AccountPollingService:
    def __init__(self, state_dir: Path, notifier: TelegramNotifier | None = None) -> None:
        monitor_dir = Path(state_dir) / "monitor"
        self.monitor = AccountMonitor(monitor_dir)
        self.outbox = Outbox(monitor_dir / "notifications.sqlite")
        self.notifier = notifier or TelegramNotifier()

    def poll(self) -> None:
        credentials = load_projectx_credentials()
        client = ProjectXClient(
            RequestsTransport(), username=credentials.username, api_key=credentials.api_key,
        )
        client.login()
        events = self.monitor.observe(client.list_accounts())
        for event in events:
            self.outbox.enqueue(event.transition_key, {"text": _event_text(event), "event": event.__dict__})
        for item in self.outbox.pending(limit=20):
            try:
                message_id = self.notifier.send(str(item["payload"]["text"]))
            except Exception as exc:  # noqa: BLE001 - durable retry boundary
                self.outbox.record_failure(item["id"], f"{type(exc).__name__}: {exc}")
                continue
            self.outbox.mark_delivered(item["id"], telegram_message_id=message_id)
