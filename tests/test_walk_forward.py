"""Unit tests for src/optimizer/walk_forward.py.

Uses synthetic bars/trades throughout (no real parquet dependency) so this
suite runs fast and does not accidentally touch the holdout window.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.orb import ORBParams, Trade
from src.optimizer.walk_forward import (
    EVAL_FEE_BY_FIRM,
    HOLDOUT_START,
    REPLAY_FIRMS,
    CandidateResult,
    FirmReplaySummary,
    FoldOOSResult,
    FoldSpec,
    _trades_in_window,
    evaluate_holdout,
    make_folds,
    params_hash,
    rank_plateau,
)
from src.rules.apex import Apex50K
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K

LUCIDFLEX_EVAL_FEE = EVAL_FEE_BY_FIRM["lucidflex"]
TOPSTEP_EVAL_FEE = EVAL_FEE_BY_FIRM["topstep"]
APEX_EOD_EVAL_FEE = EVAL_FEE_BY_FIRM["apex_eod"]
APEX_INTRADAY_EVAL_FEE = EVAL_FEE_BY_FIRM["apex_intraday"]


# ---------------------------------------------------------------------------
# make_folds: boundary correctness
# ---------------------------------------------------------------------------


def test_make_folds_never_touches_holdout() -> None:
    folds = make_folds("2020-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    assert folds, "expected at least one fold"
    for f in folds:
        assert f.oos_end <= pd.Timestamp(HOLDOUT_START)


def test_make_folds_oos_windows_non_overlapping_with_is() -> None:
    folds = make_folds("2020-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    for f in folds:
        assert f.is_end == f.oos_start  # contiguous, non-overlapping by construction
        assert f.oos_start >= f.is_end


def test_make_folds_exact_boundaries_fold0() -> None:
    folds = make_folds("2020-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6, warmup_months=3)
    f0 = folds[0]
    assert f0.is_start == pd.Timestamp("2020-01-01")
    assert f0.is_end == pd.Timestamp("2021-07-01")
    assert f0.oos_start == pd.Timestamp("2021-07-01")
    assert f0.oos_end == pd.Timestamp("2022-01-01")
    # warmup clipped to start since is_start - 3m < start
    assert f0.warmup_start == pd.Timestamp("2020-01-01")


def test_make_folds_rolls_forward_by_step_months() -> None:
    folds = make_folds("2020-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    assert folds[1].is_start == folds[0].is_start + pd.DateOffset(months=6)


def test_fold_spec_rejects_invalid_ordering() -> None:
    with pytest.raises(ValueError):
        FoldSpec(
            fold_index=0,
            warmup_start=pd.Timestamp("2020-06-01"),
            is_start=pd.Timestamp("2020-01-01"),  # before warmup_start -> invalid
            is_end=pd.Timestamp("2020-07-01"),
            oos_start=pd.Timestamp("2020-07-01"),
            oos_end=pd.Timestamp("2021-01-01"),
        )


def test_make_folds_empty_when_holdout_before_first_oos() -> None:
    folds = make_folds(
        "2020-01-01", "2020-06-01", is_months=18, oos_months=6, step_months=6, holdout_start="2020-06-01"
    )
    assert folds == []


# ---------------------------------------------------------------------------
# warm-up trade exclusion
# ---------------------------------------------------------------------------


def _trade(d: date, r: float = 1.0) -> Trade:
    ts = pd.Timestamp(d).tz_localize("UTC")
    return Trade(
        session_date=d,
        direction="long",
        entry_ts=ts,
        entry_price=100.0,
        exit_ts=ts,
        exit_price=101.0,
        r_multiple=r,
        pnl_points=1.0,
        pnl_usd_per_contract=20.0,
    )


def test_trades_in_window_excludes_warmup_trades() -> None:
    trades = [
        _trade(date(2020, 1, 1)),  # before window -> warm-up, excluded
        _trade(date(2020, 4, 1)),  # inside window
        _trade(date(2020, 6, 30)),  # inside window (end exclusive boundary check below)
        _trade(date(2020, 7, 1)),  # exactly at window end -> excluded (half-open)
    ]
    windowed = _trades_in_window(trades, pd.Timestamp("2020-04-01"), pd.Timestamp("2020-07-01"))
    dates = {t.session_date for t in windowed}
    assert dates == {date(2020, 4, 1), date(2020, 6, 30)}


def test_trades_in_window_empty_when_all_outside() -> None:
    trades = [_trade(date(2020, 1, 1)), _trade(date(2020, 1, 2))]
    windowed = _trades_in_window(trades, pd.Timestamp("2021, 1, 1"), pd.Timestamp("2021-06-01"))
    assert windowed == []


# ---------------------------------------------------------------------------
# admissibility rule
# ---------------------------------------------------------------------------


def _candidate(
    *,
    total_trades_per_fold: int,
    lucidflex_ci_lows: list[float] | None,
    lucidflex_means: list[float] | None,
    params: ORBParams | None = None,
    firm: str = "lucidflex",
) -> CandidateResult:
    """Build a synthetic CandidateResult with one firm's fold summaries populated.

    `firm` defaults to "lucidflex" for the existing admissibility tests, but
    accepts any ReplayFirmName (including "apex_eod"/"apex_intraday") so the
    same helper covers apex-variant admissibility without a parallel fixture.
    """
    fold_results = []
    for i, (ci_low, mean) in enumerate(
        zip(
            lucidflex_ci_lows or [None] * 3,
            lucidflex_means or [None] * 3,
        )
    ):
        summaries = {}
        if ci_low is not None:
            summaries[firm] = FirmReplaySummary(
                firm=firm,
                net_ev_mean=mean,
                net_ev_ci_low=ci_low,
                eval_pass_rate=0.5,
                mean_payouts=1.0,
                mean_trader_payouts=1.0,
            )
        fold_results.append(
            FoldOOSResult(
                fold_index=i,
                trade_count=total_trades_per_fold,
                win_rate=0.45,
                mean_r=0.1,
                total_r=total_trades_per_fold * 0.1,
                firm_summaries=summaries,
            )
        )
    return CandidateResult(
        params=params or ORBParams(),
        is_prop_ev_rank_score=1.0,
        fold_results=tuple(fold_results),
    )


def test_admissible_when_all_clauses_pass() -> None:
    c = _candidate(
        total_trades_per_fold=60,  # 3 folds * 60 = 180 >= 150
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
    )
    assert c.is_admissible()
    assert "lucidflex" in c.admissible_firms()


def test_candidate_result_records_risk_per_trade_usd_default() -> None:
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
    )
    assert c.risk_per_trade_usd == 200.0  # DEFAULT_RISK_PER_TRADE_USD


def test_inadmissible_when_trade_count_too_low() -> None:
    c = _candidate(
        total_trades_per_fold=10,  # 3 folds * 10 = 30 < 150
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
    )
    assert not c.is_admissible()


def test_inadmissible_when_median_ci_low_not_positive() -> None:
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[-5.0, -20.0, -1.0],  # median = -5.0, fails > 0
        lucidflex_means=[50.0, 80.0, 30.0],
    )
    assert not c.is_admissible()


def test_inadmissible_when_worst_fold_below_negative_eval_fee() -> None:
    # median ci low positive, but worst-fold mean below -eval_fee (derived lucidflex fee)
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, -(LUCIDFLEX_EVAL_FEE + 50.0)],  # worse than -fee
    )
    assert not c.is_admissible()


def test_admissible_at_exact_eval_fee_boundary_fails_strict_inequality() -> None:
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, -LUCIDFLEX_EVAL_FEE],  # exactly -eval_fee, strict > required
    )
    assert not c.is_admissible()


def test_eval_fee_by_firm_derived_from_rules_modules_not_hardcoded() -> None:
    """EVAL_FEE_BY_FIRM must track the frozen ruleset dataclasses, never a bare literal.

    LucidFlex: eval_fee (coupon-adjusted attempt cost). TopStep no-fee path has
    activation_fee=0, so the real downside of a failed attempt is the reset
    cost, not the (zero) activation fee or the recurring monthly fee.
    """
    assert EVAL_FEE_BY_FIRM["lucidflex"] == float(LucidFlex50K().eval_fee)
    assert EVAL_FEE_BY_FIRM["topstep"] == float(TopStepNoFee50K().nofee_reset_cost)
    # Pin the canonical values so a silent ruleset drift is caught here too.
    assert EVAL_FEE_BY_FIRM["lucidflex"] == 98.0
    assert EVAL_FEE_BY_FIRM["topstep"] == 109.0


def test_apex_eval_fees_derived_from_rules_module_not_hardcoded() -> None:
    """Apex fees come from Apex50K().eval_fee(variant=...), the sticker (upper-bound)

    price. Apex runs frequent 80-90% promos in practice, but the admissibility
    clause deliberately stays conservative and uses the sticker value.
    """
    rules = Apex50K()
    assert EVAL_FEE_BY_FIRM["apex_eod"] == float(rules.eval_fee(variant="eod"))
    assert EVAL_FEE_BY_FIRM["apex_intraday"] == float(rules.eval_fee(variant="intraday"))
    # Pin the canonical sticker values so a silent ruleset drift is caught here too.
    assert EVAL_FEE_BY_FIRM["apex_eod"] == 197.0
    assert EVAL_FEE_BY_FIRM["apex_intraday"] == 131.0


def test_replay_firms_includes_both_apex_variants_separately() -> None:
    assert "apex_eod" in REPLAY_FIRMS
    assert "apex_intraday" in REPLAY_FIRMS
    assert "apex_eod" != "apex_intraday"
    # Every firm in REPLAY_FIRMS must have a derived admissibility fee.
    assert set(REPLAY_FIRMS) <= set(EVAL_FEE_BY_FIRM)


def test_apex_eod_variant_admissibility_uses_its_own_fee() -> None:
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, -(APEX_EOD_EVAL_FEE - 1.0)],  # just inside -fee
        firm="apex_eod",
    )
    assert c.is_admissible()
    assert c.admissible_firms() == ["apex_eod"]


def test_apex_intraday_variant_inadmissible_below_its_own_fee() -> None:
    c = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, -(APEX_INTRADAY_EVAL_FEE + 5.0)],  # worse than -fee
        firm="apex_intraday",
    )
    assert not c.is_admissible()


def test_apex_variants_are_ranked_as_separate_products() -> None:
    """An EOD-admissible candidate and an Intraday-admissible candidate for the

    same params must not be conflated: admissible_firms() reports exactly the
    variant that actually passed, never both from one firm's summary.
    """
    eod_only = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
        firm="apex_eod",
    )
    assert eod_only.admissible_firms() == ["apex_eod"]
    assert "apex_intraday" not in eod_only.admissible_firms()


def test_inadmissible_when_no_firm_summaries_present() -> None:
    c = _candidate(total_trades_per_fold=60, lucidflex_ci_lows=None, lucidflex_means=None)
    assert not c.is_admissible()


# ---------------------------------------------------------------------------
# plateau ranking
# ---------------------------------------------------------------------------


def test_plateau_ranking_prefers_stable_neighborhood_over_sharp_peak() -> None:
    # Two admissible candidates with identical (median_ci_low, worst_fold) scores.
    # "peak" params has no admissible neighbors in the grid; "plateau" params
    # has neighbors that are also admissible. Plateau should rank first.
    peak_params = ORBParams(or_minutes=5, target_r=4.0)
    plateau_params = ORBParams(or_minutes=15, target_r=4.0)
    plateau_neighbor_a = ORBParams(or_minutes=15, target_r=None)  # differs only in target_r
    plateau_neighbor_b = ORBParams(or_minutes=30, target_r=4.0)  # differs only in or_minutes

    peak_candidate = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
        params=peak_params,
    )
    plateau_candidate = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
        params=plateau_params,
    )
    neighbor_a_candidate = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[1.0, 2.0, 1.0],
        lucidflex_means=[5.0, 5.0, 5.0],
        params=plateau_neighbor_a,
    )
    neighbor_b_candidate = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[1.0, 2.0, 1.0],
        lucidflex_means=[5.0, 5.0, 5.0],
        params=plateau_neighbor_b,
    )
    # peak's neighbors are NOT admissible (isolated peak)
    peak_neighbor_isolated = ORBParams(or_minutes=5, target_r=None)

    grid = [peak_params, plateau_params, plateau_neighbor_a, plateau_neighbor_b, peak_neighbor_isolated]
    candidates = [peak_candidate, plateau_candidate, neighbor_a_candidate, neighbor_b_candidate]

    ranked = rank_plateau(candidates, grid)
    ranked_params = [c.params for c in ranked]

    assert plateau_params in ranked_params
    assert peak_params in ranked_params
    plateau_rank = ranked_params.index(plateau_params)
    peak_rank = ranked_params.index(peak_params)
    assert plateau_rank < peak_rank, "plateau candidate should outrank the isolated peak"


def test_plateau_ranking_excludes_inadmissible_candidates() -> None:
    admissible = _candidate(
        total_trades_per_fold=60,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
        params=ORBParams(or_minutes=5),
    )
    inadmissible = _candidate(
        total_trades_per_fold=10,
        lucidflex_ci_lows=[10.0, 20.0, 5.0],
        lucidflex_means=[50.0, 80.0, 30.0],
        params=ORBParams(or_minutes=15),
    )
    ranked = rank_plateau([admissible, inadmissible], [admissible.params, inadmissible.params])
    assert len(ranked) == 1
    assert ranked[0].params == admissible.params


# ---------------------------------------------------------------------------
# holdout guard
# ---------------------------------------------------------------------------


def _synthetic_orb_bars(n_sessions: int = 5) -> pd.DataFrame:
    """Minimal RTH-session bars spanning the holdout window for guard tests.

    Guard tests don't need real trade signal — they just need `bars` to be a
    valid, non-empty tz-aware frame the guard's internal helpers can slice
    without raising. A degenerate flat series (no breakouts -> zero trades)
    keeps the replay-MC summary path harmlessly returning None.
    """
    rows = []
    start = pd.Timestamp(HOLDOUT_START).tz_localize("UTC")
    for day_offset in range(n_sessions):
        day = start + timedelta(days=day_offset)
        # 09:30-16:00 ET is 13:30-20:00 UTC outside DST; keep it simple/flat.
        for minute in range(400):
            ts = day + timedelta(hours=13, minutes=30 + minute)
            rows.append({"ts": ts, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0})
    df = pd.DataFrame(rows).set_index("ts")
    df.index.name = "ts_event"
    return df


def test_evaluate_holdout_refuses_without_unlock_flag(tmp_path: Path) -> None:
    bars = _synthetic_orb_bars()
    with pytest.raises(PermissionError):
        evaluate_holdout(
            bars,
            ORBParams(),
            "lucidflex",
            unlock_holdout=False,
            output_dir=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_evaluate_holdout_writes_record_and_sentinel(tmp_path: Path) -> None:
    bars = _synthetic_orb_bars()
    record = evaluate_holdout(
        bars,
        ORBParams(),
        "lucidflex",
        unlock_holdout=True,
        output_dir=tmp_path,
    )
    h = params_hash(ORBParams())
    assert (tmp_path / f"holdout_{h}.json").exists()
    assert (tmp_path / "HOLDOUT_UNLOCKED" / f"{h}.lock").exists()
    assert record["params_hash"] == h
    assert record["firm"] == "lucidflex"
    assert record["risk_per_trade_usd"] == 200.0  # default, recorded so the sizing assumption is never ambiguous


def test_evaluate_holdout_records_custom_risk_per_trade(tmp_path: Path) -> None:
    bars = _synthetic_orb_bars()
    record = evaluate_holdout(
        bars,
        ORBParams(or_minutes=15),
        "lucidflex",
        unlock_holdout=True,
        output_dir=tmp_path,
        risk_per_trade_usd=350.0,
    )
    assert record["risk_per_trade_usd"] == 350.0


def test_evaluate_holdout_refuses_second_run_same_hash(tmp_path: Path) -> None:
    bars = _synthetic_orb_bars()
    evaluate_holdout(bars, ORBParams(), "lucidflex", unlock_holdout=True, output_dir=tmp_path)
    with pytest.raises(PermissionError):
        evaluate_holdout(bars, ORBParams(), "lucidflex", unlock_holdout=True, output_dir=tmp_path)


def test_evaluate_holdout_different_params_hash_is_independent(tmp_path: Path) -> None:
    bars = _synthetic_orb_bars()
    evaluate_holdout(bars, ORBParams(or_minutes=5), "lucidflex", unlock_holdout=True, output_dir=tmp_path)
    # Different params -> different hash -> not blocked by the first run's sentinel.
    record = evaluate_holdout(bars, ORBParams(or_minutes=15), "lucidflex", unlock_holdout=True, output_dir=tmp_path)
    assert record["params_hash"] == params_hash(ORBParams(or_minutes=15))
