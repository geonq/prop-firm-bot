from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

import src.pipeline.strategy_registry as registry
from src.data.tv_trade_audit import TvTradeRecord
from src.pipeline.strategy_registry import (
    StrategyStats,
    compute_strategy_stats,
    screen_strategy,
)
from src.strategies.replay import ReplayDay


def _record(trade_number: int, profit: float, day: int = 5) -> TvTradeRecord:
    return TvTradeRecord(
        trade_number=trade_number,
        entry_time=datetime(2026, 1, day, 10, 0),
        exit_time=datetime(2026, 1, day, 10, 5),
        net_profit=profit,
    )


def test_compute_strategy_stats_uses_tv_net_pnl_without_default_cost_adjustment() -> None:
    records = [_record(1, 100.0), _record(2, -50.0)]
    replay_days = [ReplayDay.from_values(records[0].exit_time.date(), 0.5, -0.25)]

    stats = compute_strategy_stats(records, replay_days)
    adjusted = compute_strategy_stats(records, replay_days, cost_per_trade=4.0)

    assert stats.gross_pnl == 50.0
    assert stats.net_pnl == 50.0
    assert adjusted.net_pnl == 42.0


def test_screen_strategy_marks_bad_full_sample_as_fail_not_oos_pending() -> None:
    stats = StrategyStats(
        n_trades=250,
        n_replay_days=100,
        n_trading_days=100,
        date_start=datetime(2026, 1, 1).date(),
        date_end=datetime(2026, 5, 1).date(),
        gross_pnl=-2500.0,
        net_pnl=-2500.0,
        win_rate=0.3,
        profit_factor=0.8,
        avg_win=100.0,
        avg_loss=-100.0,
        expectancy=-10.0,
        sharpe_daily=-1.0,
        sortino_daily=-1.0,
        max_drawdown_usd=3000.0,
        max_drawdown_pct=0.06,
        max_single_day_pnl=200.0,
        max_single_day_share_of_profit=float("nan"),
    )

    result = screen_strategy(stats, "full_sample")

    assert result.status == "FAIL"
    assert any("no edge" in reason for reason in result.reasons)


def test_screen_strategy_marks_good_full_sample_as_oos_pending() -> None:
    stats = StrategyStats(
        n_trades=250,
        n_replay_days=100,
        n_trading_days=100,
        date_start=datetime(2026, 1, 1).date(),
        date_end=datetime(2026, 5, 1).date(),
        gross_pnl=10_000.0,
        net_pnl=10_000.0,
        win_rate=0.5,
        profit_factor=1.5,
        avg_win=200.0,
        avg_loss=-100.0,
        expectancy=40.0,
        sharpe_daily=1.0,
        sortino_daily=1.0,
        max_drawdown_usd=2000.0,
        max_drawdown_pct=0.04,
        max_single_day_pnl=500.0,
        max_single_day_share_of_profit=0.05,
    )

    result = screen_strategy(stats, "full_sample")

    assert result.status == "OOS_PENDING"
    assert result.reasons == ("no held-out OOS export — re-export per protocol",)


def test_build_registry_skip_mc_writes_indexes(tmp_path: Path, monkeypatch) -> None:
    tv_dir = tmp_path / "TVExports"
    strategy_dir = tmp_path / "strategies"
    mc_dir = tmp_path / "mc"
    tv_dir.mkdir()
    monkeypatch.setattr(registry, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(registry, "STRATEGIES_DIR", strategy_dir)
    monkeypatch.setattr(registry, "MC_RUNS_DIR", mc_dir)

    xlsx_path = tv_dir / "Strategy_IS_sample.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Liste der Trades"
    worksheet.append(["Trade #", "Typ", "Datum und Uhrzeit", "G&V netto USD"])
    worksheet.append([1, "Long-Ausstieg", "2026-01-05 10:05", 100])
    worksheet.append([1, "Long-Einstieg", "2026-01-05 10:00", 100])
    worksheet.append([2, "Short-Ausstieg", "2026-01-06 10:05", -50])
    worksheet.append([2, "Short-Einstieg", "2026-01-06 10:00", -50])
    workbook.save(xlsx_path)
    workbook.close()

    summary = registry.build_registry(tv_dir=tv_dir, skip_mc=True)

    assert len(summary["strategies"]) == 1
    assert (strategy_dir / "registry.parquet").exists()
    assert (mc_dir / "index.parquet").exists()
