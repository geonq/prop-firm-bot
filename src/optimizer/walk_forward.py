"""Walk-forward finetuner for the ORB strategy family.

Searches `ORBParams` space on rolling in-sample (IS) windows, prunes to the
top-K IS candidates, evaluates survivors on chronologically later
out-of-sample (OOS) folds, and scores each candidate by PROP-FIRM net EV
(via the existing block-bootstrap replay Monte Carlo — never raw backtest
PnL) per firm. Selection favors stable parameter-neighborhood plateaus over
single-point peaks. A final ~12-month holdout window is reserved and guarded
behind an explicit unlock + immutable single-use record.

Anti-overfit contract (Tasks/todo.md Phase 4B, DECISIONS.md 2026-07-17):
tune on rolling IS windows; select stable plateaus judged on OOS folds
(median + worst-fold constraint); objective = replay-MC prop-account net EV
after friction; final holdout evaluated exactly once after freeze.

Apex status: `src/pipeline/replay_monte_carlo.py` now routes `firm="apex"` via
`src/pipeline/apex_replay.py::simulate_apex_trade_replay` (landed and
adversarially reviewed). Apex EOD-trailing and Intraday-trailing are scored
as two SEPARATE firm-variants — `"apex_eod"` and `"apex_intraday"` — because
they carry different eval fees, different PA activation fees, and different
drawdown mechanics (soft DLL + EOD-only ratchet vs. no DLL + real-time
ratchet); treating them as one firm would blur two distinct products.
`CandidateResult.apex_skipped_reason` is kept for schema stability but is now
`None` since apex is scored.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from src.backtest.orb import ORBParams, Trade, run_orb_backtest, trades_to_replay_days
from src.backtest.sessions import Session, build_rth_sessions
from src.pipeline.replay_monte_carlo import run_replay_monte_carlo
from src.rules.apex import Apex50K
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K
from src.strategies.replay import ReplayDay

# "apex_eod" / "apex_intraday" are the two Apex drawdown-variant products,
# scored separately (see module docstring). ApexAccountState's
# `drawdown_variant` string ("eod" / "intraday") is derived from this name via
# _APEX_DRAWDOWN_VARIANT_BY_FIRM below — never inferred by string-slicing.
ReplayFirmName = Literal["lucidflex", "topstep", "apex_eod", "apex_intraday"]
REPLAY_FIRMS: tuple[ReplayFirmName, ...] = ("lucidflex", "topstep", "apex_eod", "apex_intraday")
_APEX_DRAWDOWN_VARIANT_BY_FIRM: dict[ReplayFirmName, str] = {
    "apex_eod": "eod",
    "apex_intraday": "intraday",
}
APEX_SKIPPED_REASON: str | None = None  # kept for schema stability; apex is now scored (see module docstring)

HOLDOUT_START = date(2025, 7, 1)
_HOLDOUT_DEFAULT_DIR = Path("Analysis/output/orb")

# Default fixed per-trade dollar risk fed to the replay MC's sizing (applied
# identically to both eval_risk and funded_risk). This is a real modeling
# assumption (ORB trades are R-multiples, not dollar sizes, so a fixed
# risk-per-trade must be chosen for the replay pipelines' eval_risk/
# funded_risk inputs) and matches Georg's target sizing geometry ($200 fixed
# risk). Exposed end-to-end (run_walk_forward/evaluate_holdout
# risk_per_trade_usd kwarg, CLI --risk flag, recorded in every output row and
# in CandidateResult) so no result is ambiguous about what sizing produced it.
DEFAULT_RISK_PER_TRADE_USD = 200.0

# Admissibility thresholds (selection rule, encoded exactly per spec).
MIN_TOTAL_OOS_TRADES = 150

# "worst-fold net-EV mean > -1 eval fee" — the actual downside of one failed
# attempt, derived from the frozen ruleset dataclasses so this can never drift
# from the encoded rules:
#   - LucidFlex: `LucidFlex50K().eval_fee` ($98, coupon-adjusted attempt cost;
#     see src/rules/lucidflex.py docstring/comments).
#   - TopStep: the No-Fee path has `activation_fee=0`, so the first attempt has
#     no eval fee at all. The real downside of a failed attempt is the cost to
#     re-enter, i.e. `TopStepNoFee50K().nofee_reset_cost` ($109) rather than
#     `nofee_monthly_fee` ($95, a recurring subscription charge, not a
#     per-attempt fee) or `activation_fee` (0, not representative of the
#     actual cost of failing and trying again).
#   - Apex: `Apex50K().eval_fee(variant=...)` returns the variant-specific
#     sticker eval fee ($197 EOD / $131 Intraday, from `eval_fee_eod` /
#     `eval_fee_intraday`). Apex runs frequent 80-90% promos in practice, so
#     the sticker price is an upper bound on the real attempt cost — the
#     admissibility clause deliberately uses the conservative (higher)
#     sticker value rather than an assumed promo price, per coordinator
#     direction: understating downside would be the wrong direction to be
#     wrong on an admissibility gate.
_apex_rules = Apex50K()
EVAL_FEE_BY_FIRM: dict[ReplayFirmName, float] = {
    "lucidflex": float(LucidFlex50K().eval_fee),
    "topstep": float(TopStepNoFee50K().nofee_reset_cost),
    "apex_eod": float(_apex_rules.eval_fee(variant="eod")),
    "apex_intraday": float(_apex_rules.eval_fee(variant="intraday")),
}


@dataclass(frozen=True)
class FoldSpec:
    """One rolling IS/OOS fold. `warmup_start` feeds the backtester enough prior

    bars to warm up indicators (ATR/vol-percentile/rel-volume lookbacks) before
    `is_start`; trades before `is_start` are discarded, never scored.
    """

    fold_index: int
    warmup_start: pd.Timestamp
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp

    def __post_init__(self) -> None:
        if not (self.warmup_start <= self.is_start < self.is_end <= self.oos_start < self.oos_end):
            raise ValueError(
                "fold ordering must satisfy warmup_start <= is_start < is_end <= oos_start < oos_end"
            )


def make_folds(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    is_months: int = 18,
    oos_months: int = 6,
    step_months: int = 6,
    warmup_months: int = 3,
    holdout_start: pd.Timestamp | str = HOLDOUT_START,
) -> list[FoldSpec]:
    """Build rolling IS/OOS folds over [start, end), never touching >= holdout_start.

    Fold `k` spans IS = [start + k*step, start + k*step + is_months) and
    OOS = [IS_end, IS_end + oos_months). `warmup_months` of bars before
    IS_start are also requested (for indicator warm-up) but never scored.
    A fold is only emitted if its OOS window ends at or before `holdout_start`.
    """
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    holdout_ts = pd.Timestamp(holdout_start)
    if start_ts >= end_ts:
        raise ValueError("start must be before end")
    if is_months <= 0 or oos_months <= 0 or step_months <= 0:
        raise ValueError("is_months, oos_months, step_months must be positive")

    folds: list[FoldSpec] = []
    k = 0
    while True:
        is_start = start_ts + pd.DateOffset(months=step_months * k)
        is_end = is_start + pd.DateOffset(months=is_months)
        oos_start = is_end
        oos_end = oos_start + pd.DateOffset(months=oos_months)
        if oos_end > holdout_ts or oos_end > end_ts:
            break
        warmup_start = is_start - pd.DateOffset(months=warmup_months)
        if warmup_start < start_ts:
            warmup_start = start_ts
        folds.append(
            FoldSpec(
                fold_index=k,
                warmup_start=warmup_start,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
        k += 1
    return folds


@dataclass(frozen=True)
class FirmReplaySummary:
    """Condensed replay-MC summary for one firm, one fold."""

    firm: ReplayFirmName
    net_ev_mean: float
    net_ev_ci_low: float
    eval_pass_rate: float
    mean_payouts: float
    mean_trader_payouts: float


@dataclass(frozen=True)
class FoldOOSResult:
    """Backtest + replay-MC outcome for one candidate on one OOS fold."""

    fold_index: int
    trade_count: int
    win_rate: float
    mean_r: float
    total_r: float
    firm_summaries: dict[ReplayFirmName, FirmReplaySummary] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateResult:
    """One ORBParams candidate's full walk-forward record."""

    params: ORBParams
    is_prop_ev_rank_score: float  # coarse IS score used for pruning, not for final selection
    fold_results: tuple[FoldOOSResult, ...]
    risk_per_trade_usd: float = DEFAULT_RISK_PER_TRADE_USD
    # Kept for schema stability; apex is now scored via "apex_eod"/"apex_intraday"
    # in REPLAY_FIRMS, so this is always None (see module docstring).
    apex_skipped_reason: str | None = APEX_SKIPPED_REASON

    @property
    def total_oos_trades(self) -> int:
        return sum(f.trade_count for f in self.fold_results)

    def median_ev_ci_low(self, firm: ReplayFirmName) -> float | None:
        values = [
            f.firm_summaries[firm].net_ev_ci_low for f in self.fold_results if firm in f.firm_summaries
        ]
        return statistics.median(values) if values else None

    def worst_fold_ev_mean(self, firm: ReplayFirmName) -> float | None:
        values = [f.firm_summaries[firm].net_ev_mean for f in self.fold_results if firm in f.firm_summaries]
        return min(values) if values else None

    def admissible_firms(self) -> list[ReplayFirmName]:
        """Firms for which this candidate satisfies the admissibility clauses.

        A firm passes if: total OOS trades across folds >= MIN_TOTAL_OOS_TRADES
        AND median-across-folds net-EV lower-CI > 0 for that firm AND
        worst-fold net-EV mean > -1 eval fee for that firm.
        """
        if self.total_oos_trades < MIN_TOTAL_OOS_TRADES:
            return []
        passing: list[ReplayFirmName] = []
        for firm in REPLAY_FIRMS:
            median_low = self.median_ev_ci_low(firm)
            worst_mean = self.worst_fold_ev_mean(firm)
            if median_low is None or worst_mean is None:
                continue
            if median_low <= 0:
                continue
            if worst_mean <= -EVAL_FEE_BY_FIRM[firm]:
                continue
            passing.append(firm)
        return passing

    def is_admissible(self) -> bool:
        return len(self.admissible_firms()) > 0

    def best_admissible_score(self) -> tuple[float, float] | None:
        """(median net-EV lower CI, worst fold mean) maximized over admissible firms.

        Used as the primary/secondary sort keys for ranking. Returns None if
        not admissible for any firm.
        """
        firms = self.admissible_firms()
        if not firms:
            return None
        best = max(
            ((self.median_ev_ci_low(f) or float("-inf"), self.worst_fold_ev_mean(f) or float("-inf")) for f in firms),
        )
        return best


