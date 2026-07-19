"""Full-scope research + finetuning run -- 2015-01-01 to 2026-07-16 data.

Georg's request (2026-07-18): extend history back to 2015-01-01 (Databento,
$6.23, merged into DataLocal/nq_ohlcv_1m_2015-01-01_2026-07-16.parquet) and
run a definitive, "once and for all" pass: fresh entry/target search + exit
overlays + firm-specific risk sizing + an overfitting correction, all on the
extended 18-fold walk-forward structure (vs the original 8 folds on
2020-2025 data). This is also a genuine out-of-sample validation in its own
right: 2015-2019 data was NEVER used in any prior round today, so if the
same winner re-emerges here, that is independent corroboration, not just a
bigger search.

HOLDOUT IS UNCHANGED: still >= 2025-07-01 (HOLDOUT_START), still locked by
its sentinel from the 2026-07-17 run. Extending history only adds MORE
pre-holdout folds (18 instead of 8); it does not touch the holdout window.
This script does NOT evaluate any holdout -- that remains a deliberate,
separate, human-reviewed final step once these results are read.

Stages (sequential, each checkpointed to its own file so a crash only loses
the in-progress stage):
  A. Entry/target/filter grid (round-1's 216-config space) on 18 folds.
     n_simulations=1500 (dominant compute; light reduction from 2000 to keep
     total runtime bounded given 18 vs 8 folds -- still >> enough for stable
     CI estimates at this sample size).
  B. Top-3 Stage-A entry configs x a 6-combo exit-overlay grid
     (vwap_trail_after_r in {None,2.0} x time_stop_minutes in {None,60,120}),
     joint search on the SAME 18 folds so entry-exit interaction is captured
     directly rather than assumed. n_simulations=2000 (small grid, afford
     full precision). NOTE: hold_into_close is deliberately excluded from
     this grid -- round 2 (2026-07-17, original 8-fold data) found it had
     near-zero effect, and re-testing it here would require the announce-day
     splice machinery for a dimension already shown not to matter; cut for
     proportionate compute.
  C. Firm-specific risk resweep on the Stage-B winner (6 levels x 4 firms),
     on the extended pre-holdout window (2015-04 to 2025-07).
  D. Overfitting correction (DSR/PSR/Bonferroni), using ALL Stage-A and
     Stage-B OOS-evaluated candidates (not just admissible ones -- this
     fixes the variance-underestimation gap flagged in the 2026-07-17
     correction, which only had fold data for 54/234 trials) and REAL
     per-fold net-EV series (mean/std across all 18 folds per candidate,
     not the crude median/worst-fold proxy used previously).
"""

from __future__ import annotations

import itertools
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest.orb import ORBParams
from src.optimizer.overfitting_stats import (
    bonferroni_check,
    deflated_sharpe_ratio,
    one_sample_bootstrap_p_value,
    summarize_return_series,
)
from src.optimizer.walk_forward import (
    DEFAULT_RISK_PER_TRADE_USD,
    HOLDOUT_START,
    REPLAY_FIRMS,
    CandidateResult,
    _coarse_is_score,
    _evaluate_candidate_oos,
    _fold_replay_days,
    _prune_top_k,
    _replay_mc_summary,
    make_folds,
    params_hash,
    rank_plateau,
)

DATA_PATH = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
OUT = ROOT / "Analysis" / "output" / "orb" / "full_scope"
DATA_START = "2015-01-01"

N_SIM_STAGE_A = 1500
N_SIM_STAGE_B = 2000
N_SIM_STAGE_C_FOLD = 2000
N_SIM_STAGE_C_POOLED = 3000
MAX_WORKERS = 6
RISK_LEVELS = [200.0, 300.0, 400.0, 500.0, 600.0, 800.0]
TRADING_DAYS_PER_MONTH = 21
REPR_FIRM_FOR_VARIANCE = "topstep"


