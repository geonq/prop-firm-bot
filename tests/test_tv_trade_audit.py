from pathlib import Path

from openpyxl import Workbook

from src.data.tv_trade_audit import load_tv_trade_records_xlsx
from src.rules.lucidflex import LucidFlex50K


def test_load_tv_trade_records_pairs_german_entry_exit_rows(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "tv_trades.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Liste der Trades"
    worksheet.append(["Trade #", "Typ", "Datum und Uhrzeit", "G&V netto USD"])
    worksheet.append([1, "Long-Ausstieg", "2026-01-05 10:00:03", 100])
    worksheet.append([1, "Long-Einstieg", "2026-01-05 10:00:00", 100])
    worksheet.append([2, "Short-Ausstieg", "2026-01-05 10:10:30", -50])
    worksheet.append([2, "Short-Einstieg", "2026-01-05 10:10:00", -50])
    workbook.save(xlsx_path)
    workbook.close()

    records = load_tv_trade_records_xlsx(xlsx_path)

    assert len(records) == 2
    assert records[0].trade_number == 1
    assert records[0].hold_seconds == 3
    assert records[0].net_profit == 100
    assert records[1].hold_seconds == 30


def test_tv_trade_records_feed_lucid_microscalping_guard(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "tv_trades.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "List of trades"
    worksheet.append(["Trade #", "Type", "Date/Time", "Net Profit USD"])
    worksheet.append([1, "Exit", "2026-01-05 10:00:03", 100])
    worksheet.append([1, "Entry", "2026-01-05 10:00:00", 100])
    worksheet.append([2, "Exit", "2026-01-05 10:10:30", 25])
    worksheet.append([2, "Entry", "2026-01-05 10:10:00", 25])
    workbook.save(xlsx_path)
    workbook.close()

    records = load_tv_trade_records_xlsx(xlsx_path)
    rules = LucidFlex50K()

    assert rules.microscalping_flagged(
        [record.net_profit for record in records],
        [record.hold_seconds for record in records],
    )