def _param_dict(params: ORBParams) -> dict:
    return {
        "or_minutes": params.or_minutes,
        "entry_mode": params.entry_mode,
        "stop_mode": params.stop_mode,
        "target_r": params.target_r,
        "vol_percentile_min": params.vol_percentile_min,
        "rel_volume_min": params.rel_volume_min,
        "slippage_ticks": params.slippage_ticks,
    }


def params_hash(params: ORBParams) -> str:
    payload = json.dumps(_param_dict(params), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _slice_bars(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    idx = bars.index
    if idx.tz is None:
        raise ValueError("bars.index must be tz-aware (UTC)")
    start_utc = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end_utc = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    return bars.loc[(idx >= start_utc) & (idx < end_utc)]


def _sessions_in_window(sessions: list[Session], start: pd.Timestamp, end: pd.Timestamp) -> list[Session]:
    start_date = start.date()
    end_date = end.date()
    return [s for s in sessions if start_date <= s.session_date < end_date]


def _trades_in_window(trades: list[Trade], start: pd.Timestamp, end: pd.Timestamp) -> list[Trade]:
    start_date = start.date()
    end_date = end.date()
    return [t for t in trades if start_date <= t.session_date < end_date]


def _fold_replay_days(
    bars: pd.DataFrame,
    params: ORBParams,
    *,
    warmup_start: pd.Timestamp,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> tuple[list[Trade], list[ReplayDay]]:
    """Backtest from `warmup_start` (indicator warm-up), keep only trades/sessions

    inside [window_start, window_end). The backtester itself has no explicit
    "warm-up" mode — warm-up is achieved here by feeding it bars starting
    before the window and discarding trades/sessions outside it after the
    fact, per the ORB no-lookahead contract (indicators only use prior
    sessions, so feeding extra history before the window is safe and does
    not leak future information into the window).
    """
    window_bars = _slice_bars(bars, warmup_start, window_end)
    all_sessions = build_rth_sessions(window_bars)
    all_trades = run_orb_backtest(window_bars, params)

    windowed_sessions = _sessions_in_window(all_sessions, window_start, window_end)
    windowed_trades = _trades_in_window(all_trades, window_start, window_end)
    replay_days = trades_to_replay_days(windowed_trades, windowed_sessions)
    return windowed_trades, replay_days


def _coarse_is_score(trades: list[Trade]) -> float:
    """Cheap IS ranking proxy: mean R multiplied by sqrt(trade count), used only

    to prune the grid before the expensive OOS replay-MC pass. Not the
    selection objective.
    """
    if not trades:
        return float("-inf")
    mean_r = sum(t.r_multiple for t in trades) / len(trades)
    return mean_r * (len(trades) ** 0.5)


def _replay_mc_summary(
    replay_days: list[ReplayDay],
    *,
    firm: ReplayFirmName,
    n_simulations: int,
    seed: int,
    block_size: int,
    eval_risk: float,
    funded_risk: float,
) -> FirmReplaySummary | None:
    if not any(d.r_multiples for d in replay_days):
        return None
    if firm == "lucidflex":
        result = run_replay_monte_carlo(
            replay_days,
            firm="lucidflex",
            n_simulations=n_simulations,
            seed=seed,
            block_size=block_size,
            lucidflex_eval_risk=eval_risk,
            lucidflex_funded_risk=funded_risk,
        )
    elif firm == "topstep":
        result = run_replay_monte_carlo(
            replay_days,
            firm="topstep",
            n_simulations=n_simulations,
            seed=seed,
            block_size=block_size,
            topstep_eval_risk=eval_risk,
            topstep_funded_risk=funded_risk,
        )
    elif firm in _APEX_DRAWDOWN_VARIANT_BY_FIRM:
        # run_replay_monte_carlo's FirmName is literally "apex"; the EOD vs.
        # intraday distinction is the apex_drawdown_variant kwarg, not a
        # separate firm value there. walk_forward.py keeps them as separate
        # ReplayFirmName entries ("apex_eod"/"apex_intraday") because they are
        # separate products with separate fees/mechanics (see module docstring).
        result = run_replay_monte_carlo(
            replay_days,
            firm="apex",
            n_simulations=n_simulations,
            seed=seed,
            block_size=block_size,
            apex_eval_risk=eval_risk,
            apex_funded_risk=funded_risk,
            apex_drawdown_variant=_APEX_DRAWDOWN_VARIANT_BY_FIRM[firm],
        )
    else:
        raise ValueError(f"unsupported replay firm: {firm}")
    return FirmReplaySummary(
        firm=firm,
        net_ev_mean=result.mean_net_ev,
        net_ev_ci_low=result.ev_ci.low,
        eval_pass_rate=result.eval_pass_rate,
        mean_payouts=result.mean_payouts,
        mean_trader_payouts=result.mean_trader_payouts,
    )


def _evaluate_candidate_oos(
    bars: pd.DataFrame,
    params: ORBParams,
    folds: list[FoldSpec],
    *,
    firms: tuple[ReplayFirmName, ...],
    n_simulations: int,
    block_size: int,
    risk_per_trade_usd: float,
    seed: int,
) -> CandidateResult:
    fold_results: list[FoldOOSResult] = []
    for fold in folds:
        trades, replay_days = _fold_replay_days(
            bars,
            params,
            warmup_start=fold.warmup_start,
            window_start=fold.oos_start,
            window_end=fold.oos_end,
        )
        n = len(trades)
        wins = [t for t in trades if t.r_multiple > 0]
        win_rate = len(wins) / n if n else 0.0
        mean_r = sum(t.r_multiple for t in trades) / n if n else 0.0
        total_r = sum(t.r_multiple for t in trades)

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

        fold_results.append(
            FoldOOSResult(
                fold_index=fold.fold_index,
                trade_count=n,
                win_rate=win_rate,
                mean_r=mean_r,
                total_r=total_r,
                firm_summaries=firm_summaries,
            )
        )

    return CandidateResult(
        params=params,
        is_prop_ev_rank_score=float("nan"),
        fold_results=tuple(fold_results),
        risk_per_trade_usd=risk_per_trade_usd,
    )


def _grid_neighbors(params: ORBParams, grid: list[ORBParams]) -> list[ORBParams]:
    """Grid neighbors: same params except exactly one field differs (Hamming distance 1)."""
    target = _param_dict(params)
    neighbors = []
    for candidate in grid:
        if candidate == params:
            continue
        cand_dict = _param_dict(candidate)
        diff = sum(1 for k in target if target[k] != cand_dict[k])
        if diff == 1:
            neighbors.append(candidate)
    return neighbors


def rank_plateau(
    candidates: list[CandidateResult],
    grid: list[ORBParams],
) -> list[CandidateResult]:
    """Rank admissible candidates by (median EV low CI, worst fold, neighbor stability).

    Neighbor stability = fraction of grid neighbors that are themselves
    admissible; candidates whose neighborhood is also admissible (a plateau)
    outrank an isolated single-point peak with an otherwise identical score.
    Non-admissible candidates are excluded entirely.
    """
    admissible = [c for c in candidates if c.is_admissible()]
    admissible_param_set = {c.params for c in admissible}

    def sort_key(c: CandidateResult) -> tuple[float, float, float]:
        median_low, worst_mean = c.best_admissible_score()  # type: ignore[misc]
        neighbors = _grid_neighbors(c.params, grid)
        stability = (
            sum(1 for n in neighbors if n in admissible_param_set) / len(neighbors) if neighbors else 0.0
        )
        return (median_low, worst_mean, stability)

    return sorted(admissible, key=sort_key, reverse=True)


def _prune_top_k(scored: list[tuple[ORBParams, float]], k: int) -> list[ORBParams]:
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    return [p for p, _ in ranked[:k]]


def run_walk_forward(
    bars: pd.DataFrame,
    param_grid: list[ORBParams],
    folds: list[FoldSpec],
    *,
    top_k_is: int = 40,
    firms: tuple[ReplayFirmName, ...] = REPLAY_FIRMS,
    n_simulations: int = 2_000,
    block_size: int = 5,
    risk_per_trade_usd: float = DEFAULT_RISK_PER_TRADE_USD,
    seed: int = 0,
    max_workers: int | None = None,
) -> list[CandidateResult]:
    """Coarse-rank the full grid on IS windows, prune to top_k_is, then run the

    expensive OOS replay-MC evaluation only on survivors. Returns candidates
    ranked by `rank_plateau` (admissible-only, plateau-preferring).

    If `holdout_start`-bounded `folds` is empty, raises — a walk-forward run
    with zero folds is a caller error, not a silent no-op.
    """
    if not folds:
        raise ValueError("folds must not be empty")
    if not param_grid:
        raise ValueError("param_grid must not be empty")

    is_scored: list[tuple[ORBParams, float]] = []
    for params in param_grid:
        scores = []
        for fold in folds:
            trades, _ = _fold_replay_days(
                bars,
                params,
                warmup_start=fold.warmup_start,
                window_start=fold.is_start,
                window_end=fold.is_end,
            )
            scores.append(_coarse_is_score(trades))
        is_scored.append((params, statistics.fmean(s for s in scores if s != float("-inf")) if any(s != float("-inf") for s in scores) else float("-inf")))

    survivors = _prune_top_k(is_scored, top_k_is)
    is_score_by_hash = {params_hash(p): score for p, score in is_scored}

    results: list[CandidateResult] = []
    if max_workers is not None and max_workers > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(
                    _evaluate_candidate_oos,
                    bars,
                    params,
                    folds,
                    firms=firms,
                    n_simulations=n_simulations,
                    block_size=block_size,
                    risk_per_trade_usd=risk_per_trade_usd,
                    seed=seed,
                )
                for params in survivors
            ]
            for fut in futures:
                results.append(fut.result())
    else:
        for params in survivors:
            results.append(
                _evaluate_candidate_oos(
                    bars,
                    params,
                    folds,
                    firms=firms,
                    n_simulations=n_simulations,
                    block_size=block_size,
                    risk_per_trade_usd=risk_per_trade_usd,
                    seed=seed,
                )
            )

    results = [
        replace(r, is_prop_ev_rank_score=is_score_by_hash.get(params_hash(r.params), float("nan")))
        for r in results
    ]
    return rank_plateau(results, survivors)


# ---------------------------------------------------------------------------
# Holdout guard
# ---------------------------------------------------------------------------


def _holdout_dir(output_dir: Path | None) -> Path:
    return output_dir if output_dir is not None else _HOLDOUT_DEFAULT_DIR


def _sentinel_path(output_dir: Path, params_h: str) -> Path:
    return output_dir / "HOLDOUT_UNLOCKED" / f"{params_h}.lock"


def _record_path(output_dir: Path, params_h: str) -> Path:
    return output_dir / f"holdout_{params_h}.json"


def evaluate_holdout(
    bars: pd.DataFrame,
    params: ORBParams,
    firm: ReplayFirmName,
    *,
    unlock_holdout: bool = False,
    holdout_start: pd.Timestamp | str = HOLDOUT_START,
    holdout_end: pd.Timestamp | str | None = None,
    warmup_months: int = 3,
    n_simulations: int = 10_000,
    block_size: int = 5,
    risk_per_trade_usd: float = DEFAULT_RISK_PER_TRADE_USD,
    seed: int = 0,
    output_dir: Path | None = None,
) -> dict:
    """Run the single, immutable holdout evaluation for one (params, firm) pair.

    Refuses to run unless `unlock_holdout=True`. Refuses a second run for the
    same params-hash by checking for a sentinel file under
    `<output_dir>/HOLDOUT_UNLOCKED/<hash>.lock`. On success, writes an
    immutable JSON record to `<output_dir>/holdout_<hash>.json` and creates
    the sentinel. `output_dir` defaults to `Analysis/output/orb` but is
    overridable for testing (never write test artifacts into the real
    Analysis/output/orb tree).
    """
    if not unlock_holdout:
        raise PermissionError(
            "evaluate_holdout refuses to run without unlock_holdout=True (holdout guard)"
        )

    out_dir = _holdout_dir(output_dir)
    params_h = params_hash(params)
    sentinel = _sentinel_path(out_dir, params_h)
    if sentinel.exists():
        raise PermissionError(
            f"holdout already evaluated for params hash {params_h} "
            f"(sentinel exists at {sentinel}); refusing second run"
        )

    holdout_start_ts = pd.Timestamp(holdout_start)
    holdout_end_ts = pd.Timestamp(holdout_end) if holdout_end is not None else bars.index.max().tz_convert("UTC")
    warmup_start = holdout_start_ts - pd.DateOffset(months=warmup_months)

    trades, replay_days = _fold_replay_days(
        bars,
        params,
        warmup_start=warmup_start,
        window_start=holdout_start_ts,
        window_end=holdout_end_ts,
    )
    n = len(trades)
    wins = [t for t in trades if t.r_multiple > 0]
    win_rate = len(wins) / n if n else 0.0
    mean_r = sum(t.r_multiple for t in trades) / n if n else 0.0

    summary = _replay_mc_summary(
        replay_days,
        firm=firm,
        n_simulations=n_simulations,
        seed=seed,
        block_size=block_size,
        eval_risk=risk_per_trade_usd,
        funded_risk=risk_per_trade_usd,
    )

    record = {
        "params_hash": params_h,
        "params": _param_dict(params),
        "firm": firm,
        "timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "holdout_start": str(holdout_start_ts.date()),
        "holdout_end": str(holdout_end_ts.date()),
        "risk_per_trade_usd": risk_per_trade_usd,
        "trade_count": n,
        "win_rate": win_rate,
        "mean_r": mean_r,
        "replay_mc": None
        if summary is None
        else {
            "net_ev_mean": summary.net_ev_mean,
            "net_ev_ci_low": summary.net_ev_ci_low,
            "eval_pass_rate": summary.eval_pass_rate,
            "mean_payouts": summary.mean_payouts,
            "mean_trader_payouts": summary.mean_trader_payouts,
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    record_path = _record_path(out_dir, params_h)
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(record_path.name, encoding="utf-8")

    return record
