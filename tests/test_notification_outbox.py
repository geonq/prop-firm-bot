from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

import pytest

from src.monitor.outbox import Outbox
from src.monitor.service import TelegramNotifier


def test_outbox_deduplicates_transition_and_retries_delivery(tmp_path: Path) -> None:
    outbox = Outbox(tmp_path / "monitor.sqlite3")

    first = outbox.enqueue("account:2:new", {"text": "New account"})
    duplicate = outbox.enqueue("account:2:new", {"text": "New account"})

    assert first == duplicate
    assert len(outbox.pending()) == 1

    outbox.record_failure(first, "telegram unavailable")
    assert outbox.pending()[0]["attempts"] == 1

    outbox.mark_delivered(first, telegram_message_id="42")
    assert outbox.pending() == []
    assert outbox.get(first)["telegram_message_id"] == "42"


def test_telegram_transport_error_does_not_expose_bot_token(monkeypatch) -> None:
    token = "sensitive-bot-token"
    notifier = TelegramNotifier(token=token, chat_id="1")

    def fail(_request, timeout):
        raise URLError(f"https://api.telegram.org/bot{token}/sendMessage failed")

    monkeypatch.setattr("urllib.request.urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        notifier.send("test")

    assert token not in str(exc_info.value)
