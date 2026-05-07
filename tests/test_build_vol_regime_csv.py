from datetime import date, timedelta

from Analysis.scripts.build_vol_regime_csv import (
    DailyBar,
    build_vol_regime_rows,
    parse_yahoo_chart_json,
    parse_stooq_daily_csv,
)


def test_parse_stooq_daily_csv() -> None:
    raw = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-05,100,102,99,101,1000\n"
        "2026-01-06,101,103,100,102,1000\n"
    )

    bars = parse_stooq_daily_csv(raw)

    assert len(bars) == 2
    assert bars[0].session_date == date(2026, 1, 5)
    assert bars[1].close == 102.0


def test_parse_yahoo_chart_json() -> None:
    raw = (
        '{"chart":{"result":[{"timestamp":[1767571200,1767657600],'
        '"indicators":{"quote":[{"close":[101.0,102.0],'
        '"high":[102.0,103.0],"low":[99.0,100.0]}]}}],"error":null}}'
    )

    bars = parse_yahoo_chart_json(raw)

    assert len(bars) == 2
    assert bars[0].close == 101.0
    assert bars[1].high == 103.0


def test_build_vol_regime_rows_are_causal_and_labeled() -> None:
    base = date(2024, 1, 1)
    bars = []
    close = 100.0
    for index in range(80):
        step = 0.15 if index % 2 == 0 else -0.10
        if index >= 55:
            step = 1.20 if index % 2 == 0 else -0.95
        close += step
        bars.append(
            DailyBar(
                session_date=base + timedelta(days=index),
                close=close,
                high=close + abs(step) + 0.5,
                low=close - abs(step) - 0.5,
            )
        )

    rows = build_vol_regime_rows(
        bars,
        symbol="test",
        rv_window=5,
        atr_window=3,
        profile_lookback=20,
    )

    assert rows
    assert {row.vol_profile for row in rows} <= {"low", "mid", "high"}
    post_transition = [row for row in rows if row.session_date >= base + timedelta(days=55)]
    assert any(row.vol_profile == "high" for row in post_transition[:10])
    assert rows[-1].session_date == bars[-1].session_date
