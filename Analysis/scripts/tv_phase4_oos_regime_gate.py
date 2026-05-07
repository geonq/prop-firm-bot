"""Strict Phase 4 OOS and volatility-regime gate for TradingView exports.

This gate intentionally treats historical XLSX backtests as candidate screens,
not proof. A candidate must survive:

1. Full raw Profile 4 distribution check.
2. Chronological train/OOS split, with the newer holdout checked separately.
3. Contiguous chronological folds.
4. External volatility-regime slices from a CSV.

The volatility-regime CSV is strict by default because a TradingView trade list
does not contain enough exogenous market information to know whether a strategy
works across future volatility environments.

CSV schema:
    session_date,vol_profile

or:
    session_date,realized_vol

If `vol_profile` is missing, `realized_vol` is bucketed into low/mid/high
terciles. Dates must match replay session dates after the TV loader has filled
no-trade weekdays.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from Analysis.scripts.tv_topstep_replay_probe import load_catalog_adaptive_sizing
from src.data.tv_trade_loader import load_tv_strategy_replay_days_xlsx
from src.pipeline.replay_monte_carlo import run_replay_monte_carlo
from src.pipeline.replay_validation import (
    ValidationGateConfig,
    ValidationSliceResult,
    chronological_folds,
    chronological_train_oos_split,
    evaluate_validation_slice,
    filter_replay_days_by_dates,
)
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing, SizingFunction
from src.strategies.replay import ReplayDay


@dataclass(frozen=True)
class VolRegimeMap:
    by_date: dict[date, str]
    source: str


def load_vol_regime_csv(path: str | Path) -> VolRegimeMap:
    """Load external per-session volatility profiles."""
    with Path(path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("volatility-regime CSV is empty")

    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        normalized_rows.append({_normalize_header(k): (v or "").strip() for k, v in row.items()})

    date_key = _first_present(normalized_rows[0], ("session_date", "date", "trading_day"))
    profile_key = _first_present(
        normalized_rows[0],
        ("vol_profile", "volatility_profile", "regime", "vol_regime"),
        required=False,
    )
    realized_vol_key = _first_present(
        normalized_rows[0],
        ("realized_vol", "realized_volatility", "atr_pct", "volatility"),
        required=False,
    )

    if profile_key is None and realized_vol_key is None:
        raise ValueError("CSV needs vol_profile or realized_vol column")

    if profile_key is not None:
        return VolRegimeMap(
            by_date={
                date.fromisoformat(row[date_key]): row[profile_key].lower()
                for row in normalized_rows
                if row.get(date_key) and row.get(profile_key)
            },
            source="vol_profile",
        )

    assert realized_vol_key is not None
    vol_rows = [
        (date.fromisoformat(row[date_key]), float(row[realized_vol_key]))
        for row in normalized_rows
        if row.get(date_key) and row.get(realized_vol_key)
    ]
    if not vol_rows:
        raise ValueError("CSV contains no realized_vol values")

    sorted_values = sorted(value for _, value in vol_rows)
    low_cut = _quantile(sorted_values, 1 / 3)
    high_cut = _quantile(sorted_values, 2 / 3)
    by_date = {}
    for session_date, value in vol_rows:
        if value <= low_cut:
            by_date[session_date] = "low"
        elif value >= high_cut:
            by_date[session_date] = "high"
        else:
            by_date[session_date] = "mid"
    return VolRegimeMap(by_date=by_date, source="realized_vol_terciles")


def build_validation_slices(
    replay_days: Sequence[ReplayDay],
    *,
    train_fraction: float,
    fold_count: int,
    vol_regimes: VolRegimeMap | None,
    required_vol_profiles: tuple[str, ...],
) -> tuple[tuple[str, str, tuple[ReplayDay, ...]], list[str]]:
    """Build named validation slices and collect strict setup failures."""
    days = tuple(replay_days)
    setup_failures: list[str] = []
    train, oos = chronological_train_oos_split(days, train_fraction=train_fraction)
    slices: list[tuple[str, str, tuple[ReplayDay, ...]]] = [
        ("full", "full", days),
        ("train", "train", train),
        ("oos_holdout", "oos", oos),
    ]
    for index, fold_days in enumerate(chronological_folds(days, fold_count=fold_count), start=1):
        slices.append((f"fold_{index}", "fold", fold_days))

    if vol_regimes is None:
        setup_failures.append("missing external volatility-regime CSV")
        return tuple(slices), setup_failures

    replay_dates = {day.session_date for day in days}
    traded_replay_dates = {day.session_date for day in days if day.r_multiples}
    vol_by_date = _carry_forward_profiles(vol_regimes.by_date, replay_dates)
    missing_dates = sorted(traded_replay_dates - set(vol_by_date))
    if missing_dates:
        setup_failures.append(
            "volatility-regime CSV missing "
            f"{len(missing_dates)} traded replay dates; first={missing_dates[0].isoformat()}"
        )

    profiles_by_date: dict[str, set[date]] = defaultdict(set)
    for session_date, profile in vol_by_date.items():
        if session_date in replay_dates:
            profiles_by_date[profile.lower()].add(session_date)

    for profile in required_vol_profiles:
        normalized = profile.lower()
        if normalized not in profiles_by_date:
            setup_failures.append(f"missing required volatility profile: {normalized}")
            continue
        regime_days = filter_replay_days_by_dates(days, profiles_by_date[normalized])
        slices.append((f"vol_{normalized}", "vol_regime", regime_days))

    return tuple(slices), setup_failures


def run_oos_regime_gate(
    replay_days: Sequence[ReplayDay],
    *,
    sizing_fn: SizingFunction,
    gate: ValidationGateConfig,
    train_fraction: float,
    fold_count: int,
    vol_regimes: VolRegimeMap | None,
    required_vol_profiles: tuple[str, ...],
    mc_n: int,
    mc_seed: int,
    block_size: int,
    payout_path: TopStepPayoutPath,
    back2funded: int,
    payout_cap: int | None,
    use_daily_loss_limit: bool,
) -> tuple[list[ValidationSliceResult], list[str]]:
    slices, setup_failures = build_validation_slices(
        replay_days,
        train_fraction=train_fraction,
        fold_count=fold_count,
        vol_regimes=vol_regimes,
        required_vol_profiles=required_vol_profiles,
    )

    results: list[ValidationSliceResult] = []
    for index, (label, kind, slice_days) in enumerate(slices):
        mc_result = None
        if mc_n > 0 and any(day.r_multiples for day in slice_days):
            mc_result = run_replay_monte_carlo(
                slice_days,
                firm="topstep",
                n_simulations=mc_n,
                seed=mc_seed + index * 10_000,
                block_size=block_size,
                sizing_fn=sizing_fn,
                topstep_payout_path=payout_path,
                topstep_max_back2funded_reactivations=back2funded,
                payout_cap=payout_cap,
                topstep_use_daily_loss_limit=use_daily_loss_limit,
                eval_cost_per_trade=5.0,
                funded_cost_per_trade=5.0,
            )
        results.append(
            evaluate_validation_slice(
                label=label,
                kind=kind,  # type: ignore[arg-type]
                replay_days=slice_days,
                gate=gate,
                mc_result=mc_result,
            )
        )
    return results, setup_failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--risk-amount", type=float, default=None)
    parser.add_argument("--sheet-name", default=None)
    parser.add_argument("--vol-regime-csv", type=Path, default=None)
    parser.add_argument(
        "--required-vol-profiles",
        default="low,mid,high",
        help="Comma-separated volatility profiles that must each pass",
    )
    parser.add_argument("--allow-missing-vol-regimes", action="store_true")
    parser.add_argument("--train-fraction", type=float, default=0.60)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--min-replay-days", type=int, default=40)
    parser.add_argument("--min-trading-days", type=int, default=20)
    parser.add_argument("--mc-n", type=int, default=1_000)
    parser.add_argument("--block-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-ev-ci-low", type=float, default=0.0)
    parser.add_argument("--min-eval-pass", type=float, default=0.0)
    parser.add_argument("--max-breach-after-pass", type=float, default=1.0)
    parser.add_argument("--payout-path", choices=("standard", "consistency"), default="consistency")
    parser.add_argument("--back2funded", type=int, default=3)
    parser.add_argument("--payout-cap", type=int, default=5)
    parser.add_argument("--uncapped", action="store_true")
    parser.add_argument("--dll", action="store_true")
    parser.add_argument("--fixed-eval-risk", type=float, default=None)
    parser.add_argument("--fixed-funded-risk", type=float, default=None)
    parser.add_argument("--no-fill-weekdays", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if (args.fixed_eval_risk is None) != (args.fixed_funded_risk is None):
        raise SystemExit("--fixed-eval-risk and --fixed-funded-risk must be passed together")

    sizing_fn: SizingFunction
    if args.fixed_eval_risk is not None:
        sizing_fn = FixedSizing(
            eval_size=args.fixed_eval_risk,
            funded_size=args.fixed_funded_risk,
        )
    else:
        sizing_fn = load_catalog_adaptive_sizing()

    replay_days = load_tv_strategy_replay_days_xlsx(
        args.xlsx,
        sheet_name=args.sheet_name,
        risk_amount=args.risk_amount,
        include_no_trade_weekdays=not args.no_fill_weekdays,
    )
    vol_regimes = load_vol_regime_csv(args.vol_regime_csv) if args.vol_regime_csv else None
    required_profiles = tuple(
        item.strip().lower()
        for item in args.required_vol_profiles.split(",")
        if item.strip()
    )

    gate = ValidationGateConfig(
        min_trades=args.min_trades,
        min_replay_days=args.min_replay_days,
        min_trading_days=args.min_trading_days,
        min_ev_ci_low=args.min_ev_ci_low,
        min_eval_pass_rate=args.min_eval_pass,
        max_funded_breach_after_pass_rate=args.max_breach_after_pass,
    )
    results, setup_failures = run_oos_regime_gate(
        replay_days,
        sizing_fn=sizing_fn,
        gate=gate,
        train_fraction=args.train_fraction,
        fold_count=args.folds,
        vol_regimes=vol_regimes,
        required_vol_profiles=required_profiles,
        mc_n=args.mc_n,
        mc_seed=args.seed,
        block_size=args.block_size,
        payout_path=TopStepPayoutPath(args.payout_path),
        back2funded=args.back2funded,
        payout_cap=None if args.uncapped else args.payout_cap,
        use_daily_loss_limit=args.dll,
    )

    if setup_failures and args.allow_missing_vol_regimes:
        setup_failures = []

    print("Phase4 OOS/regime gate")
    print(
        f"source={args.xlsx} slices={len(results)} mc_n={args.mc_n} "
        f"block={args.block_size} vol_source={vol_regimes.source if vol_regimes else 'missing'}"
    )
    for result in results:
        _print_slice(result)
    for failure in setup_failures:
        print(f"SETUP_FAIL {failure}")

    passed = not setup_failures and all(result.passed for result in results)
    print(f"FINAL {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(1)


def _print_slice(result: ValidationSliceResult) -> None:
    stats = result.stats
    mc = result.mc_result
    status = "PASS" if result.passed else "FAIL"
    base = (
        f"{status} {result.label} kind={result.kind} "
        f"trades={stats.trades} days={stats.replay_days} trading_days={stats.trading_days} "
        f"WR={stats.win_rate:.2%} R={stats.avg_win_loss_ratio:.2f} "
        f"freq={stats.trades_per_replay_day:.2f} "
        f"lag10={stats.lag10_outcome_autocorr:.2f} profile4={stats.inside_profile4}"
    )
    if mc is not None:
        base += (
            f" ev_ci_low={mc.ev_ci.low:.0f} eval_pass={mc.eval_pass_rate:.3f} "
            f"breach_after_pass={mc.funded_breach_after_pass_rate:.3f}"
        )
    print(base)
    for failure in result.failures:
        print(f"  - {failure}")


def _first_present(
    row: dict[str, str],
    candidates: tuple[str, ...],
    *,
    required: bool = True,
) -> str | None:
    for candidate in candidates:
        normalized = _normalize_header(candidate)
        if normalized in row:
            return normalized
    if required:
        raise ValueError(f"CSV missing required column; tried {candidates}")
    return None


def _normalize_header(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").replace(" ", "_").split("_"))


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute quantile of empty values")
    index = (len(sorted_values) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _carry_forward_profiles(
    by_date: dict[date, str],
    target_dates: set[date],
) -> dict[date, str]:
    """Map target dates to same-day or most recent prior volatility profile."""
    out: dict[date, str] = {}
    sorted_source = sorted(by_date)
    if not sorted_source:
        return out
    source_index = 0
    current_profile: str | None = None
    for target_date in sorted(target_dates):
        while source_index < len(sorted_source) and sorted_source[source_index] <= target_date:
            current_profile = by_date[sorted_source[source_index]]
            source_index += 1
        if current_profile is not None:
            out[target_date] = current_profile
    return out


if __name__ == "__main__":
    main()
