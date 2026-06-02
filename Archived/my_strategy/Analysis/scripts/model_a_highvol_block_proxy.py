"""Proxy-test Model A's high-volatility entry block from an existing TV CSV.

This is a first-order approximation for the Pine-side `useHighVolBlock` patch:
it removes trades whose entry timestamp is one of the blocked M15 bars
09:45, 10:00, or 10:15 NY. It does not model replacement trades that could
occur later because a skipped trade frees an intraday slot.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from Analysis.scripts.tv_topstep_replay_probe import load_catalog_adaptive_sizing
from src.pipeline.replay_validation import compute_replay_distribution_stats
from src.pipeline.topstep_replay import simulate_topstep_trade_replay
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing, SizingFunction
from src.strategies.replay import ReplayDay


EXPORT = (
    PROJECT_ROOT
    / "TVExports"
    / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5901b.csv"
)
RISK_AMOUNT = 200.0


def load_trades(path: Path = EXPORT) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["ts"] = pd.to_datetime(df["Datum und Uhrzeit"])
    exits = df[df["Typ"].str.contains("Ausstieg", na=False)].copy()
    entries = (
        df[df["Typ"].str.contains("Einstieg", na=False)]
        .set_index("Trade #")[["ts", "Signal"]]
        .rename(columns={"ts": "entry_ts", "Signal": "entry_signal"})
    )
    trades = (
        exits.set_index("Trade #")
        .join(entries, how="left")
        .reset_index()
        .rename(columns={"ts": "exit_ts", "G&V netto USD": "pnl"})
        .sort_values("entry_ts")
        .reset_index(drop=True)
    )
    trades["hour"] = trades["entry_ts"].dt.hour
    trades["minute"] = trades["entry_ts"].dt.minute
    return trades


def is_highvol_block(trades: pd.DataFrame) -> pd.Series:
    return ((trades["hour"] == 9) & (trades["minute"] == 45)) | (
        (trades["hour"] == 10) & trades["minute"].isin([0, 15])
    )


def replay_days(trades: pd.DataFrame, *, start: str | None = None) -> list[ReplayDay]:
    scoped = trades.copy()
    if start is not None:
        scoped = scoped[scoped["entry_ts"] >= pd.Timestamp(start)].copy()
    scoped["r"] = scoped["pnl"].astype(float) / RISK_AMOUNT
    first = scoped["entry_ts"].dt.date.min()
    last = scoped["entry_ts"].dt.date.max()
    grouped = scoped.groupby(scoped["entry_ts"].dt.date)["r"].apply(tuple).to_dict()
    return [
        ReplayDay(day.date(), grouped.get(day.date(), ()))
        for day in pd.bdate_range(first, last)
    ]


def pnl_stats(trades: pd.DataFrame) -> dict[str, float]:
    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "trades": float(len(trades)),
        "net": float(pnl.sum()),
        "wr": float((pnl > 0).mean()),
        "pf": float(wins.sum() / -losses.sum()),
        "exp": float(pnl.mean()),
        "avg_win": float(wins.mean()),
        "avg_loss": float(losses.mean()),
        "worst": float(pnl.min()),
        "blowthroughs": float((pnl < -420).sum()),
        "blowthrough_pnl": float(pnl[pnl < -420].sum()),
    }


def print_case(
    label: str,
    trades: pd.DataFrame,
    *,
    start: str | None = None,
) -> None:
    scoped = trades if start is None else trades[trades["entry_ts"] >= pd.Timestamp(start)]
    stats = pnl_stats(scoped)
    days = replay_days(trades, start=start)
    dist = compute_replay_distribution_stats(tuple(days))

    print(f"\n{label}")
    print(
        "pnl: "
        f"trades={stats['trades']:,.0f} net=${stats['net']:,.0f} "
        f"WR={stats['wr']:.2%} PF={stats['pf']:.2f} exp=${stats['exp']:.2f} "
        f"avgW=${stats['avg_win']:.0f} avgL=${stats['avg_loss']:.0f} "
        f"worst=${stats['worst']:,.0f} "
        f"blowthrough={stats['blowthroughs']:,.0f}/${stats['blowthrough_pnl']:,.0f}"
    )
    print(
        "dist: "
        f"replay_days={dist.replay_days:,} trading_days={dist.trading_days:,} "
        f"R_WR={dist.win_rate:.2%} R={dist.avg_win_loss_ratio:.2f} "
        f"freq={dist.trades_per_replay_day:.2f}/replay_day "
        f"lag10={dist.lag10_outcome_autocorr:.2f} profile4={dist.inside_profile4}"
    )
    for sizing_name, sizing in (
        ("adaptiveP4", load_catalog_adaptive_sizing()),
        ("fixed200", FixedSizing(eval_size=200, funded_size=200)),
    ):
        print_topstep(sizing_name, days, sizing)


def print_topstep(name: str, days: list[ReplayDay], sizing: SizingFunction) -> None:
    result = simulate_topstep_trade_replay(
        days,
        sizing_fn=sizing,
        payout_path=TopStepPayoutPath.CONSISTENCY,
        max_back2funded_reactivations=3,
        payout_cap=5,
        eval_cost_per_trade=5,
        funded_cost_per_trade=5,
    )
    print(
        f"topstep {name}: terminal={result.terminal_reason} "
        f"pass={result.eval_passed} combine_days={result.combine_days} "
        f"xfa_days={result.xfa_days} payouts={result.payout_count} "
        f"b2f={result.back2funded_count} paid=${result.trader_payouts:,.0f} "
        f"net_ev=${result.net_ev:,.0f}"
    )


def main() -> None:
    trades = load_trades()
    blocked = is_highvol_block(trades)
    blocked_trades = trades[blocked]
    proxy = trades[~blocked].copy()
    print(
        "blocked trades: "
        f"{len(blocked_trades):,} / {len(trades):,} "
        f"net=${blocked_trades['pnl'].sum():,.0f} "
        f"exp=${blocked_trades['pnl'].mean():.2f} "
        f"blowthroughs={(blocked_trades['pnl'] < -420).sum():,}"
    )
    print_case("BASELINE full 2000-2026", trades)
    print_case("PROXY high-vol block full 2000-2026", proxy)
    print_case("BASELINE recent >=2023-05-11", trades, start="2023-05-11")
    print_case("PROXY high-vol block recent >=2023-05-11", proxy, start="2023-05-11")


if __name__ == "__main__":
    main()
