from datetime import date, timedelta

import pytest

from src.pipeline.sequential_mc import (
    StoppingConfig,
    _decision_clear,
    sequential_replay_mc,
)
from src.pipeline.monte_carlo import ConfidenceInterval, MonteCarloResult
from src.strategies.replay import ReplayDay


def _mc_result(*, p_low: float, p_high: float, ev_low: float, ev_high: float) -> MonteCarloResult:
    return MonteCarloResult(
        firm="topstep",
        n_simulations=100,
        eval_pass_count=50,
        funded_breach_count=10,
        max_payout_count=5,
        eval_pass_rate=0.5,
        eval_pass_ci=ConfidenceInterval(p_low, p_high),
        funded_breach_rate=0.1,
        funded_breach_ci=ConfidenceInterval(0.05, 0.15),
        funded_breach_after_pass_rate=0.2,
        funded_breach_after_pass_ci=ConfidenceInterval(0.1, 0.3),
        max_payout_rate=0.05,
        max_payout_ci=ConfidenceInterval(0.02, 0.08),
        mean_payouts=1.0,
        mean_trader_payouts=1000.0,
        mean_net_ev=100.0,
        median_net_ev=-95.0,
        ev_stddev=100.0,
        ev_stderr=10.0,
        ev_ci=ConfidenceInterval(ev_low, ev_high),
    )


def test_decision_clear_requires_both_intervals_clear() -> None:
    stopping = StoppingConfig(p_pass_threshold=0.2, ev_threshold_usd=0.0)

    assert _decision_clear(_mc_result(p_low=0.3, p_high=0.4, ev_low=10, ev_high=20), stopping)[0]
    assert _decision_clear(_mc_result(p_low=0.1, p_high=0.3, ev_low=10, ev_high=20), stopping)[0] is False
    assert _decision_clear(_mc_result(p_low=0.3, p_high=0.4, ev_low=-10, ev_high=20), stopping)[0] is False


def test_sequential_replay_mc_stops_at_n_max_when_not_clear() -> None:
    base = date(2026, 1, 5)
    days = [
        ReplayDay.from_values(base + timedelta(days=i), 2.0, -1.0, -1.0)
        for i in range(20)
    ]

    result = sequential_replay_mc(
        days,
        firm="topstep",
        n_init=2,
        n_step=2,
        n_max=4,
        block_size=2,
        seed=1,
        topstep_eval_risk=50.0,
        topstep_funded_risk=50.0,
        eval_cost_per_trade=0.0,
        funded_cost_per_trade=0.0,
        stopping=StoppingConfig(p_pass_threshold=0.5, ev_threshold_usd=0.0),
    )

    assert result.n_run in {2, 4}
    assert result.stopped_reason in {"decision_clear", "n_max"}


def test_sequential_replay_mc_validates_required_topstep_sizing() -> None:
    with pytest.raises(ValueError, match="topstep"):
        sequential_replay_mc([], firm="topstep", n_init=1, n_step=1, n_max=1)
