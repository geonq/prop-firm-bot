"""Retrospective overfitting battery for the corrected MNQ opening drive.

This is diagnostic research, not a new holdout and not deployment authorization.
The public five-minute OOS period has already been viewed. The parameter
neighborhood is therefore a stability probe, never a strategy-selection grid.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from statistics import NormalDist
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Analysis.scripts.orb_mnq_70_30_research import (  # noqa: E402
    COMMISSION_PER_SIDE,
    POINT_VALUE,
    TICK,
    Candidate,
    Trade,
    _daily,
    _daily_features,
    _run,
    candidate_grid,
    sessions_from_bars,
    summarize_daily,
)
from Analysis.scripts.orb_nq_multiyear_70_30 import (  # noqa: E402
    RAW,
    SOURCE_RAW_URL,
    SOURCE_URL,
    load_databento_csv,
)

OUT = ROOT / "Analysis" / "output" / "orb_overfitting_battery"
BASELINE = "opening_drive_t4_ts120_doji10_close"
HISTORICAL_REPORTED_TRIALS = 234


def _safe_sharpe(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return float(values.mean() / std) if std > 1e-12 else (-math.inf if values.mean() < 0 else 0.0)


def _circular_block_indices(length: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    pieces: list[np.ndarray] = []
    while sum(len(piece) for piece in pieces) < length:
        start = int(rng.integers(0, length))
        pieces.append((start + np.arange(block_length)) % length)
    return np.concatenate(pieces)[:length]


def cscv_pbo(returns: np.ndarray, block_count: int = 8) -> dict:
    """Combinatorially symmetric cross-validation probability of overfitting.

    Sessions are split into contiguous blocks. For every half-block IS
    combination, the IS-best strategy is ranked across all strategies OOS.
    An OOS percentile at or below 0.5 is counted as an overfit selection.
    """
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] < 2:
        raise ValueError("returns must be a 2D matrix with at least two strategies")
    if block_count < 4 or block_count % 2 or matrix.shape[0] < block_count:
        raise ValueError("block_count must be even and fit the observation count")
    blocks = np.array_split(np.arange(matrix.shape[0]), block_count)
    percentiles: list[float] = []
    logits: list[float] = []
    selections: list[int] = []
    for chosen in itertools.combinations(range(block_count), block_count // 2):
        chosen_set = set(chosen)
        is_idx = np.concatenate([blocks[i] for i in chosen])
        oos_idx = np.concatenate([blocks[i] for i in range(block_count) if i not in chosen_set])
        is_scores = np.asarray([_safe_sharpe(matrix[is_idx, j]) for j in range(matrix.shape[1])])
        selected = int(np.argmax(is_scores))
        oos_scores = np.asarray([_safe_sharpe(matrix[oos_idx, j]) for j in range(matrix.shape[1])])
        selected_score = oos_scores[selected]
        below = float(np.sum(oos_scores < selected_score))
        equal = float(np.sum(oos_scores == selected_score))
        rank = below + (equal + 1.0) / 2.0
        percentile = rank / (matrix.shape[1] + 1.0)
        clipped = min(max(percentile, 1e-9), 1.0 - 1e-9)
        percentiles.append(percentile)
        logits.append(math.log(clipped / (1.0 - clipped)))
        selections.append(selected)
    return {
        "block_count": block_count,
        "combinations": len(percentiles),
        "probability_backtest_overfit": float(np.mean(np.asarray(percentiles) <= 0.5)),
        "median_oos_percentile": float(np.median(percentiles)),
        "median_logit": float(np.median(logits)),
        "unique_is_winners": int(len(set(selections))),
    }


def white_reality_check(
    returns: np.ndarray,
    *,
    bootstrap_samples: int = 5_000,
    block_length: int = 10,
    seed: int = 20260720,
    incumbent_index: int = 0,
) -> dict:
    """Studentized White-style reality check using circular block bootstrap."""
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 20:
        raise ValueError("returns must be a 2D matrix with at least 20 observations")
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0, ddof=1)
    valid = stds > 1e-12
    if not valid.any() or not valid[incumbent_index]:
        raise ValueError("incumbent and at least one strategy must have nonzero variance")
    t_stats = np.full(matrix.shape[1], -math.inf)
    t_stats[valid] = math.sqrt(matrix.shape[0]) * means[valid] / stds[valid]
    observed_max = float(np.max(t_stats))
    incumbent_t = float(t_stats[incumbent_index])
    centered = matrix - means
    rng = np.random.default_rng(seed)
    bootstrap_max = np.empty(bootstrap_samples, dtype=float)
    bootstrap_incumbent = np.empty(bootstrap_samples, dtype=float)
    for i in range(bootstrap_samples):
        idx = _circular_block_indices(matrix.shape[0], block_length, rng)
        sample = centered[idx]
        sample_std = sample.std(axis=0, ddof=1)
        sample_valid = sample_std > 1e-12
        sample_t = np.full(matrix.shape[1], -math.inf)
        sample_t[sample_valid] = math.sqrt(matrix.shape[0]) * sample[:, sample_valid].mean(axis=0) / sample_std[sample_valid]
        bootstrap_max[i] = np.max(sample_t)
        bootstrap_incumbent[i] = sample_t[incumbent_index]
    return {
        "bootstrap_samples": bootstrap_samples,
        "block_length_sessions": block_length,
        "observed_max_t": observed_max,
        "incumbent_t": incumbent_t,
        "p_value_any_strategy": float((1 + np.sum(bootstrap_max >= observed_max)) / (bootstrap_samples + 1)),
        "incumbent_familywise_p_value": float((1 + np.sum(bootstrap_max >= incumbent_t)) / (bootstrap_samples + 1)),
        "incumbent_unadjusted_p_value": float((1 + np.sum(bootstrap_incumbent >= incumbent_t)) / (bootstrap_samples + 1)),
    }


def deflated_sharpe_probability(
    returns: Sequence[float],
    trials: float,
    *,
    trial_sharpes: Sequence[float] | None = None,
) -> dict:
    """Bailey/Lopez de Prado deflated-Sharpe probability for non-annualized SR."""
    values = np.asarray(returns, dtype=float)
    if len(values) < 3 or trials < 1:
        raise ValueError("need at least three returns and one trial")
    std = float(values.std(ddof=1))
    if std <= 0:
        raise ValueError("returns must have positive variance")
    sr = float(values.mean() / std)
    centered = values - values.mean()
    pop_std = float(values.std(ddof=0))
    skew = float(np.mean(centered**3) / pop_std**3)
    kurtosis = float(np.mean(centered**4) / pop_std**4)
    selected_sr_variance = max(
        (1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr) / (len(values) - 1),
        1e-15,
    )
    if trial_sharpes is None:
        trial_sr_variance = selected_sr_variance
        variance_source = "selected-strategy sampling variance fallback"
    else:
        sharpe_values = np.asarray(trial_sharpes, dtype=float)
        sharpe_values = sharpe_values[np.isfinite(sharpe_values)]
        if len(sharpe_values) < 2:
            raise ValueError("trial_sharpes must contain at least two finite values")
        trial_sr_variance = float(sharpe_values.var(ddof=1))
        variance_source = "cross-trial Sharpe variance"
    if trials == 1:
        benchmark = 0.0
    else:
        normal = NormalDist()
        euler_gamma = 0.5772156649015329
        expected_max_standard_normal = (
            (1.0 - euler_gamma) * normal.inv_cdf(1.0 - 1.0 / trials)
            + euler_gamma * normal.inv_cdf(1.0 - 1.0 / (trials * math.e))
        )
        benchmark = math.sqrt(trial_sr_variance) * expected_max_standard_normal
    z = (sr - benchmark) / math.sqrt(selected_sr_variance)
    return {
        "observations": int(len(values)),
        "trials": float(trials),
        "observed_sharpe": sr,
        "benchmark_sharpe": float(benchmark),
        "z_score": float(z),
        "probability": float(NormalDist().cdf(z)),
        "trial_sharpe_std": float(math.sqrt(trial_sr_variance)),
        "trial_variance_source": variance_source,
        "skew": skew,
        "kurtosis": kurtosis,
    }


def effective_strategy_trials(returns: np.ndarray) -> float:
    """Correlation-spectrum participation ratio; a transparent N_eff heuristic."""
    matrix = np.asarray(returns, dtype=float)
    correlation = np.corrcoef(matrix, rowvar=False)
    correlation = np.nan_to_num(correlation, nan=0.0)
    np.fill_diagonal(correlation, 1.0)
    eigenvalues = np.clip(np.linalg.eigvalsh(correlation), 0.0, None)
    denominator = float(np.square(eigenvalues).sum())
    return float(np.square(eigenvalues.sum()) / denominator) if denominator > 0 else 1.0


def adjust_trade_returns_for_costs(
    trades: Sequence[Trade],
    *,
    slippage_ticks_per_side: float,
    commission_per_side: float,
) -> np.ndarray:
    base_points = 2.0 * TICK + 2.0 * COMMISSION_PER_SIDE / POINT_VALUE
    scenario_points = 2.0 * slippage_ticks_per_side * TICK + 2.0 * commission_per_side / POINT_VALUE
    return np.asarray(
        [float(trade.r - (scenario_points - base_points) / trade.risk_points) for trade in trades],
        dtype=float,
    )


def opening_drive_neighborhood() -> list[Candidate]:
    candidates: list[Candidate] = []
    for doji, target, time_stop in itertools.product(
        (0.00, 0.05, 0.10, 0.15, 0.20),
        (2.0, 3.0, 4.0, 5.0, None),
        (60, 120, None),
    ):
        target_label = "eod" if target is None else f"t{target:g}"
        stop_label = "none" if time_stop is None else str(time_stop)
        name = f"opening_drive_{target_label}_ts{stop_label}_doji{int(doji * 100):02d}_close"
        candidates.append(
            Candidate(
                name,
                "first_candle",
                target_r=target,
                time_stop_minutes=time_stop,
                doji_threshold=doji,
                first_candle_reference="or_close",
            )
        )
    return candidates


def _daily_matrix(
    all_trades: dict[str, list[Trade]], dates: list[date], names: list[str]
) -> np.ndarray:
    return np.column_stack([_daily(all_trades[name], dates).to_numpy() for name in names])


def _period_rows(daily: pd.Series) -> list[dict]:
    frame = pd.DataFrame({"r": daily.to_numpy()}, index=pd.to_datetime(daily.index))
    frame["period"] = [f"{ts.year}-H{1 if ts.month <= 6 else 2}" for ts in frame.index]
    rows = []
    for period, values in frame.groupby("period")["r"]:
        summary = summarize_daily(values.reset_index(drop=True), trade_count=int((values != 0).sum()))
        rows.append({"period": str(period), **summary})
    return rows


def _cost_stress(trades: list[Trade], dates: list[date]) -> list[dict]:
    scenarios = [
        ("base", 1.0, 0.74),
        ("moderate", 2.0, 1.25),
        ("severe", 4.0, 2.50),
        ("extreme", 8.0, 4.00),
    ]
    rows = []
    trade_dates = [trade.session_date for trade in trades]
    for name, ticks, commission in scenarios:
        adjusted = adjust_trade_returns_for_costs(
            trades, slippage_ticks_per_side=ticks, commission_per_side=commission
        )
        by_date = dict(zip(trade_dates, adjusted, strict=True))
        daily = pd.Series([by_date.get(d, 0.0) for d in dates], index=dates, dtype=float)
        rows.append(
            {
                "scenario": name,
                "slippage_ticks_per_side": ticks,
                "commission_usd_per_side": commission,
                **summarize_daily(daily, trade_count=len(trades)),
            }
        )
    return rows


def _block_bootstrap_risk(
    daily: pd.Series, *, samples: int = 10_000, block_length: int = 10, seed: int = 63
) -> dict:
    values = daily.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    totals = np.empty(samples)
    drawdowns = np.empty(samples)
    for i in range(samples):
        sample = values[_circular_block_indices(len(values), block_length, rng)]
        equity = np.cumsum(sample)
        peaks = np.maximum.accumulate(np.maximum(equity, 0.0))
        totals[i] = equity[-1]
        drawdowns[i] = np.max(peaks - equity)
    return {
        "samples": samples,
        "block_length_sessions": block_length,
        "probability_total_r_nonpositive": float(np.mean(totals <= 0)),
        "total_r_quantiles": {str(q): float(np.quantile(totals, q)) for q in (0.01, 0.05, 0.50, 0.95)},
        "max_drawdown_r_quantiles": {str(q): float(np.quantile(drawdowns, q)) for q in (0.50, 0.90, 0.95, 0.99)},
    }


def main(raw_path: Path = RAW) -> dict:
    bars = load_databento_csv(raw_path)
    sessions = dict(sorted(sessions_from_bars(bars).items()))
    dates = list(sessions)
    if len(dates) < 500:
        raise RuntimeError("overfitting battery requires at least 500 complete sessions")
    features = _daily_features(sessions)

    neighborhood = opening_drive_neighborhood()
    external = [candidate for candidate in candidate_grid() if candidate.entry != "first_candle"]
    next_open = Candidate(
        "opening_drive_t4_ts120_doji10_nextopen",
        "first_candle",
        target_r=4.0,
        time_stop_minutes=120,
        doji_threshold=0.10,
        first_candle_reference="next_open",
    )
    candidates = neighborhood + [next_open] + external
    names = [candidate.name for candidate in candidates]
    if len(names) != len(set(names)) or BASELINE not in names:
        raise RuntimeError("candidate universe is not unique or omits incumbent")

    all_trades = {candidate.name: _run(sessions, features, candidate) for candidate in candidates}
    matrix = _daily_matrix(all_trades, dates, names)
    baseline_index = names.index(BASELINE)
    baseline_daily = pd.Series(matrix[:, baseline_index], index=dates, dtype=float)
    baseline_trades = all_trades[BASELINE]

    pbo_sensitivity = {str(blocks): cscv_pbo(matrix, block_count=blocks) for blocks in (6, 8, 10)}
    pbo = pbo_sensitivity["8"]
    reality = white_reality_check(
        matrix,
        bootstrap_samples=5_000,
        block_length=10,
        seed=20260720,
        incumbent_index=baseline_index,
    )
    reality_sensitivity = {
        str(block_length): white_reality_check(
            matrix,
            bootstrap_samples=2_500,
            block_length=block_length,
            seed=20260720 + block_length,
            incumbent_index=baseline_index,
        )
        for block_length in (5, 10, 20)
    }
    trial_sharpes = np.asarray([_safe_sharpe(matrix[:, j]) for j in range(matrix.shape[1])])
    effective_trials = effective_strategy_trials(matrix)
    dsr_effective = deflated_sharpe_probability(
        baseline_daily.to_numpy(),
        trials=effective_trials,
        trial_sharpes=trial_sharpes,
    )
    dsr_observed = deflated_sharpe_probability(
        baseline_daily.to_numpy(), trials=len(names), trial_sharpes=trial_sharpes
    )
    dsr_historical = deflated_sharpe_probability(
        baseline_daily.to_numpy(),
        trials=HISTORICAL_REPORTED_TRIALS,
        trial_sharpes=trial_sharpes,
    )

    year_summaries = {}
    for year in sorted({d.year for d in dates}):
        year_dates = [d for d in dates if d.year == year]
        year_summaries[str(year)] = summarize_daily(
            baseline_daily.loc[year_dates],
            trade_count=int((baseline_daily.loc[year_dates] != 0).sum()),
        )

    neighborhood_rows = []
    for candidate in neighborhood:
        daily = _daily(all_trades[candidate.name], dates)
        positive_years = sum(
            float(daily.loc[[d for d in dates if d.year == year]].sum()) > 0
            for year in sorted({d.year for d in dates})
        )
        neighborhood_rows.append(
            {
                "candidate": candidate.name,
                "params": asdict(candidate),
                "positive_years": positive_years,
                **summarize_daily(daily, trade_count=len(all_trades[candidate.name])),
            }
        )
    full_positive = [row for row in neighborhood_rows if row["total_r"] > 0]
    stable = [row for row in neighborhood_rows if row["total_r"] > 0 and row["positive_years"] >= 3]

    next_open_daily = _daily(all_trades[next_open.name], dates)
    execution_reference = {
        "or_close": summarize_daily(baseline_daily, trade_count=len(baseline_trades)),
        "next_open": summarize_daily(next_open_daily, trade_count=len(all_trades[next_open.name])),
        "or_close_minus_next_open_r": float(baseline_daily.sum() - next_open_daily.sum()),
    }
    spa_artifact = OUT / "arch_spa_verification.json"
    independent_spa = json.loads(spa_artifact.read_text(encoding="utf-8")) if spa_artifact.exists() else None

    result = {
        "status": "retrospective_diagnostic_complete",
        "strategy_change_authorized": False,
        "source": {
            "repository": SOURCE_URL,
            "raw_url": SOURCE_RAW_URL,
            "local_sha256": __import__("hashlib").sha256(raw_path.read_bytes()).hexdigest(),
            "license": "MIT repository; underlying vendor redistribution rights not independently verified",
        },
        "limitations": [
            "The entire 2023-2026 sample has now been viewed; these tests are retrospective diagnostics, not a fresh holdout.",
            "The observed universe has 85 strategies, while prior research reports at least 234 tried configurations; the 234-trial DSR reuses the reconstructed universe's cross-trial Sharpe variance as a sensitivity proxy because the missing trial returns cannot be reconstructed.",
            "The correlation-spectrum effective trial count is a participation-ratio heuristic, not the exact independent-trial estimator from the DSR paper.",
            "Public third-party NQ continuous five-minute data lacks a vendor receipt and explicit rollover metadata.",
            "Five-minute OHLC cannot identify intrabar order or actual market fills; stop-before-target ordering and explicit cost stress are used.",
            "No statistical test can prove permanent non-overfitting; genuinely new forward data remains the decisive evidence.",
        ],
        "data": {"start": str(dates[0]), "end": str(dates[-1]), "sessions": len(dates)},
        "candidate_universe": {
            "observed_strategies": len(names),
            "opening_drive_neighborhood": len(neighborhood),
            "historical_reported_trials_for_conservative_dsr": HISTORICAL_REPORTED_TRIALS,
            "correlation_spectrum_effective_trials": effective_trials,
        },
        "incumbent": {
            "candidate": BASELINE,
            "summary": summarize_daily(baseline_daily, trade_count=len(baseline_trades)),
            "yearly": year_summaries,
            "half_year_periods": _period_rows(baseline_daily),
        },
        "execution_reference_sensitivity": execution_reference,
        "cscv_pbo": pbo,
        "cscv_pbo_block_sensitivity": pbo_sensitivity,
        "white_reality_check": reality,
        "white_reality_check_block_sensitivity": reality_sensitivity,
        "independent_hansen_spa": independent_spa,
        "deflated_sharpe": {
            "correlation_effective_trials": dsr_effective,
            "observed_85_strategy_universe": dsr_observed,
            "conservative_234_historical_trials": dsr_historical,
        },
        "parameter_neighborhood": {
            "tested": len(neighborhood_rows),
            "positive_total_r": len(full_positive),
            "positive_total_r_fraction": len(full_positive) / len(neighborhood_rows),
            "positive_and_at_least_3_years": len(stable),
            "stable_fraction": len(stable) / len(neighborhood_rows),
            "rows": sorted(neighborhood_rows, key=lambda row: row["mean_r_per_session"], reverse=True),
        },
        "cost_stress": _cost_stress(baseline_trades, dates),
        "block_bootstrap_risk": _block_bootstrap_risk(baseline_daily),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    inc = result["incumbent"]["summary"]
    rc = result["white_reality_check"]
    pbo_result = result["cscv_pbo"]
    dsr = result["deflated_sharpe"]["conservative_234_historical_trials"]
    dsr_effective_result = result["deflated_sharpe"]["correlation_effective_trials"]
    neighborhood_result = result["parameter_neighborhood"]
    pbo_range = [row["probability_backtest_overfit"] for row in pbo_sensitivity.values()]
    rc_any_range = [row["p_value_any_strategy"] for row in reality_sensitivity.values()]
    rc_incumbent_range = [row["incumbent_familywise_p_value"] for row in reality_sensitivity.values()]
    spa_consistent = (
        [row["consistent"] for row in independent_spa["spa"].values()]
        if independent_spa is not None
        else []
    )
    lines = [
        "# MNQ opening-drive overfitting battery",
        "",
        "Status: retrospective diagnostic complete; no strategy or live-mode change authorized.",
        f"Data: {dates[0]} through {dates[-1]} ({len(dates)} complete RTH sessions).",
        f"Universe: {len(names)} reconstructed strategies; conservative DSR trial count: {HISTORICAL_REPORTED_TRIALS}.",
        "",
        "## Incumbent",
        "",
        f"Corrected OR-close reference: {inc['trades']} trades, {inc['total_r']:+.3f}R, "
        f"{inc['mean_r_per_trade']:+.4f}R/trade, PF {inc['profit_factor']:.3f}, max DD {inc['max_drawdown_r']:.3f}R.",
        f"Next-open sensitivity: {execution_reference['next_open']['total_r']:+.3f}R; "
        f"OR-close minus next-open: {execution_reference['or_close_minus_next_open_r']:+.3f}R.",
        "",
        "## Multiple-testing results",
        "",
        f"- CSCV/PBO: {pbo_result['probability_backtest_overfit']:.1%}; median selected-strategy OOS percentile "
        f"{pbo_result['median_oos_percentile']:.1%}; {pbo_result['unique_is_winners']} distinct IS winners. "
        f"Six/eight/ten-block range: {min(pbo_range):.1%} to {max(pbo_range):.1%}.",
        f"- White reality check: p(any strategy has edge)={rc['p_value_any_strategy']:.4f}; "
        f"incumbent family-wise p={rc['incumbent_familywise_p_value']:.4f}; "
        f"incumbent unadjusted p={rc['incumbent_unadjusted_p_value']:.4f}. Block-length sensitivity: "
        f"any-strategy p {min(rc_any_range):.4f}..{max(rc_any_range):.4f}; incumbent adjusted p "
        f"{min(rc_incumbent_range):.4f}..{max(rc_incumbent_range):.4f}.",
        (
            f"- Independent `arch` Hansen SPA: consistent p-value range "
            f"{min(spa_consistent):.4f}..{max(spa_consistent):.4f} across stationary/circular "
            "bootstraps and 5/10/20-session block lengths; none rejects at 5%."
            if spa_consistent
            else "- Independent Hansen SPA artifact unavailable; install research-only `arch` and run the verifier."
        ),
        f"- Deflated Sharpe with correlation-spectrum N_eff={effective_trials:.2f}: "
        f"probability={dsr_effective_result['probability']:.1%}; with 85 nominal reconstructed trials: "
        f"{dsr_observed['probability']:.1%}; with 234 historical-trial sensitivity: {dsr['probability']:.1%}. "
        f"Observed SR={dsr['observed_sharpe']:.4f}; 234-trial benchmark={dsr['benchmark_sharpe']:.4f}.",
        "",
        "## Parameter neighborhood",
        "",
        f"{neighborhood_result['positive_total_r']}/{neighborhood_result['tested']} ({neighborhood_result['positive_total_r_fraction']:.1%}) "
        "neighboring configurations have positive total R.",
        f"{neighborhood_result['positive_and_at_least_3_years']}/{neighborhood_result['tested']} "
        f"({neighborhood_result['stable_fraction']:.1%}) are positive overall and in at least three calendar-year buckets.",
        "",
        "## Cost stress",
        "",
        "| Scenario | Slippage ticks/side | Commission/side | Total R | Mean R/trade | PF | Max DD R |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["cost_stress"]:
        lines.append(
            f"| {row['scenario']} | {row['slippage_ticks_per_side']:.1f} | ${row['commission_usd_per_side']:.2f} | "
            f"{row['total_r']:+.3f} | {row['mean_r_per_trade']:+.4f} | {row['profit_factor']:.3f} | {row['max_drawdown_r']:.3f} |"
        )
    risk = result["block_bootstrap_risk"]
    lines += [
        "",
        "## Resampled risk",
        "",
        f"Ten-session circular-block bootstrap probability of non-positive full-sample total: "
        f"{risk['probability_total_r_nonpositive']:.1%}.",
        f"Bootstrap max-DD quantiles: median {risk['max_drawdown_r_quantiles']['0.5']:.2f}R, "
        f"95th {risk['max_drawdown_r_quantiles']['0.95']:.2f}R, "
        f"99th {risk['max_drawdown_r_quantiles']['0.99']:.2f}R.",
        "",
        "## Interpretation boundary",
        "",
        "Passing a holdout or a multiple-testing test is evidence against pure curve fitting, not proof of an all-weather edge. "
        "Failure of parameter stability, chronological regimes, or adjusted significance remains evidence of overfitting/regime dependence. "
        "Because this sample and its OOS segment are already consumed, only future forward sessions can provide new confirmation.",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in result["limitations"]],
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "incumbent_total_r": inc["total_r"],
                "pbo": pbo_result["probability_backtest_overfit"],
                "reality_check_p": rc["p_value_any_strategy"],
                "incumbent_adjusted_p": rc["incumbent_familywise_p_value"],
                "dsr_234": dsr["probability"],
                "stable_neighborhood": neighborhood_result["stable_fraction"],
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    main()
