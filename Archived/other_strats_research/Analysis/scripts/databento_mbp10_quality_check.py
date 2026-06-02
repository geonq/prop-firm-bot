"""Inspect a Databento GLBX.MDP3 MBP-10 DBN file for L2 feature viability."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd


DEPTH_LEVELS = (1, 3, 5, 10)
FORWARD_SECONDS = (1, 5, 15, 60)
ROLLING_SECONDS = (5, 15, 60)


def depth_sum(df: pd.DataFrame, side: str, levels: int) -> pd.Series:
    cols = [f"{side}_sz_{idx:02d}" for idx in range(levels)]
    return df[cols].sum(axis=1).astype(float)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate MBP-10 content and derive 1-second L2 features.")
    parser.add_argument("dbn_path", help="Path to .dbn or .dbn.zst file.")
    parser.add_argument("--symbol", help="Mapped symbol to analyze. If omitted, only symbol counts are printed.")
    parser.add_argument("--chunk-size", type=int, default=250_000)
    parser.add_argument("--output-csv", help="Optional path for derived 1-second feature CSV.")
    args = parser.parse_args()

    import databento as db

    store = db.DBNStore.from_file(args.dbn_path)
    symbol_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    target_action_counts: Counter[str] = Counter()
    per_second_frames: list[pd.DataFrame] = []

    target_records = 0
    invalid_spread = 0
    min_ts = None
    max_ts = None

    for chunk in store.to_df(
        count=args.chunk_size,
        price_type="float",
        pretty_ts=True,
        map_symbols=True,
    ):
        symbol_counts.update(chunk["symbol"].astype(str).value_counts().to_dict())
        action_counts.update(chunk["action"].astype(str).value_counts().to_dict())

        if not args.symbol:
            continue

        df = chunk[chunk["symbol"] == args.symbol].copy()
        if df.empty:
            continue

        target_records += len(df)
        target_action_counts.update(df["action"].astype(str).value_counts().to_dict())
        min_ts = df["ts_event"].min() if min_ts is None else min(min_ts, df["ts_event"].min())
        max_ts = df["ts_event"].max() if max_ts is None else max(max_ts, df["ts_event"].max())

        valid_quote = (df["bid_px_00"] > 0) & (df["ask_px_00"] > df["bid_px_00"])
        invalid_spread += int((~valid_quote).sum())
        df = df[valid_quote]
        if df.empty:
            continue

        features = pd.DataFrame(index=df.index)
        features["ts_event"] = df["ts_event"]
        features["second"] = df["ts_event"].dt.floor("s")
        features["mid"] = (df["bid_px_00"] + df["ask_px_00"]) / 2.0
        features["spread"] = df["ask_px_00"] - df["bid_px_00"]
        features["events"] = 1
        features["trades"] = (df["action"] == "T").astype(int)
        features["trade_volume"] = df["size"].where(df["action"] == "T", 0)

        for levels in DEPTH_LEVELS:
            bid_depth = depth_sum(df, "bid", levels)
            ask_depth = depth_sum(df, "ask", levels)
            total_depth = bid_depth + ask_depth
            features[f"bid_depth_l{levels}"] = bid_depth
            features[f"ask_depth_l{levels}"] = ask_depth
            features[f"imbalance_l{levels}"] = (bid_depth - ask_depth) / total_depth.where(total_depth != 0)

        grouped = features.groupby("second").agg(
            ts_event=("ts_event", "last"),
            mid=("mid", "last"),
            spread=("spread", "median"),
            events=("events", "sum"),
            trades=("trades", "sum"),
            trade_volume=("trade_volume", "sum"),
            **{
                f"{name}_last": (name, "last")
                for levels in DEPTH_LEVELS
                for name in (
                    f"bid_depth_l{levels}",
                    f"ask_depth_l{levels}",
                    f"imbalance_l{levels}",
                )
            },
        )
        per_second_frames.append(grouped.reset_index())

    print(f"dataset={store.metadata.dataset}")
    print(f"schema={store.metadata.schema}")
    print(f"requested_symbols={list(store.metadata.symbols)}")
    print("symbol_counts=" + repr(symbol_counts.most_common()))
    print("action_counts=" + repr(action_counts))

    if not args.symbol:
        return

    if target_records == 0:
        raise SystemExit(f"No records found for symbol {args.symbol!r}.")

    one_second = pd.concat(per_second_frames, ignore_index=True)
    one_second = (
        one_second.sort_values(["second", "ts_event"])
        .groupby("second", as_index=False)
        .agg(
            ts_event=("ts_event", "last"),
            mid=("mid", "last"),
            spread=("spread", "median"),
            events=("events", "sum"),
            trades=("trades", "sum"),
            trade_volume=("trade_volume", "sum"),
            **{
                col: (col, "last")
                for col in one_second.columns
                if col.endswith("_last")
            },
        )
    )
    one_second = one_second.set_index("second").sort_index()

    full_index = pd.date_range(one_second.index.min(), one_second.index.max(), freq="s", tz="UTC")
    one_second = one_second.reindex(full_index)
    for col in ["mid"] + [c for c in one_second.columns if c.endswith("_last")]:
        one_second[col] = one_second[col].ffill()
    for col in ("events", "trades", "trade_volume"):
        one_second[col] = one_second[col].fillna(0)
    one_second["spread"] = one_second["spread"].ffill()

    for seconds in FORWARD_SECONDS:
        one_second[f"fwd_ret_{seconds}s"] = one_second["mid"].shift(-seconds) - one_second["mid"]

    for levels in DEPTH_LEVELS:
        bid_col = f"bid_depth_l{levels}_last"
        ask_col = f"ask_depth_l{levels}_last"
        total_depth = one_second[bid_col] + one_second[ask_col]
        depth_pressure = one_second[bid_col].diff().fillna(0) - one_second[ask_col].diff().fillna(0)
        one_second[f"depth_pressure_l{levels}"] = depth_pressure / total_depth.where(total_depth != 0)
        for seconds in ROLLING_SECONDS:
            one_second[f"depth_pressure_l{levels}_{seconds}s"] = (
                one_second[f"depth_pressure_l{levels}"].rolling(seconds, min_periods=1).sum()
            )

    print(f"target_symbol={args.symbol}")
    print(f"target_records={target_records}")
    print(f"target_actions={target_action_counts}")
    print(f"ts_event_min={min_ts}")
    print(f"ts_event_max={max_ts}")
    print(f"invalid_or_crossed_spread_records={invalid_spread}")
    print(f"seconds={len(one_second)}")
    print(f"seconds_with_events={int((one_second['events'] > 0).sum())}")
    print(f"median_events_per_active_second={one_second.loc[one_second['events'] > 0, 'events'].median():.2f}")
    print(f"median_spread={one_second['spread'].median():.4f}")
    print(f"max_spread={one_second['spread'].max():.4f}")
    print(f"trade_records={int(one_second['trades'].sum())}")
    print(f"trade_volume={int(one_second['trade_volume'].sum())}")

    corr_cols = [f"imbalance_l{levels}_last" for levels in DEPTH_LEVELS]
    for fwd in FORWARD_SECONDS:
        ret_col = f"fwd_ret_{fwd}s"
        corrs = one_second[corr_cols + [ret_col]].corr(numeric_only=True)[ret_col].drop(ret_col)
        print(f"corr_{fwd}s=" + ", ".join(f"{idx}:{val:.4f}" for idx, val in corrs.items()))

    for seconds in ROLLING_SECONDS:
        ret_col = f"fwd_ret_{seconds}s"
        pressure_cols = [f"depth_pressure_l{levels}_{seconds}s" for levels in DEPTH_LEVELS]
        corrs = one_second[pressure_cols + [ret_col]].corr(numeric_only=True)[ret_col].drop(ret_col)
        print(f"pressure_corr_{seconds}s=" + ", ".join(f"{idx}:{val:.4f}" for idx, val in corrs.items()))

    if args.output_csv:
        output = Path(args.output_csv)
        output.parent.mkdir(parents=True, exist_ok=True)
        one_second.to_csv(output, index_label="second")
        print(f"output_csv={output}")


if __name__ == "__main__":
    main()
