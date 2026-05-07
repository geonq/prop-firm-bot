import pytest

from src.pipeline.simulator import SimulationConfig, simulate_many, simulate_one
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.strategies.parametric import BernoulliTradeStrategy, PhaseAwareBernoulliStrategy


def test_simulate_one_routes_lucidflex_pipeline() -> None:
    strategy = BernoulliTradeStrategy(
        win_rate=0.0,
        rr_ratio=1.0,
        loss_size=500,
        trades_per_day=1,
    )

    result = simulate_one(
        strategy,
        SimulationConfig(firm="lucidflex", max_eval_days=10),
        seed=1,
    )

    assert result.terminal_reason == "eval_breach"
    assert result.net_ev == -98


def test_simulate_one_routes_topstep_pipeline_with_options() -> None:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        eval_loss_size=1_500,
        funded_loss_size=200,
        trades_per_day=1,
    )

    result = simulate_one(
        strategy,
        SimulationConfig(
            firm="topstep",
            topstep_payout_path=TopStepPayoutPath.CONSISTENCY,
            max_eval_days=10,
            max_funded_days=30,
            payout_cap=1,
        ),
        seed=1,
    )

    assert result.terminal_reason == "payout_cap"
    assert result.eval_passed
    assert result.payout_count == 1


def test_simulate_many_uses_same_config_for_monte_carlo() -> None:
    strategy = BernoulliTradeStrategy(
        win_rate=0.0,
        rr_ratio=1.0,
        loss_size=500,
        trades_per_day=1,
    )

    result = simulate_many(
        strategy,
        SimulationConfig(firm="lucidflex", max_eval_days=10),
        n_simulations=3,
        seed=1,
    )

    assert result.firm == "lucidflex"
    assert result.n_simulations == 3
    assert result.mean_net_ev == -98


def test_simulator_rejects_cross_firm_config() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500)

    with pytest.raises(ValueError, match="topstep_ruleset"):
        simulate_one(
            strategy,
            SimulationConfig(firm="lucidflex", topstep_ruleset=TopStepNoFee50K()),
        )

    with pytest.raises(ValueError, match="lucidflex_ruleset"):
        simulate_one(
            strategy,
            SimulationConfig(firm="topstep", lucidflex_ruleset=LucidFlex50K()),
        )


def test_simulator_rejects_lucidflex_topstep_only_options() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500)

    with pytest.raises(ValueError, match="topstep_payout_path"):
        simulate_one(
            strategy,
            SimulationConfig(
                firm="lucidflex",
                topstep_payout_path=TopStepPayoutPath.CONSISTENCY,
            ),
        )

    with pytest.raises(ValueError, match="payout_cap"):
        simulate_one(
            strategy,
            SimulationConfig(firm="lucidflex", payout_cap=1),
        )
