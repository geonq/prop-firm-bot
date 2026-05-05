"""Run a second-pass event study over derived MBP-10 1-second L2 features."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


DATE_RE = re.compile(r"(\d{8})")
DEFAULT_FEATURES = (
    "imbalance_l1_last",
    "imbalance_l3_last",
    "imbalance_l5_last",
    "imbalance_l10_last",
    "depth_pressure_l1_15s",
    "depth_pressure_l3_15s",
    "depth_pressure_l5_15s",
    "depth_pressure_l10_15s",
    "depth_pressure_l1_60s",
    "depth_pressure_l3_60s",
    "depth_pressure_l5_60s",
    "depth_pressure_l10_60s",
)
DEFAULT_HORIZONS = (5, 15, 60)
REGIME_FEATURES = (
    "imbalance_l1_last",
    "imbalance_l10_last",
    "depth_pressure_l10_15s",
    "depth_pressure_l10_60s",
)
REGIME_COLUMNS = (
    "time_regime",
    "spread_regime",
    "vol_regime",
    "vol_shape_regime",
    "vol_slope_regime",
    "vwap_band_regime",
    "vwap_slope_regime",
    "prior_rth_regime",
    "overnight_gap_regime",
    "combined_regime",
    "combined_shape_regime",
    "combined_slope_regime",
    "combined_vwap_band_regime",
    "combined_vwap_slope_regime",
    "combined_prior_rth_regime",
    "combined_gap_regime",
)


def discover_feature_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*_1s.csv"))


def session_date(path: Path) -> str:
    match = DATE_RE.search(path.name)
    return match.group(1) if match else path.stem


def session_name(path: Path) -> str:
    return path.name.removesuffix("_1s.csv")


def load_sessions(input_path: Path, dedupe_dates: bool) -> tuple[pd.DataFrame, list[str]]:
    frames = []
    skipped = []
    seen_dates: set[str] = set()
    for path in discover_feature_files(input_path):
        date = session_date(path)
        if dedupe_dates and date in seen_dates:
            skipped.append(str(path))
            continue
        seen_dates.add(date)

        df = pd.read_csv(path, parse_dates=["second", "ts_event"])
        df["session"] = session_name(path)
        df["session_date"] = date
        frames.append(df)

    if not frames:
        raise SystemExit(f"No *_1s.csv files found under {input_path}.")
    return pd.concat(frames, ignore_index=True), skipped


def split_dates(dates: list[str], train_fraction: float) -> tuple[set[str], set[str]]:
    ordered = sorted(dates)
    train_count = max(1, min(len(ordered) - 1, math.floor(len(ordered) * train_fraction)))
    train = set(ordered[:train_count])
    holdout = set(ordered[train_count:])
    return train, holdout


def add_regime_columns(df: pd.DataFrame, train_dates: set[str]) -> pd.DataFrame:
    df = df.sort_values(["session_date", "second"]).copy()
    minute_utc = df["second"].dt.hour * 60 + df["second"].dt.minute
    df["time_regime"] = np.select(
        [
            minute_utc < 14 * 60 + 30,
            minute_utc >= 18 * 60 + 30,
        ],
        ["open", "close"],
        default="midday",
    )

    train_mask = df["session_date"].isin(train_dates)
    spread_cut = df.loc[train_mask, "spread"].median()
    df["spread_regime"] = np.where(df["spread"] <= spread_cut, "tight", "wide")

    grouped = df.groupby("session_date")
    df["mid_ret_1s"] = grouped["mid"].diff()
    df["realized_vol_60s"] = (
        grouped["mid_ret_1s"]
        .rolling(60, min_periods=10)
        .std()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )
    df["realized_vol_300s"] = (
        grouped["mid_ret_1s"]
        .rolling(300, min_periods=60)
        .std()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )
    df["realized_range_300s"] = (
        grouped["mid"]
        .rolling(300, min_periods=60)
        .apply(lambda values: float(np.max(values) - np.min(values)), raw=True)
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )
    df["realized_vol_ratio_60_300"] = np.divide(
        df["realized_vol_60s"],
        df["realized_vol_300s"],
        out=np.zeros(len(df), dtype=float),
        where=df["realized_vol_300s"].to_numpy(dtype=float) > 0,
    )
    df["realized_vol_slope_60s"] = (
        df["realized_vol_60s"] - df.groupby("session_date")["realized_vol_60s"].shift(60).fillna(0.0)
    )
    low_cut = df.loc[train_mask, "realized_vol_60s"].quantile(0.33)
    high_cut = df.loc[train_mask, "realized_vol_60s"].quantile(0.67)
    df["vol_regime"] = np.select(
        [
            df["realized_vol_60s"] <= low_cut,
            df["realized_vol_60s"] >= high_cut,
        ],
        ["low_vol", "high_vol"],
        default="mid_vol",
    )
    ratio_low = df.loc[train_mask, "realized_vol_ratio_60_300"].quantile(0.33)
    ratio_high = df.loc[train_mask, "realized_vol_ratio_60_300"].quantile(0.67)
    df["vol_shape_regime"] = np.select(
        [
            df["realized_vol_ratio_60_300"] <= ratio_low,
            df["realized_vol_ratio_60_300"] >= ratio_high,
        ],
        ["vol_contracting", "vol_expanding"],
        default="vol_neutral",
    )
    slope_low = df.loc[train_mask, "realized_vol_slope_60s"].quantile(0.33)
    slope_high = df.loc[train_mask, "realized_vol_slope_60s"].quantile(0.67)
    df["vol_slope_regime"] = np.select(
        [
            df["realized_vol_slope_60s"] <= slope_low,
            df["realized_vol_slope_60s"] >= slope_high,
        ],
        ["vol_falling", "vol_rising"],
        default="vol_flat",
    )

    if "trade_volume" in df:
        volume = df["trade_volume"].clip(lower=0).fillna(0.0)
    else:
        volume = df["events"].clip(lower=0).fillna(0.0)
    weighted_mid = df["mid"] * volume
    weighted_mid_sq = df["mid"].pow(2) * volume
    cum_volume = volume.groupby(df["session_date"]).cumsum()
    cum_weighted_mid = weighted_mid.groupby(df["session_date"]).cumsum()
    cum_weighted_mid_sq = weighted_mid_sq.groupby(df["session_date"]).cumsum()
    session_vwap = np.divide(
        cum_weighted_mid,
        cum_volume,
        out=np.full(len(df), np.nan, dtype=float),
        where=cum_volume.to_numpy(dtype=float) > 0,
    )
    df["session_vwap"] = pd.Series(session_vwap, index=df.index)
    df["session_vwap"] = df.groupby("session_date")["session_vwap"].ffill().fillna(df["mid"])
    session_vwap_mean_sq = np.divide(
        cum_weighted_mid_sq,
        cum_volume,
        out=np.full(len(df), np.nan, dtype=float),
        where=cum_volume.to_numpy(dtype=float) > 0,
    )
    vwap_variance = np.maximum(session_vwap_mean_sq - df["session_vwap"].pow(2), 0.0)
    df["session_vwap_std"] = pd.Series(np.sqrt(vwap_variance), index=df.index)
    df["session_vwap_std"] = df.groupby("session_date")["session_vwap_std"].ffill().fillna(0.0)
    df["vwap_dist_points"] = df["mid"] - df["session_vwap"]
    df["vwap_dist_sigma"] = np.divide(
        df["vwap_dist_points"],
        df["session_vwap_std"],
        out=np.zeros(len(df), dtype=float),
        where=df["session_vwap_std"].to_numpy(dtype=float) > 0,
    )
    prior_vwap = df.groupby("session_date")["session_vwap"].shift(60)
    df["vwap_slope_60s"] = df["session_vwap"] - prior_vwap.fillna(df["session_vwap"])
    df["vwap_band_regime"] = np.select(
        [
            df["vwap_dist_sigma"] <= -3.0,
            df["vwap_dist_sigma"] <= -2.0,
            df["vwap_dist_sigma"] <= -1.0,
            df["vwap_dist_sigma"] >= 3.0,
            df["vwap_dist_sigma"] >= 2.0,
            df["vwap_dist_sigma"] >= 1.0,
        ],
        ["below_3sd", "below_2sd", "below_1sd", "above_3sd", "above_2sd", "above_1sd"],
        default="inside_1sd",
    )
    vwap_slope_low = df.loc[train_mask, "vwap_slope_60s"].quantile(0.33)
    vwap_slope_high = df.loc[train_mask, "vwap_slope_60s"].quantile(0.67)
    df["vwap_slope_regime"] = np.select(
        [
            df["vwap_slope_60s"] <= vwap_slope_low,
            df["vwap_slope_60s"] >= vwap_slope_high,
        ],
        ["vwap_falling", "vwap_rising"],
        default="vwap_flat",
    )

    session_context = (
        df.groupby("session_date", sort=True)
        .agg(session_open_mid=("mid", "first"), session_close_mid=("mid", "last"))
        .sort_index()
    )
    session_context["rth_return_points"] = (
        session_context["session_close_mid"] - session_context["session_open_mid"]
    )
    session_context["prior_rth_return_points"] = session_context["rth_return_points"].shift(1)
    session_context["prior_rth_close"] = session_context["session_close_mid"].shift(1)
    session_context["overnight_gap_points"] = (
        session_context["session_open_mid"] - session_context["prior_rth_close"]
    )
    df["prior_rth_return_points"] = df["session_date"].map(session_context["prior_rth_return_points"])
    df["overnight_gap_points"] = df["session_date"].map(session_context["overnight_gap_points"])
    df["prior_rth_regime"] = np.select(
        [
            df["prior_rth_return_points"].isna(),
            df["prior_rth_return_points"] > 0,
            df["prior_rth_return_points"] < 0,
        ],
        ["prior_unknown", "prior_rth_up", "prior_rth_down"],
        default="prior_rth_flat",
    )
    df["overnight_gap_regime"] = np.select(
        [
            df["overnight_gap_points"].isna(),
            df["overnight_gap_points"] > 0,
            df["overnight_gap_points"] < 0,
        ],
        ["gap_unknown", "gap_up", "gap_down"],
        default="gap_flat",
    )
    df["combined_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["vol_regime"]
    df["combined_shape_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["vol_shape_regime"]
    df["combined_slope_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["vol_slope_regime"]
    df["combined_vwap_band_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["vwap_band_regime"]
    df["combined_vwap_slope_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["vwap_slope_regime"]
    df["combined_prior_rth_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["prior_rth_regime"]
    df["combined_gap_regime"] = df["time_regime"] + "|" + df["spread_regime"] + "|" + df["overnight_gap_regime"]
    return df


def side_stats(df: pd.DataFrame, feature: str, ret_col: str, side: str, threshold: float) -> dict[str, float | str]:
    if side == "long":
        sample = df[df[feature] >= threshold]
        aligned = sample[ret_col] > 0
    else:
        sample = df[df[feature] <= threshold]
        aligned = sample[ret_col] < 0

    if sample.empty:
        return {
            "side": side,
            "threshold": threshold,
            "events": 0,
            "coverage": 0.0,
            "mean_ret": float("nan"),
            "median_ret": float("nan"),
            "hit_rate": float("nan"),
            "mean_abs_ret": float("nan"),
        }

    return {
        "side": side,
        "threshold": threshold,
        "events": len(sample),
        "coverage": len(sample) / len(df),
        "mean_ret": sample[ret_col].mean(),
        "median_ret": sample[ret_col].median(),
        "hit_rate": aligned.mean(),
        "mean_abs_ret": sample[ret_col].abs().mean(),
    }


def score_feature(
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    split: str,
    feature: str,
    horizon: int,
    quantile: float,
) -> list[dict[str, object]]:
    ret_col = f"fwd_ret_{horizon}s"
    source = train_df[[feature, ret_col]].dropna()
    scored = df[[feature, ret_col, "session_date"]].dropna()
    if len(source) < 100 or len(scored) < 100:
        return []

    low = source[feature].quantile(quantile)
    high = source[feature].quantile(1 - quantile)
    rows = []
    for side, threshold in (("long", high), ("short", low)):
        stats = side_stats(scored, feature, ret_col, side, threshold)
        rows.append(
            {
                "split": split,
                "feature": feature,
                "horizon": f"{horizon}s",
                **stats,
            }
        )
    return rows


def time_bucket_rows(df: pd.DataFrame, features: list[str], horizons: list[int]) -> list[dict[str, object]]:
    rows = []
    df = df.copy()
    df["time_bucket_utc"] = df["second"].dt.floor("30min").dt.strftime("%H:%M")
    for bucket, bucket_df in df.groupby("time_bucket_utc", sort=True):
        row: dict[str, object] = {
            "time_bucket_utc": bucket,
            "events": len(bucket_df),
            "median_spread": bucket_df["spread"].median(),
        }
        for feature in features:
            if feature not in bucket_df:
                continue
            for horizon in horizons:
                ret_col = f"fwd_ret_{horizon}s"
                if ret_col not in bucket_df:
                    continue
                corr = bucket_df[[feature, ret_col]].corr(numeric_only=True).iloc[0, 1]
                row[f"{feature}__{horizon}s_corr"] = corr
        rows.append(row)
    return rows


def coefficient_rows(df: pd.DataFrame, features: list[str], horizons: list[int]) -> list[dict[str, object]]:
    rows = []
    for (split, session_date), session_df in df.groupby(["split", "session_date"], sort=True):
        for feature in features:
            if feature not in session_df:
                continue
            for horizon in horizons:
                ret_col = f"fwd_ret_{horizon}s"
                if ret_col not in session_df:
                    continue
                sample = session_df[[feature, ret_col]].dropna()
                if len(sample) < 100:
                    continue
                feature_var = sample[feature].var()
                beta = float("nan") if feature_var == 0 else sample[[feature, ret_col]].cov().iloc[0, 1] / feature_var
                rows.append(
                    {
                        "split": split,
                        "session_date": session_date,
                        "feature": feature,
                        "horizon": f"{horizon}s",
                        "events": len(sample),
                        "corr": sample[feature].corr(sample[ret_col]),
                        "beta_points_per_unit": beta,
                        "mean_feature": sample[feature].mean(),
                        "mean_ret": sample[ret_col].mean(),
                    }
                )
    return rows


def bootstrap_interval(values: np.ndarray, rng: np.random.Generator, samples: int) -> tuple[float, float, float]:
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    if len(values) == 1 or samples <= 0:
        value = float(values.mean())
        return value, value, value
    draws = rng.choice(values, size=(samples, len(values)), replace=True).mean(axis=1)
    return float(values.mean()), float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def bootstrap_rows(
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    features: list[str],
    horizons: list[int],
    quantile: float,
    samples: int,
    seed: int,
) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed)
    rows = []
    for split, split_df in (("train", df[df["split"] == "train"]), ("holdout", df[df["split"] == "holdout"])):
        for feature in features:
            for horizon in horizons:
                ret_col = f"fwd_ret_{horizon}s"
                source = train_df[[feature, ret_col]].dropna()
                scored = split_df[[feature, ret_col]].dropna()
                if len(source) < 100 or len(scored) < 100:
                    continue
                low = source[feature].quantile(quantile)
                high = source[feature].quantile(1 - quantile)
                for side, threshold in (("long", high), ("short", low)):
                    if side == "long":
                        sample = scored[scored[feature] >= threshold].copy()
                        directional_ret = sample[ret_col].to_numpy(dtype=float)
                    else:
                        sample = scored[scored[feature] <= threshold].copy()
                        directional_ret = -sample[ret_col].to_numpy(dtype=float)
                    if len(sample) < 50:
                        continue
                    hits = (directional_ret > 0).astype(float)
                    mean_ret, mean_low, mean_high = bootstrap_interval(directional_ret, rng, samples)
                    hit_rate, hit_low, hit_high = bootstrap_interval(hits, rng, samples)
                    rows.append(
                        {
                            "split": split,
                            "feature": feature,
                            "horizon": f"{horizon}s",
                            "side": side,
                            "threshold": threshold,
                            "events": len(sample),
                            "directional_mean_ret": mean_ret,
                            "directional_mean_ret_low": mean_low,
                            "directional_mean_ret_high": mean_high,
                            "hit_rate": hit_rate,
                            "hit_rate_low": hit_low,
                            "hit_rate_high": hit_high,
                        }
                    )
    return rows


def target_stop_outcomes(
    session_df: pd.DataFrame,
    event_indices: np.ndarray,
    side: str,
    horizon: int,
    target_points: float,
    stop_points: float,
) -> tuple[int, int, int]:
    mids = session_df["mid"].to_numpy(dtype=float)
    spreads = session_df["spread"].to_numpy(dtype=float)
    targets = stops = neither = 0
    max_idx = len(session_df) - 1

    for idx in event_indices:
        end = min(idx + horizon, max_idx)
        if idx >= end:
            continue
        future_mid = mids[idx + 1 : end + 1]
        future_spread = spreads[idx + 1 : end + 1]
        if side == "long":
            entry = mids[idx] + spreads[idx] / 2.0
            exit_bid = future_mid - future_spread / 2.0
            target_hits = np.flatnonzero(exit_bid >= entry + target_points)
            stop_hits = np.flatnonzero(exit_bid <= entry - stop_points)
        else:
            entry = mids[idx] - spreads[idx] / 2.0
            exit_ask = future_mid + future_spread / 2.0
            target_hits = np.flatnonzero(exit_ask <= entry - target_points)
            stop_hits = np.flatnonzero(exit_ask >= entry + stop_points)

        first_target = target_hits[0] if len(target_hits) else None
        first_stop = stop_hits[0] if len(stop_hits) else None
        if first_target is not None and (first_stop is None or first_target <= first_stop):
            targets += 1
        elif first_stop is not None:
            stops += 1
        else:
            neither += 1
    return targets, stops, neither


def target_stop_rows(
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    features: list[str],
    horizons: list[int],
    quantile: float,
    target_points: float,
    stop_points: float,
) -> list[dict[str, object]]:
    rows = []
    for split, split_df in (("train", df[df["split"] == "train"]), ("holdout", df[df["split"] == "holdout"])):
        for feature in features:
            source = train_df[[feature]].dropna()
            if len(source) < 100:
                continue
            low = source[feature].quantile(quantile)
            high = source[feature].quantile(1 - quantile)
            for horizon in horizons:
                for side, threshold in (("long", high), ("short", low)):
                    target_count = stop_count = neither_count = 0
                    for _, session_df in split_df.groupby("session_date", sort=True):
                        session_df = session_df.sort_values("second").reset_index(drop=True)
                        if side == "long":
                            event_indices = np.flatnonzero(session_df[feature].to_numpy(dtype=float) >= threshold)
                        else:
                            event_indices = np.flatnonzero(session_df[feature].to_numpy(dtype=float) <= threshold)
                        targets, stops, neither = target_stop_outcomes(
                            session_df,
                            event_indices,
                            side,
                            horizon,
                            target_points,
                            stop_points,
                        )
                        target_count += targets
                        stop_count += stops
                        neither_count += neither
                    total = target_count + stop_count + neither_count
                    if total == 0:
                        continue
                    rows.append(
                        {
                            "split": split,
                            "feature": feature,
                            "horizon": f"{horizon}s",
                            "side": side,
                            "threshold": threshold,
                            "events": total,
                            "target_before_stop": target_count,
                            "stop_before_target": stop_count,
                            "neither": neither_count,
                            "target_rate": target_count / total,
                            "stop_rate": stop_count / total,
                            "neither_rate": neither_count / total,
                            "target_points": target_points,
                            "stop_points": stop_points,
                        }
                    )
    return rows


def regime_target_stop_rows(
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    features: list[str],
    horizons: list[int],
    quantile: float,
    target_points: float,
    stop_points: float,
    min_events: int,
) -> list[dict[str, object]]:
    rows = []
    for regime_col in REGIME_COLUMNS:
        for regime_value in sorted(df[regime_col].dropna().unique()):
            train_regime_df = train_df[train_df[regime_col] == regime_value]
            if len(train_regime_df) < min_events:
                continue
            for feature in features:
                source = train_regime_df[[feature]].dropna()
                if len(source) < min_events:
                    continue
                low = source[feature].quantile(quantile)
                high = source[feature].quantile(1 - quantile)
                for horizon in horizons:
                    for side, threshold in (("long", high), ("short", low)):
                        for split in ("train", "holdout"):
                            split_regime_df = df[(df["split"] == split) & (df[regime_col] == regime_value)]
                            if len(split_regime_df) < min_events:
                                continue
                            target_count = stop_count = neither_count = 0
                            for _, session_df in split_regime_df.groupby("session_date", sort=True):
                                session_df = session_df.sort_values("second").reset_index(drop=True)
                                values = session_df[feature].to_numpy(dtype=float)
                                if side == "long":
                                    event_indices = np.flatnonzero(values >= threshold)
                                else:
                                    event_indices = np.flatnonzero(values <= threshold)
                                targets, stops, neither = target_stop_outcomes(
                                    session_df,
                                    event_indices,
                                    side,
                                    horizon,
                                    target_points,
                                    stop_points,
                                )
                                target_count += targets
                                stop_count += stops
                                neither_count += neither
                            total = target_count + stop_count + neither_count
                            if total < min_events:
                                continue
                            rows.append(
                                {
                                    "split": split,
                                    "regime_column": regime_col,
                                    "regime": regime_value,
                                    "feature": feature,
                                    "horizon": f"{horizon}s",
                                    "side": side,
                                    "threshold": threshold,
                                    "events": total,
                                    "target_before_stop": target_count,
                                    "stop_before_target": stop_count,
                                    "neither": neither_count,
                                    "target_rate": target_count / total,
                                    "stop_rate": stop_count / total,
                                    "neither_rate": neither_count / total,
                                }
                            )
    return rows


def regime_session_target_stop_rows(
    df: pd.DataFrame,
    train_df: pd.DataFrame,
    features: list[str],
    horizons: list[int],
    quantile: float,
    target_points: float,
    stop_points: float,
    min_events: int,
) -> list[dict[str, object]]:
    rows = []
    for regime_col in REGIME_COLUMNS:
        for regime_value in sorted(df[regime_col].dropna().unique()):
            train_regime_df = train_df[train_df[regime_col] == regime_value]
            if len(train_regime_df) < min_events:
                continue
            for feature in features:
                source = train_regime_df[[feature]].dropna()
                if len(source) < min_events:
                    continue
                low = source[feature].quantile(quantile)
                high = source[feature].quantile(1 - quantile)
                for horizon in horizons:
                    for side, threshold in (("long", high), ("short", low)):
                        for (split, session_date), session_df in df[
                            df[regime_col] == regime_value
                        ].groupby(["split", "session_date"], sort=True):
                            session_df = session_df.sort_values("second").reset_index(drop=True)
                            values = session_df[feature].to_numpy(dtype=float)
                            if side == "long":
                                event_indices = np.flatnonzero(values >= threshold)
                            else:
                                event_indices = np.flatnonzero(values <= threshold)
                            targets, stops, neither = target_stop_outcomes(
                                session_df,
                                event_indices,
                                side,
                                horizon,
                                target_points,
                                stop_points,
                            )
                            total = targets + stops + neither
                            if total == 0:
                                continue
                            rows.append(
                                {
                                    "split": split,
                                    "session_date": session_date,
                                    "regime_column": regime_col,
                                    "regime": regime_value,
                                    "feature": feature,
                                    "horizon": f"{horizon}s",
                                    "side": side,
                                    "threshold": threshold,
                                    "events": total,
                                    "target_before_stop": targets,
                                    "stop_before_target": stops,
                                    "neither": neither,
                                    "target_rate": targets / total,
                                    "stop_rate": stops / total,
                                    "neither_rate": neither / total,
                                }
                            )
    return rows


def write_markdown(
    quantile_df: pd.DataFrame,
    bootstrap_df: pd.DataFrame,
    target_stop_df: pd.DataFrame,
    coefficient_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    regime_session_df: pd.DataFrame,
    output_md: Path,
    skipped: list[str],
    train_dates: set[str],
    holdout_dates: set[str],
    max_spread: float,
    target_points: float,
    stop_points: float,
) -> None:
    def markdown_table(df: pd.DataFrame) -> list[str]:
        if df.empty:
            return ["No rows scored."]
        display = df.copy()
        for col in (
            "threshold",
            "coverage",
            "mean_ret",
            "median_ret",
            "hit_rate",
            "mean_abs_ret",
            "directional_mean_ret",
            "directional_mean_ret_low",
            "directional_mean_ret_high",
            "hit_rate_low",
            "hit_rate_high",
            "target_rate",
            "stop_rate",
            "neither_rate",
            "corr",
            "beta_points_per_unit",
            "target_rate_train",
            "target_rate_holdout",
            "min_session_target_rate_train",
            "min_session_target_rate_holdout",
        ):
            if col in display:
                display[col] = display[col].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
        columns = list(display.columns)
        lines = [
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join(["---"] * len(columns)) + " |",
        ]
        for row in display.to_dict("records"):
            lines.append("| " + " | ".join(str(row[col]) for col in columns) + " |")
        return lines

    output_md.parent.mkdir(parents=True, exist_ok=True)
    top = quantile_df.sort_values(["split", "hit_rate"], ascending=[True, False]).copy()
    holdout = top[top["split"] == "holdout"].head(10)
    train = top[top["split"] == "train"].head(10)
    bootstrap_top = bootstrap_df[bootstrap_df["split"] == "holdout"].sort_values(
        "hit_rate", ascending=False
    ).head(10)
    target_top = target_stop_df[target_stop_df["split"] == "holdout"].sort_values(
        "target_rate", ascending=False
    ).head(10)
    coefficient_flips = (
        coefficient_df.pivot_table(index=["feature", "horizon"], columns="split", values="corr", aggfunc="mean")
        .dropna()
        .reset_index()
    )
    if not coefficient_flips.empty:
        coefficient_flips["sign_flip"] = (coefficient_flips["train"] * coefficient_flips["holdout"]) < 0
        coefficient_flips = coefficient_flips.sort_values("sign_flip", ascending=False).head(12)
    regime_compare = pd.DataFrame()
    if not regime_df.empty:
        regime_compare = (
            regime_df.pivot_table(
                index=["regime_column", "regime", "feature", "horizon", "side"],
                columns="split",
                values=["target_rate", "events"],
                aggfunc="first",
            )
            .dropna()
        )
        regime_compare.columns = [f"{metric}_{split}" for metric, split in regime_compare.columns]
        regime_compare = regime_compare.reset_index()
        if not regime_session_df.empty:
            session_summary = (
                regime_session_df.groupby(
                    ["regime_column", "regime", "feature", "horizon", "side", "split"],
                    sort=True,
                )
                .agg(
                    session_count=("session_date", "nunique"),
                    passing_sessions=("target_rate", lambda values: int((values > 0.50).sum())),
                    min_session_target_rate=("target_rate", "min"),
                )
                .reset_index()
                .pivot_table(
                    index=["regime_column", "regime", "feature", "horizon", "side"],
                    columns="split",
                    values=["session_count", "passing_sessions", "min_session_target_rate"],
                    aggfunc="first",
                )
                .dropna()
            )
            session_summary.columns = [f"{metric}_{split}" for metric, split in session_summary.columns]
            regime_compare = regime_compare.merge(
                session_summary.reset_index(),
                on=["regime_column", "regime", "feature", "horizon", "side"],
                how="left",
            )
        regime_compare["passes_gate"] = (
            (regime_compare["target_rate_train"] > 0.50)
            & (regime_compare["target_rate_holdout"] > 0.50)
            & (regime_compare["events_train"] >= 100)
            & (regime_compare["events_holdout"] >= 100)
            & (regime_compare["session_count_train"] >= 2)
            & (regime_compare["session_count_holdout"] >= 2)
            & (regime_compare["min_session_target_rate_train"] > 0.50)
            & (regime_compare["min_session_target_rate_holdout"] > 0.50)
        )
        regime_compare = regime_compare.sort_values(
            ["passes_gate", "target_rate_holdout", "events_holdout"],
            ascending=[False, False, False],
        ).head(15)

    lines = [
        "# Databento L2 Event Study",
        "",
        f"- train_dates: `{', '.join(sorted(train_dates))}`",
        f"- holdout_dates: `{', '.join(sorted(holdout_dates))}`",
        f"- spread_filter: `spread <= {max_spread}`",
        f"- target_stop_label: `target={target_points}` / `stop={stop_points}` points, bid/ask approximated from spread",
        f"- skipped_duplicate_files: `{len(skipped)}`",
        "",
        "## Top Holdout Extreme-Side Results",
        "",
    ]
    lines.extend(markdown_table(holdout))

    lines.extend(["", "## Top Train Extreme-Side Results", ""])
    lines.extend(markdown_table(train))

    lines.extend(["", "## Holdout Bootstrap Intervals", ""])
    lines.extend(markdown_table(bootstrap_top))

    lines.extend(["", "## Holdout Target-Before-Stop Labels", ""])
    lines.extend(markdown_table(target_top))

    lines.extend(["", "## Mean Session-Coefficient Sign Checks", ""])
    lines.extend(markdown_table(coefficient_flips))

    lines.extend(["", "## Regime-Filtered Target-Before-Stop", ""])
    lines.extend(markdown_table(regime_compare))

    if skipped:
        lines.extend(["", "## Skipped Duplicate Date Files", ""])
        lines.extend(f"- `{path}`" for path in skipped)

    output_md.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Event study over derived MBP-10 1-second feature CSVs.")
    parser.add_argument("input", help="Directory containing derived *_1s.csv files.")
    parser.add_argument("--output-dir", default="Analysis/output/l2_event_study")
    parser.add_argument("--max-spread", type=float, default=0.5)
    parser.add_argument("--quantile", type=float, default=0.10)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--target-points", type=float, default=2.0)
    parser.add_argument("--stop-points", type=float, default=2.0)
    parser.add_argument("--bootstrap-samples", type=int, default=500)
    parser.add_argument("--min-regime-events", type=int, default=100)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-dedupe-dates", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    df, skipped = load_sessions(Path(args.input), dedupe_dates=not args.no_dedupe_dates)
    df = df[(df["events"] > 0) & (df["spread"] <= args.max_spread)].copy()

    available_features = [feature for feature in DEFAULT_FEATURES if feature in df.columns]
    horizons = [horizon for horizon in DEFAULT_HORIZONS if f"fwd_ret_{horizon}s" in df.columns]
    train_dates, holdout_dates = split_dates(sorted(df["session_date"].unique()), args.train_fraction)
    df = add_regime_columns(df, train_dates)
    df["split"] = np.where(df["session_date"].isin(train_dates), "train", "holdout")
    train_df = df[df["session_date"].isin(train_dates)].copy()
    holdout_df = df[df["session_date"].isin(holdout_dates)].copy()

    rows = []
    for split, split_df in (("train", train_df), ("holdout", holdout_df)):
        for feature in available_features:
            for horizon in horizons:
                rows.extend(score_feature(split_df, train_df, split, feature, horizon, args.quantile))

    quantile_df = pd.DataFrame(rows)
    time_df = pd.DataFrame(time_bucket_rows(df, available_features, horizons))
    coefficient_df = pd.DataFrame(coefficient_rows(df, available_features, horizons))
    bootstrap_df = pd.DataFrame(
        bootstrap_rows(
            df,
            train_df,
            available_features,
            horizons,
            args.quantile,
            args.bootstrap_samples,
            args.seed,
        )
    )
    target_stop_df = pd.DataFrame(
        target_stop_rows(
            df,
            train_df,
            available_features,
            horizons,
            args.quantile,
            args.target_points,
            args.stop_points,
        )
    )
    regime_features = [feature for feature in REGIME_FEATURES if feature in df.columns]
    regime_df = pd.DataFrame(
        regime_target_stop_rows(
            df,
            train_df,
            regime_features,
            horizons,
            args.quantile,
            args.target_points,
            args.stop_points,
            args.min_regime_events,
        )
    )
    regime_session_df = pd.DataFrame(
        regime_session_target_stop_rows(
            df,
            train_df,
            regime_features,
            horizons,
            args.quantile,
            args.target_points,
            args.stop_points,
            args.min_regime_events,
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    quantile_csv = output_dir / "quantile_events.csv"
    time_csv = output_dir / "time_buckets.csv"
    coefficient_csv = output_dir / "session_coefficients.csv"
    bootstrap_csv = output_dir / "bootstrap_intervals.csv"
    target_stop_csv = output_dir / "target_stop_events.csv"
    regime_csv = output_dir / "regime_target_stop_events.csv"
    regime_session_csv = output_dir / "regime_session_target_stop_events.csv"
    summary_md = output_dir / "summary.md"
    quantile_df.to_csv(quantile_csv, index=False)
    time_df.to_csv(time_csv, index=False)
    coefficient_df.to_csv(coefficient_csv, index=False)
    bootstrap_df.to_csv(bootstrap_csv, index=False)
    target_stop_df.to_csv(target_stop_csv, index=False)
    regime_df.to_csv(regime_csv, index=False)
    regime_session_df.to_csv(regime_session_csv, index=False)
    write_markdown(
        quantile_df,
        bootstrap_df,
        target_stop_df,
        coefficient_df,
        regime_df,
        regime_session_df,
        summary_md,
        skipped,
        train_dates,
        holdout_dates,
        args.max_spread,
        args.target_points,
        args.stop_points,
    )

    print(f"sessions={df['session_date'].nunique()}")
    print(f"rows_after_filter={len(df)}")
    print(f"train_dates={','.join(sorted(train_dates))}")
    print(f"holdout_dates={','.join(sorted(holdout_dates))}")
    print(f"features={','.join(available_features)}")
    print(f"quantile_csv={quantile_csv}")
    print(f"time_csv={time_csv}")
    print(f"coefficient_csv={coefficient_csv}")
    print(f"bootstrap_csv={bootstrap_csv}")
    print(f"target_stop_csv={target_stop_csv}")
    print(f"regime_csv={regime_csv}")
    print(f"regime_session_csv={regime_session_csv}")
    print(f"summary_md={summary_md}")


if __name__ == "__main__":
    main()
