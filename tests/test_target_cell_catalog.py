import csv
import json

from Analysis.scripts.target_cell_catalog import (
    FULL_GRID,
    GridSpec,
    _write_csv,
    _write_manifest,
    run_catalog,
)


def test_full_grid_keeps_low_reward_cells() -> None:
    assert 0.20 in FULL_GRID.rr_ratios
    assert 0.30 in FULL_GRID.rr_ratios


def test_tiny_catalog_runs_two_study_shape() -> None:
    grid = GridSpec(
        win_rates=(0.50,),
        rr_ratios=(1.0,),
        trades_per_day=(1,),
        payout_paths=("lucidflex",),
        n_sims=3,
        eval_bases_search=(150.0, 250.0),
        funded_bases_search=(150.0,),
        buffer_full_fracs_search=(0.04,),
        buffer_floors_search=(0.25,),
        post_payout_shrinks_search=(1.0,),
    )

    rows = run_catalog(grid, seed=7)

    assert len(rows) == 5
    assert [(r["study"], r["sizing"], r["strategy_variant"]) for r in rows] == [
        ("sizing", "Fixed", "iid"),
        ("sizing", "BufferAware", "iid"),
        ("sizing", "Adaptive", "iid"),
        ("robustness", "Fixed", "autocorrelated"),
        ("robustness", "Fixed", "regime_switching"),
    ]
    assert rows[2]["adaptive_eval_base"] in {150.0, 250.0}
    assert all(row["n_sims"] == 3 for row in rows)


def test_writers_preserve_run_metadata(tmp_path) -> None:
    grid = GridSpec(
        win_rates=(0.50,),
        rr_ratios=(1.0,),
        trades_per_day=(1,),
        payout_paths=("topstep_standard",),
        n_sims=2,
        eval_bases_search=(150.0,),
        funded_bases_search=(150.0,),
        buffer_full_fracs_search=(0.04,),
        buffer_floors_search=(0.25,),
        post_payout_shrinks_search=(1.0,),
        topstep_use_daily_loss_limit=True,
        topstep_max_back2funded_reactivations=1,
        payout_cap=2,
    )
    rows = run_catalog(grid, seed=11)
    csv_path = tmp_path / "cells.csv"
    manifest_path = tmp_path / "manifest.json"

    _write_csv(rows, csv_path)
    _write_manifest(
        path=manifest_path,
        grid=grid,
        mode="test",
        seed=11,
        elapsed_s=1.23,
        n_rows=len(rows),
    )

    with csv_path.open() as f:
        first = next(csv.DictReader(f))
    manifest = json.loads(manifest_path.read_text())

    assert first["topstep_use_daily_loss_limit"] == "True"
    assert first["topstep_max_back2funded_reactivations"] == "1"
    assert first["payout_cap"] == "2"
    assert manifest["grid"]["topstep_use_daily_loss_limit"] is True
    assert manifest["grid"]["topstep_max_back2funded_reactivations"] == 1
    assert manifest["grid"]["payout_cap"] == 2
