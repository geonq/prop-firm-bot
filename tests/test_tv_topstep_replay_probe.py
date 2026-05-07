from datetime import date, timedelta
import random
from pathlib import Path

from openpyxl import Workbook

from Analysis.scripts.tv_topstep_replay_probe import (
    compute_replay_stats,
    load_and_run_probe,
    load_catalog_adaptive_sizing,
    run_probe,
)
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing
from src.strategies.replay import ReplayDay


def test_compute_replay_stats_flags_profile4_shape() -> None:
    start = date(2026, 1, 5)
    days = []
    outcomes = [2.0] * 27 + [-1.0] * 33
    random.Random(7).shuffle(outcomes)
    for index in range(20):
        day_outcomes = outcomes[index * 3 : index * 3 + 3]
        days.append(ReplayDay.from_values(start + timedelta(days=index), *day_outcomes))

    stats = compute_replay_stats(days)

    assert 0.40 <= stats.win_rate <= 0.50
    assert stats.avg_win_loss_ratio == 2.0
    assert 2.0 <= stats.trades_per_replay_day <= 4.0
    assert stats.inside_profile4


def test_run_probe_uses_topstep_replay() -> None:
    replay_days = [
        ReplayDay.from_values(date(2026, 1, 5) + timedelta(days=i), 1.0)
        for i in range(30)
    ]

    result = run_probe(
        replay_days,
        sizing_fn=FixedSizing(eval_size=1_000, funded_size=800),
        payout_path=TopStepPayoutPath.CONSISTENCY,
        payout_cap=1,
        max_back2funded_reactivations=0,
    )

    assert result.topstep_result.terminal_reason == "payout_cap"
    assert result.topstep_result.net_ev > 0


def test_load_and_run_probe_uses_tv_loader(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "tv_export.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Exit Time", "R Multiple"])
    current = date(2026, 1, 5)
    for _ in range(30):
        worksheet.append([current.isoformat(), 1.0])
        current += timedelta(days=1)
    workbook.save(xlsx_path)
    workbook.close()

    replay_days, result = load_and_run_probe(
        xlsx_path,
        risk_amount=None,
        sizing_fn=FixedSizing(eval_size=1_000, funded_size=800),
        payout_cap=1,
    )

    assert len(replay_days) >= 30
    assert result.topstep_result.terminal_reason == "payout_cap"


def test_profile4_sizing_falls_back_without_generated_catalog(monkeypatch, tmp_path: Path) -> None:
    import Analysis.scripts.tv_topstep_replay_probe as probe

    monkeypatch.setattr(probe, "CATALOG_CSV", tmp_path / "missing.csv")

    sizing = load_catalog_adaptive_sizing()

    assert sizing.eval_base == 150.0
    assert sizing.funded_base == 400.0
    assert sizing.buffer_full_frac == 0.04
    assert sizing.buffer_floor == 0.25
    assert sizing.post_payout_shrink == 1.0
