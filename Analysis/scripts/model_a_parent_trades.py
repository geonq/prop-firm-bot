"""Reconstitute parent trades from TradingView multi-TP exports.

TV emits each partial exit as a separate Trade # that shares the same entry
timestamp + side + entry price as its siblings. Grouping by (entry_ts, side)
recovers the parent trade.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TV_DIR = Path("/Users/georgdomke/Arbeit/VS Code/Prop Firm Bot/TVExports")

FILES = {
    "A_pre":  TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_7d0f1.csv",
    "B_post": TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5e146.csv",
}

C_TRADE  = "Trade #"
C_TYP    = "Typ"
C_TS     = "Datum und Uhrzeit"
C_SIGNAL = "Signal"
C_PRICE  = "Preis USD"
C_QTY    = "Größe (Menge)"
C_PNL    = "G&V netto USD"
C_MFE    = "Positive Exkursion USD"
C_MAE    = "Negative Exkursion USD"


def load_partials(path: Path) -> pd.DataFrame:
    """Return one row per TV 'Trade #' (entry+exit collapsed)."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    df[C_TS] = pd.to_datetime(df[C_TS])

    exits = df[df[C_TYP].str.contains("Ausstieg", na=False)].copy()
    entries = df[df[C_TYP].str.contains("Einstieg", na=False)].copy()

    entries = entries.set_index(C_TRADE)[[C_TS, C_PRICE, C_SIGNAL, C_QTY]].rename(
        columns={C_TS: "entry_ts", C_PRICE: "entry_px",
                 C_SIGNAL: "side", C_QTY: "entry_qty"}
    )
    out = exits.merge(entries, left_on=C_TRADE, right_index=True, how="left")
    out = out.rename(columns={
        C_TS: "exit_ts", C_PRICE: "exit_px", C_QTY: "exit_qty",
        C_PNL: "pnl", C_MFE: "mfe", C_MAE: "mae",
    })
    out["dir"] = np.where(out["side"].str.startswith("L"), 1, -1)
    return out[["entry_ts", "exit_ts", "side", "dir", "entry_px",
                "exit_px", "exit_qty", "pnl", "mfe", "mae"]]


def parent_trades(partials: pd.DataFrame) -> pd.DataFrame:
    """Collapse partials sharing (entry_ts, side, entry_px) into parents."""
    g = partials.groupby(["entry_ts", "side", "entry_px"], sort=False)
    parents = g.agg(
        exit_ts_last=("exit_ts", "max"),
        exit_ts_first=("exit_ts", "min"),
        n_partials=("pnl", "size"),
        total_qty=("exit_qty", "sum"),
        net_pnl=("pnl", "sum"),
        max_mfe=("mfe", "max"),
        worst_mae=("mae", "min"),
        avg_exit_px=("exit_px", "mean"),
        dir=("dir", "first"),
    ).reset_index()
    parents["hold_min"] = (
        parents["exit_ts_last"] - parents["entry_ts"]
    ).dt.total_seconds() / 60.0
    return parents


