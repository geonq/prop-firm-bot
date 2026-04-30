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


def test_consistency_allows_exact_50_percent_split() -> None:
    """Source doc says largest day must be <= 50% of total profit.

    The previous test asserted a 52% cushion ($1,560 / $3,000) which was a
    misread of the help-center example: that table is described as "calculated
    on what your actual profit earned is for the day and will vary from trader
    to trader" — a soft buffer, not a numeric threshold. Encoding strict 50%.
    """
    rules = LucidFlex50K()

    # 1500/3000 = 50% — exactly at threshold, must pass (rule is "<=").
    assert rules.consistency_ok([1_500, 1_500], 3_000)
    # 1501/3000 = 50.03% — just over the threshold, must fail.
    assert not rules.consistency_ok([1_501, 1_499], 3_000)
    # Below profit target — never eligible regardless of split.
    assert not rules.consistency_ok([1_000, 1_000], 2_000)


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
