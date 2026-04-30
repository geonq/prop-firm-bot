"""Load replay-day inputs from simple exported trade files."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.strategies.replay import ReplayDay


def load_replay_days_csv(
    path: str | Path,
    *,
    date_column: str = "session_date",
    r_multiple_column: str = "r_multiple",
) -> list[ReplayDay]:
    """Load replay days from a CSV file.

    Expected format is one row per trade, with repeated `session_date` values
    for multiple trades in one day. A row with an empty `r_multiple` records an
    explicit no-trade day.
    """
    replay_path = Path(path)
    rows_by_date: dict[date, list[float]] = defaultdict(list)

    with replay_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file has no header")
        _require_columns(reader.fieldnames, date_column=date_column, r_multiple_column=r_multiple_column)

        for row_number, row in enumerate(reader, start=2):
            session_date = _parse_date(row[date_column], row_number=row_number, column=date_column)
            raw_r_multiple = (row.get(r_multiple_column) or "").strip()
            rows_by_date.setdefault(session_date, [])
            if raw_r_multiple:
                rows_by_date[session_date].append(_parse_float(raw_r_multiple, row_number=row_number, column=r_multiple_column))

    return [ReplayDay(session_date=session_date, r_multiples=tuple(rows_by_date[session_date])) for session_date in sorted(rows_by_date)]


def _require_columns(fieldnames: list[str], *, date_column: str, r_multiple_column: str) -> None:
    missing = [column for column in (date_column, r_multiple_column) if column not in fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def _parse_date(value: str, *, row_number: int, column: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        msg = f"invalid date in row {row_number}, column {column}: {value!r}"
        raise ValueError(msg) from exc


def _parse_float(value: str, *, row_number: int, column: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        msg = f"invalid float in row {row_number}, column {column}: {value!r}"
        raise ValueError(msg) from exc
