"""No-trade filter impact analysis for Model A deep export (2019–2026).

For each rule supplied by geonq, measures: trades removed, P&L delta, WR delta,
PF delta, and efficiency ($/trade removed). Outputs a ranked table.

Usage:
    python3 Analysis/scripts/model_a_notrade_filter_impact.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEEP_CSV = (
    ROOT
    / "TVExports"
    / "geonq_Model_A_KeyOpen_OTE_V0_MNQ1_M15_DEEP_2000_2026_multitp30_2026-05-19.csv"
)

# --- BLS CPI release dates 2019–2026 (all at 8:30 AM ET) ---
_CPI_STRS = [
    # 2019
    "2019-01-11", "2019-02-14", "2019-03-12", "2019-04-10", "2019-05-10", "2019-06-12",
    "2019-07-11", "2019-08-13", "2019-09-12", "2019-10-10", "2019-11-13", "2019-12-11",
    # 2020
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12", "2020-06-10",
    "2020-07-14", "2020-08-12", "2020-09-11", "2020-10-13", "2020-11-12", "2020-12-10",
    # 2021
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12", "2021-06-10",
    "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13", "2021-11-10", "2021-12-10",
    # 2022
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11", "2022-06-10",
    "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13", "2022-11-10", "2022-12-13",
    # 2023
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10", "2023-06-13",
    "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12", "2023-11-14", "2023-12-12",
    # 2024
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12",
    "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    # 2025
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11",
    "2025-07-15", "2025-08-12", "2025-09-10", "2025-10-15", "2025-11-13", "2025-12-10",
    # 2026 (through May)
    "2026-01-15", "2026-02-11", "2026-03-11", "2026-04-09", "2026-05-13",
]
CPI_DATES: set = {pd.Timestamp(d).date() for d in _CPI_STRS}


def _nfp_dates(start: str = "2019-01-01", end: str = "2026-06-01") -> set:
    dates: set = set()
    for m in pd.date_range(start, end, freq="MS"):
        day = m
        while day.dayofweek != 4:
            day += pd.Timedelta(days=1)
        dates.add(day.date())
    return dates


NFP_DATES = _nfp_dates()
HIGH_IMPACT_DATES = CPI_DATES | NFP_DATES

DAY_BEFORE_DATES: set = set()
for _d in HIGH_IMPACT_DATES:
    DAY_BEFORE_DATES.add((pd.Timestamp(_d) - pd.offsets.BDay(1)).date())


def load_parents(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["Datum und Uhrzeit"] = pd.to_datetime(df["Datum und Uhrzeit"])

    entries = df[df["Typ"].str.contains("Einstieg", na=False)].copy()
    exits = df[df["Typ"].str.contains("Ausstieg", na=False)].copy()

    entry_idx = entries.set_index("Trade #")[
        ["Datum und Uhrzeit", "Preis USD", "Signal", "Größe (Menge)"]
    ].rename(
        columns={
            "Datum und Uhrzeit": "entry_ts",
            "Preis USD": "entry_px",
            "Signal": "side",
            "Größe (Menge)": "entry_qty",
        }
    )
    out = exits.merge(entry_idx, left_on="Trade #", right_index=True, how="left")
    out = out.rename(
        columns={
            "Datum und Uhrzeit": "exit_ts",
            "Preis USD": "exit_px",
            "Größe (Menge)": "exit_qty",
            "G&V netto USD": "pnl",
            "Positive Exkursion USD": "mfe",
            "Negative Exkursion USD": "mae",
        }
    )

    g = out.groupby(["entry_ts", "side", "entry_px"], sort=False)
    parents = g.agg(
        n_partials=("pnl", "size"),
        net_pnl=("pnl", "sum"),
        max_mfe=("mfe", "max"),
        worst_mae=("mae", "min"),
        exit_ts_last=("exit_ts", "max"),
    ).reset_index()

    parents["entry_hour"] = parents["entry_ts"].dt.hour
    parents["entry_minute"] = parents["entry_ts"].dt.minute
    parents["entry_date"] = parents["entry_ts"].dt.date
    parents["entry_dow"] = parents["entry_ts"].dt.dayofweek  # 0=Mon, 3=Thu, 4=Fri
    parents["is_winner"] = parents["net_pnl"] > 0
    return parents


def _pf(pnl: pd.Series) -> float:
    w = pnl[pnl > 0].sum()
    l = -pnl[pnl < 0].sum()
    return float(w / l) if l > 0 else float("inf")


def _stats(label: str, df: pd.DataFrame, n0: int, net0: float) -> dict:
    n = len(df)
    net = df["net_pnl"].sum()
    wr = float(df["is_winner"].mean()) if n > 0 else 0.0
    return {
        "rule": label,
        "n_kept": n,
        "n_removed": n0 - n,
        "pct_removed": (n0 - n) / n0,
        "net_pnl": net,
        "pnl_delta": net - net0,
        "WR": wr,
        "PF": _pf(df["net_pnl"]),
        "efficiency": (net - net0) / max(1, n0 - n),
    }


def main() -> None:
    print(f"Loading: {DEEP_CSV.name}")
    parents = load_parents(DEEP_CSV)
    n0 = len(parents)
    net0 = parents["net_pnl"].sum()
    wr0 = parents["is_winner"].mean()
    pf0 = _pf(parents["net_pnl"])

    print(
        f"Baseline: {n0} parent trades  "
        f"net=${net0:,.0f}  WR={wr0:.1%}  PF={pf0:.2f}"
    )
    print()

    # --- masks: True = trade to REMOVE ---
    m_pre_open = (parents["entry_hour"] == 9) & (parents["entry_minute"] == 30)
    # Rule 2 (18:00-20:00) already blocked by Pine session "0000-1555"; shown for completeness
    m_new_day = parents["entry_hour"].isin([18, 19])
    m_pre_close = parents["entry_hour"] == 15
    m_news_hour = (
        parents["entry_date"].isin(HIGH_IMPACT_DATES) & (parents["entry_hour"] == 8)
    )
    m_news_fullday = parents["entry_date"].isin(HIGH_IMPACT_DATES)
    m_day_before = parents["entry_date"].isin(DAY_BEFORE_DATES)
    # Weekly unemployment claims: every Thursday, avoid hour-8 entries
    m_thu_claims = (parents["entry_dow"] == 3) & (parents["entry_hour"] == 8)
    # Conservative union: rules that individually show signal
    m_union = m_pre_open | m_pre_close | m_news_hour | m_day_before | m_thu_claims

    masks = [
        ("1  pre-open 09:30 bar", m_pre_open),
        ("2  new-day 18-19h (Pine: already blocked)", m_new_day),
        ("3  pre-close hour 15", m_pre_close),
        ("4a CPI/NFP day, hour 8 only", m_news_hour),
        ("4b CPI/NFP full day", m_news_fullday),
        ("5  day before CPI/NFP", m_day_before),
        ("6  Thu claims, hour 8", m_thu_claims),
        ("UNION (1+3+4a+5+6)", m_union),
    ]

    rows = [_stats(label, parents[~mask], n0, net0) for label, mask in masks]
    results = pd.DataFrame(rows).sort_values("pnl_delta", ascending=False)

    print("=== No-Trade Filter Impact (sorted by P&L improvement) ===\n")
    hdr = (
        f"  {'Rule':<42}  {'n_rem':>6}  {'%rem':>6}  "
        f"{'net_pnl':>10}  {'pnl_Δ':>10}  {'WR':>6}  {'PF':>5}  {'$/rem_trade':>12}"
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for _, r in results.iterrows():
        print(
            f"  {r['rule']:<42}  {int(r['n_removed']):>6}  {r['pct_removed']:>6.1%}  "
            f"${r['net_pnl']:>9,.0f}  ${r['pnl_delta']:>+9,.0f}  "
            f"{r['WR']:>6.1%}  {r['PF']:>5.2f}  "
            f"${r['efficiency']:>+11,.0f}"
        )

    # P&L by entry hour — quick sanity check on where losses cluster
    print("\n=== P&L by entry hour ===")
    h = (
        parents.groupby("entry_hour")
        .agg(n=("net_pnl", "size"), net=("net_pnl", "sum"),
             avg=("net_pnl", "mean"), WR=("is_winner", "mean"))
        .reset_index()
    )
    for _, r in h.iterrows():
        flag = " <-- NEWS (8:30 ET)" if int(r["entry_hour"]) == 8 else ""
        flag = flag or (" <-- cash open" if int(r["entry_hour"]) == 9 else "")
        print(
            f"  {int(r['entry_hour']):02d}:xx  n={int(r['n']):>4}  "
            f"net=${r['net']:>9,.0f}  avg=${r['avg']:>+7.0f}  WR={r['WR']:.1%}{flag}"
        )

    # Show removed trades breakdown by exit type for top rules
    print("\n=== Removed-trade breakdown for UNION mask ===")
    removed = parents[m_union].copy()
    wins = removed["net_pnl"][removed["net_pnl"] > 0]
    losses = removed["net_pnl"][removed["net_pnl"] < 0]
    print(f"  Removed: {len(removed)} trades  net=${removed['net_pnl'].sum():,.0f}")
    print(f"  Winners: {len(wins)}  avg_win=${wins.mean():.0f}" if len(wins) else "  Winners: 0")
    print(f"  Losers:  {len(losses)}  avg_loss=${losses.mean():.0f}" if len(losses) else "  Losers: 0")
    print(f"  WR of removed trades: {removed['is_winner'].mean():.1%}")


if __name__ == "__main__":
    main()
