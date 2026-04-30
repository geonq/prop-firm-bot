from pathlib import Path

import pytest

from src.data.replay_loader import load_replay_days_csv


def test_load_replay_days_csv_groups_trades_and_empty_days(tmp_path: Path) -> None:
    csv_path = tmp_path / "replay.csv"
    csv_path.write_text(
        "session_date,r_multiple\n"
        "2026-01-03,1.25\n"
        "2026-01-02,\n"
        "2026-01-03,-1\n",
        encoding="utf-8",
    )

    days = load_replay_days_csv(csv_path)

    assert [day.session_date.isoformat() for day in days] == ["2026-01-02", "2026-01-03"]
    assert days[0].r_multiples == ()
    assert days[1].r_multiples == (1.25, -1.0)


def test_load_replay_days_csv_requires_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("session_date,pnl\n2026-01-02,1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="r_multiple"):
        load_replay_days_csv(csv_path)


def test_load_replay_days_csv_reports_bad_values(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("session_date,r_multiple\n2026-01-02,nope\n", encoding="utf-8")

    with pytest.raises(ValueError, match="row 2"):
        load_replay_days_csv(csv_path)
