"""Tests for src/live/report.py -- daily markdown report generator."""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from src.live.report import build_daily_report_markdown, write_daily_report
from src.live.runner import TRADE_CSV_FIELDS


def _write_trades_csv(path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _trade_row(
    *,
    session_date="2026-07-18",
    direction="long",
    entry_price=20000.0,
    exit_price=20050.0,
    exit_reason="target",
    contracts=3,
    risk_points=12.5,
    r_multiple=4.0,
    pnl_usd=300.0,
    net_pnl_usd=295.6,
    net_r=3.94,
) -> dict:
    return {
        "session_date": session_date,
        "direction": direction,
        "entry_ts": f"{session_date} 09:35:00-04:00",
        "entry_price": entry_price,
        "exit_ts": f"{session_date} 10:00:00-04:00",
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "contracts": contracts,
        "risk_points": risk_points,
        "r_multiple": r_multiple,
        "pnl_usd": pnl_usd,
        "net_pnl_usd": net_pnl_usd,
        "net_r": net_r,
        "params_hash": "8afbe6259cab2dd2",
    }


def test_report_with_no_data_does_not_crash(tmp_path):
    md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=tmp_path)
    assert "2026-07-18" in md
    assert "No trade recorded today" in md or "No trades recorded" in md


def test_report_shows_todays_trade():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _write_trades_csv(state_dir / "trades.csv", [_trade_row()])
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)
        assert "long 3x" in md
        assert "target" in md
        assert "gross R=4.000" in md


def test_report_labels_trailing_r_as_ops_metric_not_gate():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _write_trades_csv(state_dir / "trades.csv", [_trade_row()])
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)
        assert "ops health metric" in md.lower() or "ops health signal" in md.lower()
        assert "not a trading gate" in md.lower()
        assert "trailing-40 mean gross R" in md


def test_report_cumulative_stats_aggregate_multiple_trades():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        rows = [
            _trade_row(session_date="2026-07-15", r_multiple=1.0, pnl_usd=100.0, net_pnl_usd=95.0, net_r=0.95),
            _trade_row(session_date="2026-07-16", r_multiple=-1.0, pnl_usd=-100.0, net_pnl_usd=-105.0, net_r=-1.05),
            _trade_row(session_date="2026-07-17", r_multiple=4.0, pnl_usd=400.0, net_pnl_usd=395.0, net_r=3.95),
        ]
        _write_trades_csv(state_dir / "trades.csv", rows)
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)
        assert "n=3" in md
        assert "win_rate=0.6667" in md


def test_report_shows_slippage_from_events():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _write_trades_csv(state_dir / "trades.csv", [_trade_row()])
        events = [
            {"event": "LiveOrderFilled", "role": "entry", "order_id": 1, "filled_price": 20001.5, "modeled_entry_price": 20000.0, "slippage_vs_model": 1.5, "filled_size": 3},
            {"event": "TradeOpened", "session_date": "2026-07-18"},
        ]
        with (state_dir / "events.jsonl").open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)
        assert "Realized slippage vs 1-tick model" in md
        assert "n=1" in md
        assert "+1.5000" in md or "1.5" in md


def test_report_handles_malformed_jsonl_line_gracefully():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        (state_dir / "events.jsonl").write_text("not valid json\n" + json.dumps({"event": "NoTradeToday", "session_date": "2026-07-18", "reason": "doji"}) + "\n")
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)  # must not raise
        assert "doji" in md


def test_write_daily_report_creates_file_under_reports_dir(tmp_path):
    _write_trades_csv(tmp_path / "trades.csv", [_trade_row()])
    path = write_daily_report(session_date=date(2026, 7, 18), state_dir=tmp_path)
    assert path == tmp_path / "reports" / "2026-07-18.md"
    assert path.exists()
    assert "2026-07-18" in path.read_text()


def test_report_shows_no_trade_reason_when_doji():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        events = [{"event": "NoTradeToday", "session_date": "2026-07-18", "reason": "doji"}]
        with (state_dir / "events.jsonl").open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        md = build_daily_report_markdown(session_date=date(2026, 7, 18), state_dir=state_dir)
        assert "doji" in md
