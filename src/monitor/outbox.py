from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Outbox:
    """Durable transition-deduplicating notification outbox."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS notification_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transition_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    delivered_at TEXT,
                    telegram_message_id TEXT
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, transition_key: str, payload: dict[str, Any]) -> int:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notification_outbox (transition_key, payload_json, created_at) VALUES (?, ?, ?)",
                (transition_key, json.dumps(payload, sort_keys=True), _now()),
            )
            row = conn.execute("SELECT id FROM notification_outbox WHERE transition_key = ?", (transition_key,)).fetchone()
            assert row is not None
            return int(row["id"])

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_outbox WHERE delivered_at IS NULL ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, item_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM notification_outbox WHERE id = ?", (item_id,)).fetchone()
        return self._row(row) if row else None

    def record_failure(self, item_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE notification_outbox SET attempts = attempts + 1, last_error = ? WHERE id = ? AND delivered_at IS NULL",
                (error[:1000], item_id),
            )

    def mark_delivered(self, item_id: int, *, telegram_message_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE notification_outbox SET delivered_at = ?, telegram_message_id = ?, last_error = NULL WHERE id = ?",
                (_now(), telegram_message_id, item_id),
            )
