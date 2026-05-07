from datetime import date, timedelta
from pathlib import Path

from Analysis.scripts.tv_phase4_oos_regime_gate import (
    VolRegimeMap,
    build_validation_slices,
    load_vol_regime_csv,
)
from src.strategies.replay import ReplayDay


def test_load_vol_regime_csv_uses_explicit_profiles(tmp_path: Path) -> None:
    path = tmp_path / "vol.csv"
    path.write_text(
        "session_date,vol_profile\n"
        "2026-01-05,low\n"
        "2026-01-06,mid\n"
        "2026-01-07,high\n"
    )

    regimes = load_vol_regime_csv(path)

    assert regimes.source == "vol_profile"
    assert regimes.by_date[date(2026, 1, 5)] == "low"
    assert regimes.by_date[date(2026, 1, 7)] == "high"


def test_load_vol_regime_csv_buckets_realized_vol_into_terciles(tmp_path: Path) -> None:
    path = tmp_path / "vol.csv"
    path.write_text(
        "session_date,realized_vol\n"
        "2026-01-05,1\n"
        "2026-01-06,2\n"
        "2026-01-07,3\n"
        "2026-01-08,4\n"
        "2026-01-09,5\n"
    )

    regimes = load_vol_regime_csv(path)

    assert regimes.source == "realized_vol_terciles"
    assert regimes.by_date[date(2026, 1, 5)] == "low"
    assert regimes.by_date[date(2026, 1, 9)] == "high"


def test_build_validation_slices_fails_without_vol_regime_map() -> None:
    base = date(2026, 1, 5)
    days = [ReplayDay.from_values(base + timedelta(days=i), 2.0, -1.0, -1.0) for i in range(12)]

    slices, failures = build_validation_slices(
        days,
        train_fraction=0.6,
        fold_count=3,
        vol_regimes=None,
        required_vol_profiles=("low", "mid", "high"),
    )

    assert [label for label, _, _ in slices] == ["full", "train", "oos_holdout", "fold_1", "fold_2", "fold_3"]
    assert failures == ["missing external volatility-regime CSV"]


def test_build_validation_slices_allows_missing_vol_for_no_trade_days() -> None:
    base = date(2026, 1, 5)
    days = [
        ReplayDay.from_values(base, 2.0, -1.0, -1.0),
        ReplayDay.from_values(base + timedelta(days=1)),
        ReplayDay.from_values(base + timedelta(days=2), 2.0, -1.0, 2.0),
    ]
    regimes = VolRegimeMap(
        by_date={base: "low", base + timedelta(days=2): "high"},
        source="test",
    )

    _, failures = build_validation_slices(
        days,
        train_fraction=0.6,
        fold_count=1,
        vol_regimes=regimes,
        required_vol_profiles=("low", "high"),
    )

    assert failures == []


def test_build_validation_slices_carries_forward_prior_vol_profile() -> None:
    base = date(2026, 1, 5)
    days = [
        ReplayDay.from_values(base, 2.0, -1.0, -1.0),
        ReplayDay.from_values(base + timedelta(days=1), 2.0, -1.0, 2.0),
    ]
    regimes = VolRegimeMap(by_date={base: "low"}, source="test")

    slices, failures = build_validation_slices(
        days,
        train_fraction=0.6,
        fold_count=1,
        vol_regimes=regimes,
        required_vol_profiles=("low",),
    )

    assert failures == []
    vol_slice = [slice_days for label, _, slice_days in slices if label == "vol_low"][0]
    assert [day.session_date for day in vol_slice] == [base, base + timedelta(days=1)]
