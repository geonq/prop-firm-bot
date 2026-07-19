"""Run correlated frozen-ORB EV scenarios for currently encoded firms.

Usage (from repository root):
  .venv/bin/python Analysis/scripts/fleet_ev.py

Requires the private, gitignored Databento parquet at the default path. It
never re-runs selection or unlocks the spent holdout: it replays only the
already-frozen parameters against sampled dated outcomes. Output JSON is
written under ignored Analysis/output/.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import HOLDOUT_START, _fold_replay_days, params_hash
from src.pipeline.alt_firm_replay import simulate_mffu_rapid_50k, simulate_tradeify_lightning_50k
from src.pipeline.apex_replay import simulate_apex_trade_replay
from src.pipeline.lucidflex_replay import simulate_lucidflex_trade_replay
from src.pipeline.replay_monte_carlo import block_bootstrap_replay_days
from src.pipeline.topstep_replay import simulate_topstep_trade_replay

DATA = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
OUT = ROOT / "Analysis" / "output" / "fleet_ev_8afbe6259cab2dd2.json"
RISK = 400.0
N_SIMULATIONS = 10_000
BLOCK_SIZE = 5
TRADING_DAYS_PER_MONTH = 21
COUNTS = {"topstep": 5, "lucidflex": 5, "mffu_rapid": 5, "tradeify_lightning": 5}

FROZEN = ORBParams(or_minutes=5, entry_mode="first_candle", stop_mode="or_opposite", target_r=4.0,
                   vol_percentile_min=None, rel_volume_min=None, slippage_ticks=1.0,
                   vwap_trail_after_r=None, time_stop_minutes=120)


def _simulate(sampled):
    return {
        "topstep": simulate_topstep_trade_replay(sampled, eval_risk=RISK, funded_risk=RISK),
        "lucidflex": simulate_lucidflex_trade_replay(sampled, eval_risk=RISK, funded_risk=RISK),
        "mffu_rapid": simulate_mffu_rapid_50k(sampled, risk_per_trade=RISK),
        "tradeify_lightning": simulate_tradeify_lightning_50k(sampled, risk_per_trade=RISK),
    }


def _rolling_replacement_net(name: str, replay_days) -> tuple[float, int]:
    """Keep one account slot funded through the fixed horizon.

    A breach consumes its breach day. A fresh same-size account starts on the
    following available replay day; every new purchase/evaluation fee is
    already charged by the corresponding replay function. This models fresh
    replacement, not discounted resets or an undocumented account transfer.
    """
    offset = 0
    net = 0.0
    replacements = 0
    while offset < len(replay_days):
        remaining = replay_days[offset:]
        n = len(remaining)
        if name == "topstep":
            result = simulate_topstep_trade_replay(
                remaining, eval_risk=RISK, funded_risk=RISK,
                max_combine_days=n, max_xfa_days=n,
            )
            breached = (not result.combine_result.passed) or result.xfa_closed
        elif name == "lucidflex":
            result = simulate_lucidflex_trade_replay(
                remaining, eval_risk=RISK, funded_risk=RISK,
                max_eval_days=n, max_funded_days=n,
            )
            breached = (not result.eval_result.passed) or result.funded_breached
        elif name == "mffu_rapid":
            result = simulate_mffu_rapid_50k(remaining, risk_per_trade=RISK)
            breached = (not result.eval_passed) or result.funded_breached
        else:
            raise ValueError(f"replacement model unavailable for {name}")
        used = result.eval_days + result.funded_days
        if used <= 0:
            raise RuntimeError(f"{name} replay consumed no days")
        net += result.net_ev
        offset += used
        if not breached:
            break
        replacements += 1
    return net, replacements


def _quantile(values: list[float], p: float) -> float:
    return float(pd.Series(values).quantile(p, interpolation="linear"))


def main() -> None:
    if not DATA.exists():
        raise FileNotFoundError(f"Missing private market data: {DATA}")
    assert params_hash(FROZEN) == "8afbe6259cab2dd2", "frozen config drift"
    bars = pd.read_parquet(DATA)
    start = pd.Timestamp(HOLDOUT_START)
    _, replay_days = _fold_replay_days(bars, FROZEN, warmup_start=start - pd.DateOffset(months=3),
                                       window_start=start, window_end=bars.index.max().tz_convert("UTC"))
    if not replay_days:
        raise ValueError("No frozen replay days")

    rng = random.Random(0)
    firm_monthlies = {name: [] for name in COUNTS}
    firm_nets = {name: [] for name in COUNTS}
    firm_days = {name: [] for name in COUNTS}
    # Correlated by construction: one sampled sequence feeds every firm in
    # each iteration. This does not pretend five copies diversify the signal.
    compliant_fleet = []  # Topstep + Lucid + MFFU: same-bot cross-firm set.
    rolling_compliant_fleet = []
    rolling_replacements = []
    tradeify_only = []    # Tradeify contract forbids sharing this bot cross-firm.
    illustrative_all = []
    for _ in range(N_SIMULATIONS):
        sample = block_bootstrap_replay_days(replay_days, target_length=len(replay_days), block_size=BLOCK_SIZE, rng=rng)
        results = _simulate(sample)
        monthly = {}
        for name, result in results.items():
            # Scenario bands use a common fixed horizon. Dividing every path
            # by its own stopping time makes an immediate breach appear as an
            # impossibly large "monthly" loss and is not a fleet outcome.
            monthly[name] = result.net_ev / len(replay_days) * TRADING_DAYS_PER_MONTH
            firm_monthlies[name].append(monthly[name])
            firm_nets[name].append(result.net_ev)
            firm_days[name].append(max(result.eval_days + result.funded_days, 1))
        compliant = sum(monthly[n] * COUNTS[n] for n in ("topstep", "lucidflex", "mffu_rapid"))
        exclusive = monthly["tradeify_lightning"] * COUNTS["tradeify_lightning"]
        compliant_fleet.append(compliant)
        rolling_net = 0.0
        replacements = 0
        for name in ("topstep", "lucidflex", "mffu_rapid"):
            one_slot_net, one_slot_replacements = _rolling_replacement_net(name, sample)
            rolling_net += one_slot_net * COUNTS[name]
            replacements += one_slot_replacements * COUNTS[name]
        rolling_compliant_fleet.append(rolling_net / len(replay_days) * TRADING_DAYS_PER_MONTH)
        rolling_replacements.append(replacements)
        tradeify_only.append(exclusive)
        illustrative_all.append(compliant + exclusive)

    def band(values):
        return {"min_sampled_monthly": min(values), "p05_monthly": _quantile(values, .05), "median_monthly": _quantile(values, .50),
                "mean_monthly": float(pd.Series(values).mean()), "p95_monthly": _quantile(values, .95),
                "max_sampled_monthly": max(values)}

    per_account = {}
    for name, values in firm_monthlies.items():
        entry = band(values)
        entry["pipeline_throughput_mean_monthly"] = sum(firm_nets[name]) / sum(firm_days[name]) * TRADING_DAYS_PER_MONTH
        per_account[name] = entry

    record = {"params_hash": "8afbe6259cab2dd2", "risk_per_trade_usd": RISK,
              "n_simulations": N_SIMULATIONS, "block_size_trading_days": BLOCK_SIZE,
              "scenario_horizon_trading_days": len(replay_days), "account_counts": COUNTS, "firm_per_account": per_account,
              "fleet": {"compliance_feasible_same_bot": band(compliant_fleet),
                        "compliance_fleet_with_fresh_replacements": {
                            **band(rolling_compliant_fleet),
                            "mean_replacements_per_257d": float(pd.Series(rolling_replacements).mean()),
                        },
                        "tradeify_exclusive_five_account_scenario": band(tradeify_only),
                        "illustrative_all_20_accounts_NOT_COMPLIANT": band(illustrative_all)},
              "interpretation": "p05/p95 are fixed-horizon scenario percentiles, not literal worst/best. compliance_fleet_with_fresh_replacements buys a fresh same-size account on the session after every breach, charging the published purchase/eval fee each time; it does not assume reset discounts. Same sampled blocks drive all firms; there is no independence assumption. Tradeify prohibits using its bot across firms, so its five-account result cannot be added to the same ORB bot fleet."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
