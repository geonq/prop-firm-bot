from src.pipeline.lucidflex_funded import LucidFlexFundedAccount
from src.rules.lucidflex import LucidFlex50K


def close_profitable_day(account: LucidFlexFundedAccount, pnl: float) -> None:
    account.apply_trade(pnl)
    account.close_day()


def test_lucidflex_funded_requires_five_profitable_days_and_min_request() -> None:
    account = LucidFlexFundedAccount()

    for _ in range(4):
        close_profitable_day(account, 200)

    assert not account.payout_eligible()

    close_profitable_day(account, 100)
    assert account.cycle_profitable_days == 4
    assert not account.payout_eligible()

    close_profitable_day(account, 200)
    assert account.cycle_profitable_days == 5
    assert account.payout_eligible()
    assert account.eligible_payout_request_amount() == 550


def test_lucidflex_funded_payout_deducts_gross_and_tracks_trader_split() -> None:
    account = LucidFlexFundedAccount()

    for _ in range(5):
        close_profitable_day(account, 200)

    result = account.request_payout()

    assert result.gross_request == 500
    assert result.trader_receives == 450
    assert result.account_balance_after == 50_500
    assert account.total_trader_payouts == 450
    assert account.payout_count == 1
    assert account.cycle_profitable_days == 0
    assert account.cycle_start_balance == 50_500
    assert account.mll == 50_100


def test_lucidflex_funded_payout_caps_at_account_maximum() -> None:
    account = LucidFlexFundedAccount()

    for _ in range(5):
        close_profitable_day(account, 1_200)

    assert account.simulated_profit == 6_000

    result = account.request_payout()

    assert result.gross_request == 2_000
    assert result.trader_receives == 1_800
    assert result.account_balance_after == 54_000


def test_lucidflex_funded_scaling_uses_end_of_day_profit_tiers() -> None:
    account = LucidFlexFundedAccount()

    assert account.max_contracts(micros=False) == 2
    assert account.max_contracts(micros=True) == 20

    close_profitable_day(account, 1_000)

    assert account.max_contracts(micros=False) == 3
    assert account.max_contracts(micros=True) == 30

    close_profitable_day(account, 1_000)

    assert account.max_contracts(micros=False) == 4
    assert account.max_contracts(micros=True) == 40


def test_lucidflex_funded_breaches_at_mll() -> None:
    account = LucidFlexFundedAccount()

    account.apply_trade(-2_000)

    assert account.breached

    try:
        account.apply_trade(100)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected breached account to reject new trades")


def test_lucidflex_rules_payout_amount_respects_minimum_and_cap() -> None:
    rules = LucidFlex50K()

    assert rules.payout_request_amount(900) == 0
    assert rules.payout_request_amount(1_000) == 500
    assert rules.payout_request_amount(6_000) == 2_000
