from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from Analysis.scripts.orb_overfitting_battery import (
    adjust_trade_returns_for_costs,
    cscv_pbo,
    deflated_sharpe_probability,
    effective_strategy_trials,
    white_reality_check,
)


def test_cost_adjustment_uses_trade_risk_points() -> None:
    trades = [SimpleNamespace(r=1.0, risk_points=10.0)]
    adjusted = adjust_trade_returns_for_costs(
        trades,
        slippage_ticks_per_side=2,
        commission_per_side=1.24,
    )
    # Base model: 1 tick/side and $0.74/side. New costs add 0.5 + 0.5 points.
    assert np.allclose(adjusted, [0.9])


def test_cscv_pbo_is_bounded_and_counts_combinations() -> None:
    rng = np.random.default_rng(3)
    matrix = rng.normal(0.0, 1.0, size=(80, 6))
    result = cscv_pbo(matrix, block_count=8)
    assert result["combinations"] == 70
    assert 0.0 <= result["probability_backtest_overfit"] <= 1.0
    assert 0.0 <= result["median_oos_percentile"] <= 1.0


def test_white_reality_check_rejects_centered_null_for_strong_edge() -> None:
    rng = np.random.default_rng(11)
    matrix = rng.normal(0.0, 0.25, size=(240, 5))
    matrix[:, 0] += 0.20
    result = white_reality_check(matrix, bootstrap_samples=1_000, block_length=8, seed=9)
    assert result["p_value_any_strategy"] < 0.05
    assert result["observed_max_t"] > 5.0


def test_deflated_sharpe_probability_declines_with_more_trials() -> None:
    rng = np.random.default_rng(17)
    daily = rng.normal(0.08, 1.0, size=500)
    few = deflated_sharpe_probability(daily, trials=2)
    many = deflated_sharpe_probability(daily, trials=234)
    assert 0.0 <= many["probability"] <= few["probability"] <= 1.0
    assert many["benchmark_sharpe"] > few["benchmark_sharpe"]


def test_effective_trials_collapses_identical_strategies() -> None:
    base = np.linspace(-1.0, 1.0, 100)
    matrix = np.column_stack([base, base, base, base])
    assert np.isclose(effective_strategy_trials(matrix), 1.0)
