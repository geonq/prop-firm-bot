"""Apex historical trade replay pipeline tests.

Mirrors the shape used for LucidFlex/TopStep replay tests: deterministic
``ReplayDay`` fixtures exercise eval -> PA -> payouts without RNG. Also
includes a cross-check against the parametric ``simulate_apex_pipeline`` to
guard against the two paths drifting apart.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from src.pipeline.apex_pipeline import simulate_apex_pipeline
from src.pipeline.apex_replay import simulate_apex_trade_replay
from src.sizing.dynamic import BufferAwareSizing, FixedSizing
from src.strategies.parametric import BernoulliTradeStrategy
from src.strategies.replay import ReplayDay


def _daily_days(start: date, r_multiples_per_day: list[tuple[float, ...]]) -> list[ReplayDay]:
    return [
        ReplayDay(session_date=start + timedelta(days=i), r_multiples=r_multiples)
        for i, r_multiples in enumerate(r_multiples_per_day)
    ]


@dataclass
class FixedPnLStrategy:
    """Deterministic fixture: plays back a fixed per-trade P&L list in order.

    Test-only helper (intentionally NOT added to src/strategies/) so the
    parametric ``simulate_apex_pipeline`` can be driven by the exact same
    dollar P&L sequence as a ``ReplayDay`` list fed to
    ``simulate_apex_trade_replay``. ``trades_per_day`` must match the
    replay side's per-day trade count for the two paths to consume ``pnls``
    in lockstep — both pipelines call ``sample_trade`` at most
    ``trades_per_day`` times per day and break early on breach / phase
    transition / soft-DLL lock, so a day that ends early on one path must
    also end early (with the same trade count) on the other, or the flat
    index will drift out of sync.
    """

    pnls: list[float]
    trades_per_day: int = 1
    _index: int = field(default=0, init=False, repr=False)

    def sample_trade(self, rng: random.Random) -> float:
        value = self.pnls[self._index]
        self._index += 1
        return value


class TestApexReplayAlwaysWin:
    def test_always_win_passes_eval_and_collects_capped_payouts(self) -> None:
        # R=1.0 every day, risk raised to $2,000/trade so cycle-1 gross
        # accrual ($10,000 over 5 qualifying days) actually exceeds the
        # $1,500 cycle-1 cap and the cap binds (at $1,000/trade the old
        # version of this test never triggered the cap at all).
        days = _daily_days(date(2026, 1, 1), [(1.0,)] * 30)

        result = simulate_apex_trade_replay(
            days, eval_risk=2_000, funded_risk=2_000, drawdown_variant="eod", max_eval_days=10, max_funded_days=25
        )

        assert result.eval_result.passed
        assert result.eval_days == 2  # 3,000 / 2,000 -> 2 winning days to pass
        # 5 full payout cycles complete within the 25-day funded horizon,
        # each capped at the cycle-1..5 ladder (1,500/1,800/2,100/2,400/2,700
        # = 10,500 total) rather than the raw $10,000/cycle gross accrual --
        # this is the assertion that actually proves the cap bound.
        assert result.payout_count == 5
        assert result.trader_payouts == 10_500
        assert result.net_ev == 10_500 - 296  # eval fee 197 + PA activation 99

    def test_always_lose_breaches_eval_losing_only_the_fee(self) -> None:
        # R=-1.0 with risk 2,000 -> single trade touches the eval threshold
        # exactly (48,000), breaching immediately; only the eval fee is lost.
        days = _daily_days(date(2026, 1, 1), [(-1.0,)] * 5)

        result = simulate_apex_trade_replay(
            days, eval_risk=2_000, funded_risk=2_000, drawdown_variant="eod", max_eval_days=5
        )

        assert result.terminal_reason == "eval_breach"
        assert result.eval_result.breached
        assert result.payout_count == 0
        assert result.trader_payouts == 0
        assert result.net_ev == -197  # EOD eval fee only


class TestApexReplayEodSoftDll:
    def test_soft_dll_pauses_mid_day_and_skips_remaining_trades(self) -> None:
        # Day 1: three -$500 trades at risk sizing that makes each trade
        # -$500. After two trades, cumulative day P&L is -$1,000, which
        # trips the EOD soft DLL and must skip the third trade entirely.
        # Day 2 resumes normally.
        days = [
            ReplayDay(session_date=date(2026, 1, 1), r_multiples=(-1.0, -1.0, -1.0)),
            ReplayDay(session_date=date(2026, 1, 2), r_multiples=(0.2,)),
        ]

        result = simulate_apex_trade_replay(
            days, eval_risk=500, funded_risk=500, drawdown_variant="eod", max_eval_days=5
        )

        # Day 1 ends at 50,000 - 500 - 500 = 49,000 (third trade skipped,
        # so it does NOT reach 48,500). Day 2 adds +100 (0.2 * 500).
        assert result.eval_result.ending_balance == 49_100
        assert result.eval_days == 2
        assert not result.eval_result.breached

    def test_soft_dll_lock_does_not_persist_into_next_day(self) -> None:
        # If the DLL lock leaked into day 2, the day-2 winning trade would
        # never execute and balance would stay flat at day 1's close.
        days = [
            ReplayDay(session_date=date(2026, 1, 1), r_multiples=(-1.0, -1.0, -1.0)),
            ReplayDay(session_date=date(2026, 1, 2), r_multiples=(0.2,)),
        ]

        result = simulate_apex_trade_replay(
            days, eval_risk=500, funded_risk=500, drawdown_variant="eod", max_eval_days=5
        )

        assert result.eval_result.ending_balance != 49_000  # would be flat if DLL leaked


class TestApexReplayDrawdownVariantDivergence:
    def test_intraday_ratchet_breaches_where_eod_survives_same_trade_stream(self) -> None:
        # Same single-day trade stream (+$1,000 then -$2,000), fed through
        # both variants. EOD: threshold stays static at 48,000 all day (only
        # moves at close) -> balance 49,000 survives. Intraday: threshold
        # ratchets to 49,000 immediately after the +$1,000 peak -> the
        # -$2,000 trade drops balance to exactly 49,000, touching the
        # ratcheted threshold and breaching.
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(1.0, -2.0))]

        eod_result = simulate_apex_trade_replay(
            days, eval_risk=1_000, funded_risk=1_000, drawdown_variant="eod", max_eval_days=5
        )
        intraday_result = simulate_apex_trade_replay(
            days, eval_risk=1_000, funded_risk=1_000, drawdown_variant="intraday", max_eval_days=5
        )

        assert not eod_result.eval_result.breached
        assert intraday_result.eval_result.breached
        assert eod_result.eval_result.ending_balance == intraday_result.eval_result.ending_balance == 49_000


class TestApexReplayBoundary:
    def test_exact_threshold_touch_breaches(self) -> None:
        # Single -$2,000 trade touches the eval threshold (48,000) exactly.
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(-2.0,))]

        result = simulate_apex_trade_replay(
            days, eval_risk=1_000, funded_risk=1_000, drawdown_variant="eod", max_eval_days=5
        )

        assert result.eval_result.breached
        assert result.eval_result.ending_balance == 48_000

    def test_one_dollar_above_threshold_survives(self) -> None:
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(-1.999,))]

        result = simulate_apex_trade_replay(
            days, eval_risk=1_000, funded_risk=1_000, drawdown_variant="eod", max_eval_days=5
        )

        assert not result.eval_result.breached


class TestApexReplayInputValidation:
    def test_unsorted_replay_days_raises(self) -> None:
        days = [
            ReplayDay(session_date=date(2026, 1, 2), r_multiples=(1.0,)),
            ReplayDay(session_date=date(2026, 1, 1), r_multiples=(1.0,)),
        ]
        with pytest.raises(ValueError):
            simulate_apex_trade_replay(days, eval_risk=1_000, funded_risk=1_000)

    def test_non_positive_risk_raises(self) -> None:
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(1.0,))]
        with pytest.raises(ValueError):
            simulate_apex_trade_replay(days, eval_risk=0, funded_risk=1_000)
        with pytest.raises(ValueError):
            simulate_apex_trade_replay(days, eval_risk=1_000, funded_risk=-1)


class TestApexReplayDynamicSizing:
    def test_rejects_sizing_fn_and_fixed_risk_together(self) -> None:
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(1.0,))]
        with pytest.raises(ValueError, match="either sizing_fn or eval_risk/funded_risk"):
            simulate_apex_trade_replay(
                days,
                sizing_fn=FixedSizing(eval_size=1_000, funded_size=1_000),
                eval_risk=1_000,
                funded_risk=1_000,
            )

    def test_rejects_neither_sizing_fn_nor_fixed_risk(self) -> None:
        days = [ReplayDay(session_date=date(2026, 1, 1), r_multiples=(1.0,))]
        with pytest.raises(ValueError, match="required when sizing_fn is omitted"):
            simulate_apex_trade_replay(days)

    def test_sizing_fn_equivalent_to_fixed_risk_is_bit_identical(self) -> None:
        days = _daily_days(date(2026, 1, 1), [(1.0,)] * 30)

        fixed = simulate_apex_trade_replay(
            days,
            eval_risk=2_000,
            funded_risk=2_000,
            drawdown_variant="eod",
            max_eval_days=10,
            max_funded_days=25,
        )
        via_sizing_fn = simulate_apex_trade_replay(
            days,
            sizing_fn=FixedSizing(eval_size=2_000, funded_size=2_000),
            drawdown_variant="eod",
            max_eval_days=10,
            max_funded_days=25,
        )

        assert via_sizing_fn == fixed

    def test_buffer_aware_sizing_shrinks_near_threshold(self) -> None:
        # Default Apex50K starts with buffer_fraction exactly at
        # BufferAwareSizing's full_buffer_fraction (0.04, i.e. the $2,000
        # trailing-drawdown buffer over the $50,000 account size), so the
        # first losing day is sized at full base risk ($1,000). Each
        # subsequent losing day shrinks the buffer further, so the
        # per-trade dollar loss should shrink monotonically as the balance
        # approaches the threshold.
        sizing_fn = BufferAwareSizing(eval_base=1_000, funded_base=1_000)
        days = [
            ReplayDay(date(2026, 1, 1), (-1.0,)),
            ReplayDay(date(2026, 1, 2), (-1.0,)),
            ReplayDay(date(2026, 1, 3), (-1.0,)),
        ]

        result = simulate_apex_trade_replay(
            days,
            sizing_fn=sizing_fn,
            drawdown_variant="eod",
            max_eval_days=3,
            max_funded_days=1,
        )

        assert result.eval_days == 3
        assert result.terminal_reason == "eval_breach"
        day1_loss = 1_000.0  # full base risk, buffer_fraction == full_buffer_fraction
        day2_loss = 50_000.0 - day1_loss - 48_375.0  # balance after day 2 close
        day3_loss = abs(result.eval_result.largest_day_profit)
        assert day2_loss == pytest.approx(625.0)
        assert day3_loss == pytest.approx(390.625)
        assert day1_loss > day2_loss > day3_loss


def _assert_pipeline_results_match(replay_result, param_result) -> None:
    assert replay_result.terminal_reason == param_result.terminal_reason
    assert replay_result.eval_result.passed == param_result.eval_result.passed
    assert replay_result.eval_days == param_result.eval_days
    assert replay_result.funded_days == param_result.funded_days
    assert replay_result.payout_count == param_result.payout_count
    assert replay_result.trader_payouts == param_result.trader_payouts
    assert replay_result.net_ev == param_result.net_ev
    assert replay_result.ending_funded_balance == param_result.ending_funded_balance


class TestApexReplayParametricCrossCheck:
    def test_replay_matches_parametric_pipeline_happy_path(self) -> None:
        # Baseline agreement check on an all-win stream. This alone is
        # insufficient to guard against drift in the DLL / near-threshold /
        # payout-cap / breach branches -- see the mixed-trajectory test
        # below for those.
        strategy = BernoulliTradeStrategy(win_rate=1.0, rr_ratio=1.0, loss_size=200, trades_per_day=1)
        param_result = simulate_apex_pipeline(
            strategy, seed=1, max_eval_days=20, max_funded_days=15, drawdown_variant="eod"
        )

        # Equivalent replay: +$200/trade every day (R=1.0 at risk=$200),
        # same day-count horizons as the parametric run.
        days = _daily_days(date(2026, 1, 1), [(1.0,)] * 35)
        replay_result = simulate_apex_trade_replay(
            days, eval_risk=200, funded_risk=200, drawdown_variant="eod", max_eval_days=20, max_funded_days=15
        )

        _assert_pipeline_results_match(replay_result, param_result)

    def test_replay_matches_parametric_pipeline_on_mixed_trajectory_covering_dll_threshold_cap_and_breach(
        self,
    ) -> None:
        # Strongest guard against the two paths drifting: a single
        # deterministic mixed win/loss dollar-P&L sequence, fed identically
        # to both the parametric pipeline (via FixedPnLStrategy) and the
        # replay path (via matching ReplayDay tuples), engineered to hit
        # every divergence-prone branch in one trajectory:
        #
        #   Eval day 1  (3 trades, +1000 each): profit target (3,000) is
        #     reached exactly on the 3rd trade -- PA activates mid-day.
        #   Funded day 1 (-500, -500, [skipped]): cumulative day loss hits
        #     -1,000 after trade 2, tripping the EOD soft DLL. The 3rd
        #     scheduled trade of the day must be SKIPPED by both loops
        #     (daily_locked breaks the per-day trade loop in both
        #     apex_pipeline.py and apex_replay.py).
        #   Funded day 2 (-999, 0, 0): drops balance to exactly 48,001 --
        #     one dollar above the still-static EOD threshold (48,000,
        #     which has not moved yet because it only updates at day
        #     close) -- a near-threshold survival day, no breach.
        #   Funded days 3-7 (1000, 0, 0 each x5): five qualifying
        #     (>=$150) days accrue cycle profit of $3,001 gross -- above
        #     the $1,500 cycle-1 cap, forcing a capped payout with $1,501
        #     of residual profit rolling forward in balance rather than
        #     being paid out.
        #   Funded day 8 (-2000, [skipped], [skipped]): a single large
        #     loss after the payout pulls balance to/below the
        #     now-elevated threshold (50,100, locked via the safety net
        #     reached during days 3-7) -- a funded PA breach terminal.
        #
        # trades_per_day=3 is fixed on the parametric side; days that
        # naturally consume fewer than 3 trades (DLL trip, breach) do so
        # identically on both paths because both loops break on the same
        # conditions (BREACHED_PA / PA transition / daily_locked) after
        # the same number of calls -- so the flat FixedPnLStrategy index
        # and the replay's per-day r_multiples tuples stay in lockstep.
        flat_pnls = [
            1000, 1000, 1000,  # eval day 1 -- PA activates on trade 3
            -500, -500,  # funded day 1 -- DLL trips after trade 2, trade 3 skipped
            -999, 0, 0,  # funded day 2 -- near-threshold survival (48,001)
            1000, 0, 0,  # funded day 3
            1000, 0, 0,  # funded day 4
            1000, 0, 0,  # funded day 5
            1000, 0, 0,  # funded day 6
            1000, 0, 0,  # funded day 7 -- cycle profit 3,001 > 1,500 cap
            -2000,  # funded day 8 -- breach, trades 2-3 skipped
        ]
        strategy = FixedPnLStrategy(pnls=list(flat_pnls), trades_per_day=3)
        param_result = simulate_apex_pipeline(
            strategy, seed=1, max_eval_days=5, max_funded_days=10, drawdown_variant="eod"
        )

        replay_days = [
            ReplayDay(date(2026, 1, 1), (1000.0, 1000.0, 1000.0)),  # eval day 1
            ReplayDay(date(2026, 1, 2), (-500.0, -500.0)),  # funded day 1, DLL trip
            ReplayDay(date(2026, 1, 3), (-999.0, 0.0, 0.0)),  # funded day 2
            ReplayDay(date(2026, 1, 4), (1000.0, 0.0, 0.0)),  # funded day 3
            ReplayDay(date(2026, 1, 5), (1000.0, 0.0, 0.0)),  # funded day 4
            ReplayDay(date(2026, 1, 6), (1000.0, 0.0, 0.0)),  # funded day 5
            ReplayDay(date(2026, 1, 7), (1000.0, 0.0, 0.0)),  # funded day 6
            ReplayDay(date(2026, 1, 8), (1000.0, 0.0, 0.0)),  # funded day 7, cap trips
            ReplayDay(date(2026, 1, 9), (-2000.0,)),  # funded day 8, breach
        ]
        # eval_risk = funded_risk = 1.0 so each r_multiple IS the dollar
        # P&L directly, matching flat_pnls exactly.
        replay_result = simulate_apex_trade_replay(
            replay_days, eval_risk=1.0, funded_risk=1.0, drawdown_variant="eod", max_eval_days=5, max_funded_days=10
        )

        # Pin down the actual trajectory numbers (traced independently via
        # direct ApexAccountState calls before writing this test) so a
        # regression shows up as a concrete wrong number, not just an
        # equality mismatch between two possibly-equally-wrong paths.
        assert param_result.terminal_reason == "funded_breach"
        assert param_result.eval_days == 1
        assert param_result.funded_days == 8
        assert param_result.payout_count == 1
        assert param_result.trader_payouts == 1_500  # capped, not the raw 3,001 cycle profit
        assert param_result.net_ev == 1_500 - 296  # eval fee 197 + PA activation 99
        assert param_result.ending_funded_balance == 49_501

        _assert_pipeline_results_match(replay_result, param_result)
