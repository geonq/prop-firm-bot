import random

from src.pipeline.monte_carlo import run_monte_carlo
from src.strategies.parametric import (
    AutocorrelatedPhaseAwareBernoulliStrategy,
    RegimeSwitchingPhaseAwareBernoulliStrategy,
    StrategyRegime,
)


def test_autocorrelated_strategy_repeats_after_first_trade_at_full_persistence() -> None:
    strategy = AutocorrelatedPhaseAwareBernoulliStrategy(
        win_rate=0.50,
        rr_ratio=1.0,
        eval_loss_size=100,
        funded_loss_size=100,
        autocorrelation=1.0,
    )
    rng = random.Random(1)

    trades = [strategy.sample_trade(rng, phase="eval") for _ in range(5)]

    assert len(set(trades)) == 1


def test_autocorrelated_strategy_reset_clears_previous_outcome() -> None:
    strategy = AutocorrelatedPhaseAwareBernoulliStrategy(
        win_rate=0.0,
        rr_ratio=1.0,
        eval_loss_size=100,
        funded_loss_size=100,
        autocorrelation=1.0,
    )
    rng = random.Random(1)
    strategy.sample_trade(rng, phase="eval")

    assert strategy._last_win is False
    strategy.reset()
    assert strategy._last_win is None


def test_regime_switching_strategy_uses_weighted_regimes() -> None:
    strategy = RegimeSwitchingPhaseAwareBernoulliStrategy(
        regimes=(
            StrategyRegime("loss", probability=1.0, win_rate=0.0, rr_ratio=1.0),
        ),
        eval_loss_size=100,
        funded_loss_size=100,
    )

    losses = [strategy.sample_trade(random.Random(i), phase="eval") for i in range(10)]

    assert all(pnl == -100 for pnl in losses)


def test_autocorrelated_strategy_runs_through_monte_carlo_without_state_leakage() -> None:
    strategy = AutocorrelatedPhaseAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        eval_loss_size=750,
        funded_loss_size=200,
        autocorrelation=1.0,
    )

    first = run_monte_carlo(
        strategy,
        firm="lucidflex",
        n_simulations=3,
        seed=10,
        max_eval_days=10,
        max_funded_days=15,
    )
    second = run_monte_carlo(
        strategy,
        firm="lucidflex",
        n_simulations=3,
        seed=10,
        max_eval_days=10,
        max_funded_days=15,
    )

    assert first.mean_net_ev == second.mean_net_ev
    assert first.eval_pass_rate == second.eval_pass_rate
