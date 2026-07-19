"""Apex Trader Funding 4.0 ruleset boundary tests.

Mirrors ``tests/test_rulesets.py`` conventions: exercise the rule module
(``src/rules/apex.py``) directly so an encoding regression is caught without
needing a state-machine round trip.
"""

from __future__ import annotations

import pytest

from src.rules.apex import Apex50K


class TestApexThreshold:
    def test_eval_initial_threshold(self) -> None:
        rules = Apex50K()
        assert rules.eval_initial_threshold == 48_000

    def test_safety_net_balance(self) -> None:
        rules = Apex50K()
        # start + $100 buffer = 50,100.
        assert rules.safety_net_balance == 50_100

    def test_eod_threshold_trails_up_with_closing_balance(self) -> None:
        rules = Apex50K()
        # Closing $50,500 -> candidate 48,500. Above the initial 48,000.
        assert rules.update_eod_threshold_after_close(50_500, rules.eval_initial_threshold) == 48_500

    def test_eod_threshold_never_moves_down(self) -> None:
        rules = Apex50K()
        # Already at 49,000; close at 50,000 -> candidate 48,000 < current.
        assert rules.update_eod_threshold_after_close(50_000, 49_000) == 49_000

    def test_eod_threshold_locks_at_safety_net_when_trail_balance_reached(self) -> None:
        rules = Apex50K()
        # Closing >= 52,100 (safety_net + drawdown) locks threshold at 50,100.
        assert rules.update_eod_threshold_after_close(52_100, 49_000) == 50_100

    def test_eod_threshold_one_dollar_below_lock_point_does_not_lock(self) -> None:
        rules = Apex50K()
        # Closing at 52,099.99 -> candidate 50,099.99, capped at 50,100 anyway
        # via min(), but should not hit the "locked" branch's exact value by
        # coincidence -- verify candidate math directly below the boundary.
        assert rules.update_eod_threshold_after_close(52_099, 49_000) == 50_099

    def test_eod_threshold_stays_locked_after_drawdown(self) -> None:
        rules = Apex50K()
        # Once locked at 50,100, dropping below the trail balance must not
        # reduce the threshold -- the lock is irreversible.
        assert rules.update_eod_threshold_after_close(51_000, 50_100) == 50_100

    def test_intraday_threshold_ratchets_on_peak(self) -> None:
        rules = Apex50K()
        # Peak reaches 51,000 -> candidate threshold 49,000.
        assert rules.update_intraday_threshold(51_000, rules.eval_initial_threshold) == 49_000

    def test_intraday_threshold_locks_at_safety_net(self) -> None:
        rules = Apex50K()
        assert rules.update_intraday_threshold(52_100, 49_000) == 50_100

    def test_intraday_threshold_never_moves_down(self) -> None:
        rules = Apex50K()
        assert rules.update_intraday_threshold(50_000, 49_000) == 49_000


class TestApexFees:
    def test_eval_fee_variants(self) -> None:
        rules = Apex50K()
        assert rules.eval_fee(variant="eod") == 197
        assert rules.eval_fee(variant="intraday") == 131

    def test_pa_activation_fee_variants(self) -> None:
        rules = Apex50K()
        assert rules.pa_activation_fee(variant="eod") == 99
        assert rules.pa_activation_fee(variant="intraday") == 79

    def test_unknown_variant_raises(self) -> None:
        rules = Apex50K()
        with pytest.raises(ValueError):
            rules.eval_fee(variant="bogus")
        with pytest.raises(ValueError):
            rules.pa_activation_fee(variant="bogus")


class TestApexPayoutConsistency:
    def test_payout_consistency_exact_50_percent_passes(self) -> None:
        rules = Apex50K()
        assert rules.payout_consistency_ok([500, 500, 500], 1_500)

    def test_payout_consistency_just_over_50_percent_fails(self) -> None:
        rules = Apex50K()
        assert not rules.payout_consistency_ok([800, 300, 300], 1_400)

    def test_payout_consistency_zero_profit_returns_false(self) -> None:
        rules = Apex50K()
        assert not rules.payout_consistency_ok([], 0)


class TestApexPayoutMath:
    def test_zero_profit_returns_zero(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(0, cycle_number=1) == 0.0

    def test_below_minimum_returns_zero(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(499, cycle_number=1) == 0.0

    def test_at_minimum_is_eligible(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(500, cycle_number=1) == 500.0

    def test_cycle_1_capped_at_1500(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(10_000, cycle_number=1) == 1_500.0

    def test_cycle_6_capped_at_3000(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(10_000, cycle_number=6) == 3_000.0

    def test_cycle_7_is_uncapped(self) -> None:
        rules = Apex50K()
        assert rules.payout_request_amount(10_000, cycle_number=7) == 10_000.0

    def test_cycle_number_below_one_raises(self) -> None:
        rules = Apex50K()
        with pytest.raises(ValueError):
            rules.payout_request_amount(1_000, cycle_number=0)

    def test_full_100_percent_split(self) -> None:
        rules = Apex50K()
        assert rules.trader_payout_amount(1_000) == pytest.approx(1_000.0)

    def test_payout_cap_for_cycle_ladder(self) -> None:
        rules = Apex50K()
        assert rules.payout_cap_for_cycle(1) == 1_500.0
        assert rules.payout_cap_for_cycle(5) == 2_700.0
        assert rules.payout_cap_for_cycle(6) == 3_000.0
        assert rules.payout_cap_for_cycle(7) is None


class TestApexMaxContracts:
    def test_eval_phase_is_flat_6_or_60(self) -> None:
        rules = Apex50K()
        assert rules.max_contracts(phase="eval", micros=False) == 6
        assert rules.max_contracts(phase="eval", micros=True) == 60

    def test_pa_starts_at_2_and_caps_at_4(self) -> None:
        rules = Apex50K()
        assert rules.max_contracts(phase="pa", simulated_profit=0) == 2
        assert rules.max_contracts(phase="pa", simulated_profit=2_500) == 3
        assert rules.max_contracts(phase="pa", simulated_profit=5_000) == 4
        assert rules.max_contracts(phase="pa", simulated_profit=100_000) == 4

    def test_pa_micros_scale_10x(self) -> None:
        rules = Apex50K()
        assert rules.max_contracts(phase="pa", simulated_profit=5_000, micros=True) == 40

    def test_unknown_phase_raises(self) -> None:
        rules = Apex50K()
        with pytest.raises(ValueError):
            rules.max_contracts(phase="invalid")


class TestApexQualifyingDay:
    def test_qualifying_day_threshold(self) -> None:
        rules = Apex50K()
        assert rules.is_qualifying_day(150)
        assert not rules.is_qualifying_day(149.99)


class TestApexParameterization:
    def test_25k_tier_is_constructible(self) -> None:
        rules = Apex50K(account_size=25_000, profit_target=1_500, trailing_drawdown=1_500)
        assert rules.eval_initial_threshold == 23_500
        assert rules.safety_net_balance == 25_100

    def test_100k_tier_is_constructible(self) -> None:
        rules = Apex50K(account_size=100_000, profit_target=6_000, trailing_drawdown=3_000)
        assert rules.eval_initial_threshold == 97_000
        assert rules.safety_net_balance == 100_100

    def test_150k_tier_is_constructible(self) -> None:
        rules = Apex50K(account_size=150_000, profit_target=9_000, trailing_drawdown=5_000)
        assert rules.eval_initial_threshold == 145_000
        assert rules.safety_net_balance == 150_100
