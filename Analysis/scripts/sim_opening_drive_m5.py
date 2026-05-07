"""Local Python simulation of nq_p4_opening_drive_v0.pine on M5.

Loads MNQM6 1-sec mid-price bars from Analysis/output/mbp10_batch/derived/,
resamples to 5-min OHLC, and replays the Pine logic to count how often each
intermediate condition fires. Goal is to find the bottleneck without needing
TradingView.

Caveats:
- 6 RTH-only days, no overnight priming for the 170-min EMA.
- Mid price (no spread effects on entries).
- Session strings handled in UTC: ET 08:45-11:00 = 12:45-15:00 UTC.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_GLOB = str(ROOT / "Analysis/output/mbp10_batch/derived/*_MNQM6_1s.csv")

# Pine inputs (defaults from nq_p4_opening_drive_v0.pine)
ATR_MIN = 70
DRIVE_LOOKBACK_MIN = 30
DRIVE_ATR = 0.85
EMA_MIN = 170
PULLBACK_EMA_MIN = 25
PULLBACK_MIN = 25
DRIVE_VALID_MIN = 30

BAR_MIN = 5  # M5
ATR_LEN = max(2, round(ATR_MIN / BAR_MIN))
DRIVE_LOOKBACK = max(2, round(DRIVE_LOOKBACK_MIN / BAR_MIN))
EMA_LEN = max(2, round(EMA_MIN / BAR_MIN))
PULLBACK_EMA_LEN = max(2, round(PULLBACK_EMA_MIN / BAR_MIN))
PULLBACK_BARS = max(1, round(PULLBACK_MIN / BAR_MIN))
DRIVE_VALID_BARS = max(1, round(DRIVE_VALID_MIN / BAR_MIN))

# Entry window: 0845-1100 ET = 12:45-15:00 UTC. tradeSession: 0835-1455 ET = 12:35-18:55 UTC.
# (TV session strings interpret as the SYMBOL'S exchange tz; for CME_MINI:NQ1! that's ET.)
ENTRY_START_UTC = "12:45"
ENTRY_END_UTC = "15:00"


def load_bars() -> pd.DataFrame:
    files = sorted(glob.glob(DATA_GLOB))
    print(f"loaded {len(files)} day files")
    frames = []
    for f in files:
        df = pd.read_csv(f, usecols=["second", "mid"])
        df["second"] = pd.to_datetime(df["second"], utc=True)
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sort_values("second").reset_index(drop=True)


def resample_5min(secs: pd.DataFrame) -> pd.DataFrame:
    secs = secs.set_index("second")
    o = secs["mid"].resample("5min").first()
    h = secs["mid"].resample("5min").max()
    l = secs["mid"].resample("5min").min()
    c = secs["mid"].resample("5min").last()
    bars = pd.concat([o, h, l, c], axis=1).dropna()
    bars.columns = ["open", "high", "low", "close"]
    return bars


def atr(bars: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = bars["high"], bars["low"], bars["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    # Pine's ta.atr uses RMA (Wilder). RMA = EMA with alpha=1/n.
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def barssince(cond: pd.Series) -> pd.Series:
    """Pine ta.barssince: bars since last True. Na before first True."""
    out = np.full(len(cond), np.nan)
    last = -1
    for i, v in enumerate(cond.values):
        if v:
            last = i
            out[i] = 0
        elif last >= 0:
            out[i] = i - last
    return pd.Series(out, index=cond.index)


def main():
    secs = load_bars()
    bars = resample_5min(secs)
    print(f"resampled to {len(bars)} M5 bars from {bars.index[0]} to {bars.index[-1]}")

    bars["atr"] = atr(bars, ATR_LEN)
    bars["ema_slow"] = ema(bars["close"], EMA_LEN)
    bars["ema_pull"] = ema(bars["close"], PULLBACK_EMA_LEN)
    bars["drive_move"] = (bars["close"] - bars["close"].shift(DRIVE_LOOKBACK)) / bars["atr"]

    bars["long_drive"] = (bars["drive_move"] >= DRIVE_ATR) & (bars["close"] > bars["ema_slow"])
    bars["short_drive"] = (bars["drive_move"] <= -DRIVE_ATR) & (bars["close"] < bars["ema_slow"])

    bars["since_long_drive"] = barssince(bars["long_drive"])
    bars["since_short_drive"] = barssince(bars["short_drive"])
    bars["long_drive_recent"] = bars["since_long_drive"].notna() & (bars["since_long_drive"] <= DRIVE_VALID_BARS)
    bars["short_drive_recent"] = bars["since_short_drive"].notna() & (bars["since_short_drive"] <= DRIVE_VALID_BARS)

    bars["lowest_low"] = bars["low"].rolling(PULLBACK_BARS).min()
    bars["highest_high"] = bars["high"].rolling(PULLBACK_BARS).max()
    bars["long_pullback_touched"] = bars["lowest_low"] <= bars["ema_pull"]
    bars["short_pullback_touched"] = bars["highest_high"] >= bars["ema_pull"]

    t = bars.index.tz_convert("UTC").time
    in_entry = (t >= pd.Timestamp(ENTRY_START_UTC).time()) & (t <= pd.Timestamp(ENTRY_END_UTC).time())
    bars["in_entry"] = in_entry

    bars["long_signal"] = (
        bars["in_entry"]
        & bars["long_drive_recent"]
        & bars["long_pullback_touched"]
        & (bars["close"] > bars["ema_pull"])
        & (bars["close"] > bars["ema_slow"])
    )
    bars["short_signal"] = (
        bars["in_entry"]
        & bars["short_drive_recent"]
        & bars["short_pullback_touched"]
        & (bars["close"] < bars["ema_pull"])
        & (bars["close"] < bars["ema_slow"])
    )

    print("\n=== condition counts (within entry window only) ===")
    ew = bars[bars["in_entry"]]
    print(f"entry-window bars                : {len(ew)}")
    print(f"close > ema_slow                 : {ew['close'].gt(ew['ema_slow']).sum()}")
    print(f"close < ema_slow                 : {ew['close'].lt(ew['ema_slow']).sum()}")
    print(f"long_drive raw                   : {ew['long_drive'].sum()}")
    print(f"short_drive raw                  : {ew['short_drive'].sum()}")
    print(f"long_drive_recent                : {ew['long_drive_recent'].sum()}")
    print(f"short_drive_recent               : {ew['short_drive_recent'].sum()}")
    print(f"long_pullback_touched            : {ew['long_pullback_touched'].sum()}")
    print(f"short_pullback_touched           : {ew['short_pullback_touched'].sum()}")
    print(f"long_signal (all 5 conditions)   : {ew['long_signal'].sum()}")
    print(f"short_signal (all 5 conditions)  : {ew['short_signal'].sum()}")

    print("\n=== drive_move distribution in entry window ===")
    print(ew["drive_move"].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).to_string())

    print("\n=== pre-fix vs post-fix: how many bars meet OLD long signal (pullback to ema_slow)? ===")
    old_long_pullback = bars["lowest_low"] <= bars["ema_slow"]
    old_long_signal = (
        bars["in_entry"]
        & bars["long_drive_recent"]
        & old_long_pullback
        & (bars["close"] > bars["ema_slow"])
    )
    print(f"OLD long_signal (pullback to slow EMA): {old_long_signal.sum()}")


if __name__ == "__main__":
    main()
