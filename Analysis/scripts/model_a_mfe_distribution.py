"""MFE / MAE distribution probe for Model A Deep Backtesting export.

Diagnoses:
- For each trade bucket (hard L/S exit win/loss, Session flat win/loss),
  what does the MFE (max favorable excursion) distribution look like in R-multiples?
- How many losers went +1R favorable before reversing? (BE retrospective)
- How many session-flat winners exceeded 2R MFE before drifting back? (partial-TP idea)

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


def load_trades(xlsx: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx)
    exits = raw[raw["Signal"].isin(["L exit", "S exit", "Session flat"])].copy()
    exits["mfe_pts"] = exits["Positive Exkursion USD"] / NQ_USD_PER_PT
    exits["mae_pts"] = exits["Negative Exkursion USD"].abs() / NQ_USD_PER_PT
    exits["pnl_usd"] = exits["G&V netto USD"]
    exits["pnl_R"] = exits["pnl_usd"] / DEFAULT_RISK_USD
    exits["mfe_R"] = exits["mfe_pts"] / DEFAULT_STOP_PTS
    exits["mae_R"] = exits["mae_pts"] / DEFAULT_STOP_PTS
    exits["is_winner"] = exits["pnl_usd"] > 0
    exits["bucket"] = exits["Signal"] + np.where(exits["is_winner"], " WIN", " LOSS")
    return exits


def percentiles(s: pd.Series, qs: list[float]) -> dict[float, float]:
    return {q: float(np.quantile(s, q)) for q in qs}


def summarize(df: pd.DataFrame) -> None:
    print(f"Total trades: {len(df)}")
    overall_wr = df["is_winner"].mean()
    avg_win = df.loc[df["is_winner"], "pnl_R"].mean()
    avg_loss = df.loc[~df["is_winner"], "pnl_R"].mean()
    print(
        f"Overall WR={overall_wr:.2%} avg_win_R={avg_win:.2f} "
        f"avg_loss_R={avg_loss:.2f} ratio={abs(avg_win / avg_loss):.2f}"
    )
    print()

    qs = [0.10, 0.25, 0.50, 0.75, 0.90]
    print("=== MFE distribution by bucket (R-multiples) ===")
    for bucket, sub in df.groupby("bucket"):
        ps = percentiles(sub["mfe_R"], qs)
        share = len(sub) / len(df)
        print(
            f"  {bucket:>20} n={len(sub):>5} ({share:.1%})  "
            f"p10={ps[0.10]:.2f} p25={ps[0.25]:.2f} p50={ps[0.50]:.2f} "
            f"p75={ps[0.75]:.2f} p90={ps[0.90]:.2f}"
        )
    print()

    print("=== MAE distribution by bucket (R-multiples) ===")
    for bucket, sub in df.groupby("bucket"):
        ps = percentiles(sub["mae_R"], qs)
        print(
            f"  {bucket:>20} n={len(sub):>5}  "
            f"p10={ps[0.10]:.2f} p25={ps[0.25]:.2f} p50={ps[0.50]:.2f} "
            f"p75={ps[0.75]:.2f} p90={ps[0.90]:.2f}"
        )
    print()

    # BE retrospective: of LOSERS, how many ever went >= 1R favorable?
    losers = df[~df["is_winner"]]
    for bucket, sub in losers.groupby("Signal"):
        for thr in [0.5, 1.0, 1.5, 2.0]:
            pct = (sub["mfe_R"] >= thr).mean()
            print(
                f"  Losers in '{bucket}' n={len(sub)}: MFE >= {thr}R = {pct:.1%}"
            )
        print()

    # Partial-TP (c) study: of session-flat WINNERS, MFE distribution and
    # how many would have hit a partial-TP at fixed R levels.
    print("=== Partial-TP study on Session flat WINNERS ===")
    sf_win = df[(df["Signal"] == "Session flat") & df["is_winner"]]
    print(f"Session flat winners: {len(sf_win)}")
    for thr in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        pct = (sf_win["mfe_R"] >= thr).mean()
        print(f"  MFE >= {thr}R: {pct:.1%}")
    print()
    print(
        f"Session flat winners realized R median={sf_win['pnl_R'].median():.2f} "
        f"mean={sf_win['pnl_R'].mean():.2f} "
        f"vs MFE_R median={sf_win['mfe_R'].median():.2f} "
        f"mean={sf_win['mfe_R'].mean():.2f}"
    )
    print()

    # Counter-factual expectancy if we replaced session-flat exits with a
    # partial-TP at Y R (whichever hit first: TP or hard SL or session-flat
    # logic preserved). Approximation: if a trade's MFE >= Y, we'd capture Y;
    # else session-flat preserves the realized PnL.
    print("=== Counter-factual: replace session-flat with partial-TP cap ===")
    base_ev = df["pnl_R"].mean()
    base_wr = df["is_winner"].mean()
    print(f"Baseline: EV={base_ev:.3f}R/trade  WR={base_wr:.2%}  n={len(df)}")
    for partial_tp in [2.0, 2.5, 3.0, 4.0, 5.0]:
        sim = df.copy()
        # For trades where MFE >= partial_tp, assume partial-TP fills at +partial_tp R.
        # Trades with MFE < partial_tp keep their realized PnL.
        # NOTE: this is a simplification — we cannot tell from MFE alone whether
        # the partial-TP fill would have happened before or after the actual exit.
        # If MFE >= partial_tp, MFE was reached at SOME point during the trade,
        # so a static partial-TP would have triggered.
        hit = sim["mfe_R"] >= partial_tp
        sim.loc[hit, "pnl_R"] = partial_tp
        sim["is_winner"] = sim["pnl_R"] > 0
        ev = sim["pnl_R"].mean()
        wr = sim["is_winner"].mean()
        avg_w = sim.loc[sim["is_winner"], "pnl_R"].mean()
        avg_l = sim.loc[~sim["is_winner"], "pnl_R"].mean()
        print(
            f"  partial_tp={partial_tp}R: EV={ev:+.3f}R/trade  WR={wr:.2%}  "
            f"avg_W={avg_w:.2f}  avg_L={avg_l:.2f}  hits={hit.sum()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xlsx",
        default="TVExports/geonq_Model_A_KeyOpen_OTE_V0_NQ1_2000_now.xlsx",
    )
    args = parser.parse_args()
    df = load_trades(Path(args.xlsx))
    summarize(df)


if __name__ == "__main__":
    main()
