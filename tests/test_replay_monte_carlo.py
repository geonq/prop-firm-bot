import random
from datetime import date, timedelta

import pytest

from src.pipeline.replay_monte_carlo import (
    block_bootstrap_replay_days,
    run_replay_monte_carlo,
)
from src.strategies.replay import ReplayDay


def _winning_replay_days(n: int, trades_per_day: int = 3, r_win: float = 2.0) -> list[ReplayDay]:
    base = date(2026, 1, 5)
    return [
        ReplayDay.from_values(base + timedelta(days=i), *([r_win] * trades_per_day))
        for i in range(n)
    ]


def _losing_replay_days(n: int, trades_per_day: int = 3) -> list[ReplayDay]:
    base = date(2026, 1, 5)
    return [
        ReplayDay.from_values(base + timedelta(days=i), *([-1.0] * trades_per_day))
        for i in range(n)
    ]


def test_block_bootstrap_returns_target_length() -> None:
    days = _winning_replay_days(20)
    sampled = block_bootstrap_replay_days(
        days, target_length=20, block_size=5, rng=random.Random(0)
    )

    assert len(sampled) == 20
    assert all(isinstance(d, ReplayDay) for d in sampled)


def test_block_bootstrap_is_deterministic_for_same_seed() -> None:
    days = _winning_replay_days(15)
    sampled_a = block_bootstrap_replay_days(days, target_length=15, block_size=3, rng=random.Random(7))
    sampled_b = block_bootstrap_replay_days(days, target_length=15, block_size=3, rng=random.Random(7))

    assert sampled_a == sampled_b


def test_block_bootstrap_block_size_one_yields_iid_resample() -> None:
    days = _winning_replay_days(10)
    sampled = block_bootstrap_replay_days(
        days, target_length=10, block_size=1, rng=random.Random(0), restamp_dates=False
    )

    assert len(sampled) == 10
    sources = {d.session_date for d in sampled}
    assert sources.issubset({d.session_date for d in days})


def test_block_bootstrap_restamps_dates_to_ascending_by_default() -> None:
    days = _winning_replay_days(10)
    sampled = block_bootstrap_replay_days(
        days, target_length=10, block_size=3, rng=random.Random(0)
    )
    dates = [d.session_date for d in sampled]

    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


def test_block_bootstrap_block_size_larger_than_source_clamps() -> None:
    days = _winning_replay_days(4)
    sampled = block_bootstrap_replay_days(
        days, target_length=4, block_size=10, rng=random.Random(0), restamp_dates=False
    )

    assert len(sampled) == 4
    assert sampled == tuple(days)


def test_block_bootstrap_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        block_bootstrap_replay_days([], target_length=5, block_size=2, rng=random.Random(0))


def test_block_bootstrap_rejects_nonpositive_target_length() -> None:
    days = _winning_replay_days(5)
    with pytest.raises(ValueError, match="target_length"):
        block_bootstrap_replay_days(days, target_length=0, block_size=2, rng=random.Random(0))


def test_block_bootstrap_rejects_nonpositive_block_size() -> None:
    days = _winning_replay_days(5)
    with pytest.raises(ValueError, match="block_size"):
        block_bootstrap_replay_days(days, target_length=5, block_size=0, rng=random.Random(0))


def test_run_replay_monte_carlo_topstep_winning_history_hits_payout_cap() -> None:
    days = _winning_replay_days(120, trades_per_day=3, r_win=2.0)

    result = run_replay_monte_carlo(
        days,
        firm="topstep",
        n_simulations=5,
        seed=1,
        block_size=5,
        topstep_eval_risk=200.0,
        topstep_funded_risk=200.0,
        max_combine_days=30,
        max_xfa_days=60,
        payout_cap=2,
    )

    assert result.firm == "topstep"
    assert result.n_simulations == 5
    assert result.eval_pass_rate == 1.0
    assert result.max_payout_rate == 1.0
    assert result.mean_net_ev > 0


def test_run_replay_monte_carlo_topstep_losing_history_breaches_combine() -> None:
    days = _losing_replay_days(60)

    result = run_replay_monte_carlo(
        days,
        firm="topstep",
        n_simulations=4,
        seed=1,
        block_size=5,
        topstep_eval_risk=200.0,
        topstep_funded_risk=200.0,
        max_combine_days=20,
        max_xfa_days=40,
    )

    assert result.eval_pass_rate == 0.0
    assert result.max_payout_rate == 0.0
    assert result.mean_net_ev <= 0


def test_run_replay_monte_carlo_lucidflex_requires_risk_amounts() -> None:
    days = _winning_replay_days(20)

    with pytest.raises(ValueError, match="lucidflex_eval_risk"):
        run_replay_monte_carlo(days, firm="lucidflex", n_simulations=2, seed=0)


def test_run_replay_monte_carlo_is_deterministic_for_same_seed() -> None:
    days = _winning_replay_days(40, trades_per_day=2, r_win=1.5)

    a = run_replay_monte_carlo(
        days,
        firm="topstep",
        n_simulations=6,
        seed=42,
        block_size=4,
        topstep_eval_risk=200.0,
        topstep_funded_risk=200.0,
        max_combine_days=20,
        max_xfa_days=40,
        payout_cap=2,
    )
    b = run_replay_monte_carlo(
        days,
        firm="topstep",
        n_simulations=6,
        seed=42,
        block_size=4,
        topstep_eval_risk=200.0,
        topstep_funded_risk=200.0,
        max_combine_days=20,
        max_xfa_days=40,
        payout_cap=2,
    )

    assert a.mean_net_ev == b.mean_net_ev
    assert a.eval_pass_rate == b.eval_pass_rate
    assert a.funded_breach_rate == b.funded_breach_rate


def test_run_replay_monte_carlo_rejects_unknown_firm() -> None:
    days = _winning_replay_days(10)
    with pytest.raises(ValueError, match="unknown firm"):
        run_replay_monte_carlo(days, firm="bogus", n_simulations=2, seed=0)  # type: ignore[arg-type]
