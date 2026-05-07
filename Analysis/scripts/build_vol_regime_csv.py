"""Fetch daily market data and build a causal volatility-regime CSV.

Default source is Yahoo Finance daily QQQ data, used as a liquid NQ/NDX
volatility proxy. The output is intended for `tv_phase4_oos_regime_gate.py`.

Run:
    .venv/bin/python Analysis/scripts/build_vol_regime_csv.py \
        --symbol QQQ \
        --output Analysis/output/vol_regimes/qqq_daily_vol_regimes.csv

Output schema:
    session_date,realized_vol,vol_profile,source_symbol,rv_window,profile_lookback

`vol_profile` is causal by default: each day's low/mid/high label is based on
that day's rolling realized volatility compared with the prior
`profile_lookback` realized-vol observations. No future dates are used.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_OUTPUT = Path("Analysis/output/vol_regimes/qqq_daily_vol_regimes.csv")


@dataclass(frozen=True)
class DailyBar:
    session_date: date
    close: float
    high: float
    low: float


@dataclass(frozen=True)
class VolRegimeRow:
    session_date: date
    realized_vol: float
    atr_pct: float
    vol_profile: str
    source_symbol: str
    rv_window: int
    profile_lookback: int


def fetch_yahoo_daily_bars(
    symbol: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[DailyBar]:
    """Fetch daily OHLC data from Yahoo Finance's chart endpoint."""
    period1 = _unix_seconds(start_date or date(2000, 1, 1))
    period2 = _unix_seconds(end_date or date(2100, 1, 1))
    url = (
        YAHOO_CHART_URL.format(symbol=symbol.upper())
        + f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"failed to fetch {url}") from exc
    return parse_yahoo_chart_json(raw)


def parse_yahoo_chart_json(raw_json: str) -> list[DailyBar]:
    """Parse Yahoo chart JSON into sorted daily bars."""
    payload = json.loads(raw_json)
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise ValueError(f"Yahoo chart error: {error}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart response contains no result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    bars: list[DailyBar] = []
    for timestamp, close, high, low in zip(timestamps, closes, highs, lows, strict=False):
        if close is None or high is None or low is None:
            continue
        bars.append(
            DailyBar(
                session_date=datetime.fromtimestamp(timestamp, tz=timezone.utc).date(),
                close=float(close),
                high=float(high),
                low=float(low),
            )
        )
    return sorted(bars, key=lambda bar: bar.session_date)


def parse_stooq_daily_csv(raw_csv: str) -> list[DailyBar]:
    """Parse Stooq CSV text into sorted daily bars.

    Kept for unit-level parser coverage and fallback/manual CSV use. Stooq's
    no-key daily endpoint may require an API key depending on environment.
    """
    rows = list(csv.DictReader(raw_csv.splitlines()))
    bars: list[DailyBar] = []
    for row in rows:
        if not row or row.get("Close") in {None, "", "0"}:
            continue
        bars.append(
            DailyBar(
                session_date=date.fromisoformat(row["Date"]),
                close=float(row["Close"]),
                high=float(row["High"]),
                low=float(row["Low"]),
            )
        )
    return sorted(bars, key=lambda bar: bar.session_date)


def build_vol_regime_rows(
    bars: Sequence[DailyBar],
    *,
    symbol: str,
    rv_window: int = 20,
    atr_window: int = 14,
    profile_lookback: int = 252,
    low_quantile: float = 1 / 3,
    high_quantile: float = 2 / 3,
) -> list[VolRegimeRow]:
    """Compute causal realized-volatility regime rows from daily bars."""
    if rv_window <= 1:
        raise ValueError("rv_window must be greater than 1")
    if atr_window <= 0:
        raise ValueError("atr_window must be positive")
    if profile_lookback < 10:
        raise ValueError("profile_lookback must be at least 10")
    if not 0 < low_quantile < high_quantile < 1:
        raise ValueError("quantiles must satisfy 0 < low < high < 1")
    if len(bars) <= rv_window + profile_lookback:
        raise ValueError("not enough bars for requested windows")

    log_returns = [0.0]
    true_ranges = [bars[0].high - bars[0].low]
    for prev, current in zip(bars, bars[1:], strict=False):
        log_returns.append(math.log(current.close / prev.close))
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - prev.close),
                abs(current.low - prev.close),
            )
        )

    realized_vols: list[float | None] = []
    atr_pcts: list[float | None] = []
    for index, bar in enumerate(bars):
        if index < rv_window:
            realized_vols.append(None)
        else:
            window = log_returns[index - rv_window + 1 : index + 1]
            realized_vols.append(_sample_std(window) * math.sqrt(252))

        if index + 1 < atr_window:
            atr_pcts.append(None)
        else:
            atr = sum(true_ranges[index - atr_window + 1 : index + 1]) / atr_window
            atr_pcts.append(atr / bar.close if bar.close else None)

    rows: list[VolRegimeRow] = []
    for index, bar in enumerate(bars):
        realized_vol = realized_vols[index]
        atr_pct = atr_pcts[index]
        if realized_vol is None or atr_pct is None:
            continue
        history = [
            value
            for value in realized_vols[max(0, index - profile_lookback) : index]
            if value is not None
        ]
        if len(history) < profile_lookback:
            continue
        low_cut = _quantile(sorted(history), low_quantile)
        high_cut = _quantile(sorted(history), high_quantile)
        if realized_vol <= low_cut:
            profile = "low"
        elif realized_vol >= high_cut:
            profile = "high"
        else:
            profile = "mid"
        rows.append(
            VolRegimeRow(
                session_date=bar.session_date,
                realized_vol=realized_vol,
                atr_pct=atr_pct,
                vol_profile=profile,
                source_symbol=symbol,
                rv_window=rv_window,
                profile_lookback=profile_lookback,
            )
        )
    return rows


def write_vol_regime_csv(rows: Sequence[VolRegimeRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "session_date",
                "realized_vol",
                "atr_pct",
                "vol_profile",
                "source_symbol",
                "rv_window",
                "profile_lookback",
            ),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "session_date": row.session_date.isoformat(),
                    "realized_vol": f"{row.realized_vol:.8f}",
                    "atr_pct": f"{row.atr_pct:.8f}",
                    "vol_profile": row.vol_profile,
                    "source_symbol": row.source_symbol,
                    "rv_window": row.rv_window,
                    "profile_lookback": row.profile_lookback,
                }
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="QQQ", help="Yahoo Finance symbol, e.g. QQQ")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2000, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=None)
    parser.add_argument("--rv-window", type=int, default=20)
    parser.add_argument("--atr-window", type=int, default=14)
    parser.add_argument("--profile-lookback", type=int, default=252)
    parser.add_argument("--low-quantile", type=float, default=1 / 3)
    parser.add_argument("--high-quantile", type=float, default=2 / 3)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    bars = fetch_yahoo_daily_bars(
        args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    rows = build_vol_regime_rows(
        bars,
        symbol=args.symbol,
        rv_window=args.rv_window,
        atr_window=args.atr_window,
        profile_lookback=args.profile_lookback,
        low_quantile=args.low_quantile,
        high_quantile=args.high_quantile,
    )
    write_vol_regime_csv(rows, args.output)
    counts = {profile: sum(1 for row in rows if row.vol_profile == profile) for profile in ("low", "mid", "high")}
    print(
        f"Wrote {len(rows)} rows to {args.output} "
        f"from {bars[0].session_date}..{bars[-1].session_date} "
        f"counts={counts}"
    )


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    index = (len(sorted_values) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _unix_seconds(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
