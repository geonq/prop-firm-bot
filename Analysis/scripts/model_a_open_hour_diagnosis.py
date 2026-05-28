"""Diagnose why 9-11 AM NY Model A entries fail.

Hypotheses to test against the M15 post-patch export:
- H1 MFE-naked entries: losers have near-zero MFE before stopping out
       (Pine enters at first fib touch; discretion would wait for confirmation).
- H2 Minute-of-hour clustering: losses concentrate on specific M15 bars after the 09:30 open.
- H3 Side asymmetry: longs vs shorts behave differently in this window.
- H4 Same-day prior stopout: entering after an earlier stopout = chasing on a strong-trend day.
- H5 Setup level: are losses concentrated near a specific fib level distance?
       (Limited — Pine doesn't tag the fib in the export, only the level price.)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

P = Path("/Users/georgdomke/Arbeit/VS Code/Prop Firm Bot/TVExports/"
        "geonq_Model_A_KeyOpen_OTE_V0_CME_MINI_NQ1!_2026-05-09_5901b.csv")


def load() -> pd.DataFrame:
    df = pd.read_csv(P, encoding="utf-8-sig")
    df["ts"] = pd.to_datetime(df["Datum und Uhrzeit"])
    exits = df[df["Typ"].str.contains("Ausstieg", na=False)].copy()
    ent = (df[df["Typ"].str.contains("Einstieg", na=False)]
             .set_index("Trade #")[["ts", "Preis USD", "Signal"]]
             .rename(columns={"ts": "entry_ts", "Preis USD": "entry_px",
                              "Signal": "side"}))
    out = exits.set_index("Trade #").join(ent, how="left").rename(columns={
        "ts": "exit_ts", "Preis USD": "exit_px",
        "G&V netto USD": "pnl",
        "Positive Exkursion USD": "mfe",
        "Negative Exkursion USD": "mae",
    })
    out["dir"] = np.where(out["side"].str.startswith("L"), 1, -1)
    out["hour"] = out["entry_ts"].dt.hour
    out["minute"] = out["entry_ts"].dt.minute
    out["date"] = out["entry_ts"].dt.date
    out["hold_min"] = (out["exit_ts"] - out["entry_ts"]).dt.total_seconds() / 60
    out["pt_pnl"] = out["pnl"] / 20.0  # NQ point value
    out["mfe_pt"] = out["mfe"] / 20.0
    return out.reset_index().sort_values("entry_ts").reset_index(drop=True)


def winrate(s: pd.Series) -> float:
    return float((s > 0).sum() / len(s)) * 100 if len(s) else 0.0


def main() -> None:
    t = load()
    open_w = t[(t["hour"] >= 9) & (t["hour"] <= 11)].copy()
    rest   = t[~((t["hour"] >= 9) & (t["hour"] <= 11))].copy()

    print("=" * 110)
    print(f"M15 post-patch — 9–11 AM NY window: {len(open_w):,} of {len(t):,} trades")
    print(f"  Window net:  ${open_w['pnl'].sum():,.0f}   WR: {winrate(open_w['pnl']):.1f}%   exp: ${open_w['pnl'].mean():.1f}")
    print(f"  Rest of day: ${rest['pnl'].sum():,.0f}   WR: {winrate(rest['pnl']):.1f}%   exp: ${rest['pnl'].mean():.1f}")
    print()

    # H1 — MFE-naked entries
    print("H1 — MFE distribution by outcome (9–11 AM only):")
    open_w["bucket"] = pd.cut(open_w["pnl"], bins=[-1e9, -420, -50, 50, 1e9],
                              labels=["blow-thru (<-$420)", "loser (-420..-50)",
                                      "scratch (±50)", "winner (>$50)"])
    mfe_dist = open_w.groupby("bucket", observed=True).agg(
        n=("pnl", "size"),
        median_mfe_pt=("mfe_pt", "median"),
        mean_mfe_pt=("mfe_pt", "mean"),
        zero_mfe_pct=("mfe", lambda s: (s < 1e-6).mean() * 100),
        mfe_lt_2pt=("mfe_pt", lambda s: (s < 2.0).mean() * 100),
    ).reset_index()
    print(mfe_dist.to_string(index=False))
    print()
    print("Read: if blow-throughs and losers have median MFE near 0 while winners")
    print("show meaningful MFE, an 'arm-after-N-pts' filter would cut the bad ones.")
    print()

    # H2 — minute-of-hour clustering after 09:30
    print("H2 — entry-minute breakdown (M15 bars: :00, :15, :30, :45):")
    by_min = (open_w.groupby(["hour", "minute"], observed=True)
                    .agg(n=("pnl", "size"),
                         net=("pnl", "sum"),
                         wr=("pnl", lambda s: winrate(s)),
                         exp=("pnl", "mean"),
                         bt=("pnl", lambda s: (s < -420).sum()))
                    .reset_index())
    print(by_min.to_string(index=False))
    print()

    # H3 — side asymmetry
    print("H3 — long vs short in 9–11 AM:")
    side_split = (open_w.groupby("side", observed=True)
                        .agg(n=("pnl", "size"),
                             net=("pnl", "sum"),
                             wr=("pnl", lambda s: winrate(s)),
                             exp=("pnl", "mean"),
                             bt=("pnl", lambda s: (s < -420).sum()))
                        .reset_index())
    print(side_split.to_string(index=False))
    print()

    # H4 — same-day prior stopout
    print("H4 — was there a prior trade SAME DAY before this 9–11 AM entry?")
    t["prev_pnl_same_day"] = t.groupby("date")["pnl"].shift(1)
    open_with_prev = t[(t["hour"] >= 9) & (t["hour"] <= 11)].copy()
    open_with_prev["prev_state"] = pd.cut(
        open_with_prev["prev_pnl_same_day"],
        bins=[-1e9, -50, 50, 1e9],
        labels=["after_loser", "after_scratch", "after_winner"],
    ).astype(object)
    open_with_prev.loc[open_with_prev["prev_pnl_same_day"].isna(), "prev_state"] = "first_of_day"
    by_prev = (open_with_prev.groupby("prev_state", observed=True)
                              .agg(n=("pnl", "size"),
                                   net=("pnl", "sum"),
                                   wr=("pnl", lambda s: winrate(s)),
                                   exp=("pnl", "mean"),
                                   bt=("pnl", lambda s: (s < -420).sum()))
                              .reset_index())
    print(by_prev.to_string(index=False))
    print()

    # H1b — what does an MFE-armed filter actually save?
    print("H1b — counterfactual: skip 9-11 AM trades that show MFE < threshold")
    print("(Cannot apply post-hoc directly; instead estimate the upside if we")
    print(" required price to first move ≥ X pts in trade direction before entering.)")
    print(f"  Of 9-11 AM losers, share with MFE = 0:  {(open_w[open_w['pnl']<-50]['mfe'] < 1e-6).mean()*100:.1f}%")
    print(f"  Of 9-11 AM winners, share with MFE = 0: {(open_w[open_w['pnl']>50]['mfe'] < 1e-6).mean()*100:.1f}%")
    print()

    # H5 — long vs short hour breakdown (does the asymmetry change by hour?)
    print("H5 — side performance by hour (9, 10, 11 AM):")
    grid = (open_w.groupby(["hour", "side"], observed=True)
                  .agg(n=("pnl", "size"),
                       net=("pnl", "sum"),
                       wr=("pnl", lambda s: winrate(s)),
                       exp=("pnl", "mean"))
                  .reset_index())
    print(grid.to_string(index=False))


if __name__ == "__main__":
    main()
