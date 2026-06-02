"""Compare all Model A exports — pre-patch vs post-patch Pine.

Reports headline stats plus the three bug-related diagnostics:
- Same-bar entry+exit share (was 27.5% pre-patch)
- maxTradesPerNyDay violations (was 12% of days pre-patch)
- Stop blow-throughs (loss > 2x configured 10pt stop, ie. > $420 incl. slip)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TV_DIR = Path("/Users/georgdomke/Arbeit/VS Code/Prop Firm Bot/TVExports")

FILES = {
    "A_pre  (10:12, BE off)":          TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_7d0f1.csv",
    "B_post (11:04, BE on)":           TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5e146.csv",
    "C_05d0b (11:39, post-patch)":     TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_05d0b.csv",
    "D_5901b (11:40, post-patch)":     TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5901b.csv",
    "E_477eb (11:40, post-patch)":     TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_477eb.csv",
    "F_f6074 (11:40, post-patch)":     TV_DIR / "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_f6074.csv",
}

C_TRADE = "Trade #"
C_TYP   = "Typ"
C_TS    = "Datum und Uhrzeit"
C_SIG   = "Signal"
C_PX    = "Preis USD"
C_PNL   = "G&V netto USD"
C_MFE   = "Positive Exkursion USD"
C_MAE   = "Negative Exkursion USD"


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df[C_TS] = pd.to_datetime(df[C_TS])
    exits = df[df[C_TYP].str.contains("Ausstieg", na=False)].copy()
    entries = df[df[C_TYP].str.contains("Einstieg", na=False)].set_index(C_TRADE)[[C_TS, C_PX, C_SIG]].rename(
        columns={C_TS: "entry_ts", C_PX: "entry_px", C_SIG: "side"}
    )
    out = exits.merge(entries, left_on=C_TRADE, right_index=True, how="left")
    out = out.rename(columns={C_TS: "exit_ts", C_PX: "exit_px", C_PNL: "pnl",
                              C_MFE: "mfe", C_MAE: "mae"})
    out["dir"] = np.where(out["side"].str.startswith("L"), 1, -1)
    out["hold_min"] = (out["exit_ts"] - out["entry_ts"]).dt.total_seconds() / 60.0
    out["day"] = out["entry_ts"].dt.date
    return out[["entry_ts", "exit_ts", "day", "side", "dir",
                "entry_px", "exit_px", "pnl", "mfe", "mae", "hold_min"]].reset_index(drop=True)


def max_dd(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def stats(t: pd.DataFrame) -> dict:
    pnl = t["pnl"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gw, gl = wins.sum(), -losses.sum()
    eq = pnl.cumsum()
    same_bar = t[t["hold_min"] == 0]
    per_day = t.groupby("day").size()
    big_loss = pnl[pnl < -420]  # > 2x default 10pt stop incl. slip
    worst = pnl.min()
    return {
        "n":         len(t),
        "net":       float(pnl.sum()),
        "wr":        float(len(wins) / len(t)) if len(t) else 0.0,
        "pf":        float(gw / gl) if gl > 0 else np.inf,
        "exp":       float(pnl.mean()) if len(t) else 0.0,
        "avg_w":     float(wins.mean()) if len(wins) else 0.0,
        "avg_l":     float(losses.mean()) if len(losses) else 0.0,
        "dd":        max_dd(eq),
        "samebar_n": len(same_bar),
        "samebar_pct": len(same_bar) / len(t) * 100 if len(t) else 0.0,
        "samebar_pnl": float(same_bar["pnl"].sum()),
        "days":      len(per_day),
        "days_over_2": int((per_day > 2).sum()),
        "max_per_day": int(per_day.max()) if len(per_day) else 0,
        "blowthrough_n": int((pnl < -420).sum()),
        "blowthrough_pnl": float(big_loss.sum()),
        "worst_loss": float(worst) if len(t) else 0.0,
    }


def main() -> None:
    results: dict[str, dict] = {}
    for tag, path in FILES.items():
        if not path.exists():
            print(f"MISSING: {tag} -> {path}")
            continue
        t = load_trades(path)
        results[tag] = stats(t)

    # Headline P&L table
    print("=" * 130)
    print("HEADLINE P&L")
    print("=" * 130)
    print(f"{'tag':<32} {'n':>6} {'net':>12} {'WR':>7} {'PF':>5} {'exp':>7} "
          f"{'avgW':>8} {'avgL':>8} {'maxDD':>12} {'worst':>9}")
    for tag, s in results.items():
        print(f"{tag:<32} {s['n']:>6} {s['net']:>12,.0f} {s['wr']*100:>6.2f}% "
              f"{s['pf']:>5.2f} {s['exp']:>7.2f} {s['avg_w']:>8.0f} {s['avg_l']:>8.0f} "
              f"{s['dd']:>12,.0f} {s['worst_loss']:>9,.0f}")

    # Bug diagnostics
    print()
    print("=" * 130)
    print("BUG DIAGNOSTICS  (pre-patch had: same-bar 27.5%, days_over_2 = 742/6210, blowthroughs = 134)")
    print("=" * 130)
    print(f"{'tag':<32} {'samebar_n':>10} {'sb_%':>7} {'sb_pnl':>12} "
          f"{'days':>6} {'days>2':>7} {'max/day':>8} {'blowthru':>9} {'bt_pnl':>11}")
    for tag, s in results.items():
        sb_pct = f"{s['samebar_pct']:.2f}%"
        d_over = f"{s['days_over_2']}/{s['days']}"
        print(f"{tag:<32} {s['samebar_n']:>10,} {sb_pct:>7} "
              f"{s['samebar_pnl']:>12,.0f} {s['days']:>6,} {d_over:>7} "
              f"{s['max_per_day']:>8} {s['blowthrough_n']:>9} {s['blowthrough_pnl']:>11,.0f}")

    # Date range check (sanity — full history vs partial)
    print()
    print("=" * 130)
    print("DATE RANGE  (confirms whether each export covers full 2000–2026 history)")
    print("=" * 130)
    for tag, path in FILES.items():
        if not path.exists():
            continue
        t = load_trades(path)
        print(f"{tag:<32} first={t['entry_ts'].min()}  last={t['entry_ts'].max()}")


if __name__ == "__main__":
    main()
