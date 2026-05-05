"""Replay a TradingView XLSX export through LucidFlex risk sweeps.

Run:
    .venv/bin/python Analysis/scripts/tv_lucidflex_replay_probe.py \
        --xlsx TVExports/strategy_export.xlsx \
        --risk-amount 100 \
        --eval-risks 200,250,300 \
        --funded-risks 100,125,150
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.tv_trade_loader import load_tv_strategy_replay_days_xlsx
from src.pipeline.lucidflex_pipeline import LucidFlexPipelineResult
from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.strategies.replay import ReplayDay


DEFAULT_EVAL_RISKS = (200.0, 250.0, 300.0)
DEFAULT_FUNDED_RISKS = (100.0, 125.0, 150.0)


@dataclass(frozen=True)
class ReplayProbeRow:
    eval_risk: float
    funded_risk: float
    terminal_reason: str
    eval_passed: bool
    eval_days: int
    funded_days: int
    payout_count: int
    trader_payouts: float
    net_ev: float


def run_probe(
    replay_days: Sequence[ReplayDay],
    *,
    eval_risks: Sequence[float] = DEFAULT_EVAL_RISKS,
    funded_risks: Sequence[float] = DEFAULT_FUNDED_RISKS,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
) -> list[ReplayProbeRow]:
    """Run one historical trade sequence through a LucidFlex risk grid."""
    rows: list[ReplayProbeRow] = []
    for eval_risk in eval_risks:
        for funded_risk in funded_risks:
            result = simulate_lucidflex_trade_replay(
                replay_days,
                eval_risk=eval_risk,
                funded_risk=funded_risk,
                max_eval_days=max_eval_days,
                max_funded_days=max_funded_days,
            )
            rows.append(_to_row(eval_risk, funded_risk, result))
    return sorted(rows, key=lambda row: row.net_ev, reverse=True)


def load_and_run_probe(
    xlsx_path: str | Path,
    *,
    risk_amount: float,
    eval_risks: Sequence[float] = DEFAULT_EVAL_RISKS,
    funded_risks: Sequence[float] = DEFAULT_FUNDED_RISKS,
    sheet_name: str | None = None,
    include_no_trade_weekdays: bool = True,
    max_eval_days: int = 90,
    max_funded_days: int = 180,
) -> tuple[list[ReplayDay], list[ReplayProbeRow]]:
    replay_days = load_tv_strategy_replay_days_xlsx(
        xlsx_path,
        sheet_name=sheet_name,
        risk_amount=risk_amount,
        include_no_trade_weekdays=include_no_trade_weekdays,
    )
    rows = run_probe(
        replay_days,
        eval_risks=eval_risks,
        funded_risks=funded_risks,
        max_eval_days=max_eval_days,
        max_funded_days=max_funded_days,
    )
    return replay_days, rows


def parse_float_list(raw: str) -> tuple[float, ...]:
    values = tuple(float(part.strip()) for part in raw.split(",") if part.strip())
    if not values:
        raise argparse.ArgumentTypeError("expected at least one comma-separated number")
    if any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("risk values must be positive")
    return values


def _to_row(eval_risk: float, funded_risk: float, result: LucidFlexPipelineResult) -> ReplayProbeRow:
    return ReplayProbeRow(
        eval_risk=eval_risk,
        funded_risk=funded_risk,
        terminal_reason=result.terminal_reason,
        eval_passed=result.eval_passed,
        eval_days=result.eval_days,
        funded_days=result.funded_days,
        payout_count=result.payout_count,
        trader_payouts=result.trader_payouts,
        net_ev=result.net_ev,
    )


def _print_table(rows: Sequence[ReplayProbeRow], *, limit: int) -> None:
    header = (
        f"{'evalR':>7} {'fundR':>7} {'terminal':>14} {'pass':>5} "
        f"{'eval d':>7} {'fund d':>7} {'payouts':>7} {'paid':>9} {'net EV':>9}"
    )
    print(header)
    print("-" * len(header))
    for row in rows[:limit]:
        print(
            f"{row.eval_risk:7.0f} {row.funded_risk:7.0f} {row.terminal_reason:>14} "
            f"{str(row.eval_passed):>5} {row.eval_days:7d} {row.funded_days:7d} "
            f"{row.payout_count:7d} {row.trader_payouts:9.0f} {row.net_ev:9.0f}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, type=Path, help="TradingView Strategy Tester XLSX export")
    parser.add_argument("--risk-amount", required=True, type=float, help="Dollar risk used to derive R from TV profit")
    parser.add_argument("--eval-risks", type=parse_float_list, default=DEFAULT_EVAL_RISKS)
    parser.add_argument("--funded-risks", type=parse_float_list, default=DEFAULT_FUNDED_RISKS)
    parser.add_argument("--sheet-name", default=None)
    parser.add_argument("--max-eval-days", type=int, default=90)
    parser.add_argument("--max-funded-days", type=int, default=180)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--no-fill-weekdays", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    replay_days, rows = load_and_run_probe(
        args.xlsx,
        risk_amount=args.risk_amount,
        eval_risks=args.eval_risks,
        funded_risks=args.funded_risks,
        sheet_name=args.sheet_name,
        include_no_trade_weekdays=not args.no_fill_weekdays,
        max_eval_days=args.max_eval_days,
        max_funded_days=args.max_funded_days,
    )
    trade_count = sum(len(day.r_multiples) for day in replay_days)
    print(f"Loaded {trade_count} trades across {len(replay_days)} replay weekdays from {args.xlsx}")
    print("Single historical sequence; no Monte Carlo confidence interval.")
    _print_table(rows, limit=args.limit)


if __name__ == "__main__":
    main()
