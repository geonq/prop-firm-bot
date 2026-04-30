from src.pipeline.topstep_account import TopStepNoFeeAccountState, TopStepPhase
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath


def close_combine_day(account: TopStepNoFeeAccountState, pnl: float) -> None:
    account.update(pnl)
    account.close_day()


def close_xfa_day(account: TopStepNoFeeAccountState, pnl: float) -> None:
    account.update(pnl)
    account.close_day()


def pass_combine(account: TopStepNoFeeAccountState) -> None:
    close_combine_day(account, 1_500)
    account.update(1_500)


def test_topstep_50k_core_values() -> None:
    rules = TopStepNoFee50K()

    assert rules.combine_starting_balance == 50_000
    assert rules.combine_profit_target == 3_000
    assert rules.combine_initial_mll == 48_000
    assert rules.xfa_initial_mll == -2_000
    assert rules.nofee_monthly_fee == 95
    assert rules.activation_fee == 0
    assert rules.max_contracts(micros=False, phase="combine") == 5
    assert rules.max_contracts(micros=True, phase="combine") == 50


def test_topstep_combine_mll_trails_and_locks_at_starting_balance() -> None:
    rules = TopStepNoFee50K()

    assert rules.update_combine_mll_after_close(50_500, rules.combine_initial_mll) == 48_500
    assert rules.update_combine_mll_after_close(52_500, 49_000) == 50_000
    assert rules.update_combine_mll_after_close(51_000, 50_000) == 50_000


def test_topstep_account_passes_combine_and_xfa_starts_at_zero() -> None:
    account = TopStepNoFeeAccountState()

    pass_combine(account)

    assert account.phase == TopStepPhase.XFA
    assert account.is_passed_eval
    assert account.balance == 0
    assert account.mll == -2_000


def test_topstep_combine_consistency_blocks_single_day_pass() -> None:
    account = TopStepNoFeeAccountState()

    event = account.update(3_000)

    assert event.phase == TopStepPhase.COMBINE
    assert account.balance == 53_000
    assert not account.is_passed_eval


def test_topstep_combine_breach_and_reset_cost() -> None:
    account = TopStepNoFeeAccountState()

    event = account.update(-2_000)

    assert event.phase == TopStepPhase.COMBINE_FAILED
    assert account.is_breached

    reset_cost = account.attempt_reset()

    assert reset_cost == 109
    assert account.phase == TopStepPhase.COMBINE
    assert account.balance == 50_000
    assert account.mll == 48_000
    assert account.total_fees_paid == 204


def test_topstep_xfa_standard_payout_and_mll_reset() -> None:
    account = TopStepNoFeeAccountState()
    pass_combine(account)

    for _ in range(5):
        close_xfa_day(account, 200)

    received = account.request_payout()

    assert received == 450
    assert account.balance == 500
    assert account.mll == 0
    assert account.payout_count == 1
    assert account.standard_winning_days == 0
    assert account.total_trader_payouts == 450


def test_topstep_xfa_standard_payout_cap() -> None:
    account = TopStepNoFeeAccountState()
    pass_combine(account)

    for _ in range(5):
        close_xfa_day(account, 1_200)

    received = account.request_payout()

    assert received == 1_800
    assert account.balance == 4_000


def test_topstep_xfa_consistency_path_requires_three_balanced_days() -> None:
    account = TopStepNoFeeAccountState(payout_path=TopStepPayoutPath.CONSISTENCY)
    pass_combine(account)

    close_xfa_day(account, 1_000)
    close_xfa_day(account, 1_000)
    close_xfa_day(account, 1_000)

    received = account.request_payout()

    assert received == 1_350
    assert account.balance == 1_500


def test_topstep_xfa_mll_closes_and_back2funded_resets_before_first_payout() -> None:
    account = TopStepNoFeeAccountState()
    pass_combine(account)

    event = account.update(-2_000)

    assert event.phase == TopStepPhase.XFA_CLOSED

    cost = account.attempt_back2funded()

    assert cost == 599
    assert account.phase == TopStepPhase.XFA
    assert account.balance == 0
    assert account.mll == -2_000
    assert account.total_fees_paid == 694


def test_topstep_back2funded_unavailable_after_first_payout() -> None:
    account = TopStepNoFeeAccountState()
    pass_combine(account)

    for _ in range(5):
        close_xfa_day(account, 200)
    account.request_payout()
    account.update(-500)

    assert account.phase == TopStepPhase.XFA_CLOSED

    try:
        account.attempt_back2funded()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected Back2Funded to be unavailable after payout")


def test_topstep_optional_dll_locks_only_until_day_close() -> None:
    account = TopStepNoFeeAccountState(use_daily_loss_limit=True)

    event = account.update(-1_000)

    assert event.phase == TopStepPhase.COMBINE
    assert account.daily_locked
    assert not account.is_breached

    try:
        account.update(100)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected DLL lock to reject same-session trade")

    account.close_day()

    assert not account.daily_locked
    assert account.phase == TopStepPhase.COMBINE