def max_dd(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def stats(df: pd.DataFrame, pnl_col: str) -> dict:
    pnl = df[pnl_col].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gw, gl = wins.sum(), -losses.sum()
    eq = pnl.cumsum()
    return {
        "trades": len(df),
        "net": float(pnl.sum()),
        "wr": float(len(wins) / len(df)) if len(df) else 0.0,
        "avg_w": float(wins.mean()) if len(wins) else 0.0,
        "avg_l": float(losses.mean()) if len(losses) else 0.0,
        "exp": float(pnl.mean()),
        "pf": float(gw / gl) if gl > 0 else np.inf,
        "dd": max_dd(eq),
    }


def fmt(label: str, s: dict, mfe: float | None = None, mae: float | None = None,
        partials_avg: float | None = None) -> str:
    extra = ""
    if mfe is not None:
        extra += f"  MFE=${mfe:>7.2f}  MAE=${mae:>7.2f}"
    if partials_avg is not None:
        extra += f"  partials/parent={partials_avg:.2f}"
    return (
        f"{label:<26} n={s['trades']:>6}  net=${s['net']:>11,.0f}  "
        f"WR={s['wr']*100:>5.2f}%  PF={s['pf']:>5.2f}  E=${s['exp']:>7.2f}  "
        f"AvgW=${s['avg_w']:>7.2f}  AvgL=${s['avg_l']:>7.2f}  "
        f"DD=${s['dd']:>10,.0f}" + extra
    )


def main() -> None:
    print("=" * 130)
    print("MODEL A — PARENT-TRADE RECONSTITUTION (group partials by entry_ts+side+entry_px)")
    print("=" * 130)

    rows = []
    for tag, path in FILES.items():
        partials = load_partials(path)
        parents = parent_trades(partials)
        rows.append((tag, partials, parents))

        s_part = stats(partials, "pnl")
        s_par = stats(parents, "net_pnl")
        ratio = len(partials) / len(parents) if len(parents) else 0.0
        print(fmt(f"{tag} [TV partials]", s_part,
                  mfe=partials["mfe"].mean(), mae=partials["mae"].mean()))
        print(fmt(f"{tag} [parent trades]", s_par,
                  mfe=parents["max_mfe"].mean(), mae=parents["worst_mae"].mean(),
                  partials_avg=ratio))
        # parent partial-count distribution
        dist = parents["n_partials"].value_counts().sort_index()
        dist_str = "  ".join(f"{int(k)}x:{int(v):,}" for k, v in dist.items())
        print(f"   partials-per-parent: {dist_str}")
        print()

    # head-to-head on parent trades
    a = rows[0][2]
    b = rows[1][2]
    sa, sb = stats(a, "net_pnl"), stats(b, "net_pnl")
    print("-" * 130)
    print("PARENT-TRADE DELTA  B_post - A_pre")
    print("-" * 130)
    deltas = {
        "trades": sb["trades"] - sa["trades"],
        "net":    sb["net"] - sa["net"],
        "wr_pp":  (sb["wr"] - sa["wr"]) * 100,
        "pf":     sb["pf"] - sa["pf"],
        "exp":    sb["exp"] - sa["exp"],
        "avg_w":  sb["avg_w"] - sa["avg_w"],
        "avg_l":  sb["avg_l"] - sa["avg_l"],
        "dd":     sb["dd"] - sa["dd"],
        "mfe":    b["max_mfe"].mean() - a["max_mfe"].mean(),
        "mae":    b["worst_mae"].mean() - a["worst_mae"].mean(),
    }
    for k, v in deltas.items():
        if k == "wr_pp":
            print(f"  {k:<10} {v:+.2f} pp")
        elif k in {"pf", "exp"}:
            print(f"  {k:<10} {v:+.3f}")
        else:
            print(f"  {k:<10} {v:+,.2f}")

    # P&L bucket on parents
    print("\nParent-trade P&L buckets:")
    bins = [-1e9, -500, -200, -100, -50, -10, -1, 1, 10, 50, 100, 200, 500, 1e9]
    labels = ["<-500", "-500..-200", "-200..-100", "-100..-50", "-50..-10",
              "-10..-1", "-1..1", "1..10", "10..50", "50..100", "100..200",
              "200..500", ">500"]
    ca = pd.cut(a["net_pnl"], bins=bins, labels=labels).value_counts().reindex(labels, fill_value=0)
    cb = pd.cut(b["net_pnl"], bins=bins, labels=labels).value_counts().reindex(labels, fill_value=0)
    print(f"  {'bucket':<14} {'A_pre':>10} {'B_post':>10} {'delta':>10}")
    for lab in labels:
        print(f"  {lab:<14} {int(ca[lab]):>10,} {int(cb[lab]):>10,} {int(cb[lab]-ca[lab]):>+10,}")

    # MFE-vs-realized on parents — did BE / multi-TP capture more of the favorable excursion?
    print("\nFavorable-excursion capture (parent-level): realized / max_MFE on winners")
    for tag, _, parents in rows:
        win = parents[parents["net_pnl"] > 0]
        denom = win["max_mfe"].replace(0, np.nan)
        capture = (win["net_pnl"] / denom).clip(lower=0, upper=2).dropna()
        print(f"  {tag:<8}  median={capture.median():.2f}  mean={capture.mean():.2f}  "
              f"winners={len(win):,}  median_MFE=${win['max_mfe'].median():.0f}  "
              f"median_realized=${win['net_pnl'].median():.0f}")


if __name__ == "__main__":
    main()
