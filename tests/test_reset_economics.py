from src.optimizer.reset_economics import lucidflex_reset_decision, topstep_reset_decision


def test_lucidflex_reset_beats_normal_coupon_fresh_account_by_three_dollars() -> None:
    decision = lucidflex_reset_decision()

    assert decision.firm == "lucidflex"
    assert decision.reset_cost == 95
    assert decision.fresh_cost == 98
    assert decision.net_savings_from_reset == 3
    assert decision.prefer_reset_before_friction is True
    assert decision.breakeven_nonprice_value == 0


def test_lucidflex_vault_discount_can_make_fresh_account_better_than_reset() -> None:
    decision = lucidflex_reset_decision(current_eval_fee=70)

    assert decision.net_savings_from_reset == -25
    assert decision.prefer_reset_before_friction is False
    assert decision.breakeven_nonprice_value == 25


def test_topstep_reset_needs_nonprice_value_to_beat_fresh_monthly_fee() -> None:
    decision = topstep_reset_decision()

    assert decision.firm == "topstep"
    assert decision.reset_cost == 109
    assert decision.fresh_cost == 95
    assert decision.net_savings_from_reset == -14
    assert decision.prefer_reset_before_friction is False
    assert decision.breakeven_nonprice_value == 14
