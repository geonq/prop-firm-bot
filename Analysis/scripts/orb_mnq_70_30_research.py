"""Independent 70/30 MNQ five-minute ORB diagnostic.

This is a research-only script. It does not modify the frozen live strategy. Candidate
rules are literature-anchored and selected only on the first chronological 70% of
sessions; the final 30% is evaluated once after selection.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Analysis" / "output" / "orb_mnq_70_30"
RAW = OUT / "mnq_yahoo_5m_60d.csv"
ET = "America/New_York"
TICK = 0.25
POINT_VALUE = 2.0
COMMISSION_PER_SIDE = 0.74

Entry = Literal["first_candle", "directional_breakout"]
Stop = Literal["or_opposite", "atr_frac"]
FirstCandleReference = Literal["or_close", "next_open"]


@dataclass(frozen=True)
class Candidate:
    name: str
    entry: Entry
    stop: Stop = "or_opposite"
    stop_atr_frac: float | None = None
    target_r: float | None = 4.0
    time_stop_minutes: int | None = 120
    entry_cutoff: time = time(15, 30)
    rel_volume_min: float | None = None
    vol_percentile_min: float | None = None
    or_range_atr_min: float | None = None
    doji_threshold: float = 0.10
    first_candle_reference: FirstCandleReference = "next_open"


@dataclass(frozen=True)
class Trade:
    session_date: date
    candidate: str
    direction: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    risk_points: float
    r: float
    exit_reason: str


def chronological_split(dates: list[date], ratio: float = 0.70) -> tuple[list[date], list[date]]:
    if not 0.0 < ratio < 1.0:
        raise ValueError("ratio must be between zero and one")
    ordered = sorted(set(dates))
    cut = int(math.floor(len(ordered) * ratio))
    if cut == 0 or cut == len(ordered):
        raise ValueError("not enough dates for split")
    return ordered[:cut], ordered[cut:]


def percentile_rank(value: float, reference: list[float]) -> float:
    if not reference:
        return float("nan")
    return 100.0 * sum(x <= value for x in reference) / len(reference)


def summarize_daily(daily: pd.Series, *, trade_count: int) -> dict:
    values = daily.astype(float)
    equity = values.cumsum()
    running_max = equity.cummax().clip(lower=0.0)
    drawdown = running_max - equity
    nonzero = values[values != 0]
    losses = -nonzero[nonzero < 0].sum()
    wins = nonzero[nonzero > 0].sum()
    std = float(nonzero.std(ddof=1)) if len(nonzero) > 1 else float("nan")
    return {
        "sessions": int(len(values)),
        "trades": int(trade_count),
        "trade_rate": float(trade_count / len(values)) if len(values) else float("nan"),
        "total_r": float(values.sum()),
        "mean_r_per_session": float(values.mean()) if len(values) else float("nan"),
        "mean_r_per_trade": float(nonzero.mean()) if len(nonzero) else float("nan"),
        "win_rate": float((nonzero > 0).mean()) if len(nonzero) else float("nan"),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "max_drawdown_r": float(drawdown.max()) if len(drawdown) else 0.0,
        "trade_sharpe": float(nonzero.mean() / std * math.sqrt(len(nonzero))) if std > 0 else float("nan"),
    }


def download_bars() -> pd.DataFrame:
    import yfinance as yf

    frame = yf.download(
        "MNQ=F", period="60d", interval="5m", prepost=True,
        auto_adjust=False, progress=False, threads=False,
    )
    if frame.empty:
        raise RuntimeError("Yahoo returned no MNQ five-minute bars")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(a).lower().replace(" ", "_") for a, _ in frame.columns]
    else:
        frame.columns = [str(c).lower().replace(" ", "_") for c in frame.columns]
    frame = frame[["open", "high", "low", "close", "volume"]].dropna()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index = frame.index.tz_convert(ET)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(RAW)
    return frame


def sessions_from_bars(bars: pd.DataFrame) -> dict[date, pd.DataFrame]:
    rth = bars.between_time("09:30", "15:59")
    sessions: dict[date, pd.DataFrame] = {}
    for session_date, day in rth.groupby(rth.index.date):
        # Normal full RTH has 78 five-minute bars. Exclude early closes and degraded data.
        if len(day) >= 75 and day.index[0].time() == time(9, 30):
            sessions[session_date] = day.iloc[:78].copy()
    return sessions


def _daily_features(sessions: dict[date, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    previous_close = None
    true_ranges: list[float] = []
    first_volumes: list[float] = []
    daily_returns: list[float] = []
    for d, bars in sessions.items():
        high, low = float(bars.high.max()), float(bars.low.min())
        close, open_ = float(bars.close.iloc[-1]), float(bars.open.iloc[0])
        tr = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        atr_prior = float(np.mean(true_ranges[-14:])) if len(true_ranges) >= 14 else np.nan
        rel_volume = float(bars.volume.iloc[0] / np.mean(first_volumes[-14:])) if len(first_volumes) >= 14 and np.mean(first_volumes[-14:]) > 0 else np.nan
        realized = float(np.std(daily_returns[-20:], ddof=1)) if len(daily_returns) >= 20 else np.nan
        prior_realized_values = []
        if len(daily_returns) >= 20:
            for end in range(20, len(daily_returns) + 1):
                prior_realized_values.append(float(np.std(daily_returns[end - 20:end], ddof=1)))
        vol_percentile = (
            sum(x <= realized for x in prior_realized_values) / len(prior_realized_values)
            if prior_realized_values else np.nan
        )
        or_range = float(bars.high.iloc[0] - bars.low.iloc[0])
        rows.append({
            "date": d, "atr_prior": atr_prior, "rel_volume": rel_volume,
            "vol_percentile": vol_percentile,
            "or_range_atr": or_range / atr_prior if atr_prior > 0 else np.nan,
        })
        if previous_close is not None:
            daily_returns.append(close / previous_close - 1.0)
        previous_close = close
        true_ranges.append(tr)
        first_volumes.append(float(bars.volume.iloc[0]))
    return pd.DataFrame(rows).set_index("date")


def _fill(price: float, side: str) -> float:
    return price + TICK if side == "buy" else price - TICK


def _eligible(candidate: Candidate, feature: pd.Series) -> bool:
    checks = [
        candidate.rel_volume_min is None or (pd.notna(feature.rel_volume) and feature.rel_volume >= candidate.rel_volume_min),
        candidate.vol_percentile_min is None or (pd.notna(feature.vol_percentile) and feature.vol_percentile >= candidate.vol_percentile_min),
        candidate.or_range_atr_min is None or (pd.notna(feature.or_range_atr) and feature.or_range_atr >= candidate.or_range_atr_min),
    ]
    return all(checks)


def simulate_day(day: pd.DataFrame, d: date, candidate: Candidate, feature: pd.Series) -> Trade | None:
    if not _eligible(candidate, feature):
        return None
    first = day.iloc[0]
    or_open, or_close = float(first.open), float(first.close)
    or_high, or_low = float(first.high), float(first.low)
    or_range = or_high - or_low
    if or_range <= 0 or abs(or_close - or_open) / or_range < candidate.doji_threshold:
        return None
    direction = "long" if or_close > or_open else "short"
    post = day.iloc[1:]

    if candidate.entry == "first_candle":
        entry_idx = 0
        entry_ts = post.index[0]
        raw_entry = or_close if candidate.first_candle_reference == "or_close" else float(post.open.iloc[0])
    else:
        entry_idx = None
        entry_ts = None
        raw_entry = None
        for idx, (ts, bar) in enumerate(post.iterrows()):
            if ts.time() > candidate.entry_cutoff:
                break
            if direction == "long" and float(bar.high) >= or_high:
                entry_idx, entry_ts, raw_entry = idx, ts, max(or_high, float(bar.open))
                break
            if direction == "short" and float(bar.low) <= or_low:
                entry_idx, entry_ts, raw_entry = idx, ts, min(or_low, float(bar.open))
                break
        if entry_idx is None:
            return None

    entry = _fill(float(raw_entry), "buy" if direction == "long" else "sell")
    if candidate.stop == "or_opposite":
        stop = or_low if direction == "long" else or_high
    else:
        if candidate.stop_atr_frac is None or not pd.notna(feature.atr_prior):
            return None
        distance = candidate.stop_atr_frac * float(feature.atr_prior)
        stop = entry - distance if direction == "long" else entry + distance
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    target = None if candidate.target_r is None else entry + candidate.target_r * risk * (1 if direction == "long" else -1)
    remaining = post.iloc[int(entry_idx):]
    deadline = entry_ts + pd.Timedelta(minutes=candidate.time_stop_minutes) if candidate.time_stop_minutes else None
    reached_one_r = False
    pending_time_exit = False

    for ts, bar in remaining.iterrows():
        open_, high, low, close = map(float, (bar.open, bar.high, bar.low, bar.close))
        stop_hit = low <= stop if direction == "long" else high >= stop
        target_hit = False if target is None else (high >= target if direction == "long" else low <= target)
        if stop_hit:
            raw_exit, reason = stop, "stop"
        elif target_hit:
            raw_exit, reason = float(target), "target"
        elif pending_time_exit:
            raw_exit, reason = open_, "time_stop"
        else:
            favorable_close = (close - entry) if direction == "long" else (entry - close)
            reached_one_r = reached_one_r or favorable_close >= risk
            if deadline is not None and ts >= deadline and not reached_one_r:
                pending_time_exit = True
            continue
        exit_price = _fill(raw_exit, "sell" if direction == "long" else "buy")
        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        net_points = gross - (2 * COMMISSION_PER_SIDE / POINT_VALUE)
        return Trade(d, candidate.name, direction, entry_ts, ts, entry, exit_price, risk, net_points / risk, reason)

    ts = remaining.index[-1]
    raw_exit = float(remaining.close.iloc[-1])
    exit_price = _fill(raw_exit, "sell" if direction == "long" else "buy")
    gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
    net_points = gross - (2 * COMMISSION_PER_SIDE / POINT_VALUE)
    return Trade(d, candidate.name, direction, entry_ts, ts, entry, exit_price, risk, net_points / risk, "eod")


def candidate_grid() -> list[Candidate]:
    # Small, pre-specified, literature-motivated grid. No OOS-driven mutation.
    return [
        Candidate("deployed_opening_drive", "first_candle", first_candle_reference="or_close"),
        Candidate("true_orb_orstop_4r_120_cut1030", "directional_breakout", entry_cutoff=time(10, 30)),
        Candidate("true_orb_orstop_eod_cut1030", "directional_breakout", target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30)),
        Candidate("true_orb_orstop_eod_relvol1", "directional_breakout", target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30), rel_volume_min=1.0),
        Candidate("true_orb_atr05_eod_relvol1", "directional_breakout", stop="atr_frac", stop_atr_frac=0.05, target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30), rel_volume_min=1.0),
        Candidate("true_orb_atr10_eod", "directional_breakout", stop="atr_frac", stop_atr_frac=0.10, target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30)),
        Candidate("true_orb_atr10_eod_relvol1", "directional_breakout", stop="atr_frac", stop_atr_frac=0.10, target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30), rel_volume_min=1.0),
        Candidate("true_orb_atr10_eod_vol50", "directional_breakout", stop="atr_frac", stop_atr_frac=0.10, target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30), vol_percentile_min=0.50),
        Candidate("true_orb_atr10_eod_range10atr", "directional_breakout", stop="atr_frac", stop_atr_frac=0.10, target_r=None, time_stop_minutes=None, entry_cutoff=time(10, 30), or_range_atr_min=0.10),
        Candidate("true_orb_atr10_4r_120", "directional_breakout", stop="atr_frac", stop_atr_frac=0.10, target_r=4.0, time_stop_minutes=120, entry_cutoff=time(10, 30)),
    ]


def _run(sessions: dict[date, pd.DataFrame], features: pd.DataFrame, candidate: Candidate) -> list[Trade]:
    return [t for d, day in sessions.items() if (t := simulate_day(day, d, candidate, features.loc[d])) is not None]


def _daily(trades: list[Trade], dates: list[date]) -> pd.Series:
    by_date = {t.session_date: t.r for t in trades}
    return pd.Series([by_date.get(d, 0.0) for d in dates], index=dates, dtype=float)


def _paired_bootstrap_delta(winner: pd.Series, baseline: pd.Series, seed: int = 7) -> dict:
    diff = (winner - baseline).to_numpy()
    rng = np.random.default_rng(seed)
    samples = rng.choice(diff, size=(20_000, len(diff)), replace=True).mean(axis=1)
    return {
        "mean_delta_r_per_session": float(diff.mean()),
        "ci95": [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))],
        "probability_delta_positive": float((samples > 0).mean()),
    }


def main() -> None:
    bars = download_bars()
    sessions = sessions_from_bars(bars)
    dates = list(sessions)
    insample_dates, outsample_dates = chronological_split(dates, 0.70)
    features = _daily_features(sessions)
    candidates = candidate_grid()
    all_trades = {c.name: _run(sessions, features, c) for c in candidates}

    rows = []
    for c in candidates:
        trades = all_trades[c.name]
        is_trades = [t for t in trades if t.session_date in set(insample_dates)]
        oos_trades = [t for t in trades if t.session_date in set(outsample_dates)]
        is_daily = _daily(is_trades, insample_dates)
        oos_daily = _daily(oos_trades, outsample_dates)
        is_summary = summarize_daily(is_daily, trade_count=len(is_trades))
        oos_summary = summarize_daily(oos_daily, trade_count=len(oos_trades))
        trade_values = is_daily[is_daily != 0]
        se = float(trade_values.std(ddof=1) / math.sqrt(len(trade_values))) if len(trade_values) > 1 else float("inf")
        # Conservative IS-only selection: one-standard-error lower bound; require >=8 trades.
        score = float(trade_values.mean() - se) if len(trade_values) >= 8 else float("-inf")
        rows.append({"candidate": c.name, "params": asdict(c), "is_score": score, "is": is_summary, "oos": oos_summary})

    winner_row = max(rows, key=lambda row: row["is_score"])
    winner_name = winner_row["candidate"]
    baseline_name = "deployed_opening_drive"
    winner_oos = _daily([t for t in all_trades[winner_name] if t.session_date in set(outsample_dates)], outsample_dates)
    baseline_oos = _daily([t for t in all_trades[baseline_name] if t.session_date in set(outsample_dates)], outsample_dates)

    latest_dates = dates[-10:]
    baseline_all = _daily(all_trades[baseline_name], dates)
    latest_sum = float(baseline_all.loc[latest_dates].sum())
    historical_10day = [float(baseline_all.iloc[i:i + 10].sum()) for i in range(0, len(dates) - 19)]
    rng = np.random.default_rng(11)
    is_values = _daily([t for t in all_trades[baseline_name] if t.session_date in set(insample_dates)], insample_dates).to_numpy()
    boot_sums = rng.choice(is_values, size=(50_000, 10), replace=True).sum(axis=1)
    tail = {
        "latest_dates": [str(d) for d in latest_dates],
        "latest_10_session_total_r": latest_sum,
        "percentile_vs_prior_rolling_10_session_windows": percentile_rank(latest_sum, historical_10day),
        "percentile_vs_is_bootstrap": float(100 * (boot_sums <= latest_sum).mean()),
        "is_bootstrap_5th_percentile_r": float(np.quantile(boot_sums, 0.05)),
        "is_bootstrap_expected_10_session_r": float(boot_sums.mean()),
    }

    result = {
        "source": "Yahoo Finance MNQ=F, unadjusted 5-minute bars, RTH only",
        "source_limits": [
            "60-day vendor-limited sample; continuous-contract construction and volume are vendor-specific",
            "five-minute bars cannot resolve within-bar path; stop-first conservative ordering used",
            "results are strategy research, not authorization to alter the live hash-locked configuration",
        ],
        "data_start": str(min(dates)), "data_end": str(max(dates)), "sessions": len(dates),
        "split": {
            "ratio": "70/30 chronological", "is_sessions": len(insample_dates), "oos_sessions": len(outsample_dates),
            "is_start": str(insample_dates[0]), "is_end": str(insample_dates[-1]),
            "oos_start": str(outsample_dates[0]), "oos_end": str(outsample_dates[-1]),
        },
        "costs": {"slippage_ticks_per_side": 1, "commission_usd_per_side": COMMISSION_PER_SIDE, "mnq_point_value": POINT_VALUE},
        "selection_rule": "highest IS mean trade R minus one standard error, minimum 8 IS trades; OOS never used for selection",
        "winner": winner_name,
        "candidates": rows,
        "oos_winner_minus_baseline": _paired_bootstrap_delta(winner_oos, baseline_oos),
        "recent_tail": tail,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    flat_trades = [asdict(t) for trades in all_trades.values() for t in trades]
    pd.DataFrame(flat_trades).to_csv(OUT / "trades.csv", index=False)

    lines = [
        "# MNQ ORB 70/30 diagnostic", "",
        f"Data: {result['data_start']} to {result['data_end']} ({result['sessions']} full RTH sessions).",
        f"Split: IS {result['split']['is_start']}..{result['split']['is_end']} ({result['split']['is_sessions']}), "
        f"OOS {result['split']['oos_start']}..{result['split']['oos_end']} ({result['split']['oos_sessions']}).",
        f"IS-selected winner: `{winner_name}`.", "", "## Candidate results", "",
        "| Candidate | IS trades | IS mean R/trade | IS total R | OOS trades | OOS mean R/trade | OOS total R | OOS max DD R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda x: x["is_score"], reverse=True):
        lines.append(
            f"| {row['candidate']} | {row['is']['trades']} | {row['is']['mean_r_per_trade']:.3f} | {row['is']['total_r']:.3f} | "
            f"{row['oos']['trades']} | {row['oos']['mean_r_per_trade']:.3f} | {row['oos']['total_r']:.3f} | {row['oos']['max_drawdown_r']:.3f} |"
        )
    delta = result["oos_winner_minus_baseline"]
    lines += [
        "", "## OOS comparison", "",
        f"Winner-minus-baseline mean: {delta['mean_delta_r_per_session']:.3f} R/session; bootstrap 95% CI "
        f"[{delta['ci95'][0]:.3f}, {delta['ci95'][1]:.3f}], P(delta>0)={delta['probability_delta_positive']:.3f}.",
        "", "## Recent two-week tail", "",
        f"Latest 10 sessions: {tail['latest_10_session_total_r']:.3f} R; percentile vs prior rolling windows "
        f"{tail['percentile_vs_prior_rolling_10_session_windows']:.1f}; percentile vs IS bootstrap "
        f"{tail['percentile_vs_is_bootstrap']:.1f}. IS bootstrap expected 10-session result "
        f"{tail['is_bootstrap_expected_10_session_r']:.3f} R and 5th percentile {tail['is_bootstrap_5th_percentile_r']:.3f} R.",
        "", "## Limitations", "",
    ] + [f"- {x}" for x in result["source_limits"]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"winner": winner_name, "split": result["split"], "delta": delta, "tail": tail}, indent=2))


if __name__ == "__main__":
    main()
