from __future__ import annotations

from pathlib import Path

from src.reporting.operational import build_operational_report


def test_operational_report_exposes_fail_closed_unknowns(tmp_path: Path) -> None:
    report = build_operational_report(state_dir=tmp_path, control_dir=tmp_path / "control")

    assert "Trading mode: stopped" in report
    assert "Activation gate: unconfigured" in report
    assert "Broker reconciliation: unavailable" in report
    assert "Today: 0 trades" in report
