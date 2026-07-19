"""Apex end-to-end pipeline tests.

Mirrors ``tests/test_lucidflex_pipeline.py`` conventions: deterministic
always-win / always-lose strategies exercise the full eval -> PA -> payout
loop without needing RNG-sensitive assertions.
"""

from __future__ import annotations

from src.pipeline.apex_pipeline import simulate_apex_pipeline
from src.strategies.parametric import BernoulliTradeStrategy


def test_pipeline_losing_strategy_loses_eval_fee_only_eod() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=2_000, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=10, max_funded_days=30, drawdown_variant="eod")

    assert result.terminal_reason == "eval_breach"
    assert result.payout_count == 0
    assert result.trader_payouts == 0
    assert result.net_ev == -197


def test_pipeline_losing_strategy_loses_eval_fee_only_intraday() -> None:
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=2_000, trades_per_day=1)

    result = simulate_apex_pipeline(
        strategy, seed=1, max_eval_days=10, max_funded_days=30, drawdown_variant="intraday"
    )

    assert result.terminal_reason == "eval_breach"
    assert result.net_ev == -131


def test_pipeline_winning_strategy_passes_eval_in_one_trade() -> None:
    # win_rate=1.0 makes every trade +200; eval target 3,000 / 200 = 15
    # trades at 1 trade/day = 15 eval days exactly.
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=200, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=20, max_funded_days=15, drawdown_variant="eod")

    assert result.eval_result.passed
    assert result.eval_days == 15


def test_pipeline_winning_strategy_collects_payout_cycles() -> None:
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=200, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=20, max_funded_days=15, drawdown_variant="eod")

    # Funded phase: 5 qualifying days ($200 each) per payout cycle.
    # 15 funded days = 3 completed payout cycles.
    assert result.funded_days == 15
    assert result.payout_count == 3
    assert result.trader_payouts == 3_000  # cycle 1: 1,000 + cycle 2: 1,000 + cycle 3: 1,000
    assert result.net_ev == 3_000 - 296  # eval fee 197 + PA activation 99


def test_pipeline_funded_timeout_keeps_collected_payouts() -> None:
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=200, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=20, max_funded_days=6, drawdown_variant="eod")

    assert result.terminal_reason == "funded_timeout"
    assert result.payout_count == 1
    assert result.trader_payouts == 1_000
    assert result.net_ev == 1_000 - 296


def test_pipeline_boundary_trade_touches_threshold_exactly() -> None:
    # A single -$2,000 trade touches the eval threshold exactly (48,000)
    # and must breach, matching the ruleset's <=' convention.
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=2_000, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=1, max_funded_days=1, drawdown_variant="eod")

    assert result.eval_result.breached
    assert not result.eval_result.passed


def test_pipeline_intraday_variant_has_no_soft_dll_pause() -> None:
    # Intraday variant should never report a DLL-locked session; a -$1,000
    # day should just continue trading (or breach only at -$2,000).
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=1_000, trades_per_day=2)

    result = simulate_apex_pipeline(
        strategy, seed=1, max_eval_days=1, max_funded_days=1, drawdown_variant="intraday"
    )

    # Two -$1,000 trades in one day = -$2,000, breaching the threshold
    # (48,000) on the second trade since there is no DLL pause to stop it.
    assert result.eval_result.breached


def test_pipeline_180_day_winner_recovers_stranded_cycle_residual() -> None:
    # Regression test for the stranded-profit bug at the pipeline level.
    # +$1,000/day winner over a 180-day funded horizon: cycles 1-6 pay out
    # the capped ladder (13,500 total), stranding 16,500 in balance under
    # the old bug. Cycle 7 is uncapped and must recover the full $16,500
    # residual plus its own $5,000 accrual (21,500), then draining balance
    # back to the starting balance correctly breaches the account against
    # the frozen threshold rather than crashing the pipeline loop.
    strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=1_000, trades_per_day=1)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=10, max_funded_days=180, drawdown_variant="eod")

    assert result.terminal_reason == "funded_breach"
    assert result.payout_count == 7
    assert result.trader_payouts == 35_000  # 13,500 (cycles 1-6) + 21,500 (cycle 7 incl. residual)
    assert result.ending_funded_balance == 50_000
    # net_ev = trader_payouts - (eval fee 197 + PA activation 99)
    assert result.net_ev == 35_000 - 296


def test_pipeline_eod_variant_dll_pause_prevents_same_day_breach() -> None:
    # EOD variant: after the first -$1,000 trade, the soft DLL locks the
    # session, so a second scheduled trade that day never executes and
    # the account survives (does not reach the -$2,000 threshold that day).
    strategy = BernoulliTradeStrategy(win_rate=0.0, rr_ratio=1.0, loss_size=1_000, trades_per_day=2)

    result = simulate_apex_pipeline(strategy, seed=1, max_eval_days=1, max_funded_days=1, drawdown_variant="eod")

    assert not result.eval_result.breached
