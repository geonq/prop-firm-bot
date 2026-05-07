from datetime import date, timedelta

from src.pipeline.replay_validation import (
    ValidationGateConfig,
    chronological_folds,
    chronological_train_oos_split,
    compute_replay_distribution_stats,
    evaluate_validation_slice,
    filter_replay_days_by_dates,
)
from src.strategies.replay import ReplayDay


def _profile4_days(n: int = 30) -> list[ReplayDay]:
    base = date(2026, 1, 5)
    pattern = [2.0, -1.0, -1.0, 2.0, -1.0, 2.0]
    return [
        ReplayDay.from_values(
            base + timedelta(days=i),
            pattern[(i * 3) % len(pattern)],
            pattern[(i * 3 + 1) % len(pattern)],
            pattern[(i * 3 + 2) % len(pattern)],
        )
        for i in range(n)
    ]


def test_compute_replay_distribution_stats_profile4_shape() -> None:
    stats = compute_replay_distribution_stats(_profile4_days(40))

    assert stats.inside_profile4
    assert stats.trades == 120
    assert stats.replay_days == 40
    assert stats.trades_per_replay_day == 3.0


def test_chronological_train_oos_split_preserves_order() -> None:
    days = _profile4_days(10)
    train, oos = chronological_train_oos_split(days, train_fraction=0.6)

    assert len(train) == 6
    assert len(oos) == 4
    assert train[-1].session_date < oos[0].session_date


def test_chronological_folds_cover_all_days() -> None:
    days = _profile4_days(11)
    folds = chronological_folds(days, fold_count=4)

    assert sum(len(fold) for fold in folds) == len(days)
    assert folds[0][0] == days[0]
    assert folds[-1][-1] == days[-1]


def test_evaluate_validation_slice_fails_non_profile4_distribution() -> None:
    days = [
        ReplayDay.from_values(date(2026, 1, 5) + timedelta(days=i), 2.0)
        for i in range(50)
    ]

    result = evaluate_validation_slice(
        label="bad",
        kind="oos",
        replay_days=days,
        gate=ValidationGateConfig(min_trades=10, min_replay_days=10, min_trading_days=10),
    )

    assert not result.passed
    assert "raw distribution outside Profile 4" in result.failures


def test_filter_replay_days_by_dates() -> None:
    days = _profile4_days(5)
    keep = {days[1].session_date, days[3].session_date}

    filtered = filter_replay_days_by_dates(days, keep)

    assert [day.session_date for day in filtered] == [days[1].session_date, days[3].session_date]
