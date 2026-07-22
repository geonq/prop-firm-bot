from __future__ import annotations

from pathlib import Path

from src.live.projectx import Account
from src.monitor.accounts import AccountEvent, AccountMonitor
from src.monitor.service import AccountPollingService, _event_text


def _account(account_id: int, name: str, *, can_trade: bool = True, visible: bool = True, balance: float = 50_000) -> Account:
    return Account(id=account_id, name=name, can_trade=can_trade, is_visible=visible, balance=balance)


def test_first_snapshot_records_inventory_without_claiming_accounts_are_new(tmp_path: Path) -> None:
    monitor = AccountMonitor(tmp_path)

    events = monitor.observe([_account(1, "Practice")])

    assert events == []
    assert monitor.snapshot()["accounts"]["1"]["name"] == "Practice"


def test_new_account_is_detected_once_across_restart(tmp_path: Path) -> None:
    AccountMonitor(tmp_path).observe([_account(1, "Practice")])

    events = AccountMonitor(tmp_path).observe([_account(1, "Practice"), _account(2, "New Combine")])
    repeated = AccountMonitor(tmp_path).observe([_account(1, "Practice"), _account(2, "New Combine")])

    assert [(event.kind, event.evidence) for event in events] == [("new_account", "confirmed")]
    assert repeated == []


def test_tradability_loss_is_confirmed_but_reason_is_not_invented(tmp_path: Path) -> None:
    monitor = AccountMonitor(tmp_path)
    monitor.observe([_account(7, "150K")])

    events = monitor.observe([_account(7, "150K", can_trade=False)])

    assert events[0].kind == "tradability_changed"
    assert events[0].evidence == "confirmed"
    assert events[0].details["old"] is True
    assert events[0].details["new"] is False
    assert "breach" not in events[0].message.lower()


def test_disappearing_account_reports_unknown_reason(tmp_path: Path) -> None:
    monitor = AccountMonitor(tmp_path)
    monitor.observe([_account(9, "XFA")])

    events = monitor.observe([])

    assert events[0].kind == "removed_or_hidden"
    assert events[0].evidence == "confirmed"
    assert "reason unknown" in events[0].message.lower()


def test_polling_service_uses_monitor_directory_as_snapshot_parent(tmp_path: Path) -> None:
    service = AccountPollingService(tmp_path)

    assert service.monitor.path == tmp_path / "monitor" / "accounts.json"


def test_event_text_uses_factual_account_event_fields() -> None:
    event = AccountEvent(
        transition_key="account:2:new",
        kind="new_account",
        account_id=2,
        account_name="New Combine",
        evidence="confirmed",
        message="New ProjectX account observed: New Combine (2).",
        details={},
        observed_at="2026-07-22T12:00:00+00:00",
    )

    text = _event_text(event)

    assert "New ProjectX account observed" in text
    assert "evidence: confirmed" in text
    assert "not a payout or rule-outcome claim" in text
