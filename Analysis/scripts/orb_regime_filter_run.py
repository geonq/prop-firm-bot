"""Phase 6A-R: regime-gate filter study on the frozen ORB base config.

Pre-registered spec: Tasks/todo.md "Phase 6A-R — Regime filter, IS/OOS
across full decade" (2026-07-18, geonq directive). Binding grid, exactly:
  (A) Kaufman Efficiency Ratio, lookback in {10, 20}, threshold in {0.25, 0.35} -> 4 configs
  (B) trailing shadow-ORB mean R, K in {20, 40}, threshold in {0.0, 0.05} -> 4 configs
  + unfiltered baseline -> 9 distinct trade lists total, each evaluated on
    all 18 folds x 4 firms at $400 risk via the same replay-MC harness as
    this morning's orb_regime_filter_check.py (n_simulations, block_size,
    risk all identical so results are directly comparable).

Base config is FROZEN as-is (or=5/first_candle/or_opposite/4R/120min/$400,
MNQ-scaled risk sizing at the replay-MC layer) -- NO base-param re-tuning in
this script. The "filter" is a post-hoc gate on the UNFILTERED shadow trade
list (src/backtest/regime.py), computed ONCE per fold and reused across all
9 configs; src/backtest/orb.py itself is never touched or re-parameterized.

HOLDOUT_START (2025-07-01) is never touched: make_folds() already refuses to
emit any fold whose OOS window would cross it (same guard
orb_full_scope_run.py / orb_regime_filter_check.py rely on), and this script
never imports or calls evaluate_holdout(). The 8afbe6259cab2dd2 sentinel
stays spent and untouched.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest.orb import ORBParams, Trade, _daily_ohlcv, run_orb_backtest
from src.backtest.regime import (
    RegimeFilterSpec,
    apply_gate,
    gated_trades_for_spec,
    replay_days_from_trades,
    trailing_shadow_r,
)
from src.backtest.sessions import build_rth_sessions
from src.optimizer.walk_forward import (
    HOLDOUT_START,
    REPLAY_FIRMS,
    FirmReplaySummary,
    FoldOOSResult,
    ReplayFirmName,
    _replay_mc_summary,
    _sessions_in_window,
    _slice_bars,
    _trades_in_window,
    make_folds,
)

OUT = ROOT / "Analysis" / "output" / "orb" / "regime_v2"
PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
RISK = 400.0
N_SIM = 2000
BLOCK_SIZE = 5
SEED = 0

FROZEN_BASE = ORBParams(
    or_minutes=5,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    slippage_ticks=1.0,
    time_stop_minutes=120,
)

# ---------------------------------------------------------------------------
# The binding 9-config grid (Tasks/todo.md "Phase 6A-R"). Nothing else.
# ---------------------------------------------------------------------------
GRID: list[RegimeFilterSpec] = [
    RegimeFilterSpec(label="unfiltered", family="unfiltered", lookback_or_k=None, threshold=None),
    RegimeFilterSpec(label="er10_t025", family="er", lookback_or_k=10, threshold=0.25),
    RegimeFilterSpec(label="er10_t035", family="er", lookback_or_k=10, threshold=0.35),
    RegimeFilterSpec(label="er20_t025", family="er", lookback_or_k=20, threshold=0.25),
    RegimeFilterSpec(label="er20_t035", family="er", lookback_or_k=20, threshold=0.35),
    RegimeFilterSpec(label="trailR_k20_t000", family="trailing_r", lookback_or_k=20, threshold=0.0),
    RegimeFilterSpec(label="trailR_k20_t005", family="trailing_r", lookback_or_k=20, threshold=0.05),
    RegimeFilterSpec(label="trailR_k40_t000", family="trailing_r", lookback_or_k=40, threshold=0.0),
    RegimeFilterSpec(label="trailR_k40_t005", family="trailing_r", lookback_or_k=40, threshold=0.05),
]

# Two distinct cutoffs, per the pre-registered spec text (Tasks/todo.md
# "Phase 6A-R"), which are NOT the same date:
#   - ERA_SPLIT_DATE (2020-01-01): the REPORTING era split ("report explicit
#     pre/post-2020-01-01 era split, filtered vs unfiltered, per firm").
#   - RETENTION_CUTOFF_DATE (2021-01-01): the ADMISSIBILITY retention basis
#     ("must retain >=70% of unfiltered 2021+ fold EV") -- fold 7
#     (oos_start=2020-01-01) is POST the reporting split but PRE the
#     retention cutoff, so these two dates matter independently and must
#     not be collapsed into one.
ERA_SPLIT_DATE = pd.Timestamp("2020-01-01")
RETENTION_CUTOFF_DATE = pd.Timestamp("2021-01-01")


@dataclass(frozen=True)
class RegimeCandidateResult:
    """One (spec) point's full walk-forward record -- same shape/semantics as
    src.optimizer.walk_forward.CandidateResult, but for a post-hoc-gated
    trade list instead of a distinct ORBParams. Kept as a separate dataclass
    rather than reusing CandidateResult because CandidateResult.params_hash
    genuinely requires a distinct ORBParams identity, which a regime gate
    (same base ORBParams, different trade LIST) does not have.
    """

    spec: RegimeFilterSpec
    fold_results: tuple[FoldOOSResult, ...]

    @property
    def total_oos_trades(self) -> int:
        return sum(f.trade_count for f in self.fold_results)

    def median_ev_ci_low(self, firm: ReplayFirmName) -> float | None:
        values = [f.firm_summaries[firm].net_ev_ci_low for f in self.fold_results if firm in f.firm_summaries]
        return statistics.median(values) if values else None

    def worst_fold_ev_mean(self, firm: ReplayFirmName) -> float | None:
        values = [f.firm_summaries[firm].net_ev_mean for f in self.fold_results if firm in f.firm_summaries]
        return min(values) if values else None

    def worst_fold_positive_on_all_folds(self, firm: ReplayFirmName) -> bool:
        """Pre-registered admissibility clause 1: worst fold POSITIVE on ALL 18 folds.

        Distinct from `worst_fold_ev_mean` > 0 (which only checks the single
        worst value) -- this explicitly checks every fold individually so a
        fold with no firm_summaries entry (e.g. zero trades that fold) does
        NOT silently pass; it must have a present, positive net_ev_mean on
        EVERY fold in `fold_results`.
        """
        if not self.fold_results:
            return False
        for f in self.fold_results:
            summary = f.firm_summaries.get(firm)
            if summary is None or summary.net_ev_mean <= 0:
                return False
        return True

    def era_sums(
        self, firm: ReplayFirmName, fold_oos_start: dict[int, pd.Timestamp], *, cutoff: pd.Timestamp
    ) -> tuple[float, float]:
        """(sum of fold EV for folds with oos_start < cutoff, sum for oos_start >= cutoff), for `firm`.

        A fold is classified by its OOS window's own start date (looked up
        via `fold_oos_start[fold_index]`, since `FoldOOSResult` itself only
        carries `fold_index`, not the fold's timestamps). Folds with no
        firm_summaries entry for `firm` contribute 0 to their era's sum (not
        skipped -- absence of trades that fold is itself informative and
        must not silently vanish from the total). Called with two DIFFERENT
        cutoffs by the caller (see ERA_SPLIT_DATE vs RETENTION_CUTOFF_DATE
        module-level constants) for two distinct purposes: the reporting
        era split (2020-01-01) and the admissibility retention basis
        (2021-01-01) -- these are not interchangeable, see their docstrings.
        """
        pre = 0.0
        post = 0.0
        for f in self.fold_results:
            summary = f.firm_summaries.get(firm)
            ev = summary.net_ev_mean if summary is not None else 0.0
            if fold_oos_start[f.fold_index] < cutoff:
                pre += ev
            else:
                post += ev
        return pre, post


def _daily_closes_for_window(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """RTH daily closes indexed by session_date, over [start, end)."""
    window_bars = _slice_bars(bars, start, end)
    sessions = build_rth_sessions(window_bars)
    if not sessions:
        return pd.Series(dtype=float)
    daily = _daily_ohlcv(sessions)
    return daily["close"]


def _unfiltered_shadow_trades(bars: pd.DataFrame, *, warmup_start: pd.Timestamp, oos_end: pd.Timestamp) -> list[Trade]:
    """Backtest FROZEN_BASE over [warmup_start, oos_end) with NO windowing clip.

    Deliberately does NOT use walk_forward._fold_replay_days, which clips
    its returned trade list to [window_start, window_end) -- that clip is
    correct for scoring (a fold must only be SCORED on its own OOS window),
    but wrong for the trailing_shadow_r signal's own input, which needs the
    fold's warmup-period trades as real trailing history (see
    _evaluate_fold_all_specs docstring). This function returns the FULL,
    un-clipped shadow trade list for the fold's whole span; callers window
    it down to the OOS subset themselves (via _trades_in_window) wherever a
    scoring-eligible candidate pool is actually needed.
    """
    window_bars = _slice_bars(bars, warmup_start, oos_end)
    return run_orb_backtest(window_bars, FROZEN_BASE)


def _trailing_shadow_r_full_span(
    full_span_shadow_trades: list[Trade], oos_session_dates: list, K: int
) -> pd.Series:
    """trailing_shadow_r, computed with the FULL fold-span shadow trade list as
    history but only asked for signal VALUES on the OOS window's own session
    dates -- see src.backtest.regime.trailing_shadow_r for the causal
    contract itself (unchanged); this wrapper only controls how much history
    is made available to it.
    """
    return trailing_shadow_r(full_span_shadow_trades, oos_session_dates, K)


def _evaluate_fold_all_specs(
    bars: pd.DataFrame,
    fold,
    *,
    firms: tuple[ReplayFirmName, ...],
    n_simulations: int,
    block_size: int,
    risk_per_trade_usd: float,
    seed: int,
) -> dict[str, FoldOOSResult]:
    """Compute the shadow trade list ONCE for this fold, then gate it 9 ways.

    Returns {spec.label: FoldOOSResult} for every spec in GRID.

    IMPORTANT: `full_span_shadow_trades` below spans warmup_start..oos_end
    (the WHOLE fold, including the IS/warmup period), NOT just the OOS
    window. This matters specifically for the trailing_shadow_r signal: its
    "last K shadow trades" must be able to look back into the fold's own
    warmup/IS period for real trailing history, otherwise the first ~K
    trading days of every OOS window would show a spuriously blank/NaN
    trailing-R signal (blocked) purely because this fold's own bookkeeping
    artificially clipped the shadow list to the OOS window, not because
    there was genuinely no prior trading history. src.backtest.regime's own
    causal contract (shift/strict-inequality) is unaffected either way --
    this is purely about how much TRUE history is made available to it, not
    about leaking anything forward.
    """
    full_span_shadow_trades = _unfiltered_shadow_trades(bars, warmup_start=fold.warmup_start, oos_end=fold.oos_end)
    oos_shadow_trades = _trades_in_window(full_span_shadow_trades, fold.oos_start, fold.oos_end)

    window_bars = _slice_bars(bars, fold.warmup_start, fold.oos_end)
    all_sessions = build_rth_sessions(window_bars)
    oos_sessions = _sessions_in_window(all_sessions, fold.oos_start, fold.oos_end)
    oos_session_dates = [s.session_date for s in oos_sessions]

    # Daily closes over the FULL fold span (warmup_start..oos_end) so the ER
    # lookback (max 20 trading days) always has warmup history available
    # before the OOS window even starts -- fold.warmup_start is 3 calendar
    # months before is_start, comfortably more than 20 trading days before
    # oos_start (which is is_months=18 further out still).
    daily_closes = _daily_closes_for_window(bars, fold.warmup_start, fold.oos_end)

    results: dict[str, FoldOOSResult] = {}
    for spec in GRID:
        if spec.family == "trailing_r":
            # Gate the OOS-window trades using the FULL-SPAN shadow list for
            # signal history (see docstring), but only ever GATE (drop-or-keep)
            # trades that are themselves in the OOS window -- oos_shadow_trades
            # is exactly that candidate pool.
            signal = _trailing_shadow_r_full_span(full_span_shadow_trades, oos_session_dates, spec.lookback_or_k)
            gated = apply_gate(oos_shadow_trades, signal, spec.threshold)
        else:
            gated = gated_trades_for_spec(
                spec, shadow_trades=oos_shadow_trades, daily_closes=daily_closes, session_dates=oos_session_dates
            )
        replay_days = replay_days_from_trades(gated, oos_sessions)

        n = len(gated)
        win_rate = (sum(1 for t in gated if t.r_multiple > 0) / n) if n else 0.0
        mean_r = (sum(t.r_multiple for t in gated) / n) if n else 0.0
        total_r = sum(t.r_multiple for t in gated)

        firm_summaries: dict[ReplayFirmName, FirmReplaySummary] = {}
        for firm in firms:
            summary = _replay_mc_summary(
                replay_days,
                firm=firm,
                n_simulations=n_simulations,
                seed=seed + fold.fold_index,
                block_size=block_size,
                eval_risk=risk_per_trade_usd,
                funded_risk=risk_per_trade_usd,
            )
            if summary is not None:
                firm_summaries[firm] = summary

        results[spec.label] = FoldOOSResult(
            fold_index=fold.fold_index,
            trade_count=n,
            win_rate=win_rate,
            mean_r=mean_r,
            total_r=total_r,
            firm_summaries=firm_summaries,
        )
    return results


def _fold_task(args):
    bars, fold = args
    return fold.fold_index, _evaluate_fold_all_specs(
        bars, fold, firms=REPLAY_FIRMS, n_simulations=N_SIM, block_size=BLOCK_SIZE, risk_per_trade_usd=RISK, seed=SEED
    )


def _run(*, smoke: bool, max_workers: int) -> None:
    bars = pd.read_parquet(PARQUET)
    folds = make_folds("2015-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    if smoke:
        folds = folds[:2]
        print(f"SMOKE TEST: {len(folds)} folds, 1 config subset check")

    print(f"{len(GRID)} regime configs x {len(folds)} folds x {len(REPLAY_FIRMS)} firms, risk=${RISK}")
    t0 = time.monotonic()

    # Per-fold, all 9 specs share ONE shadow trade computation -- parallelize
    # over FOLDS (not over the 9xfold cross product), since the shadow trade
    # list + daily closes are the expensive shared work per fold.
    fold_results_by_label: dict[str, list[FoldOOSResult]] = {spec.label: [] for spec in GRID}
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_fold_task, (bars, fold)) for fold in folds]
        completed = {}
        for i, fut in enumerate(futures):
            fold_index, results_by_label = fut.result()
            completed[fold_index] = results_by_label
            print(f"fold {i + 1}/{len(folds)} done ({time.monotonic() - t0:.0f}s elapsed)", flush=True)

    for fold in folds:
        for spec in GRID:
            fold_results_by_label[spec.label].append(completed[fold.fold_index][spec.label])

    fold_oos_start: dict[int, pd.Timestamp] = {fold.fold_index: fold.oos_start for fold in folds}

    candidates = {
        spec.label: RegimeCandidateResult(spec=spec, fold_results=tuple(fold_results_by_label[spec.label]))
        for spec in GRID
    }

    rows = []
    admissibility_notes = []
    for spec in GRID:
        cand = candidates[spec.label]
        for firm in REPLAY_FIRMS:
            # Reporting era split (2020-01-01) -- separate from the retention basis below.
            pre2020_sum, post2020_sum = cand.era_sums(firm, fold_oos_start, cutoff=ERA_SPLIT_DATE)

            # Admissibility retention basis (2021-01-01), per spec text: "must retain
            # >=70% of unfiltered 2021+ fold EV" -- NOT the same cutoff as the reporting split.
            _, retention_sum = cand.era_sums(firm, fold_oos_start, cutoff=RETENTION_CUTOFF_DATE)
            unfiltered_retention_sum = candidates["unfiltered"].era_sums(
                firm, fold_oos_start, cutoff=RETENTION_CUTOFF_DATE
            )[1]
            retention_pct = (
                (retention_sum / unfiltered_retention_sum * 100.0) if unfiltered_retention_sum > 0 else float("nan")
            )
            worst_positive_all = cand.worst_fold_positive_on_all_folds(firm)
            admissible = bool(worst_positive_all and retention_pct >= 70.0)

            pre2020_trades = sum(
                f.trade_count for f in cand.fold_results if fold_oos_start[f.fold_index] < ERA_SPLIT_DATE
            )
            post2020_trades = sum(
                f.trade_count for f in cand.fold_results if fold_oos_start[f.fold_index] >= ERA_SPLIT_DATE
            )
            unfiltered_pre2020_trades = sum(
                f.trade_count
                for f in candidates["unfiltered"].fold_results
                if fold_oos_start[f.fold_index] < ERA_SPLIT_DATE
            )
            pre2020_block_pct = (
                (1 - pre2020_trades / unfiltered_pre2020_trades) * 100.0
                if unfiltered_pre2020_trades > 0
                else float("nan")
            )

            # 2021+ trade counts (the RETENTION_CUTOFF_DATE basis, matching the
            # coordinator's report instruction: "blocked >80% of pre-2020 trades but
            # <20% of 2021+ trades" -- a distinct cutoff from post2020_trades above).
            trades_2021plus = sum(
                f.trade_count for f in cand.fold_results if fold_oos_start[f.fold_index] >= RETENTION_CUTOFF_DATE
            )
            unfiltered_trades_2021plus = sum(
                f.trade_count
                for f in candidates["unfiltered"].fold_results
                if fold_oos_start[f.fold_index] >= RETENTION_CUTOFF_DATE
            )
            block_pct_2021plus = (
                (1 - trades_2021plus / unfiltered_trades_2021plus) * 100.0
                if unfiltered_trades_2021plus > 0
                else float("nan")
            )

            row = {
                "label": spec.label,
                "family": spec.family,
                "lookback_or_k": spec.lookback_or_k,
                "threshold": spec.threshold,
                "firm": firm,
                "total_oos_trades": cand.total_oos_trades,
                "pre2020_trades": pre2020_trades,
                "post2020_trades": post2020_trades,
                "pre2020_block_pct": pre2020_block_pct,
                "trades_2021plus": trades_2021plus,
                "block_pct_2021plus": block_pct_2021plus,
                "worst_fold_ev_mean": cand.worst_fold_ev_mean(firm),
                "median_ev_ci_low": cand.median_ev_ci_low(firm),
                "pre2020_era_ev_sum": pre2020_sum,
                "post2020_era_ev_sum": post2020_sum,
                "retention_pct_of_unfiltered_2021plus": retention_pct,
                "worst_fold_positive_all_18": worst_positive_all,
                "admissible": admissible,
            }
            rows.append(row)

            if spec.family != "unfiltered" and pre2020_block_pct > 80.0 and block_pct_2021plus < 20.0:
                admissibility_notes.append(
                    f"{spec.label}/{firm}: blocks {pre2020_block_pct:.1f}% of pre-2020 trades but only "
                    f"{block_pct_2021plus:.1f}% of 2021+ trades (the hoped-for shape)"
                )

    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = OUT / ("regime_v2_smoke.csv" if smoke else "regime_v2.csv")
    df.to_csv(csv_path, index=False)

    per_fold_detail = {
        spec.label: [
            {
                "fold_index": f.fold_index,
                "trade_count": f.trade_count,
                "win_rate": f.win_rate,
                "mean_r": f.mean_r,
                "firm_summaries": {
                    firm: {
                        "net_ev_mean": s.net_ev_mean,
                        "net_ev_ci_low": s.net_ev_ci_low,
                        "eval_pass_rate": s.eval_pass_rate,
                    }
                    for firm, s in f.firm_summaries.items()
                },
            }
            for f in candidates[spec.label].fold_results
        ]
        for spec in GRID
    }
    json_path = OUT / ("regime_v2_smoke.json" if smoke else "regime_v2.json")
    json_path.write_text(
        json.dumps(
            {
                "grid": [
                    {"label": s.label, "family": s.family, "lookback_or_k": s.lookback_or_k, "threshold": s.threshold}
                    for s in GRID
                ],
                "n_folds": len(folds),
                "risk_per_trade_usd": RISK,
                "n_simulations": N_SIM,
                "block_size": BLOCK_SIZE,
                "seed": SEED,
                "era_split_date": str(ERA_SPLIT_DATE.date()),
                "admissibility_criteria": "worst_fold_ev_mean > 0 on ALL 18 folds AND >=70% retention of unfiltered 2021+ era EV sum",
                "per_fold_detail": per_fold_detail,
                "hoped_for_shape_notes": admissibility_notes,
            },
            indent=2,
            default=str,
        )
    )

    elapsed = time.monotonic() - t0
    print(f"\nwrote {csv_path}\nwrote {json_path}\nelapsed {elapsed:.0f}s")
    print(f"\n{'label':<18} {'firm':<15} {'worst_fold':>12} {'med_ci_low':>12} {'retention%':>11} {'admissible':>11}")
    for row in rows:
        print(
            f"{row['label']:<18} {row['firm']:<15} {row['worst_fold_ev_mean']:>12.2f} "
            f"{row['median_ev_ci_low']:>12.2f} {row['retention_pct_of_unfiltered_2021plus']:>11.1f} "
            f"{str(row['admissible']):>11}"
        )
    if admissibility_notes:
        print("\nHOPED-FOR SHAPE FLAGS:")
        for note in admissibility_notes:
            print(f"  {note}")
    else:
        print("\nNo config blocks >80% of pre-2020 trades while blocking <20% of 2021+ trades.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="1 config subset x 2 folds only")
    parser.add_argument("--max-workers", type=int, default=6)
    args = parser.parse_args()
    _run(smoke=args.smoke, max_workers=args.max_workers)


if __name__ == "__main__":
    main()