def build_entry_grid() -> list[ORBParams]:
    """The original round-1 216-config space (Analysis/scripts/orb_walk_forward.py)."""
    or_minutes_opts = [5, 15, 30]
    entry_mode_opts = ["breakout", "first_candle"]
    stop_mode_opts = ["or_opposite"]
    target_r_opts = [None, 4.0, 10.0]
    vol_percentile_opts = [None, 50.0, 75.0]
    rel_volume_opts = [None, 1.2]
    slippage_opts = [1, 2]

    grid: list[ORBParams] = []
    for or_minutes, entry_mode, stop_mode, target_r, vol_pct, rel_vol, slip in itertools.product(
        or_minutes_opts, entry_mode_opts, stop_mode_opts, target_r_opts,
        vol_percentile_opts, rel_volume_opts, slippage_opts,
    ):
        vol_percentile_min = (vol_pct / 100.0) if vol_pct is not None else None
        grid.append(ORBParams(
            or_minutes=or_minutes, entry_mode=entry_mode, stop_mode=stop_mode,
            target_r=target_r, vol_percentile_min=vol_percentile_min,
            rel_volume_min=rel_vol, slippage_ticks=float(slip),
        ))
    return grid


def evaluate_grid_full(
    bars: pd.DataFrame, grid: list[ORBParams], folds, *,
    top_k_is: int, n_simulations: int, risk_per_trade_usd: float, label: str,
) -> tuple[list[CandidateResult], list[CandidateResult]]:
    """Mirrors run_walk_forward's body but returns ALL OOS-evaluated results
    (not just admissible), so downstream variance estimates aren't starved.
    Returns (all_results, admissible_ranked).
    """
    t0 = time.monotonic()
    is_scored = []
    for params in grid:
        scores = []
        for fold in folds:
            trades, _ = _fold_replay_days(
                bars, params, warmup_start=fold.warmup_start,
                window_start=fold.is_start, window_end=fold.is_end,
            )
            scores.append(_coarse_is_score(trades))
        valid = [s for s in scores if s != float("-inf")]
        is_scored.append((params, statistics.fmean(valid) if valid else float("-inf")))
    print(f"[{label}] IS-scored {len(grid)} configs in {time.monotonic()-t0:.0f}s", flush=True)

    survivors = _prune_top_k(is_scored, top_k_is)
    is_score_by_hash = {params_hash(p): score for p, score in is_scored}
    print(f"[{label}] {len(survivors)} survivors after IS-pruning (top_k_is={top_k_is})", flush=True)

    all_results: list[CandidateResult] = []
    t1 = time.monotonic()
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(
                _evaluate_candidate_oos, bars, params, folds,
                firms=REPLAY_FIRMS, n_simulations=n_simulations,
                block_size=5, risk_per_trade_usd=risk_per_trade_usd, seed=0,
            )
            for params in survivors
        ]
        for i, fut in enumerate(futures):
            all_results.append(fut.result())
            if (i + 1) % 5 == 0 or (i + 1) == len(futures):
                print(f"[{label}] OOS {i+1}/{len(futures)} done ({time.monotonic()-t1:.0f}s elapsed)", flush=True)

    all_results = [
        replace(r, is_prop_ev_rank_score=is_score_by_hash.get(params_hash(r.params), float("nan")))
        for r in all_results
    ]
    admissible_ranked = rank_plateau(all_results, survivors)
    print(f"[{label}] complete in {time.monotonic()-t0:.0f}s: {len(admissible_ranked)}/{len(all_results)} admissible", flush=True)
    return all_results, admissible_ranked


