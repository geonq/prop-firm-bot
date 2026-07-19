"""Quantization tests for src/live/sizing.py::contracts_for."""

from __future__ import annotations

import pytest

from src.live.sizing import contracts_for


def test_basic_quantization():
    # stop=5 points, MNQ point_value=2.0 -> risk/contract=$10, budget=$400 -> 40 contracts, clamped
    contracts = contracts_for(5.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20)
    assert contracts == 20  # clamp wins: 400/10=40 > max_contracts=20


def test_floor_rounds_down_not_up():
    # risk/contract = 30*2.0 = $60. 400/60 = 6.666... -> floor to 6.
    contracts = contracts_for(30.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20)
    assert contracts == 6


def test_zero_contract_skip_when_risk_exceeds_budget():
    # risk/contract = 250*2.0 = $500 > $400 budget -> 0 contracts (skip trade).
    contracts = contracts_for(250.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20)
    assert contracts == 0


def test_exact_division_no_floor_loss():
    # risk/contract = 20*2.0 = $40. 400/40 = 10 exactly.
    contracts = contracts_for(20.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20)
    assert contracts == 10


def test_max_contracts_clamp_below_budget_allowance():
    # risk/contract = 1*2.0 = $2. 400/2 = 200, but max_contracts=5 clamps it.
    contracts = contracts_for(1.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=5)
    assert contracts == 5


def test_default_frozen_config_stop_distance_example():
    # A typical MNQ ORB stop distance, sanity check against the documented
    # floor(400 / (stop_pts * 2.0)) formula from Tasks/todo.md.
    stop_points = 15.0
    expected = int(400.0 // (stop_points * 2.0))
    assert contracts_for(stop_points, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20) == expected


@pytest.mark.parametrize("bad_stop", [0.0, -5.0, float("nan"), float("inf")])
def test_invalid_stop_points_raises(bad_stop):
    with pytest.raises(ValueError):
        contracts_for(bad_stop, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=20)


def test_invalid_risk_raises():
    with pytest.raises(ValueError):
        contracts_for(5.0, risk_per_trade_usd=0.0, point_value=2.0, max_contracts=20)


def test_invalid_point_value_raises():
    with pytest.raises(ValueError):
        contracts_for(5.0, risk_per_trade_usd=400.0, point_value=0.0, max_contracts=20)


def test_invalid_max_contracts_raises():
    with pytest.raises(ValueError):
        contracts_for(5.0, risk_per_trade_usd=400.0, point_value=2.0, max_contracts=0)
