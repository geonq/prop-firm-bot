"""Phase 1 ruleset boundary tests.

Per ``Tasks/todo.md`` Phase 1 exit criteria:
- breach detection fires at the exact threshold
- consistency rule violation is caught
- payout eligibility math is correct
- ``max_contracts`` returns the documented cap for each phase
- firm-level trading-hour rules (flatten/reopen) reject out-of-window holds

These tests exercise the rule modules directly (``src/rules/lucidflex.py``
and ``src/rules/topstep.py``) so a future encoding regression is caught
without needing a state-machine round trip.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath


NY = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# LucidFlex 50K
# ---------------------------------------------------------------------------


class TestLucidFlexConsistency:
    def test_below_target_never_passes(self) -> None:
        rules = LucidFlex50K()
        # 50% of profit but profit short of $3,000 target.
        assert not rules.consistency_ok([1_000, 1_000], 2_000)

    def test_exact_50_percent_passes(self) -> None:
        rules = LucidFlex50K()
        # 1500 / 3000 = 0.50 exactly. Source rule is "<= 50%".
        assert rules.consistency_ok([1_500, 1_500], 3_000)

    def test_just_over_50_percent_fails(self) -> None:
        rules = LucidFlex50K()
        # 1501 / 3000 = 0.5003 — strictly over the threshold.
        assert not rules.consistency_ok([1_501, 1_499], 3_000)

    def test_zero_profit_returns_false(self) -> None:
        # Defensive: should not divide by zero when profit hasn't accumulated.
        rules = LucidFlex50K()
        assert not rules.consistency_ok([], 0)


class TestLucidFlexMLLTrailing:
    def test_mll_trails_up_with_closing_balance(self) -> None:
        rules = LucidFlex50K()
        # Closing $50,500 → candidate MLL = 48,500. Above the initial 48,000.
        assert rules.update_mll_after_close(50_500, rules.initial_mll) == 48_500

    def test_mll_never_moves_down(self) -> None:
        rules = LucidFlex50K()
        # Already at 49,000; close at 50,000 → candidate 48,000 < current.
        # The "never moves down" invariant must keep MLL at 49,000.
        assert rules.update_mll_after_close(50_000, 49_000) == 49_000

    def test_mll_locks_at_50_100_when_trail_balance_reached(self) -> None:
        rules = LucidFlex50K()
        # Source doc: closing >= $52,100 locks MLL at $50,100 permanently.
        assert rules.update_mll_after_close(52_100, 49_000) == 50_100

    def test_mll_stays_locked_after_drawdown(self) -> None:
        rules = LucidFlex50K()
        # Once locked at 50,100, dropping below the trail balance must not
        # reduce the MLL — the trail is irreversible.
        assert rules.update_mll_after_close(51_000, 50_100) == 50_100


class TestLucidFlexPayoutMath:
    def test_zero_profit_returns_zero(self) -> None:
        rules = LucidFlex50K()
        assert rules.payout_request_amount(0) == 0.0

    def test_below_minimum_returns_zero(self) -> None:
        rules = LucidFlex50K()
        # 50% of $999 = $499.50 < $500 minimum → no request allowed.
        assert rules.payout_request_amount(999) == 0.0

    def test_at_minimum_is_eligible(self) -> None:
        rules = LucidFlex50K()
        # 50% of $1,000 = $500 → exactly at minimum.
        assert rules.payout_request_amount(1_000) == 500.0

    def test_capped_at_2000_for_50k(self) -> None:
        rules = LucidFlex50K()
        # 50% of $10,000 = $5,000 → capped at $2,000 per source table.
        assert rules.payout_request_amount(10_000) == 2_000.0

    def test_trader_split_is_90_10(self) -> None:
        rules = LucidFlex50K()
        # Gross $1,000 → trader receives $900.
        assert rules.trader_payout_amount(1_000) == pytest.approx(900.0)


class TestLucidFlexMaxContracts:
    def test_eval_phase_is_flat_4_or_40(self) -> None:
        rules = LucidFlex50K()
        assert rules.max_contracts(phase="eval", micros=False) == 4
        assert rules.max_contracts(phase="eval", micros=True) == 40

    def test_funded_scaling_at_each_tier(self) -> None:
        rules = LucidFlex50K()
        # Source doc, 50K column: $0-$999 → 2, $1k-$1.99k → 3, $2k+ → 4.
        assert rules.max_contracts(phase="funded", simulated_profit=0) == 2
        assert rules.max_contracts(phase="funded", simulated_profit=999) == 2
        assert rules.max_contracts(phase="funded", simulated_profit=1_000) == 3
        assert rules.max_contracts(phase="funded", simulated_profit=1_999) == 3
        assert rules.max_contracts(phase="funded", simulated_profit=2_000) == 4
        assert rules.max_contracts(phase="funded", simulated_profit=10_000) == 4

    def test_funded_micros_scale_10x(self) -> None:
        rules = LucidFlex50K()
        # 1 mini = 10 micros at LucidFlex.
        assert rules.max_contracts(phase="funded", simulated_profit=1_500, micros=True) == 30

    def test_unknown_phase_raises(self) -> None:
        rules = LucidFlex50K()
        with pytest.raises(ValueError):
            rules.max_contracts(phase="invalid")


class TestLucidFlexTradingHours:
    """Source doc: flat by 4:45 PM EST Mon-Fri; reopen 6:00 PM EST Sun-Thu."""

    def test_naive_datetime_raises(self) -> None:
        # Replaying historical trades without timezone info is a correctness
        # trap (DST transitions silently move boundaries). Reject explicitly.
        rules = LucidFlex50K()
        with pytest.raises(ValueError):
            rules.must_be_flat(datetime(2026, 4, 30, 12, 0))

    def test_midday_weekday_is_tradeable(self) -> None:
        rules = LucidFlex50K()
        # Wednesday noon EST — well inside open hours.
        assert rules.is_tradeable(datetime(2026, 4, 29, 12, 0, tzinfo=NY))

    def test_exactly_at_flatten_time_must_be_flat(self) -> None:
        rules = LucidFlex50K()
        # 4:45:00 PM Wednesday — doc says "flat BY 4:45 PM" → at the boundary
        # itself, must be flat.
        assert rules.must_be_flat(datetime(2026, 4, 29, 16, 45, tzinfo=NY))

    def test_one_second_before_flatten_is_tradeable(self) -> None:
        rules = LucidFlex50K()
        assert rules.is_tradeable(datetime(2026, 4, 29, 16, 44, 59, tzinfo=NY))

    def test_exactly_at_reopen_is_tradeable(self) -> None:
        rules = LucidFlex50K()
        # 6:00:00 PM Wednesday — at reopen, tradeable again.
        assert rules.is_tradeable(datetime(2026, 4, 29, 18, 0, tzinfo=NY))

    def test_one_second_before_reopen_must_be_flat(self) -> None:
        rules = LucidFlex50K()
        assert rules.must_be_flat(datetime(2026, 4, 29, 17, 59, 59, tzinfo=NY))

    def test_friday_after_flatten_must_be_flat(self) -> None:
        rules = LucidFlex50K()
        # Friday 5 PM — Friday close stays in effect through the weekend.
        assert rules.must_be_flat(datetime(2026, 5, 1, 17, 0, tzinfo=NY))

    def test_saturday_always_flat(self) -> None:
        rules = LucidFlex50K()
        # Saturday at any time — firm closed.
        assert rules.must_be_flat(datetime(2026, 5, 2, 12, 0, tzinfo=NY))

    def test_sunday_before_reopen_must_be_flat(self) -> None:
        rules = LucidFlex50K()
        assert rules.must_be_flat(datetime(2026, 5, 3, 17, 0, tzinfo=NY))

    def test_sunday_at_reopen_is_tradeable(self) -> None:
        rules = LucidFlex50K()
        # Sunday 6:00 PM EST — reopen for Monday's session.
        assert rules.is_tradeable(datetime(2026, 5, 3, 18, 0, tzinfo=NY))

    def test_utc_input_converted_correctly(self) -> None:
        rules = LucidFlex50K()
        # 8:00 PM UTC = 4:00 PM EDT (April 29, 2026, DST in effect).
        # 4:00 PM EDT is before 4:45 PM flatten → tradeable.
        ts_utc = datetime(2026, 4, 29, 20, 0, tzinfo=ZoneInfo("UTC"))
        assert rules.is_tradeable(ts_utc)


# ---------------------------------------------------------------------------
# TopStep 50K No Activation Fee
# ---------------------------------------------------------------------------


class TestTopStepConsistency:
    def test_below_combine_target_never_passes(self) -> None:
        rules = TopStepNoFee50K()
        assert not rules.combine_consistency_ok([1_000, 1_000], 2_000)

    def test_combine_at_exact_50_percent_passes(self) -> None:
        rules = TopStepNoFee50K()
        # 1500/3000 = 0.50 exactly — encoded with "<=", consistent with Lucid.
        assert rules.combine_consistency_ok([1_500, 1_500], 3_000)

    def test_combine_just_over_50_percent_fails(self) -> None:
        rules = TopStepNoFee50K()
        assert not rules.combine_consistency_ok([1_501, 1_499], 3_000)

    def test_xfa_at_exact_40_percent_passes(self) -> None:
        rules = TopStepNoFee50K()
        # 400/1000 = 0.40 — encoded with "<=".
        assert rules.xfa_consistency_ok([400, 300, 300], 1_000)

    def test_xfa_just_over_40_percent_fails(self) -> None:
        rules = TopStepNoFee50K()
        assert not rules.xfa_consistency_ok([401, 300, 299], 1_000)


class TestTopStepMLLTrailing:
    def test_combine_mll_trails_up(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.update_combine_mll_after_close(50_500, rules.combine_initial_mll) == 48_500

    def test_combine_mll_locks_at_starting_balance(self) -> None:
        rules = TopStepNoFee50K()
        # Source doc: locks at $50,000 (the original starting balance), NOT
        # at start + buffer like LucidFlex's $50,100.
        assert rules.update_combine_mll_after_close(52_500, 49_000) == 50_000

    def test_combine_mll_never_moves_down(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.update_combine_mll_after_close(51_000, 50_000) == 50_000

    def test_xfa_mll_trails_from_negative_to_zero(self) -> None:
        rules = TopStepNoFee50K()
        # Initial -2000; closing at 1500 → candidate -500.
        assert rules.update_xfa_mll_after_close(1_500, -2_000) == -500

    def test_xfa_mll_locks_at_zero(self) -> None:
        rules = TopStepNoFee50K()
        # Closing at 3000 → candidate 1000, but locks at 0.
        assert rules.update_xfa_mll_after_close(3_000, -500) == 0


class TestTopStepPayoutMath:
    def test_zero_balance_returns_zero(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.payout_request_amount(0) == 0.0

    def test_standard_below_minimum(self) -> None:
        rules = TopStepNoFee50K()
        # 50% of $200 = $100 < $125 minimum.
        assert rules.payout_request_amount(200) == 0.0

    def test_standard_at_minimum(self) -> None:
        rules = TopStepNoFee50K()
        # 50% of $250 = $125 → exactly at minimum.
        assert rules.payout_request_amount(250) == 125.0

    def test_standard_capped_at_2000(self) -> None:
        rules = TopStepNoFee50K()
        # 50% of $10,000 = $5,000 → Standard cap is $2,000 for 50K.
        assert rules.payout_request_amount(10_000, TopStepPayoutPath.STANDARD) == 2_000.0

    def test_consistency_capped_at_3000(self) -> None:
        rules = TopStepNoFee50K()
        # 50% of $10,000 = $5,000 → Consistency cap is $3,000 for 50K.
        assert rules.payout_request_amount(10_000, TopStepPayoutPath.CONSISTENCY) == 3_000.0

    def test_trader_split_is_90_10(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.trader_payout_amount(1_000) == pytest.approx(900.0)


class TestTopStepMaxContracts:
    def test_combine_is_flat_5_or_50(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.max_contracts(phase="combine", micros=False) == 5
        assert rules.max_contracts(phase="combine", micros=True) == 50

    def test_xfa_scaling_tiers(self) -> None:
        # Source table: $0-$1,500 → 2, $1,500+ → 3, $2,000+ → 5.
        rules = TopStepNoFee50K()
        assert rules.max_contracts(phase="xfa", balance=0) == 2
        assert rules.max_contracts(phase="xfa", balance=1_499) == 2
        assert rules.max_contracts(phase="xfa", balance=1_500) == 3
        assert rules.max_contracts(phase="xfa", balance=1_999) == 3
        assert rules.max_contracts(phase="xfa", balance=2_000) == 5
        assert rules.max_contracts(phase="xfa", balance=2_001) == 5
        assert rules.max_contracts(phase="xfa", balance=10_000) == 5

    def test_xfa_micros_scale_10x(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.max_contracts(phase="xfa", balance=2_500, micros=True) == 50

    def test_unknown_phase_raises(self) -> None:
        rules = TopStepNoFee50K()
        with pytest.raises(ValueError):
            rules.max_contracts(phase="invalid")


class TestTopStepTradingHours:
    """Source doc: flat by 3:10 PM CT Mon-Fri; reopen 5:00 PM CT."""

    def test_naive_datetime_raises(self) -> None:
        rules = TopStepNoFee50K()
        with pytest.raises(ValueError):
            rules.must_be_flat(datetime(2026, 4, 30, 12, 0))

    def test_midday_weekday_is_tradeable(self) -> None:
        rules = TopStepNoFee50K()
        # Wednesday 10 AM CT — well inside open hours.
        assert rules.is_tradeable(datetime(2026, 4, 29, 10, 0, tzinfo=CT))

    def test_exactly_at_flatten_time_must_be_flat(self) -> None:
        rules = TopStepNoFee50K()
        # 3:10:00 PM Wednesday — boundary itself must be flat.
        assert rules.must_be_flat(datetime(2026, 4, 29, 15, 10, tzinfo=CT))

    def test_one_second_before_flatten_is_tradeable(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.is_tradeable(datetime(2026, 4, 29, 15, 9, 59, tzinfo=CT))

    def test_exactly_at_reopen_is_tradeable(self) -> None:
        rules = TopStepNoFee50K()
        # 5:00:00 PM Wednesday — at reopen, tradeable.
        assert rules.is_tradeable(datetime(2026, 4, 29, 17, 0, tzinfo=CT))

    def test_friday_after_flatten_must_be_flat(self) -> None:
        rules = TopStepNoFee50K()
        # Friday 4 PM CT — Friday close runs through weekend.
        assert rules.must_be_flat(datetime(2026, 5, 1, 16, 0, tzinfo=CT))

    def test_saturday_always_flat(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.must_be_flat(datetime(2026, 5, 2, 12, 0, tzinfo=CT))

    def test_sunday_at_reopen_is_tradeable(self) -> None:
        rules = TopStepNoFee50K()
        # Sunday 5:00 PM CT — reopen for Monday's session.
        assert rules.is_tradeable(datetime(2026, 5, 3, 17, 0, tzinfo=CT))

    def test_sunday_before_reopen_must_be_flat(self) -> None:
        rules = TopStepNoFee50K()
        assert rules.must_be_flat(datetime(2026, 5, 3, 16, 59, tzinfo=CT))