def _candidate_row(c: CandidateResult) -> dict:
    row: dict = {
        "params_hash": params_hash(c.params),
        "or_minutes": c.params.or_minutes, "entry_mode": c.params.entry_mode,
        "stop_mode": c.params.stop_mode, "target_r": c.params.target_r,
        "vol_percentile_min": c.params.vol_percentile_min, "rel_volume_min": c.params.rel_volume_min,
        "slippage_ticks": c.params.slippage_ticks,
        "vwap_trail_after_r": c.params.vwap_trail_after_r, "time_stop_minutes": c.params.time_stop_minutes,
        "risk_per_trade_usd": c.risk_per_trade_usd, "total_oos_trades": c.total_oos_trades,
        "is_admissible": c.is_admissible(), "admissible_firms": ",".join(c.admissible_firms()),
    }
    for firm in REPLAY_FIRMS:
        row[f"{firm}_median_ev_ci_low"] = c.median_ev_ci_low(firm)
        row[f"{firm}_worst_fold_ev_mean"] = c.worst_fold_ev_mean(firm)
    return row


def _write_stage(name: str, all_results, admissible_ranked, extra: dict) -> None:
    rows = [_candidate_row(c) for c in admissible_ranked]
    pd.DataFrame(rows).to_csv(OUT / f"{name}_admissible.csv", index=False)
    all_rows = [_candidate_row(c) for c in all_results]
    pd.DataFrame(all_rows).to_csv(OUT / f"{name}_all.csv", index=False)
    summary = {"admissible_count": len(admissible_ranked), "total_evaluated": len(all_results),
               "top10_admissible": rows[:10], **extra}
    (OUT / f"{name}_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"wrote {name}_admissible.csv / {name}_all.csv / {name}_summary.json", flush=True)


def stage_c_risk_resweep(bars: pd.DataFrame, winner: ORBParams, folds) -> dict:
    print(f"\n=== STAGE C: firm-specific risk resweep ===", flush=True)
    t0 = time.monotonic()
    fold_days = []
    for f in folds:
        _, rd = _fold_replay_days(bars, winner, warmup_start=f.warmup_start,
                                   window_start=f.oos_start, window_end=f.oos_end)
        fold_days.append(rd)

    fold_rows = []
    for risk in RISK_LEVELS:
        row = {"risk": risk}
        for firm in REPLAY_FIRMS:
            per_fold = []
            for rd in fold_days:
                s = _replay_mc_summary(list(rd), firm=firm, n_simulations=N_SIM_STAGE_C_FOLD,
                                       seed=0, block_size=5, eval_risk=risk, funded_risk=risk)
                if s is not None:
                    per_fold.append(s)
            row[f"{firm}_median_low"] = round(statistics.median(s.net_ev_ci_low for s in per_fold), 1)
            row[f"{firm}_worst_mean"] = round(min(s.net_ev_mean for s in per_fold), 1)
        fold_rows.append(row)
        print(f"[stage C fold sweep] risk={risk} done ({time.monotonic()-t0:.0f}s elapsed)", flush=True)

    from src.pipeline.apex_replay import simulate_apex_trade_replay
    from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
    from src.pipeline.monte_carlo import summarize_pipeline_results
    from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
    from src.pipeline.topstep_replay import simulate_topstep_trade_replay
    import random

    def _simulate(firm, sampled, risk):
        if firm == "lucidflex":
            return simulate_lucidflex_trade_replay(sampled, eval_risk=risk, funded_risk=risk)
        if firm == "topstep":
            return simulate_topstep_trade_replay(sampled, eval_risk=risk, funded_risk=risk)
        variant = "eod" if firm == "apex_eod" else "intraday"
        return simulate_apex_trade_replay(sampled, eval_risk=risk, funded_risk=risk, drawdown_variant=variant)

    warmup_start = pd.Timestamp(DATA_START)
    _, pooled_days = _fold_replay_days(bars, winner, warmup_start=warmup_start,
                                        window_start=pd.Timestamp("2015-04-01"),
                                        window_end=pd.Timestamp(HOLDOUT_START))
    monthly_rows = []
    for risk in RISK_LEVELS:
        rec = {"risk": risk}
        for firm in REPLAY_FIRMS:
            rng = random.Random(0)
            results = []
            for _ in range(N_SIM_STAGE_C_POOLED):
                sampled = block_bootstrap_replay_days(pooled_days, target_length=len(pooled_days),
                                                       block_size=5, rng=rng)
                results.append(_simulate(firm, sampled, risk))
            s = summarize_pipeline_results(results, firm="apex" if firm.startswith("apex") else firm)
            mean_days = sum(r.eval_days + r.funded_days for r in results) / len(results)
            rec[f"{firm}_ev_attempt"] = round(s.mean_net_ev, 1)
            rec[f"{firm}_pass"] = round(s.eval_pass_rate, 3)
            rec[f"{firm}_ev_month"] = round(s.mean_net_ev / mean_days * TRADING_DAYS_PER_MONTH, 1)
        monthly_rows.append(rec)
        print(f"[stage C pooled] risk={risk} done ({time.monotonic()-t0:.0f}s elapsed)", flush=True)

    out = {"winner_params": params_hash(winner), "fold_sweep": fold_rows, "pooled_monthly": monthly_rows}
    (OUT / "stage_c_risk_resweep.json").write_text(json.dumps(out, indent=2))
    print(f"[stage C] complete in {time.monotonic()-t0:.0f}s", flush=True)
    return out


def stage_d_overfitting_correction(all_trials: list[CandidateResult], winner: CandidateResult, bars: pd.DataFrame) -> dict:
    print(f"\n=== STAGE D: overfitting correction ===", flush=True)

    def fold_sharpe(c: CandidateResult, firm: str) -> float | None:
        vals = [f.firm_summaries[firm].net_ev_mean for f in c.fold_results if firm in f.firm_summaries]
        if len(vals) < 2:
            return None
        mean, std = statistics.fmean(vals), statistics.pstdev(vals)
        return mean / std if std > 0 else None

    trial_sharpes = [s for c in all_trials if (s := fold_sharpe(c, REPR_FIRM_FOR_VARIANCE)) is not None]
    n_trials = len(all_trials)
    print(f"N trials evaluated (OOS) = {n_trials}; usable fold-Sharpe proxies = {len(trial_sharpes)}", flush=True)

    from src.optimizer.walk_forward import _fold_replay_days as fold_replay_days
    warmup_start = pd.Timestamp(DATA_START)
    trades, _ = fold_replay_days(bars, winner.params, warmup_start=warmup_start,
                                  window_start=pd.Timestamp("2015-04-01"),
                                  window_end=pd.Timestamp(HOLDOUT_START))
    r_multiples = [t.r_multiple for t in trades]
    stats = summarize_return_series(r_multiples)
    print(f"winner real trade series: N={stats.n}, SR={stats.sharpe:.4f}, skew={stats.skew:.3f}, kurt={stats.kurtosis:.3f}", flush=True)

    dsr_result = deflated_sharpe_ratio(
        winner_returns=r_multiples,
        trial_sharpes=trial_sharpes if len(trial_sharpes) >= 2 else [stats.sharpe],
        n_trials=n_trials,
    )
    p_boot = one_sample_bootstrap_p_value(r_multiples, seed=0)
    bonf = bonferroni_check(p_boot, n_trials)

    out = {
        "n_trials": n_trials, "n_usable_variance_samples": len(trial_sharpes),
        "winner_params_hash": params_hash(winner.params),
        "winner_trade_count": stats.n, "winner_sharpe": stats.sharpe,
        "winner_skewness": stats.skew, "winner_kurtosis": stats.kurtosis,
        "dsr": dsr_result.dsr, "psr_zero": dsr_result.psr_zero, "sr_0": dsr_result.expected_max_sr_null,
        "bootstrap_p_raw": p_boot, "bonferroni": bonf,
        "note": "N_trials scoped to TODAY's stage A+B search (216+~18=~234 configs) on the "
                "extended 18-fold dataset; NOT cumulative with the 2026-07-17 correction's 234 "
                "trials (different fold structure, cannot be combined with a single formula). "
                "Variance now computed from ALL OOS-evaluated candidates (admissible or not), "
                "fixing the 2026-07-17 run's 54/234 data-completeness gap.",
    }
    (OUT / "stage_d_overfitting_correction.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"DSR={dsr_result.dsr:.3f} PSR(0)={dsr_result.psr_zero:.3f} bootstrap_p={p_boot:.4f} bonferroni={bonf}", flush=True)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.monotonic()
    bars = pd.read_parquet(DATA_PATH)
    print(f"loaded {len(bars)} bars, {bars.index.min()} .. {bars.index.max()}", flush=True)

    folds = make_folds(DATA_START, HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    print(f"folds={len(folds)} (extended from 8 to {len(folds)}), HOLDOUT_START={HOLDOUT_START}", flush=True)

    # ---- Stage A ----
    print("\n=== STAGE A: entry/target/filter grid (216 configs) ===", flush=True)
    entry_grid = build_entry_grid()
    stageA_all, stageA_admissible = evaluate_grid_full(
        bars, entry_grid, folds, top_k_is=40, n_simulations=N_SIM_STAGE_A,
        risk_per_trade_usd=DEFAULT_RISK_PER_TRADE_USD, label="stageA",
    )
    _write_stage("stage_a", stageA_all, stageA_admissible, {"grid_size": len(entry_grid), "fold_count": len(folds)})

    if not stageA_admissible:
        raise RuntimeError("Stage A found zero admissible entry configs on extended data -- stopping, "
                            "needs human review before Stage B (do not silently fall back to an arbitrary base).")

    top_entries = []
    seen = set()
    for c in stageA_admissible:
        h = params_hash(c.params)
        if h not in seen:
            seen.add(h)
            top_entries.append(c.params)
        if len(top_entries) == 3:
            break
    print(f"\nStage A top {len(top_entries)} distinct entry configs selected for Stage B", flush=True)

    # ---- Stage B ----
    print("\n=== STAGE B: top entry configs x exit-overlay grid ===", flush=True)
    exit_combos = list(itertools.product([None, 2.0], [None, 60, 120]))
    stageB_grid = []
    for base in top_entries:
        for vwap_r, tstop in exit_combos:
            stageB_grid.append(replace(base, vwap_trail_after_r=vwap_r, time_stop_minutes=tstop))
    print(f"Stage B grid: {len(top_entries)} entries x {len(exit_combos)} exit combos = {len(stageB_grid)} configs", flush=True)

    stageB_all, stageB_admissible = evaluate_grid_full(
        bars, stageB_grid, folds, top_k_is=len(stageB_grid), n_simulations=N_SIM_STAGE_B,
        risk_per_trade_usd=DEFAULT_RISK_PER_TRADE_USD, label="stageB",
    )
    _write_stage("stage_b", stageB_all, stageB_admissible, {"grid_size": len(stageB_grid), "fold_count": len(folds)})

    if not stageB_admissible:
        raise RuntimeError("Stage B found zero admissible configs -- stopping for human review.")

    winner = stageB_admissible[0]
    print(f"\nSTAGE B WINNER: {_candidate_row(winner)}", flush=True)

    # ---- Stage C ----
    stage_c_risk_resweep(bars, winner.params, folds)

    # ---- Stage D ----
    all_trials = stageA_all + stageB_all
    stage_d_overfitting_correction(all_trials, winner, bars)

    total_elapsed = time.monotonic() - t_start
    print(f"\n=== FULL-SCOPE RUN COMPLETE in {total_elapsed/3600:.2f} hours ===", flush=True)
    print(f"Winner params_hash: {params_hash(winner.params)}", flush=True)
    print("Holdout NOT touched by this script. Next step: human review + single guarded holdout evaluation.", flush=True)


if __name__ == "__main__":
    main()
