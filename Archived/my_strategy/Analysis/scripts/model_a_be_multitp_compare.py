"""Compare Model A KeyOpen OTE V0 exports (BE + multi-TP iteration check)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TV_DIR = Path("/Users/georgdomke/Arbeit/VS Code/Prop Firm Bot/TVExports")

FILES = {
    "A_pre":  TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_7d0f1.csv",
    "B_post": TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5e146.csv",
}

COLS = {
    "trade":  "Trade #",
    "typ":    "Typ",
    "ts":     "Datum und Uhrzeit",
    "signal": "Signal",
    "price":  "Preis USD",
    "qty":    "Größe (Menge)",
    "pnl":    "G&V netto USD",
    "mfe":    "Positive Exkursion USD",
    "mae":    "Negative Exkursion USD",
}


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df[COLS["ts"]] = pd.to_datetime(df[COLS["ts"]])
    return df


def trades_view(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse entry/exit rows to one row per trade (use the exit row)."""
    exits = df[df[COLS["typ"]].str.contains("Ausstieg", na=False)].copy()
    entries = (
        df[df[COLS["typ"]].str.contains("Einstieg", na=False)]
        .set_index(COLS["trade"])[[COLS["ts"], COLS["price"], COLS["signal"]]]
        .rename(columns={
            COLS["ts"]: "entry_ts",
            COLS["price"]: "entry_px",
            COLS["signal"]: "side",
        })
    )
    out = exits.merge(entries, left_on=COLS["trade"], right_index=True, how="left")
    out = out.rename(columns={
        COLS["ts"]: "exit_ts",
        COLS["price"]: "exit_px",
        COLS["pnl"]: "pnl",
        COLS["mfe"]: "mfe",
        COLS["mae"]: "mae",
        COLS["qty"]: "qty",
    })
    out["dir"] = np.where(out["side"].str.startswith("L"), 1, -1)
    out["hold_min"] = (out["exit_ts"] - out["entry_ts"]).dt.total_seconds() / 60.0
    return out[["entry_ts", "exit_ts", "side", "dir", "entry_px", "exit_px",
                "qty", "pnl", "mfe", "mae", "hold_min"]].reset_index(drop=True)


def max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def headline(t: pd.DataFrame) -> dict:
    pnl = t["pnl"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    equity = pnl.cumsum()
    return {
        "trades": len(t),
        "longs": int((t["dir"] == 1).sum()),
        "shorts": int((t["dir"] == -1).sum()),
        "net_pnl": float(pnl.sum()),
        "win_rate": float(len(wins) / len(t)) if len(t) else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "expectancy": float(pnl.mean()),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "max_dd": max_drawdown(equity),
        "median_hold_min": float(t["hold_min"].median()),
        "avg_mfe": float(t["mfe"].mean()),
        "avg_mae": float(t["mae"].mean()),
        "be_or_tiny_loss_pct": float(((pnl >= -10) & (pnl <= 10)).mean()),
        "scratch_pct": float((np.abs(pnl) < 1e-6).mean()),
    }


def fmt_row(label: str, vals: dict) -> str:
    return (
        f"{label:<8} "
        f"trades={vals['trades']:>6}  "
        f"net=${vals['net_pnl']:>11,.0f}  "
        f"WR={vals['win_rate']*100:>5.2f}%  "
        f"PF={vals['profit_factor']:>5.2f}  "
        f"E=${vals['expectancy']:>7.2f}  "
        f"AvgW=${vals['avg_win']:>7.2f}  AvgL=${vals['avg_loss']:>7.2f}  "
        f"DD=${vals['max_dd']:>10,.0f}  "
        f"hold={vals['median_hold_min']:>5.0f}m  "
        f"MFE=${vals['avg_mfe']:>6.2f}  MAE=${vals['avg_mae']:>6.2f}  "
        f"|PnL|<$10: {vals['be_or_tiny_loss_pct']*100:>4.1f}%"
    )


def main() -> None:
    summaries: dict[str, dict] = {}
    trades_per: dict[str, pd.DataFrame] = {}
    for tag, path in FILES.items():
        df = load(path)
        t = trades_view(df)
        trades_per[tag] = t
        summaries[tag] = headline(t)

    print("=" * 110)
    print("MODEL A KEYOPEN OTE V0 — BE / MULTI-TP COMPARISON")
    print("=" * 110)
    for tag in FILES:
        print(fmt_row(tag, summaries[tag]))
    print()

    a, b = summaries["A_pre"], summaries["B_post"]
    delta = {
        "trades":        b["trades"] - a["trades"],
        "net_pnl":       b["net_pnl"] - a["net_pnl"],
        "win_rate":      b["win_rate"] - a["win_rate"],
        "profit_factor": b["profit_factor"] - a["profit_factor"],
        "expectancy":    b["expectancy"] - a["expectancy"],
        "max_dd":        b["max_dd"] - a["max_dd"],
        "avg_mfe":       b["avg_mfe"] - a["avg_mfe"],
        "avg_mae":       b["avg_mae"] - a["avg_mae"],
    }
    print("DELTA  B_post - A_pre")
    print("-" * 110)
    for k, v in delta.items():
        sign = "+" if v >= 0 else ""
        if k in {"win_rate"}:
            print(f"  {k:<14} {sign}{v*100:.2f} pp")
        elif k in {"profit_factor", "expectancy"}:
            print(f"  {k:<14} {sign}{v:.3f}")
        else:
            print(f"  {k:<14} {sign}{v:,.2f}")

    # Distribution of trade outcomes — does BE squash small losers?
    print("\nP&L bucket counts (per-trade $ pnl):")
    bins = [-1e9, -500, -200, -100, -50, -10, -1, 1, 10, 50, 100, 200, 500, 1e9]
    labels = ["<-500", "-500..-200", "-200..-100", "-100..-50", "-50..-10",
              "-10..-1", "-1..1", "1..10", "10..50", "50..100", "100..200",
              "200..500", ">500"]
    print(f"  {'bucket':<14} {'A_pre':>10} {'B_post':>10} {'delta':>10}")
    for tag in FILES:
        cuts = pd.cut(trades_per[tag]["pnl"], bins=bins, labels=labels)
        trades_per[tag] = trades_per[tag].assign(bucket=cuts)
    counts_a = trades_per["A_pre"]["bucket"].value_counts().reindex(labels, fill_value=0)
    counts_b = trades_per["B_post"]["bucket"].value_counts().reindex(labels, fill_value=0)
    for lab in labels:
        ca, cb = int(counts_a[lab]), int(counts_b[lab])
        print(f"  {lab:<14} {ca:>10,} {cb:>10,} {cb-ca:>+10,}")


if __name__ == "__main__":
    main()
