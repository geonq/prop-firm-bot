"""Replay a TradingView XLSX export through the TopStep target profile.

Run:
    .venv/bin/python Analysis/scripts/tv_topstep_replay_probe.py \
        --xlsx TVExports/robust_trend_export.xlsx \
        --risk-amount 100
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.tv_trade_loader import load_tv_strategy_replay_days_xlsx
from src.pipeline.topstep_pipeline import TopStepPipelineResult
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import AdaptiveSizing, FixedSizing, SizingFunction
from src.strategies.replay import ReplayDay


CATALOG_CSV = PROJECT_ROOT / "Analysis" / "output" / "target_cell_catalog" / "cells.csv"
PROFILE4_DEFAULT_ADAPTIVE_SIZING = AdaptiveSizing(
    eval_base=150.0,
    funded_base=400.0,
    buffer_full_frac=0.04,
    buffer_floor=0.25,
    post_payout_shrink=1.0,
)


@dataclass(frozen=True)
class ReplayStats:
    trades: int
    replay_days: int
    trading_days: int
    win_rate: float
    avg_win_loss_ratio: float
    trades_per_replay_day: float
    trades_per_trading_day: float
    lag10_outcome_autocorr: float
    inside_profile4: bool


@dataclass(frozen=True)
class TopStepReplayProbeResult:
    stats: ReplayStats
    topstep_result: TopStepPipelineResult


def load_catalog_adaptive_sizing(
    *,
    win_rate: float = 0.45,
    rr_ratio: float = 2.0,
    trades_per_day: int = 3,
    payout_path: str = "topstep_consistency",
) -> AdaptiveSizing:
    """Load the Profile 4 Adaptive sizing params from the catalog output."""
    if CATALOG_CSV.exists():
        with CATALOG_CSV.open() as handle:
            for row in csv.DictReader(handle):
                if (
                    row["study"] == "sizing"
                    and row["sizing"] == "Adaptive"
                    and row["strategy_variant"] == "iid"
                    and row["payout_path"] == payout_path
                    and float(row["win_rate"]) == win_rate
                    and float(row["rr_ratio"]) == rr_ratio
                    and int(row["trades_per_day"]) == trades_per_day
                ):
                    return AdaptiveSizing(
                        eval_base=float(row["adaptive_eval_base"]),
                        funded_base=float(row["adaptive_funded_base"]),
                        buffer_full_frac=float(row["adaptive_buffer_full_frac"]),
                        buffer_floor=float(row["adaptive_buffer_floor"]),
                        post_payout_shrink=float(row["adaptive_post_payout_shrink"]),
                    )
    if (
        win_rate == 0.45
        and rr_ratio == 2.0
        and trades_per_day == 3
        and payout_path == "topstep_consistency"
    ):
        return PROFILE4_DEFAULT_ADAPTIVE_SIZING
    raise KeyError("Profile 4 TopStep Consistency Adaptive sizing row not found")


def run_probe(
    replay_days: Sequence[ReplayDay],
    *,
    sizing_fn: SizingFunction,
    payout_path: TopStepPayoutPath = TopStepPayoutPath.CONSISTENCY,
    use_daily_loss_limit: bool = False,
    max_back2funded_reactivations: int = 3,
    payout_cap: int | None = 5,
    max_combine_days: int = 90,
    max_xfa_days: int = 180,
) -> TopStepReplayProbeResult:
    stats = compute_replay_stats(replay_days)
    result = simulate_topstep_trade_replay(
        replay_days,
        sizing_fn=sizing_fn,
        payout_path=payout_path,
        use_daily_loss_limit=use_daily_loss_limit,
        max_back2funded_reactivations=max_back2funded_reactivations,
        payout_cap=payout_cap,
        max_combine_days=max_combine_days,
        max_xfa_days=max_xfa_days,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )
    return TopStepReplayProbeResult(stats=stats, topstep_result=result)


def load_and_run_probe(
    xlsx_path: str | Path,
    *,
    risk_amount: float | None,
    sheet_name: str | None = None,
    sizing_fn: SizingFunction | None = None,
    include_no_trade_weekdays: bool = True,
    payout_path: TopStepPayoutPath = TopStepPayoutPath.CONSISTENCY,
    use_daily_loss_limit: bool = False,
    max_back2funded_reactivations: int = 3,
    payout_cap: int | None = 5,
) -> tuple[list[ReplayDay], TopStepReplayProbeResult]:
    replay_days = load_tv_strategy_replay_days_xlsx(
        xlsx_path,
        sheet_name=sheet_name,
        risk_amount=risk_amount,
        include_no_trade_weekdays=include_no_trade_weekdays,
    )
    result = run_probe(
        replay_days,
        sizing_fn=sizing_fn or load_catalog_adaptive_sizing(),
        payout_path=payout_path,
        use_daily_loss_limit=use_daily_loss_limit,
        max_back2funded_reactivations=max_back2funded_reactivations,
        payout_cap=payout_cap,
    )
    return replay_days, result


def compute_replay_stats(replay_days: Sequence[ReplayDay]) -> ReplayStats:
    r_multiples = [r for day in replay_days for r in day.r_multiples]
    if not r_multiples:
        raise ValueError("replay contains no trades")
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r < 0]
    trading_days = sum(1 for day in replay_days if day.r_multiples)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    avg_win_loss_ratio = avg_win / avg_loss if avg_loss else float("inf")
    win_rate = len(wins) / len(r_multiples)
    stats = ReplayStats(
        trades=len(r_multiples),
        replay_days=len(replay_days),
        trading_days=trading_days,
        win_rate=win_rate,
        avg_win_loss_ratio=avg_win_loss_ratio,
        trades_per_replay_day=len(r_multiples) / len(replay_days),
        trades_per_trading_day=len(r_multiples) / trading_days if trading_days else 0.0,
        lag10_outcome_autocorr=_outcome_autocorr(r_multiples, lag=10),
        inside_profile4=False,
    )
    return replace(stats, inside_profile4=_inside_profile4(stats))


def _outcome_autocorr(r_multiples: Sequence[float], *, lag: int) -> float:
    outcomes = [1.0 if r > 0 else 0.0 for r in r_multiples if r != 0]
    if len(outcomes) <= lag:
        return 0.0
    x = outcomes[:-lag]
    y = outcomes[lag:]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in x)
    var_y = sum((b - mean_y) ** 2 for b in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x * var_y) ** 0.5


def _inside_profile4(stats: ReplayStats) -> bool:
    return (
        0.40 <= stats.win_rate <= 0.50
        and 1.7 <= stats.avg_win_loss_ratio <= 2.3
        and 2.0 <= stats.trades_per_replay_day <= 4.0
        and stats.lag10_outcome_autocorr <= 0.3
    )


def _print_result(result: TopStepReplayProbeResult) -> None:
    stats = result.stats
    topstep = result.topstep_result
    print(
        "Stats: "
        f"trades={stats.trades} replay_days={stats.replay_days} trading_days={stats.trading_days} "
        f"WR={stats.win_rate:.2%} R={stats.avg_win_loss_ratio:.2f} "
        f"freq={stats.trades_per_replay_day:.2f}/replay_day "
        f"lag10_autocorr={stats.lag10_outcome_autocorr:.2f} "
        f"profile4={stats.inside_profile4}"
    )
    print(
        "TopStep: "
        f"terminal={topstep.terminal_reason} pass={topstep.eval_passed} "
        f"combine_days={topstep.combine_days} xfa_days={topstep.xfa_days} "
        f"payouts={topstep.payout_count} b2f={topstep.back2funded_count} "
        f"paid={topstep.trader_payouts:.0f} net_ev={topstep.net_ev:.0f}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xlsx",
        required=True,
        type=Path,
        help="TradingView Strategy Tester XLSX export",
    )
    parser.add_argument(
        "--risk-amount",
        type=float,
        default=None,
        help="Dollar risk used to derive R if no R column exists",
    )
    parser.add_argument("--sheet-name", default=None)
    parser.add_argument(
        "--payout-path",
        choices=("standard", "consistency"),
        default="consistency",
    )
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
        raise SystemExit(
            "--fixed-eval-risk and --fixed-funded-risk must be passed together"
        )
    sizing_fn: SizingFunction | None = None
    if args.fixed_eval_risk is not None and args.fixed_funded_risk is not None:
        sizing_fn = FixedSizing(
            eval_size=args.fixed_eval_risk,
            funded_size=args.fixed_funded_risk,
        )
    try:
        replay_days, result = load_and_run_probe(
            args.xlsx,
            risk_amount=args.risk_amount,
            sheet_name=args.sheet_name,
            sizing_fn=sizing_fn,
            include_no_trade_weekdays=not args.no_fill_weekdays,
            payout_path=TopStepPayoutPath(args.payout_path),
            use_daily_loss_limit=args.dll,
            max_back2funded_reactivations=args.back2funded,
            payout_cap=None if args.uncapped else args.payout_cap,
        )
    except ValueError as exc:
        if "replay contains no trades" in str(exc):
            raise SystemExit(
                "TradingView export contains no closed trades. "
                "Run the strategy on a trade-producing intraday chart, then export the trade list again."
            ) from exc
        raise
    print(
        f"Loaded {sum(len(day.r_multiples) for day in replay_days)} trades "
        f"across {len(replay_days)} replay weekdays"
    )
    _print_result(result)


if __name__ == "__main__":
    main()
