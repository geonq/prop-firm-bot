"""Follow-up analysis: evaluate the more broadly-admissible Stage-B alternative.

Stage B's automated winner (params_hash b063d80725ce5adc, target_r=None,
uncapped runner) was picked by rank_plateau's narrow "best single admissible
firm" metric, but is admissible on LucidFlex ONLY and its Stage-D DSR came
back 0.000 -- a strong-tailed (kurtosis=31.9), fragile, likely-noise result.
This script re-evaluates the alternative candidate (params_hash
8afbe6259cab2dd2: or=5, first_candle, target_r=4.0, time_stop=120, no
vwap_trail), which is admissible on lucidflex + apex_eod + apex_intraday in
the raw Stage B pass, through the SAME Stage C (risk resweep) and Stage D
(overfitting correction) treatment for a fair head-to-head comparison before
selecting the final candidate for the one-shot holdout evaluation.

Reuses the reviewed src.optimizer.walk_forward machinery + the already-run
Stage A/B trial pool for the DSR trial-variance estimate (that pool describes
the search process, not the specific winner, so it is valid to reuse against
any candidate drawn from that same search).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    DEFAULT_RISK_PER_TRADE_USD,
    HOLDOUT_START,
    REPLAY_FIRMS,
    _evaluate_candidate_oos,
    make_folds,
    params_hash,
)

sys.path.insert(0, str(ROOT / "Analysis" / "scripts"))
import orb_full_scope_run as fsr  # reuse stage_c_risk_resweep, stage_d_overfitting_correction, _candidate_row

OUT = ROOT / "Analysis" / "output" / "orb" / "full_scope"

ALT_PARAMS = ORBParams(
    or_minutes=5,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=1.0,
    vwap_trail_after_r=None,
    time_stop_minutes=120,
)


def main() -> None:
    bars = pd.read_parquet(fsr.DATA_PATH)
    folds = make_folds("2015-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    print(f"alt candidate params_hash={params_hash(ALT_PARAMS)} (expect 8afbe6259cab2dd2)")

    t0 = time.monotonic()
    alt_candidate = _evaluate_candidate_oos(
        bars, ALT_PARAMS, folds, firms=REPLAY_FIRMS,
        n_simulations=2000, block_size=5, risk_per_trade_usd=DEFAULT_RISK_PER_TRADE_USD, seed=0,
    )
    print(f"re-evaluated in {time.monotonic()-t0:.0f}s: {fsr._candidate_row(alt_candidate)}")

    # Stage C on the alternative candidate.
    fsr.OUT = OUT
    c_out = fsr.stage_c_risk_resweep(bars, ALT_PARAMS, folds)
    (OUT / "stage_c_ALT_risk_resweep.json").write_text(json.dumps(c_out, indent=2))

    # Stage D: reuse the Stage A+B trial pool for variance, this candidate as winner.
    stageA_all = pd.read_csv(OUT / "stage_a_all.csv")
    stageB_all = pd.read_csv(OUT / "stage_b_all.csv")
    # Need real CandidateResult objects (not CSV rows) for fold-level Sharpe variance --
    # re-derive by re-running IS-pruned survivors is too expensive; instead reuse the
    # ALREADY-COMPUTED stage A/B all_results by re-evaluating just the params list from
    # the CSVs is also expensive (58 candidates). Pragmatic choice: recompute variance
    # from the CSV's median/worst fold proxy (same method the 2026-07-17 correction used)
    # rather than re-running all 58 OOS evaluations a second time -- documented as a
    # deliberate scope cut, not an oversight.
    def proxy_sharpe(row) -> float | None:
        median_low = row.get(f"{fsr.REPR_FIRM_FOR_VARIANCE}_median_ev_ci_low")
        worst_mean = row.get(f"{fsr.REPR_FIRM_FOR_VARIANCE}_worst_fold_ev_mean")
        if pd.isna(median_low) or pd.isna(worst_mean):
            return None
        spread = abs(median_low - worst_mean)
        return median_low / spread if spread > 0 else None

    all_rows = pd.concat([stageA_all, stageB_all], ignore_index=True)
    trial_sharpes = [s for _, r in all_rows.iterrows() if (s := proxy_sharpe(r)) is not None]
    n_trials = len(all_rows)
    print(f"N trials={n_trials}, usable proxy sharpes={len(trial_sharpes)}")

    from src.optimizer.overfitting_stats import (
        bonferroni_check, deflated_sharpe_ratio, one_sample_bootstrap_p_value, summarize_return_series,
    )
    from src.optimizer.walk_forward import _fold_replay_days

    warmup_start = pd.Timestamp("2015-01-01")
    trades, _ = _fold_replay_days(bars, ALT_PARAMS, warmup_start=warmup_start,
                                   window_start=pd.Timestamp("2015-04-01"),
                                   window_end=pd.Timestamp(HOLDOUT_START))
    r_multiples = [t.r_multiple for t in trades]
    stats = summarize_return_series(r_multiples)
    print(f"alt winner real trade series: N={stats.n}, SR={stats.sharpe:.4f}, skew={stats.skew:.3f}, kurt={stats.kurtosis:.3f}")

    dsr_result = deflated_sharpe_ratio(
        winner_returns=r_multiples,
        trial_sharpes=trial_sharpes if len(trial_sharpes) >= 2 else [stats.sharpe],
        n_trials=n_trials,
    )
    p_boot = one_sample_bootstrap_p_value(r_multiples, seed=0)
    bonf = bonferroni_check(p_boot, n_trials)

    d_out = {
        "n_trials": n_trials, "n_usable_variance_samples": len(trial_sharpes),
        "variance_method": "CSV median/worst-fold proxy (Stage A+B pool reused; NOT re-running "
                            "58 OOS evaluations a second time -- deliberate scope cut)",
        "winner_params_hash": params_hash(ALT_PARAMS),
        "winner_trade_count": stats.n, "winner_sharpe": stats.sharpe,
        "winner_skewness": stats.skew, "winner_kurtosis": stats.kurtosis,
        "dsr": dsr_result.dsr, "psr_zero": dsr_result.psr_zero, "sr_0": dsr_result.expected_max_sr_null,
        "bootstrap_p_raw": p_boot, "bonferroni": bonf,
    }
    (OUT / "stage_d_ALT_overfitting_correction.json").write_text(json.dumps(d_out, indent=2, default=str))
    print(f"DSR={dsr_result.dsr:.3f} PSR(0)={dsr_result.psr_zero:.3f} bootstrap_p={p_boot:.4f} bonferroni={bonf}")
    print("\nALT CANDIDATE ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
