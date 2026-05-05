import pytest

from src.pipeline.monte_carlo import run_monte_carlo, run_parametric_grid, summarize_pipeline_results
from src.strategies.parametric import BernoulliTradeStrategy, PhaseAwareBernoulliStrategy


def test_lucidflex_monte_carlo_losing_strategy_loses_eval_fee() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500, trades_per_day=1)

    result = run_monte_carlo(
        strategy,
        firm="lucidflex",
        n_simulations=5,
        seed=1,
        max_eval_days=10,
        max_funded_days=20,
    )

    assert result.eval_pass_rate == 0
    assert result.funded_breach_rate == 0
    assert result.mean_net_ev == -98
    assert result.ev_stderr == 0
    assert result.ev_ci.low == -98
    assert result.ev_ci.high == -98


def test_topstep_monte_carlo_winning_strategy_hits_payout_cap() -> None:
    strategy = PhaseAwareBernoulliStrategy(
        win_rate=1.0,
        rr_ratio=1.0,
        eval_loss_size=1_500,
        funded_loss_size=200,
    )

    result = run_monte_carlo(
        strategy,
        firm="topstep",
        n_simulations=4,
        seed=1,
        max_eval_days=10,
        max_funded_days=30,
        payout_cap=2,
    )

    assert result.eval_pass_rate == 1
    assert result.max_payout_rate == 1
    assert result.mean_net_ev == 1_030
    assert result.eval_pass_ci.low > 0
    assert result.eval_pass_ci.high == 1


def test_parametric_grid_returns_shared_metrics_for_both_firms() -> None:
    luci, top = (
        run_parametric_grid(
            firm=firm,
            profiles=((1.0, 1.0),),
            eval_risks=(1_500.0,),
            funded_risks=(200.0,),
            n_simulations=3,
            max_eval_days=10,
            max_funded_days=30,
            payout_cap=2,
        )[0]
        for firm in ("lucidflex", "topstep")
    )

    assert luci.firm == "lucidflex"
    assert top.firm == "topstep"
    assert luci.eval_pass_rate == 1
    assert top.eval_pass_rate == 1
    assert luci.ev_ci.low <= luci.mean_net_ev <= luci.ev_ci.high
    assert top.ev_ci.low <= top.mean_net_ev <= top.ev_ci.high


def test_summarize_rejects_empty_results() -> None:
    with pytest.raises(ValueError, match="results"):
        summarize_pipeline_results([], firm="lucidflex")
