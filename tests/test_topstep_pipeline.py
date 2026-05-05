from src.pipeline.topstep_pipeline import simulate_topstep_pipeline
from src.sizing.dynamic import FixedSizing
from src.strategies.parametric import (
    BernoulliTradeStrategy,
    PhaseAwareBernoulliStrategy,
    StateAwareBernoulliStrategy,
)


def test_topstep_pipeline_losing_strategy_fails_combine() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500, trades_per_day=1)

    result = simulate_topstep_pipeline(strategy, seed=1, max_combine_days=10, max_xfa_days=30)

    assert result.terminal_reason == "combine_breach"
    assert not result.eval_passed
    assert result.payout_count == 0
    assert result.trader_payouts == 0
    assert result.net_ev == -95


def test_topstep_pipeline_winning_strategy_reaches_simulation_payout_cap() -> None:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        eval_loss_size=1_500,
        funded_loss_size=200,
        trades_per_day=1,
    )

    result = simulate_topstep_pipeline(
        strategy,
        seed=1,
        max_combine_days=10,
        max_xfa_days=30,
        payout_cap=2,
    )

    assert result.terminal_reason == "payout_cap"
    assert result.eval_passed
    assert result.combine_days == 2
    assert result.xfa_days == 10
    assert result.payout_count == 2
    assert result.gross_payouts == 1_250
    assert result.trader_payouts == 1_125
    assert result.net_ev == 1_030
    assert result.ending_xfa_balance == 750


def test_topstep_pipeline_xfa_timeout_keeps_collected_payouts() -> None:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        eval_loss_size=1_500,
        funded_loss_size=200,
        trades_per_day=1,
    )

    result = simulate_topstep_pipeline(
        strategy,
        seed=1,
        max_combine_days=10,
        max_xfa_days=6,
    )

    assert result.terminal_reason == "xfa_timeout"
    assert result.payout_count == 1
    assert result.trader_payouts == 450
    assert result.net_ev == 355
    assert result.ending_xfa_balance == 700


def test_topstep_pipeline_state_aware_strategy_runs_through_xfa() -> None:
    strategy = StateAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        sizing_fn=FixedSizing(eval_size=1_500, funded_size=200),
        trades_per_day=1,
    )

    result = simulate_topstep_pipeline(
        strategy,
        seed=1,
        max_combine_days=10,
        max_xfa_days=6,
    )

    assert result.eval_passed
    assert result.payout_count == 1
    assert result.terminal_reason == "xfa_timeout"


def test_topstep_pipeline_can_use_back2funded_before_first_payout() -> None:
    class ScriptedStrategy:
        trades_per_day = 1

        def __init__(self) -> None:
            self._pnls = iter([1_500, 1_500, -2_000, -2_000])

        def sample_trade(self, rng) -> float:
            return next(self._pnls)

    result = simulate_topstep_pipeline(
        ScriptedStrategy(),
        seed=1,
        max_combine_days=10,
        max_xfa_days=3,
        max_back2funded_reactivations=1,
    )

    assert result.eval_passed
    assert result.back2funded_count == 1
    assert result.terminal_reason == "xfa_closed"
    assert result.net_ev == -694
