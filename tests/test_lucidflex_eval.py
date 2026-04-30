from src.pipeline.eval_simulator import simulate_lucidflex_eval
from src.rules.lucidflex import LucidFlex50K
from src.strategies.parametric import BernoulliTradeStrategy


def test_lucidflex_50k_core_values() -> None:
    rules = LucidFlex50K()

    assert rules.starting_balance == 50_000
    assert rules.profit_target == 3_000
    assert rules.initial_mll == 48_000
    assert rules.locked_mll_balance == 50_100
    assert rules.max_contracts(micros=False, phase="eval") == 4
    assert rules.max_contracts(micros=True, phase="eval") == 40


def test_lucidflex_eod_mll_trails_and_locks() -> None:
    rules = LucidFlex50K()

    assert rules.update_mll_after_close(50_500, rules.initial_mll) == 48_500
    assert rules.update_mll_after_close(52_100, 49_000) == 50_100
    assert rules.update_mll_after_close(51_000, 50_100) == 50_100


def test_consistency_allows_two_day_pass_with_cushion() -> None:
    rules = LucidFlex50K()

    assert rules.consistency_ok([1_560, 1_440], 3_000)
    assert not rules.consistency_ok([1_570, 1_430], 3_000)


def test_always_win_strategy_passes_lucidflex_eval() -> None:
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=750, trades_per_day=1)

    result = simulate_lucidflex_eval(strategy, seed=1, max_days=10)

    assert result.passed
    assert result.days_used == 4
    assert result.total_profit == 3_000


def test_always_loss_strategy_breaches_lucidflex_eval() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500, trades_per_day=1)

    result = simulate_lucidflex_eval(strategy, seed=1, max_days=10)

    assert result.breached
    assert result.days_used == 4
    assert result.ending_balance == 48_000
