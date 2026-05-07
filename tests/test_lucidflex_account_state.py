from src.pipeline.lucidflex_account import LucidFlexAccountState, LucidFlexPhase


def close_profitable_day(account: LucidFlexAccountState, pnl: float) -> None:
    account.update(pnl)
    account.close_day()


def test_lucidflex_account_passes_eval_and_starts_funded_clean() -> None:
    account = LucidFlexAccountState()

    close_profitable_day(account, 1_500)
    event = account.update(1_500)

    assert event.phase == LucidFlexPhase.FUNDED
    assert account.is_passed_eval
    assert account.balance == 50_000
    assert account.mll == 48_000
    assert account.cycle_profitable_days == 0


def test_lucidflex_account_consistency_blocks_single_day_pass() -> None:
    account = LucidFlexAccountState()

    event = account.update(3_000)

    assert event.phase == LucidFlexPhase.EVAL
    assert not account.is_passed_eval
    assert account.balance == 53_000


def test_lucidflex_account_eval_breach_and_reset() -> None:
    account = LucidFlexAccountState()

    event = account.update(-2_000)

    assert event.phase == LucidFlexPhase.BREACHED_EVAL
    assert account.is_breached

    reset_cost = account.attempt_reset()

    assert reset_cost == 95
    assert account.phase == LucidFlexPhase.EVAL
    assert account.balance == 50_000
    assert account.mll == 48_000
    assert account.total_fees_paid == 193


def test_lucidflex_account_funded_payout_and_terminal_max_payouts() -> None:
    account = LucidFlexAccountState()
    close_profitable_day(account, 1_500)
    account.update(1_500)

    total_received = 0.0
    for _ in range(5):
        for _ in range(5):
            close_profitable_day(account, 750)
        total_received += account.request_payout()

    assert account.phase == LucidFlexPhase.MAX_PAYOUTS
    assert account.payout_count == 5
    assert account.total_trader_payouts == total_received
    assert account.net_ev == total_received - 98


def test_lucidflex_account_funded_breach_after_pass() -> None:
    account = LucidFlexAccountState()
    close_profitable_day(account, 1_500)
    account.update(1_500)

    event = account.update(-2_000)

    assert event.phase == LucidFlexPhase.BREACHED_FUNDED
    assert account.is_breached


def test_lucidflex_payout_requires_five_profitable_cycle_days() -> None:
    account = LucidFlexAccountState()
    close_profitable_day(account, 1_500)
    account.update(1_500)

    for _ in range(4):
        close_profitable_day(account, 750)

    try:
        account.request_payout()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected payout to require five profitable days")

    close_profitable_day(account, 750)

    assert account.request_payout() > 0


def test_lucidflex_eval_consistency_can_be_repaired_by_extra_profit_day() -> None:
    account = LucidFlexAccountState()

    close_profitable_day(account, 2_000)
    account.update(1_000)

    assert account.phase == LucidFlexPhase.EVAL
    assert account.balance == 53_000

    account.close_day()
    account.update(1_000)

    assert account.phase == LucidFlexPhase.FUNDED
