"""Deflated Sharpe Ratio (DSR) / Probabilistic Sharpe Ratio (PSR) correction
for the ORB round-1 + round-2 walk-forward parameter search.

WHY: round 1 tested 216 ORBParams configs and round 2 tested 18 exit-overlay
configs on top of round 1's winner, all scored on the SAME 8 out-of-sample
(OOS) folds via replay-Monte-Carlo net EV per firm. Searching 234 configs
against the same fold data and then reporting the best one's EV as "the
strategy's edge" is classic backtest-overfitting / selection bias: even with
zero true skill, the best of 234 noisy trials will look good by chance. This
script quantifies how much of the round-2 winner's apparent edge survives
that correction, via Bailey & Lopez de Prado (2014), "The Deflated Sharpe
Ratio: Correcting for Selection Bias, Backtest Overfitting, and
Non-Normality" (Journal of Portfolio Management), and the trial-count
correction term from Bailey, Borwein, Lopez de Prado, Zhu, "Probability of
Backtest Overfitting". The math itself lives in
`src/optimizer/overfitting_stats.py` (reusable, no pandas dependency); this
script is the ORB-specific data plumbing around it.

DATA-MAPPING DECISIONS (read before trusting the numbers — there is no
single "right" way to map fold-summary CSVs onto DSR's inputs; these are the
principled, conservative choices made here):

1. "Trials" (N in step 2, the expected-max-Sharpe-under-null term):
   N = 234 = 216 (round 1 grid size, per `walk_forward_summary.json`
   grid_size) + 18 (round 2 grid, `round2_search.json`, all 18 rows). This
   is the number of configs actually SEARCHED against the fold data,
   regardless of whether their fold-level numbers were persisted to disk.

2. Var[{SR_n}] (the cross-trial variance of Sharpe-like scores, used to
   scale the E[max SR] null benchmark) can only be estimated from configs
   whose fold-level numbers were actually SAVED. Round 1's
   `walk_forward_results.csv` / `walk_forward_summary.json` persisted only
   the 36 ADMISSIBLE candidates out of 216 searched (confirmed via
   `admissible_count: 36` in walk_forward_summary.json and
   `full_run.log`) — the other 180 non-admissible configs' fold data was
   never written to disk anywhere in this repo. Round 2 saved all 18 rows.
   So Var[{SR_n}] here is estimated from 36 + 18 = 54 available proxy
   Sharpes, NOT the full 234. This is EXPLICITLY FLAGGED AS AN
   APPROXIMATION: the 180 missing configs were the WORSE, rejected ones, so
   including them would only widen the cross-trial spread (higher
   Var[{SR_n}]) and thus RAISE the E[max SR] null benchmark, making the DSR
   verdict MORE conservative (harder to clear), not less. Using only the 54
   surviving/searched configs with saved data is therefore a
   non-conservative-direction gap — the true DSR is very likely LOWER
   (harder to clear) than what this script reports. This is the single
   biggest caveat in this analysis and is restated in the JSON output's
   "caveats" field.

   Per-config Sharpe-like proxy: for round 1's 36 saved rows, only two
   fold-level numbers survive per firm (`{firm}_median_ev_ci_low` and
   `{firm}_worst_fold_ev_mean}` — NOT a full per-fold series, and NOT a
   simple across-fold mean/std). We use
   proxy_sharpe = median_ev_ci_low / abs(median_ev_ci_low - worst_fold_ev_mean)
   as a conservative "location / spread" proxy: the numerator is a
   conservative (lower-CI) location estimate, the denominator is the
   distance from that location down to the single worst fold observed,
   standing in for a dispersion estimate when the full fold series isn't
   available. If worst_fold_ev_mean == median_ev_ci_low (denominator 0,
   degenerate), the config is dropped from the trial-variance pool with a
   count logged. For round 2's 18 saved rows, the same proxy is used from
   `{firm}_fold_median` / `{firm}_fold_worst`. TopStep is used as the
   representative firm column (least-null, most complete data across both
   rounds, and the firm round 2's `best_median` was actually maximized
   over — see round2_search.json, row 0 has the highest topstep_fold_median
   of any row/firm).

   UNITS WARNING (important, and why this script computes DSR the way it
   does): this fold-EV proxy Sharpe is on a completely different numerical
   scale than a Sharpe computed from the winner's real per-trade
   R-multiples (dollar-EV-of-a-fold-set-of-trades divided by a dollar
   spread, vs. mean-R-per-trade divided by std-R-per-trade — verified
   empirically: proxy Sharpes across the 54 saved configs range ~0.15-1.15,
   while the winner's real per-trade R-multiple Sharpe is ~0.08). Bailey &
   Lopez de Prado's PSR formula requires SR_hat and SR* (the benchmark) to
   be on the SAME scale — plugging a per-trade R-multiple SR_hat against an
   E[max SR] benchmark built from dollar-EV proxy Sharpes would silently
   produce a meaningless DSR (verified: doing this naively collapses DSR to
   ~0.0 even though the winner clears every other significance check,
   because the null benchmark sits on an unrelated, larger scale). This
   script resolves the mismatch by computing DSR ENTIRELY in the fold-EV
   proxy-Sharpe unit: the winner's own SR_hat for the DSR step is ALSO
   computed via the identical `_proxy_sharpe` formula from its OWN
   round2_search.json row (median=1670.5, worst=437.5 -> proxy Sharpe
   ~1.355), so SR_hat and the E[max SR] null benchmark are unit-consistent.
   T for this proxy-scale PSR/DSR uses the winner's actual trade count
   (see decision #3) since T is a sample-size correction, not a
   scale-dependent quantity, and using the real trade count is more
   statistically honest than pretending T=8 (fold count).

   SAMPLE-SIZE WARNING (equally important): the proxy Sharpe for every
   trial, including the winner's own, is estimated from 8 OOS folds per
   config — NOT from 1173 individual trades. T in the PSR formula is a
   sample-size correction on the SAME observations that produced SR_hat, so
   the proxy-scale DSR/PSR(0) computation below uses T=8 (the fold count),
   not the winner's real per-trade count. Using the real trade count
   (T=1173) here would be a genuine statistical error: it would claim 1173
   independent observations of a quantity (the fold-EV proxy Sharpe) that
   was actually only ever estimated from 8 folds, producing a false,
   over-confident DSR (verified empirically: T=1173 collapses DSR to
   1.0000/100% via an enormous sqrt(T-1) term that swamps the real,
   fold-level uncertainty; T=8 gives a materially different, more
   defensible number). This IS the primary, small-sample-honest DSR
   reported by this script, and its small T means it should be read as
   directionally informative, not a precise probability — flagged in
   caveats.

   The winner's REAL per-trade R-multiple series (decision #3 below) is
   still fully computed and reported as a SEPARATE, correctly-scaled
   diagnostic: PSR(0) on the R-multiple series (T=1173, its own real
   observation count) answers "is the per-trade edge distinguishable from
   zero" (a valid, well-scaled, well-powered question on its own, just not
   the same question as DSR). It is not combined with the dollar-EV-proxy
   trial variance inside one PSR call, and does not inherit the T=8
   small-sample caveat. Both PSR(0) values (fold-EV proxy scale at T=8, and
   R-multiple scale at T=1173) are reported in the output so nothing is
   hidden, and the headline DSR is the T=8 fold-EV-scale number since that
   is the only one that actually answers "how much of the 234-config search
   result survives correction" (the R-multiple PSR(0) says nothing about
   the search/selection problem at all, only about single-config edge).

3. "Return series" for the winner's own trade count T and, separately, its
   real per-trade skew/kurtosis/Sharpe diagnostic (decision #2's closing
   paragraph) is NOT taken from fold summaries — those only give T=8 (fold
   count), far too few observations for skew/kurtosis to be meaningful.
   Instead this script RE-RUNS the backtest for the round-2 winning config
   (or_minutes=15, first_candle, or_opposite stop, target_r=4.0,
   slippage_ticks=2.0, vwap_trail_after_r=2.0, time_stop_minutes=120,
   hold_into_close=False — round2_search.json row 0, the config with the
   highest best_median) across the FULL pre-holdout window (2020-04-01 to
   HOLDOUT_START=2025-07-01, matching `Analysis/scripts/orb_risk_sweep.py`'s
   Stage-2 pooled-window convention and warmup_start=2020-01-01), using
   `src.optimizer.walk_forward._fold_replay_days` (same machinery round 1/2
   used) to get the ACTUAL per-trade R-multiples. T = number of trades
   (1173 actual, larger than round 2's oos_trades=890 because round 2's
   figure is pooled over OOS folds only, while this re-run also covers the
   IS portions of the pre-holdout window — both are legitimate trade
   counts for different windows; this script's T is deliberately the
   larger, full-pre-holdout-window count since more observations is a more
   statistically sound basis for skew/kurtosis). Sharpe/skew/kurtosis for
   this diagnostic are computed directly on the R-multiple series (mean R /
   std R per trade; NOT annualized — R-multiples are already a
   risk-normalized, unitless per-trade return, so "annualizing" would
   require an assumed trades/year figure not implied by the R-multiple
   itself; this script reports the raw per-trade figure and states this
   convention rather than picking an arbitrary annualization factor).

4. Bonferroni cross-check: bootstraps a one-sided p-value for
   "true mean R-multiple > 0" from the winner's actual per-trade R-multiple
   series (10,000 resamples, seeded), then multiplies by N=234 trials and
   compares to alpha=0.05. This check is entirely on the real R-multiple
   series and is not affected by the units issue in #2 (it never touches
   Var[{SR_n}] or E[max SR]).

Output: Analysis/output/orb/overfitting_correction.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.overfitting_stats import (
    bonferroni_check,
    expected_max_sharpe_under_null,
    one_sample_bootstrap_p_value,
    probabilistic_sharpe_ratio,
    summarize_return_series,
)
from src.optimizer.walk_forward import HOLDOUT_START, _fold_replay_days

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
ROUND1_CSV = ROOT / "Analysis" / "output" / "orb" / "walk_forward_results.csv"
ROUND2_JSON = ROOT / "Analysis" / "output" / "orb" / "round2_search.json"
OUT_PATH = ROOT / "Analysis" / "output" / "orb" / "overfitting_correction.json"

ROUND1_GRID_SIZE = 216
ROUND2_GRID_SIZE = 18
N_TRIALS_TOTAL = ROUND1_GRID_SIZE + ROUND2_GRID_SIZE  # 234

REPRESENTATIVE_FIRM = "topstep"

# Round-2 winning config (round2_search.json row 0 — highest best_median,
# vwap_trail_after_r=2.0 + time_stop_minutes=120 + hold_into_close=off; see
# Coordination/HANDOFF.md "Round 2 (2026-07-17 evening) CLOSED" entry).
WINNER_PARAMS = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
    hold_into_close=False,
    vwap_trail_after_r=2.0,
    time_stop_minutes=120,
)

WINDOW_START = pd.Timestamp("2020-04-01")  # matches orb_risk_sweep.py Stage 2 pooled window
WINDOW_END = pd.Timestamp(HOLDOUT_START)  # 2025-07-01, never touches holdout
WARMUP_START = pd.Timestamp("2020-01-01")

N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 0
ALPHA = 0.05

# The fold-EV proxy Sharpe (for every trial including the winner) is
# estimated from 8 OOS folds per config -- NOT from the winner's 1173
# individual trades. T for the proxy-scale PSR/DSR must match the actual
# sample size behind SR_hat (see module docstring, SAMPLE-SIZE WARNING).
N_FOLDS = 8


def _proxy_sharpe(median_ci_low: float, worst_mean: float) -> float | None:
    """Location/spread proxy Sharpe from two summary numbers (median lower-CI,
    worst-fold mean) when the full per-fold series isn't available. See
    module docstring, data-mapping decision #2. Returns None if degenerate
    (worst == median, zero spread)."""
    spread = abs(median_ci_low - worst_mean)
    if spread == 0.0:
        return None
    return median_ci_low / spread


def _load_round1_trial_sharpes(firm: str) -> tuple[list[float], int, int]:
    """Returns (proxy_sharpes, n_rows_loaded, n_dropped_degenerate)."""
    df = pd.read_csv(ROUND1_CSV)
    median_col = f"{firm}_median_ev_ci_low"
    worst_col = f"{firm}_worst_fold_ev_mean"
    if median_col not in df.columns or worst_col not in df.columns:
        raise ValueError(f"expected columns {median_col!r}/{worst_col!r} not found in {ROUND1_CSV}")
    sharpes: list[float] = []
    dropped = 0
    for _, row in df.iterrows():
        median_low = row[median_col]
        worst_mean = row[worst_col]
        if pd.isna(median_low) or pd.isna(worst_mean):
            continue
        proxy = _proxy_sharpe(float(median_low), float(worst_mean))
        if proxy is None:
            dropped += 1
            continue
        sharpes.append(proxy)
    return sharpes, len(df), dropped


def _load_round2_trial_sharpes(firm: str) -> tuple[list[float], int, int]:
    with open(ROUND2_JSON) as f:
        rows = json.load(f)
    median_key = f"{firm}_fold_median"
    worst_key = f"{firm}_fold_worst"
    sharpes: list[float] = []
    dropped = 0
    for row in rows:
        if median_key not in row or worst_key not in row:
            raise ValueError(f"expected keys {median_key!r}/{worst_key!r} not found in {ROUND2_JSON}")
        proxy = _proxy_sharpe(float(row[median_key]), float(row[worst_key]))
        if proxy is None:
            dropped += 1
            continue
        sharpes.append(proxy)
    return sharpes, len(rows), dropped


def _winner_proxy_sharpe(firm: str) -> float:
    """The winning config's OWN proxy Sharpe, on the identical basis as the
    other 53 trial proxy Sharpes (see module docstring decision #2, UNITS
    WARNING). Taken directly from round2_search.json row 0."""
    with open(ROUND2_JSON) as f:
        rows = json.load(f)
    row0 = rows[0]
    proxy = _proxy_sharpe(float(row0[f"{firm}_fold_median"]), float(row0[f"{firm}_fold_worst"]))
    if proxy is None:
        raise RuntimeError("winner's own proxy Sharpe is degenerate (zero spread); cannot compute DSR")
    return proxy


def _regenerate_winner_r_multiples() -> list[float]:
    bars = pd.read_parquet(PARQUET)
    trades, _ = _fold_replay_days(
        bars,
        WINNER_PARAMS,
        warmup_start=WARMUP_START,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
    )
    return [t.r_multiple for t in trades]


def _verdict_sentence(dsr: float, n_trials: int, psr_zero_proxy: float, psr_zero_r: float) -> str:
    pct = dsr * 100
    psr_pct = psr_zero_proxy * 100
    psr_r_pct = psr_zero_r * 100
    return (
        f"DSR = {dsr:.3f} means there is a {pct:.1f}% probability the winning "
        f"configuration's true (fold-EV-scale) Sharpe ratio exceeds what we'd "
        f"expect from the best of {n_trials} equally-lucky configurations with "
        f"ZERO true skill (i.e. after fully discounting for having searched "
        f"{n_trials} configs against the same fold data). For comparison, the "
        f"UNCORRECTED PSR(0) on that same fold-EV scale = {psr_pct:.1f}% "
        f"(probability the true Sharpe is merely > 0, ignoring the "
        f"multiple-testing/selection problem entirely) — the gap between these "
        f"two numbers IS the overfitting discount. Separately, on the winner's "
        f"REAL per-trade R-multiple series (T=actual trade count, not fold "
        f"count), PSR(0) = {psr_r_pct:.1f}% -- i.e. before any trial correction "
        f"at all, is the per-trade edge even distinguishable from zero noise."
    )


def main() -> None:
    print(f"N trials total (round1 grid + round2 grid) = {N_TRIALS_TOTAL}")

    r1_sharpes, r1_n, r1_dropped = _load_round1_trial_sharpes(REPRESENTATIVE_FIRM)
    r2_sharpes, r2_n, r2_dropped = _load_round2_trial_sharpes(REPRESENTATIVE_FIRM)
    trial_sharpes = r1_sharpes + r2_sharpes
    print(
        f"proxy Sharpes loaded: round1 {len(r1_sharpes)}/{r1_n} rows "
        f"(admissible-only survivors of {ROUND1_GRID_SIZE} searched; {r1_dropped} dropped degenerate), "
        f"round2 {len(r2_sharpes)}/{r2_n} rows ({r2_dropped} dropped degenerate) "
        f"-> {len(trial_sharpes)} usable proxy Sharpes for Var[{{SR_n}}]"
    )
    if len(trial_sharpes) < 2:
        raise RuntimeError("fewer than 2 usable proxy Sharpes; cannot estimate cross-trial variance")

    print(f"regenerating winner's per-trade R-multiples over [{WINDOW_START.date()}, {WINDOW_END.date()})...")
    winner_r_multiples = _regenerate_winner_r_multiples()
    print(f"winner trade count T = {len(winner_r_multiples)}")

    # Real per-trade R-multiple diagnostic (correctly scaled on its own terms;
    # see module docstring decision #3 and UNITS WARNING in decision #2).
    r_stats = summarize_return_series(winner_r_multiples)
    psr_zero_r_multiple = probabilistic_sharpe_ratio(
        r_stats.sharpe, 0.0, r_stats.n, r_stats.skew, r_stats.kurtosis
    )
    print(
        f"winner (real R-multiples): T={r_stats.n} mean_R={r_stats.mean:.4f} std_R={r_stats.std:.4f} "
        f"SR_hat={r_stats.sharpe:.4f} skew={r_stats.skew:.4f} kurtosis(raw)={r_stats.kurtosis:.4f} "
        f"PSR(0)={psr_zero_r_multiple:.4f}"
    )

    # DSR proper: computed on the fold-EV proxy-Sharpe scale (unit-consistent
    # with the E[max SR] null benchmark — see UNITS WARNING), at T=N_FOLDS=8
    # (see SAMPLE-SIZE WARNING — the proxy Sharpe for every trial, winner
    # included, is only ever estimated from 8 folds, regardless of how many
    # individual trades sit inside those folds). Skew/kurtosis are borrowed
    # from the winner's real R-multiple series as the best available shape
    # estimate (a single dollar-EV summary number has no skew/kurtosis of
    # its own); this is an approximation, flagged in caveats.
    winner_proxy_sr = _winner_proxy_sharpe(REPRESENTATIVE_FIRM)
    # N in the two Phi^-1 terms is the TRUE trial count searched (234), per
    # task spec; Var[{SR_n}] is still estimated only from the 54 available
    # proxy scores (see module docstring decision #2 -- the 180 missing
    # round-1 configs were worse, so this understates the true variance and
    # thus understates E[max SR], making the reported DSR LESS conservative
    # than reality in this one respect, compounding caveat #1).
    e_max_sr, var_across = expected_max_sharpe_under_null(trial_sharpes, n_trials=N_TRIALS_TOTAL)
    psr_zero_proxy = probabilistic_sharpe_ratio(
        winner_proxy_sr, 0.0, N_FOLDS, r_stats.skew, r_stats.kurtosis
    )
    dsr_proxy = probabilistic_sharpe_ratio(
        winner_proxy_sr, e_max_sr, N_FOLDS, r_stats.skew, r_stats.kurtosis
    )

    print(f"winner proxy Sharpe (fold-EV scale, unit-consistent with trials, T={N_FOLDS} folds) = {winner_proxy_sr:.4f}")
    print(f"Var[SR_n] estimated from {len(trial_sharpes)}/{N_TRIALS_TOTAL} available proxy trials = {var_across:.6f}")
    print(f"E[max SR | null, N={N_TRIALS_TOTAL} trials searched] = {e_max_sr:.4f}")
    print(f"PSR(0) [proxy scale, T={N_FOLDS}]  = {psr_zero_proxy:.4f}")
    print(f"DSR    [proxy scale, T={N_FOLDS}]  = {dsr_proxy:.4f}")

    bootstrap_p = one_sample_bootstrap_p_value(winner_r_multiples, n_boot=N_BOOTSTRAP, seed=BOOTSTRAP_SEED)
    bonferroni = bonferroni_check(bootstrap_p, N_TRIALS_TOTAL, alpha=ALPHA)
    print(
        f"bootstrap one-sided p(mean R <= 0) = {bootstrap_p:.5f}; "
        f"Bonferroni-adjusted (x{N_TRIALS_TOTAL}) = {bonferroni['bonferroni_adjusted_p']:.5f}; "
        f"passes alpha={ALPHA}: {bonferroni['passes_bonferroni']}"
    )

    verdict = _verdict_sentence(dsr_proxy, N_TRIALS_TOTAL, psr_zero_proxy, psr_zero_r_multiple)
    print()
    print(verdict)

    output = {
        "methodology": (
            "Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio / Probabilistic "
            "Sharpe Ratio, with expected-max-Sharpe-under-null trial correction from "
            "Bailey, Borwein, Lopez de Prado, Zhu, 'Probability of Backtest Overfitting'. "
            "Raw (Pearson) kurtosis convention throughout (normal = 3.0). DSR/PSR(0) "
            "computed on the fold-EV proxy-Sharpe scale for unit consistency with the "
            "trial-variance benchmark; a separate PSR(0) on the real per-trade "
            "R-multiple series is also reported (see script docstring UNITS WARNING)."
        ),
        "n_trials_total": N_TRIALS_TOTAL,
        "n_trials_round1_grid": ROUND1_GRID_SIZE,
        "n_trials_round2_grid": ROUND2_GRID_SIZE,
        "representative_firm_for_variance": REPRESENTATIVE_FIRM,
        "n_proxy_sharpes_used_for_variance": len(trial_sharpes),
        "proxy_sharpes_round1_count": len(r1_sharpes),
        "proxy_sharpes_round1_of_searched": r1_n,
        "proxy_sharpes_round2_count": len(r2_sharpes),
        "var_across_trials": var_across,
        "expected_max_sr_under_null": e_max_sr,
        "n_folds_used_as_T_for_proxy_scale": N_FOLDS,
        "winner_params": {
            "or_minutes": WINNER_PARAMS.or_minutes,
            "entry_mode": WINNER_PARAMS.entry_mode,
            "stop_mode": WINNER_PARAMS.stop_mode,
            "target_r": WINNER_PARAMS.target_r,
            "slippage_ticks": WINNER_PARAMS.slippage_ticks,
            "hold_into_close": WINNER_PARAMS.hold_into_close,
            "vwap_trail_after_r": WINNER_PARAMS.vwap_trail_after_r,
            "time_stop_minutes": WINNER_PARAMS.time_stop_minutes,
        },
        "winner_window": {"start": str(WINDOW_START.date()), "end": str(WINDOW_END.date())},
        "winner_return_series_stats_r_multiple": {
            "n_trades": r_stats.n,
            "mean_r": r_stats.mean,
            "std_r": r_stats.std,
            "sharpe_per_trade": r_stats.sharpe,
            "skew": r_stats.skew,
            "kurtosis_raw": r_stats.kurtosis,
            "psr_zero": psr_zero_r_multiple,
            "note": "per-trade R-multiple series, NOT annualized (see module docstring decision #3)",
        },
        "winner_proxy_sharpe_fold_ev_scale": winner_proxy_sr,
        "psr_zero_proxy_scale": psr_zero_proxy,
        "dsr_proxy_scale": dsr_proxy,
        "bonferroni_check": {
            **bonferroni,
            "p_value_source": "one-sided bootstrap on winner's per-trade R-multiples, H0: mean R <= 0",
            "n_bootstrap": N_BOOTSTRAP,
            "bootstrap_seed": BOOTSTRAP_SEED,
        },
        "verdict": verdict,
        "caveats": [
            "Var[{SR_n}] is estimated from only 54 of 234 searched configs (36 "
            "round-1 admissible survivors + 18 round-2 rows) because round 1's "
            "180 non-admissible configs' fold data was never persisted to disk. "
            "The missing configs were the WORSE ones, so including them would "
            "widen Var[{SR_n}] and RAISE (make more conservative) the E[max SR] "
            "null benchmark -- the true DSR is very likely LOWER than reported here.",
            "Per-config proxy Sharpe is median_ev_ci_low / |median_ev_ci_low - "
            "worst_fold_ev_mean|, a location/spread stand-in built from only two "
            "saved summary numbers per config, not a full fold-level return series.",
            "The fold-EV proxy Sharpe scale and the real per-trade R-multiple "
            "Sharpe scale are NOT numerically comparable (empirically ~0.15-1.4 "
            "vs ~0.08) -- DSR/PSR(0) are reported entirely on the proxy scale for "
            "internal consistency with the trial-variance benchmark; the "
            "R-multiple-scale PSR(0) is a separate, independently-valid "
            "diagnostic of per-trade edge, not an input to DSR.",
            "The headline DSR/PSR(0) use T=8 (fold count), NOT the winner's 1173 "
            "real trades, because the proxy Sharpe for every trial (including the "
            "winner) is only ever estimated from 8 OOS folds regardless of how "
            "many trades sit inside them -- using T=1173 there would falsely claim "
            "1173 independent observations of a quantity actually estimated from "
            "8 data points (verified: doing so collapses DSR to 1.0000/100% via "
            "an inflated sqrt(T-1) term). With T=8 this is a genuinely small-sample "
            "DSR estimate and should be read as directionally informative, not a "
            "precise probability.",
            "Skew/kurtosis fed into the T=8 proxy-scale PSR/DSR are borrowed from "
            "the winner's real per-trade R-multiple distribution as the best "
            "available shape estimate, since a single dollar-EV fold summary has "
            "no skew/kurtosis of its own -- per-trade R-multiple skew/kurtosis is "
            "almost certainly NOT the same as the true skew/kurtosis of the "
            "8-fold EV distribution (fold EV aggregates ~100+ trades each, so by "
            "the CLT its true shape is likely closer to Normal than the raw "
            "per-trade distribution), so this is an approximation in the "
            "conservative-to-optimistic direction that is not signed a priori.",
            "Per-trade Sharpe is not annualized; R-multiples are already a "
            "risk-normalized per-trade quantity and annualizing would require an "
            "assumed trades/year figure not implied by the data.",
        ],
    }

    OUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
