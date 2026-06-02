"""Monte Carlo a TradingView XLSX export through the TopStep target profile.

Block-bootstrap the historical replay-day sequence many times, run each
resampling through `simulate_topstep_trade_replay`, and aggregate. This
estimates the distribution of eval-pass rate, funded-breach rate, and net EV
under plausible reorderings of the same trade history.

Run:
    .venv/bin/python Analysis/scripts/tv_topstep_replay_mc.py \
        --xlsx TVExports/<export>.xlsx \
        --risk-amount 100 \
        --n 10000 \
        --block-size 5
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.tv_trade_loader import load_tv_strategy_replay_days_xlsx
from src.pipeline.replay_monte_carlo import run_replay_monte_carlo
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing, SizingFunction

# Reuse the single-shot probe's catalog-loaded Adaptive sizing for parity
from Analysis.scripts.tv_topstep_replay_probe import (
    compute_replay_stats,
    load_catalog_adaptive_sizing,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--risk-amount", type=float, default=None)
    parser.add_argument("--sheet-name", default=None)
    parser.add_argument("--n", type=int, default=10_000, help="Monte Carlo simulations")
    parser.add_argument(
        "--block-size",
        type=int,
        default=5,
        help="Block bootstrap block size in replay days (1=iid, 5~weekly, 10~biweekly)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--target-length",
        type=int,
        default=None,
        help="Bootstrapped replay length in days; defaults to source length",
    )
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
        raise SystemExit("--fixed-eval-risk and --fixed-funded-risk must be passed together")

    sizing_fn: SizingFunction | None = None
    if args.fixed_eval_risk is not None and args.fixed_funded_risk is not None:
        sizing_fn = FixedSizing(eval_size=args.fixed_eval_risk, funded_size=args.fixed_funded_risk)
    else:
        sizing_fn = load_catalog_adaptive_sizing()

    replay_days = load_tv_strategy_replay_days_xlsx(
        args.xlsx,
        sheet_name=args.sheet_name,
        risk_amount=args.risk_amount,
        include_no_trade_weekdays=not args.no_fill_weekdays,
    )
    if not any(day.r_multiples for day in replay_days):
        raise SystemExit(
            "TradingView export contains no closed trades. "
            "Run the strategy on a trade-producing intraday chart, then export the trade list again."
        )

    stats = compute_replay_stats(replay_days)
    print(
        f"Source: trades={stats.trades} replay_days={stats.replay_days} "
        f"trading_days={stats.trading_days} WR={stats.win_rate:.2%} "
        f"R={stats.avg_win_loss_ratio:.2f} freq={stats.trades_per_replay_day:.2f}/replay_day "
        f"lag10_autocorr={stats.lag10_outcome_autocorr:.2f} profile4={stats.inside_profile4}"
    )

    result = run_replay_monte_carlo(
        replay_days,
        firm="topstep",
        n_simulations=args.n,
        seed=args.seed,
        block_size=args.block_size,
        target_length=args.target_length,
        sizing_fn=sizing_fn,
        topstep_payout_path=TopStepPayoutPath(args.payout_path),
        topstep_use_daily_loss_limit=args.dll,
        topstep_max_back2funded_reactivations=args.back2funded,
        payout_cap=None if args.uncapped else args.payout_cap,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )

    print(
        "MC: "
        f"n={result.n_simulations} block={args.block_size} "
        f"eval_pass={result.eval_pass_rate:.3f} [{result.eval_pass_ci.low:.3f},{result.eval_pass_ci.high:.3f}] "
        f"funded_breach={result.funded_breach_rate:.3f} [{result.funded_breach_ci.low:.3f},{result.funded_breach_ci.high:.3f}] "
        f"breach_after_pass={result.funded_breach_after_pass_rate:.3f} "
        f"max_payout={result.max_payout_rate:.3f} "
        f"mean_payouts={result.mean_payouts:.2f}"
    )
    print(
        "EV: "
        f"mean=${result.mean_net_ev:.0f} median=${result.median_net_ev:.0f} "
        f"stderr=${result.ev_stderr:.0f} "
        f"95% CI=[${result.ev_ci.low:.0f}, ${result.ev_ci.high:.0f}]"
    )


if __name__ == "__main__":
    main()
