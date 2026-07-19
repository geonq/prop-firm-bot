"""Round-2 extension search — exit overlays on the frozen ORB baseline.

PRE-HOLDOUT FOLD EVIDENCE ONLY (holdout burned 2026-07-17). Grid: 18 combos of
literature-backed exit overlays on the frozen entry (or=15, first_candle,
or_opposite stop, 4R target, no filters, slip 2 ticks):
  hold_into_close in {off, on, announce_only}   (Baltussen JFE 2021; Lucca-Moench gate)
  vwap_trail_after_r in {None, 2.0}             (Zarattini SPY 2024, Maróy 2025)
  time_stop_minutes in {None, 60, 120}          (Howard 2026)
Risk: flat $400 (risk-sweep conclusion). announce_only is spliced per session
date from the on/off runs (entries are identical; hold only affects post-15:30
exits), using DataLocal/announcement_days.csv (FOMC/CPI/NFP, verified).
"""

from __future__ import annotations

import csv
import itertools
import json
import sys
from dataclasses import replace
from datetime import date as date_t
from pathlib import Path
from statistics import median

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    HOLDOUT_START,
    _fold_replay_days,
    _replay_mc_summary,
    make_folds,
)

PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
CALENDAR = ROOT / "DataLocal" / "announcement_days.csv"
OUT = ROOT / "Analysis" / "output" / "orb"
FIRMS = ["lucidflex", "topstep", "apex_eod", "apex_intraday"]
RISK = 400.0
N_SIMS = 2_000

BASE = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
)


def load_announce_days() -> set[date_t]:
    days: set[date_t] = set()
    with open(CALENDAR) as f:
        for row in csv.DictReader(f):
            days.add(date_t.fromisoformat(row["date"]))
    return days


def splice_replay_days(days_on, days_off, announce: set[date_t]):
    """Per-session choice: announce-day sessions take the hold-on exit, others hold-off.

    Both runs share identical entries; only post-15:30 exits differ, so a
    per-date splice is exact. Day lists must align by session_date.
    """
    by_date_on = {d.session_date: d for d in days_on}
    out = []
    for d in days_off:
        out.append(by_date_on[d.session_date] if d.session_date in announce else d)
    return out


def main() -> None:
    bars = pd.read_parquet(PARQUET)
    announce = load_announce_days()
    folds = make_folds(pd.Timestamp("2020-01-01"), pd.Timestamp(HOLDOUT_START))
    print(f"folds={len(folds)} announce_days={len(announce)}")

    grid = list(itertools.product(["off", "on", "announce_only"], [None, 2.0], [None, 60, 120]))
    rows = []
    for hold_mode, vwap_r, tstop in grid:
        row = {"hold_into_close": hold_mode, "vwap_trail_after_r": vwap_r, "time_stop_minutes": tstop}
        per_fold: dict[str, list[float]] = {f: [] for f in FIRMS}
        total_trades = 0
        for f in folds:
            kw = dict(warmup_start=f.oos_start - pd.DateOffset(months=3),
                      window_start=f.oos_start, window_end=f.oos_end)
            p_off = replace(BASE, hold_into_close=False,
                            vwap_trail_after_r=vwap_r, time_stop_minutes=tstop)
            if hold_mode == "off":
                trades, rd = _fold_replay_days(bars, p_off, **kw)
            elif hold_mode == "on":
                p_on = replace(p_off, hold_into_close=True)
                trades, rd = _fold_replay_days(bars, p_on, **kw)
            else:
                p_on = replace(p_off, hold_into_close=True)
                trades, rd_off = _fold_replay_days(bars, p_off, **kw)
                _, rd_on = _fold_replay_days(bars, p_on, **kw)
                rd = splice_replay_days(rd_on, rd_off, announce)
            total_trades += len(trades)
            for firm in FIRMS:
                s = _replay_mc_summary(list(rd), firm=firm, n_simulations=N_SIMS, seed=0,
                                       block_size=5, eval_risk=RISK, funded_risk=RISK)
                if s is not None:
                    per_fold[firm].append(s.net_ev_mean)
        row["oos_trades"] = total_trades
        for firm in FIRMS:
            row[f"{firm}_fold_median"] = round(median(per_fold[firm]), 1)
            row[f"{firm}_fold_worst"] = round(min(per_fold[firm]), 1)
        row["best_median"] = max(row[f"{f}_fold_median"] for f in FIRMS)
        rows.append(row)
        print(row)

    rows.sort(key=lambda r: -r["best_median"])
    (OUT / "round2_search.json").write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {OUT / 'round2_search.json'}")
    print("\nTOP 5 vs baseline (baseline = first row where all overlays off):")
    for r in rows[:5]:
        print(r)


if __name__ == "__main__":
    main()
