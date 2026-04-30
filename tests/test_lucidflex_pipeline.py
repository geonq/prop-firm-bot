from src.pipeline.lucidflex_pipeline import simulate_lucidflex_pipeline
from src.strategies.parametric import BernoulliTradeStrategy


def test_pipeline_losing_strategy_loses_eval_fee_only() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=500, trades_per_day=1)

    result = simulate_lucidflex_pipeline(strategy, seed=1, max_eval_days=10, max_funded_days=30)

    assert result.terminal_reason == "eval_breach"
    assert result.payout_count == 0
    assert result.trader_payouts == 0
    assert result.net_ev == -175


def test_pipeline_winning_strategy_reaches_max_simulated_payouts() -> None:
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=750, trades_per_day=1)

    result = simulate_lucidflex_pipeline(strategy, seed=1, max_eval_days=10, max_funded_days=40)

    assert result.terminal_reason == "max_payouts"
    assert result.eval_days == 4
    assert result.funded_days == 25
    assert result.payout_count == 5
    assert result.gross_payouts == 9_875
    assert result.trader_payouts == 8_887.5
    assert result.net_ev == 8_712.5


def test_pipeline_funded_timeout_keeps_collected_payouts() -> None:
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=750, trades_per_day=1)

    result = simulate_lucidflex_pipeline(strategy, seed=1, max_eval_days=10, max_funded_days=6)

    assert result.terminal_reason == "funded_timeout"
    assert result.payout_count == 1
    assert result.trader_payouts == 1_687.5
    assert result.net_ev == 1_512.5
