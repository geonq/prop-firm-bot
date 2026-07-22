"""Multi-year, research-only chronological 70/30 NQ ORB evaluation.

The candidate set is fixed before the untouched final 30% is evaluated. A
replacement is eligible only when its IS lower-confidence score is positive,
it has at least 100 IS trades, and at least three of four chronological IS
folds are profitable. This script never mutates live configuration.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Analysis.scripts.orb_mnq_70_30_research import (  # noqa: E402
    COMMISSION_PER_SIDE,
    POINT_VALUE,
    _daily,
    _daily_features,
    _paired_bootstrap_delta,
    _run,
    candidate_grid,
    chronological_split,
    sessions_from_bars,
    summarize_daily,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Analysis" / "output" / "orb_nq_multiyear"
RAW = OUT / "nq_databento_5min.csv"
SOURCE_URL = "https://github.com/prashanthaitha24/nq-strategy-b-bot"
SOURCE_RAW_URL = (
    "https://raw.githubusercontent.com/prashanthaitha24/"
    "nq-strategy-b-bot/main/data/nq_databento_5min.csv"
)
ET = "America/New_York"


def load_databento_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    timestamp_column = next((name for name in ("ts_event", "ts", "datetime") if name in frame.columns), None)
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if timestamp_column is None:
        missing.add("ts_event|ts")
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="raise")
    frame = frame[["open", "high", "low", "close", "volume"]].copy()
    frame.index = pd.DatetimeIndex(timestamps).tz_convert(ET)
    frame = frame.apply(pd.to_numeric, errors="raise")
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def chronological_folds(dates: list[date], count: int = 4) -> list[list[date]]:
    if count < 2 or len(dates) < count:
        raise ValueError("need at least two non-empty folds")
    indices = np.array_split(np.arange(len(dates)), count)
    return [[dates[int(i)] for i in chunk] for chunk in indices]


def _score(daily: pd.Series, trade_count: int) -> float:
    values = daily[daily != 0]
    if trade_count < 100 or len(values) < 2:
        return float("-inf")
    se = float(values.std(ddof=1) / math.sqrt(len(values)))
    return float(values.mean() - se)


def _json_number(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _bar_boundary_gap_stats(sessions: dict[date, pd.DataFrame]) -> dict:
    gaps = np.asarray(
        [float(day.open.iloc[1] - day.close.iloc[0]) for day in sessions.values()],
        dtype=float,
    )
    return {
        "sessions": int(len(gaps)),
        "exact_match_rate": float((gaps == 0).mean()),
        "mean_abs_points": float(np.abs(gaps).mean()),
        "p95_abs_points": float(np.quantile(np.abs(gaps), 0.95)),
        "max_abs_points": float(np.abs(gaps).max()),
    }


def main(raw_path: Path = RAW) -> dict:
    bars = load_databento_csv(raw_path)
    sessions = dict(sorted(sessions_from_bars(bars).items()))
    dates = list(sessions)
    if len(dates) < 500:
        raise RuntimeError(f"multi-year gate requires at least 500 complete RTH sessions; got {len(dates)}")
    is_dates, oos_dates = chronological_split(dates, 0.70)
    is_set, oos_set = set(is_dates), set(oos_dates)
    folds = chronological_folds(is_dates, 4)
    features = _daily_features(sessions)
    candidates = candidate_grid()

    # Phase 1: candidate selection sees only the first 70%.
    trades_by_name = {candidate.name: _run(sessions, features, candidate) for candidate in candidates}
    is_rows: list[dict] = []
    for candidate in candidates:
        all_trades = trades_by_name[candidate.name]
        is_trades = [trade for trade in all_trades if trade.session_date in is_set]
        is_daily = _daily(is_trades, is_dates)
        fold_rows = []
        for index, fold_dates in enumerate(folds, start=1):
            fold_set = set(fold_dates)
            fold_trades = [trade for trade in is_trades if trade.session_date in fold_set]
            fold_rows.append(
                {
                    "fold": index,
                    "start": str(fold_dates[0]),
                    "end": str(fold_dates[-1]),
                    **summarize_daily(_daily(fold_trades, fold_dates), trade_count=len(fold_trades)),
                }
            )
        score = _score(is_daily, len(is_trades))
        positive_folds = sum(row["total_r"] > 0 for row in fold_rows)
        eligible = bool(score > 0 and len(is_trades) >= 100 and positive_folds >= 3)
        is_rows.append(
            {
                "candidate": candidate.name,
                "params": asdict(candidate),
                "is_score": _json_number(score),
                "positive_is_folds": positive_folds,
                "eligible_replacement": eligible,
                "is": summarize_daily(is_daily, trade_count=len(is_trades)),
                "is_folds": fold_rows,
            }
        )

    eligible = [row for row in is_rows if row["eligible_replacement"] and row["candidate"] != "deployed_opening_drive"]
    selected = max(eligible, key=lambda row: row["is_score"])["candidate"] if eligible else None

    # Phase 2: candidate set and selection are frozen; now evaluate final 30% once.
    rows = []
    for is_row in is_rows:
        name = is_row["candidate"]
        oos_trades = [trade for trade in trades_by_name[name] if trade.session_date in oos_set]
        row = dict(is_row)
        row["oos"] = summarize_daily(_daily(oos_trades, oos_dates), trade_count=len(oos_trades))
        yearly = {}
        for year in sorted({d.year for d in dates}):
            year_dates = [d for d in dates if d.year == year]
            year_set = set(year_dates)
            year_trades = [trade for trade in trades_by_name[name] if trade.session_date in year_set]
            yearly[str(year)] = summarize_daily(_daily(year_trades, year_dates), trade_count=len(year_trades))
        row["yearly"] = yearly
        rows.append(row)

    baseline_name = "deployed_opening_drive"
    comparison = None
    if selected is not None:
        selected_oos = _daily(
            [trade for trade in trades_by_name[selected] if trade.session_date in oos_set], oos_dates
        )
        baseline_oos = _daily(
            [trade for trade in trades_by_name[baseline_name] if trade.session_date in oos_set], oos_dates
        )
        comparison = _paired_bootstrap_delta(selected_oos, baseline_oos, seed=20260720)

    checksum = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    result = {
        "source": {
            "description": "Public NQ.c.0 continuous five-minute bars described by its repository as Databento data",
            "repository": SOURCE_URL,
            "raw_url": SOURCE_RAW_URL,
            "local_sha256": checksum,
        },
        "limits": [
            "Public third-party copy; raw vendor receipt and contract-roll metadata were not included.",
            "NQ five-minute continuous-contract bars are used as the price-path proxy; MNQ execution costs are modeled.",
            "Five-minute OHLC cannot resolve same-bar path; the simulator uses conservative stop-before-target ordering.",
            "This is strategy research only and does not authorize a live strategy or mode change.",
        ],
        "data": {
            "start": str(dates[0]),
            "end": str(dates[-1]),
            "complete_rth_sessions": len(dates),
            "raw_rows": int(len(bars)),
            "or_close_to_next_open": _bar_boundary_gap_stats(sessions),
        },
        "split": {
            "rule": "chronological 70/30",
            "is_start": str(is_dates[0]),
            "is_end": str(is_dates[-1]),
            "is_sessions": len(is_dates),
            "oos_start": str(oos_dates[0]),
            "oos_end": str(oos_dates[-1]),
            "oos_sessions": len(oos_dates),
        },
        "selection_gate": {
            "description": "IS mean trade R minus one standard error > 0; >=100 IS trades; >=3/4 profitable chronological IS folds",
            "selected_replacement": selected,
            "strategy_change_authorized": False,
        },
        "costs": {
            "slippage_ticks_per_side": 1,
            "commission_usd_per_side": COMMISSION_PER_SIDE,
            "mnq_point_value": POINT_VALUE,
        },
        "candidates": rows,
        "selected_oos_minus_baseline": comparison,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    sorted_rows = sorted(rows, key=lambda row: row["is_score"] if row["is_score"] is not None else -math.inf, reverse=True)
    lines = [
        "# Multi-year NQ/MNQ ORB chronological 70/30 study",
        "",
        f"Data: {dates[0]} through {dates[-1]}, {len(dates)} complete RTH sessions.",
        f"IS: {is_dates[0]} through {is_dates[-1]} ({len(is_dates)} sessions).",
        f"Untouched OOS: {oos_dates[0]} through {oos_dates[-1]} ({len(oos_dates)} sessions).",
        f"IS-selected replacement: `{selected}`." if selected else "IS-selected replacement: none passed the predefined gate.",
        "Live strategy change authorized: no.",
        "",
        "## Candidate results",
        "",
        "| Candidate | Gate | Positive folds | IS trades | IS total R | IS mean R/trade | OOS trades | OOS total R | OOS mean R/trade | OOS max DD R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted_rows:
        lines.append(
            f"| {row['candidate']} | {'pass' if row['eligible_replacement'] else 'fail'} | {row['positive_is_folds']}/4 | "
            f"{row['is']['trades']} | {row['is']['total_r']:.3f} | {row['is']['mean_r_per_trade']:.4f} | "
            f"{row['oos']['trades']} | {row['oos']['total_r']:.3f} | {row['oos']['mean_r_per_trade']:.4f} | "
            f"{row['oos']['max_drawdown_r']:.3f} |"
        )
    lines += ["", "## Timing parity diagnostic", ""]
    gap = result["data"]["or_close_to_next_open"]
    lines.append(
        f"First OR close equals next five-minute open in {gap['exact_match_rate']:.2%} of sessions; "
        f"mean absolute gap {gap['mean_abs_points']:.4f} points, 95th percentile {gap['p95_abs_points']:.4f}, "
        f"maximum {gap['max_abs_points']:.4f}. Live execution still uses the actual market fill as source of truth."
    )
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in result["limits"]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"split": result["split"], "selected": selected, "comparison": comparison}, indent=2))
    return result


if __name__ == "__main__":
    main()
