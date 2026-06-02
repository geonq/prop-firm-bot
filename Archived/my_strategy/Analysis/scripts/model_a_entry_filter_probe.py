"""Entry-filter probe for Model A Deep Backtesting export.

Goal: identify subsets of trades — defined ONLY by features known at entry time —
where expectancy is materially better than the −0.133R baseline. Anything with
EV ≥ 0 after a filter is a deployable filter candidate.

Features available in the TV trade-list export:
- entry timestamp (chart timezone — NQ futures = exchange/CT but we report NY hour)
- direction (Long vs Short)

Features NOT in the export (would require re-export with feature tags or
reconstructing Pine state from bar data):
- ATR regime at entry
- Fib level used (0.618 / 0.705 / 0.786)
- Key-open used (18:00 / 00:00 / 08:30 / 09:30 / 10:00 NY)
- Swing-range size
- Touched-valid vs fresh level
- Displacement at entry

NQ full contract: $20/pt. Default stop = 10 pts ($200) per Pine config.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

NQ_USD_PER_PT = 20.0
DEFAULT_STOP_PTS = 10.0
DEFAULT_RISK_USD = DEFAULT_STOP_PTS * NQ_USD_PER_PT  # 200
BASELINE_EV_R = -0.133


def load_trades(xlsx: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx)
    raw["Datum und Uhrzeit"] = pd.to_datetime(raw["Datum und Uhrzeit"])
    entries = raw[raw["Signal"].isin(["L", "S"])][
        ["Trade #", "Signal", "Datum und Uhrzeit", "Preis USD"]
    ].rename(
        columns={
            "Signal": "direction",
            "Datum und Uhrzeit": "entry_dt",
            "Preis USD": "entry_price",
        }
    )
    exits = raw[raw["Signal"].isin(["L exit", "S exit", "Session flat"])][
        [
            "Trade #",
            "Signal",
            "Datum und Uhrzeit",
            "G&V netto USD",
            "Positive Exkursion USD",
            "Negative Exkursion USD",
        ]
    ].rename(
        columns={
            "Signal": "exit_kind",
            "Datum und Uhrzeit": "exit_dt",
            "G&V netto USD": "pnl_usd",
            "Positive Exkursion USD": "mfe_usd",
            "Negative Exkursion USD": "mae_usd",
        }
    )
    df = entries.merge(exits, on="Trade #", how="inner")
    df["pnl_R"] = df["pnl_usd"] / DEFAULT_RISK_USD
    df["mfe_R"] = df["mfe_usd"] / NQ_USD_PER_PT / DEFAULT_STOP_PTS
    df["mae_R"] = df["mae_usd"].abs() / NQ_USD_PER_PT / DEFAULT_STOP_PTS
    df["is_winner"] = df["pnl_usd"] > 0
    df["hold_minutes"] = (
        df["exit_dt"] - df["entry_dt"]
    ).dt.total_seconds() / 60.0

    # Treat the export timestamps as already-in-NY for time-of-day bucketing.
    # The Pine session is "0000-1555" NY and the workbook was exported with the
    # NQ1! contract running on its native exchange clock; the replay probe uses
    # these timestamps directly so we follow the same convention here.
    df["entry_hour"] = df["entry_dt"].dt.hour
    df["entry_dow"] = df["entry_dt"].dt.dayofweek  # 0=Mon
    df["entry_year"] = df["entry_dt"].dt.year
    df["entry_month"] = df["entry_dt"].dt.month

    bins = [-1, 7, 11, 14, 23]
    labels = ["00-07 overnight", "08-11 NY-AM", "12-14 NY-mid", "15-23 close/eve"]
    df["session_phase"] = pd.cut(df["entry_hour"], bins=bins, labels=labels)
    return df


def bucket_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, sub in df.groupby(group_col, observed=True):
        if len(sub) == 0:
            continue
        wr = sub["is_winner"].mean()
        ev = sub["pnl_R"].mean()
        avg_w = (
            sub.loc[sub["is_winner"], "pnl_R"].mean()
            if sub["is_winner"].any()
            else np.nan
        )
        avg_l = (
            sub.loc[~sub["is_winner"], "pnl_R"].mean()
            if (~sub["is_winner"]).any()
            else np.nan
        )
        rows.append(
            {
                group_col: key,
                "n": len(sub),
                "share": len(sub) / len(df),
                "WR": wr,
                "EV_R": ev,
                "avg_W_R": avg_w,
                "avg_L_R": avg_l,
            }
        )
    return pd.DataFrame(rows).sort_values("EV_R", ascending=False)


def fmt_table(df: pd.DataFrame, group_col: str) -> str:
    lines = []
    header = f"  {group_col:>20} | n      share  WR     EV_R    avg_W   avg_L"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for _, r in df.iterrows():
        lines.append(
            f"  {str(r[group_col]):>20} | {int(r['n']):>5}  {r['share']:.1%}  "
            f"{r['WR']:.1%}  {r['EV_R']:+.3f}  "
            f"{r['avg_W_R']:.2f}  {r['avg_L_R']:.2f}"
        )
    return "\n".join(lines)


def two_d_table(df: pd.DataFrame, row_col: str, col_col: str) -> None:
    pivot_ev = df.pivot_table(
        index=row_col,
        columns=col_col,
        values="pnl_R",
        aggfunc="mean",
        observed=True,
    )
    pivot_n = df.pivot_table(
        index=row_col,
        columns=col_col,
        values="pnl_R",
        aggfunc="count",
        observed=True,
    )
    print(f"\n=== EV_R by {row_col} × {col_col} ===")
    print(pivot_ev.round(3).to_string())
    print(f"\n=== n by {row_col} × {col_col} ===")
    print(pivot_n.fillna(0).astype(int).to_string())


def deployable_candidates(df: pd.DataFrame, group_col: str) -> None:
    stats = bucket_stats(df, group_col)
    cands = stats[(stats["EV_R"] > 0) & (stats["n"] >= 100)]
    if cands.empty:
        print(f"  No {group_col} bucket with EV > 0 and n ≥ 100.")
        return
    print(f"  Deployable filter candidates ({group_col}, EV > 0, n ≥ 100):")
    for _, r in cands.iterrows():
        print(
            f"    {r[group_col]}: n={int(r['n'])} WR={r['WR']:.1%} "
            f"EV={r['EV_R']:+.3f}R"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xlsx",
        default="TVExports/geonq_Model_A_KeyOpen_OTE_V0_NQ1_2000_now.xlsx",
    )
    args = parser.parse_args()
    df = load_trades(Path(args.xlsx))

    print(f"Loaded {len(df)} trades from {args.xlsx}")
    print(
        f"Baseline: WR={df['is_winner'].mean():.2%} "
        f"EV={df['pnl_R'].mean():+.3f}R/trade  "
        f"first={df['entry_dt'].min()} last={df['entry_dt'].max()}"
    )
    print()

    for col in ["direction", "entry_hour", "entry_dow", "session_phase", "entry_year"]:
        stats = bucket_stats(df, col)
        print(f"=== {col} ===")
        print(fmt_table(stats, col))
        print()

    print("=== Deployable filter candidates ===")
    for col in ["direction", "entry_hour", "session_phase", "entry_dow"]:
        deployable_candidates(df, col)
    print()

    two_d_table(df, "entry_hour", "direction")
    two_d_table(df, "session_phase", "direction")
    two_d_table(df, "entry_year", "direction")


if __name__ == "__main__":
    main()
