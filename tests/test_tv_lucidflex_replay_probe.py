from datetime import date, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

from Analysis.scripts.tv_lucidflex_replay_probe import load_and_run_probe, parse_float_list, run_probe
from src.strategies.replay import ReplayDay


def test_run_probe_sorts_lucidflex_risk_rows_by_net_ev() -> None:
    replay_days = [ReplayDay.from_values(date(2026, 1, 2) + timedelta(days=i), 1.0) for i in range(30)]

    rows = run_probe(
        replay_days,
        eval_risks=(750.0, 100.0),
        funded_risks=(200.0,),
        max_eval_days=10,
        max_funded_days=30,
    )

    assert rows[0].net_ev >= rows[1].net_ev
    assert rows[0].terminal_reason == "max_payouts"
    assert rows[0].net_ev > 0


def test_load_and_run_probe_uses_tv_xlsx_loader(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "tv_export.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Exit Time", "Profit USD"])
    current = date(2026, 1, 5)
    for _ in range(30):
        worksheet.append([current.isoformat(), 100])
        current += timedelta(days=1)
    workbook.save(xlsx_path)
    workbook.close()

    replay_days, rows = load_and_run_probe(
        xlsx_path,
        risk_amount=100,
        eval_risks=(750.0,),
        funded_risks=(200.0,),
        max_eval_days=10,
        max_funded_days=30,
    )

    assert len(replay_days) >= 30
    assert rows[0].terminal_reason == "max_payouts"


def test_parse_float_list_rejects_non_positive_values() -> None:
    assert parse_float_list("100, 125.5") == (100.0, 125.5)

    with pytest.raises(Exception, match="positive"):
        parse_float_list("100,0")
