from datetime import date

from src.pipeline.alt_firm_replay import simulate_mffu_rapid_50k, simulate_tradeify_lightning_50k
from src.strategies.replay import ReplayDay


def days(*r_values):
    return [ReplayDay.from_values(date(2026, 1, index + 2), value) for index, value in enumerate(r_values)]


def test_tradeify_charges_purchase_and_breaches_at_floor():
    result = simulate_tradeify_lightning_50k(days(-5.0), risk_per_trade=400)
    assert result.funded_breached
    assert result.net_ev == -492.0


def test_tradeify_requires_consistency_before_first_payout():
    result = simulate_tradeify_lightning_50k(days(4.0, 4.0, 4.0, 4.0, 4.0), risk_per_trade=400)
    assert result.payout_count == 1
    assert result.trader_payouts == 1_800.0


def test_mffu_failed_eval_loses_purchase_only():
    result = simulate_mffu_rapid_50k(days(-5.0), risk_per_trade=400)
    assert not result.eval_passed
    assert result.net_ev == -109.0


def test_mffu_passes_then_preserves_buffer_for_payout():
    # Two +4R days pass the $3k / 50%-consistency evaluation; then two
    # further +4R days fund the buffer and produce a $1,100 gross payout.
    result = simulate_mffu_rapid_50k(days(4.0, 4.0, 4.0, 4.0), risk_per_trade=400)
    assert result.eval_passed
    assert result.payout_count == 1
    assert result.trader_payouts == 990.0
