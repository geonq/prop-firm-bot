"""Reconcile a TradingView strategy-tester export of orb_frozen_v2_round4.pine
against the Python backtester (run_orb_backtest + FROZEN_PARAMS) trade-by-trade.

Usage:
    python3 Analysis/scripts/orb_tv_cross_check.py PineScripts/<export>.csv

Context (2026-07-19): TV's current engine force-fills market orders at the
signal bar's CLOSE and stamps trades with the bar's OPEN time, so TV entries
print 09:30 while the actual fill moment equals Python's 09:35-bar-open entry.
TV runs CME_MINI:MNQ1! (TV feed); Python runs Databento NQ continuous — a
small, roughly constant price offset between the two feeds is expected and is
estimated from matched entries, then removed before exit-price comparisons.

What this checks, in order of importance:
  1. Trade universe: same session dates traded (missing/extra days).
  2. Direction agreement on matched days.
  3. Exit-reason agreement (TV X-L/X-S = stop-or-target, disambiguated by
     price against the Python trade's stop/target levels after offset removal).
  4. Fill semantics: do TV stop/target exits honor the exact level (Python
     model) or fill elsewhere (e.g. bar closes -> extra adverse slippage)?
  5. Aggregate: win rate + mean R on the matched set.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import run_orb_backtest  # noqa: E402
from src.live.config import FROZEN_PARAMS, MNQ  # noqa: E402

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
PARQUET_END = pd.Timestamp("2026-07-16")


def load_tv(csv_path: Path) -> pd.DataFrame:
    tv = pd.read_csv(csv_path)
    tv.columns = [c.strip("﻿") for c in tv.columns]
    tv["dt"] = pd.to_datetime(tv["Datum und Uhrzeit"])
    entries = tv[tv["Typ"].str.contains("Einstieg")].set_index("Trade-Nummer")
    exits = tv[tv["Typ"].str.contains("Ausstieg")].set_index("Trade-Nummer")
    out = pd.DataFrame(
        {
            "date": entries["dt"].dt.date,
            "entry_label": entries["dt"],
            "direction": entries["Typ"].map(lambda t: "long" if "Long" in t else "short"),
            "entry_price": entries["Preis USD"].astype(float),
            "qty": entries["Größe (Menge)"].astype(float),
            "exit_label": exits["dt"],
            "exit_signal": exits["Signal"],
            "exit_price": exits["Preis USD"].astype(float),
            "net_pnl": exits["Netto G&V USD"].astype(float),
        }
    )
    return out.sort_values("entry_label").reset_index(drop=True)


def python_reference(start: str, end: str) -> pd.DataFrame:
    bars = pd.read_parquet(PARQUET)
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    trades = run_orb_backtest(bars.loc[(bars.index >= s) & (bars.index < e)], FROZEN_PARAMS)
    rows = []
    for t in trades:
        risk_pts = abs(t.pnl_points / t.r_multiple) if t.r_multiple else float("nan")
        stop = t.entry_price - risk_pts if t.direction == "long" else t.entry_price + risk_pts
        tgt = (
            t.entry_price + FROZEN_PARAMS.target_r * risk_pts
            if t.direction == "long"
            else t.entry_price - FROZEN_PARAMS.target_r * risk_pts
        )
        rows.append(
            {
                "date": t.session_date,
                "py_direction": t.direction,
                "py_entry": t.entry_price,
                "py_exit": t.exit_price,
                "py_reason": t.exit_reason,
                "py_r": t.r_multiple,
                "py_stop": stop,
                "py_target": tgt,
            }
        )
    return pd.DataFrame(rows)


def main(csv_path: Path) -> None:
    tv = load_tv(csv_path)
    print(f"TV export: {len(tv)} trades, {tv.date.min()} -> {tv.date.max()}")
    print("entry labels:", tv.entry_label.dt.strftime("%H:%M").value_counts().to_dict())
    print("qty: min", tv.qty.min(), "max", tv.qty.max(), "| margin calls:",
          int((tv.exit_signal == "Margin call").sum()))
    ts = tv[tv.exit_signal == "TimeStop"]
    if len(ts):
        d = (ts.exit_label - ts.entry_label).dt.total_seconds() / 60
        print("TimeStop label-durations (min):", sorted(d.unique()))

    start = str(tv.date.min())
    end = str(min(pd.Timestamp(str(tv.date.max())), PARQUET_END).date())
    py = python_reference(start, end)
    print(f"\nPython reference on [{start}, {end}]: {len(py)} trades")

    tv_cmp = tv[pd.to_datetime(tv.date.astype(str)) <= PARQUET_END]
    m = tv_cmp.merge(py, on="date", how="outer", indicator=True)
    both = m[m._merge == "both"].copy()
    only_tv = m[m._merge == "left_only"]
    only_py = m[m._merge == "right_only"]
    print(f"matched days: {len(both)} | TV-only: {len(only_tv)} | Python-only: {len(only_py)}")
    if len(only_tv):
        print("  TV-only dates (first 10):", list(only_tv.date.astype(str).head(10)))
    if len(only_py):
        print("  Python-only dates (first 10):", list(only_py.date.astype(str).head(10)))

    dir_ok = (both.direction == both.py_direction)
    print(f"direction agreement: {dir_ok.mean():.1%} ({(~dir_ok).sum()} flips)")
    if (~dir_ok).any():
        print("  flipped dates:", list(both.loc[~dir_ok, "date"].astype(str).head(10)))

    agree = both[dir_ok].copy()
    agree["entry_delta"] = agree.entry_price - agree.py_entry
    offset = agree.entry_delta.median()
    print(f"\nfeed offset (TV MNQ - Databento NQ), median of entry deltas: {offset:+.2f} pts "
          f"(IQR {agree.entry_delta.quantile(0.25):+.2f}..{agree.entry_delta.quantile(0.75):+.2f})")

    # Exit-reason mapping. TV Signal: TimeStop, EoD, X-L/X-S (stop OR target).
    def tv_reason(row) -> str:
        if row.exit_signal == "TimeStop":
            return "time_stop"
        if row.exit_signal == "EoD":
            return "eod"
        if row.exit_signal in ("X-L", "X-S"):
            adj = row.exit_price - offset
            return "stop" if abs(adj - row.py_stop) <= abs(adj - row.py_target) else "target"
        return str(row.exit_signal)

    agree["tv_reason"] = agree.apply(tv_reason, axis=1)
    reason_ok = agree.tv_reason == agree.py_reason
    print(f"exit-reason agreement: {reason_ok.mean():.1%}")
    if (~reason_ok).any():
        cross = pd.crosstab(agree.tv_reason, agree.py_reason)
        print(cross.to_string())
        bad = agree.loc[~reason_ok, ["date", "tv_reason", "py_reason"]].head(12)
        print(bad.to_string(index=False))

    # Fill semantics on agreed stop/target exits: TV exit (offset-removed) vs the level.
    for reason, level_col in (("stop", "py_stop"), ("target", "py_target")):
        sub = agree[(agree.tv_reason == reason) & (agree.py_reason == reason)]
        if len(sub):
            dev = (sub.exit_price - offset) - sub[level_col]
            print(f"{reason} fills vs level (offset-removed): n={len(sub)} "
                  f"median {dev.median():+.2f} pts, IQR {dev.quantile(0.25):+.2f}..{dev.quantile(0.75):+.2f}, "
                  f"max|dev| {dev.abs().max():.2f}")

    # Aggregate on the matched, direction-agreed set.
    tv_wr = (agree.net_pnl > 0).mean()
    py_wr = (agree.py_r > 0).mean()
    # TV R: net pnl / (qty * risk_pts * point_value); risk_pts from the Python levels.
    risk_pts = (agree.py_entry - agree.py_stop).abs()
    tv_r = agree.net_pnl / (agree.qty * risk_pts * MNQ.point_value)
    print(f"\nmatched-set aggregates: n={len(agree)}")
    print(f"  win rate: TV {tv_wr:.1%} vs Python {py_wr:.1%}")
    print(f"  mean R:  TV {tv_r.mean():+.4f} (net of TV commission) vs Python {agree.py_r.mean():+.4f} (net of NQ-scale friction)")
    print(f"  R correlation: {tv_r.corr(agree.py_r):.4f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
