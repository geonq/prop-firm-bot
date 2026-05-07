"""Persist TV strategy exports + MC results as dashboard-ready artifacts.

Walks ``TVExports/*.xlsx``, parses each into a canonical trade ledger, computes
in-sample stats, runs MC across TopStep 50K and LucidFlex 50K, and writes
artifacts the dashboard reads. The dashboard never re-runs MC; it renders what
this module produced.

Output layout::

    Analysis/output/tv_strategies/
        registry.parquet                           # one row per strategy
        {strategy_id}/
            meta.json                              # name, dates, stats, screening
            trades.parquet                         # canonical ledger

    Analysis/output/mc_runs/
        index.parquet                              # one row per (strategy, firm)
        {strategy_id}/
            {firm}/
                summary.json                       # MonteCarloResult dump
                config.json                        # N, seed, sizing, costs
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.tv_trade_audit import TvTradeRecord, load_tv_trade_records_xlsx
from src.data.tv_trade_loader import load_tv_strategy_replay_days_xlsx
from src.pipeline.monte_carlo import ConfidenceInterval, MonteCarloResult
from src.pipeline.sequential_mc import (
    SequentialMCResult,
    StoppingConfig,
    sequential_replay_mc,
)
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing
from src.strategies.replay import ReplayDay


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TV_EXPORTS_DIR = PROJECT_ROOT / "TVExports"
STRATEGIES_DIR = PROJECT_ROOT / "Analysis" / "output" / "tv_strategies"
MC_RUNS_DIR = PROJECT_ROOT / "Analysis" / "output" / "mc_runs"

DEFAULT_RISK_AMOUNT = 200.0
DEFAULT_BLOCK_SIZE = 5
DEFAULT_N_INIT = 2_000
DEFAULT_N_STEP = 2_000
DEFAULT_N_MAX = 50_000
DEFAULT_SEED = 0
DEFAULT_COST_PER_TRADE = 0.0  # TV trade-list P&L is already net; avoid double-counting costs.
DEFAULT_P_PASS_THRESHOLD = 0.20
DEFAULT_EV_THRESHOLD_USD = 0.0


_OOS_FILENAME_RE = re.compile(r"_(IS|OOS)[_.]", re.IGNORECASE)


@dataclass(frozen=True)
class StrategyStats:
    n_trades: int
    n_replay_days: int
    n_trading_days: int
    date_start: date
    date_end: date
    gross_pnl: float
    net_pnl: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    sharpe_daily: float
    sortino_daily: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    max_single_day_pnl: float
    max_single_day_share_of_profit: float


@dataclass(frozen=True)
class ScreeningResult:
    status: str  # PASS | FAIL | OOS_PENDING
    reasons: tuple[str, ...]
    rubric: dict[str, Any]


@dataclass(frozen=True)
class StrategyMeta:
    strategy_id: str
    display_name: str
    source_file: str
    oos_role: str  # full_sample | is | oos
    pair_key: str | None  # links IS+OOS exports
    stats: StrategyStats
    screening: ScreeningResult
    ingested_at: str


# ----- ingest -----------------------------------------------------------------


def _hash_records(records: list[TvTradeRecord]) -> str:
    h = hashlib.sha256()
    for r in records:
        h.update(
            f"{r.trade_number}|{r.entry_time.isoformat()}|{r.exit_time.isoformat()}|"
            f"{r.net_profit:.4f}\n".encode()
        )
    return h.hexdigest()[:12]


def _parse_oos_role(filename: str) -> tuple[str, str | None]:
    """Return (oos_role, pair_key). Pair key is the filename minus IS/OOS marker."""
    m = _OOS_FILENAME_RE.search(filename)
    if not m:
        return "full_sample", None
    marker = m.group(1).lower()
    pair_key = _OOS_FILENAME_RE.sub("_", filename, count=1)
    return marker, pair_key


def _display_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"_\d{4}-\d{2}-\d{2}.*$", "", stem)
    return stem.replace("_", " ").strip()


def compute_strategy_stats(
    records: list[TvTradeRecord],
    replay_days: list[ReplayDay],
    *,
    cost_per_trade: float = DEFAULT_COST_PER_TRADE,
) -> StrategyStats:
    tv_net_pnls = [r.net_profit for r in records]
    pnls = [pnl - cost_per_trade for pnl in tv_net_pnls]
    if not pnls:
        raise ValueError("strategy has no trades")

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_pnl = sum(tv_net_pnls)
    net_pnl = sum(pnls)

    profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = statistics.fmean(losses) if losses else 0.0
    expectancy = statistics.fmean(pnls)
    win_rate = len(wins) / len(pnls)

    # Daily Sharpe / Sortino on session-day P&L.
    by_day: dict[date, float] = {}
    for r, pnl in zip(records, pnls, strict=True):
        d = r.exit_time.date()
        by_day[d] = by_day.get(d, 0.0) + pnl
    daily = list(by_day.values())
    if len(daily) > 1:
        mu = statistics.fmean(daily)
        sigma = statistics.pstdev(daily)
        downside = [min(0.0, x - 0.0) for x in daily]
        downside_sigma = math.sqrt(statistics.fmean([d * d for d in downside]))
        sharpe_daily = (mu / sigma) * math.sqrt(252) if sigma else 0.0
        sortino_daily = (mu / downside_sigma) * math.sqrt(252) if downside_sigma else 0.0
    else:
        sharpe_daily = sortino_daily = 0.0

    # Max drawdown in USD from running equity (peak-to-trough on cumulative P&L,
    # anchored at 0). Pct is reported against $50k starting capital — strategies
    # with negative cumulative P&L don't have a peak above zero, so pct-of-peak
    # is undefined.
    cum = 0.0
    peak = 0.0
    max_dd_usd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = peak - cum
        if dd > max_dd_usd:
            max_dd_usd = dd
    max_dd_pct = max_dd_usd / 50_000.0  # vs $50k starting capital

    max_day = max(daily) if daily else 0.0
    # Single-day concentration is only defined when net P&L is positive — for
    # losing strategies the consistency-rule check is moot.
    if net_pnl > 0:
        max_day_share = max_day / net_pnl
    else:
        max_day_share = float("nan")

    dates = [r.exit_time.date() for r in records]
    n_trading_days = len(by_day)
    n_replay_days = len(replay_days) or n_trading_days

    return StrategyStats(
        n_trades=len(records),
        n_replay_days=n_replay_days,
        n_trading_days=n_trading_days,
        date_start=min(dates),
        date_end=max(dates),
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        sharpe_daily=sharpe_daily,
        sortino_daily=sortino_daily,
        max_drawdown_usd=max_dd_usd,
        max_drawdown_pct=max_dd_pct,
        max_single_day_pnl=max_day,
        max_single_day_share_of_profit=max_day_share,
    )


# ----- screening --------------------------------------------------------------


# Prop-firm-EV rubric (asymmetric upside; failed accounts acceptable).
RUBRIC = {
    "min_trades": 200,
    "min_sortino_daily": 0.8,
    "max_single_day_share": 0.40,  # TopStep XFA + LucidFlex 50% strict; we want margin.
    "min_profit_factor": 1.30,
    # MC-derived (applied after MC runs):
    "min_eval_pass_rate": 0.20,
    "min_mean_net_ev_usd": 500.0,
}


def screen_strategy(stats: StrategyStats, oos_role: str) -> ScreeningResult:
    """Pre-MC screening (filters that don't need simulation)."""
    reasons: list[str] = []

    if stats.n_trades < RUBRIC["min_trades"]:
        reasons.append(
            f"trades={stats.n_trades} < {RUBRIC['min_trades']} (insufficient power)"
        )
    if stats.sortino_daily < RUBRIC["min_sortino_daily"]:
        reasons.append(
            f"sortino_daily={stats.sortino_daily:.2f} < {RUBRIC['min_sortino_daily']}"
        )
    share = stats.max_single_day_share_of_profit
    if not math.isnan(share) and share > RUBRIC["max_single_day_share"]:
        reasons.append(
            f"max_day_share={share:.2f} > "
            f"{RUBRIC['max_single_day_share']} (consistency-rule risk)"
        )
    if stats.net_pnl <= 0:
        reasons.append(f"net_pnl=${stats.net_pnl:.0f} (no edge)")
    if stats.profit_factor < RUBRIC["min_profit_factor"]:
        reasons.append(
            f"profit_factor={stats.profit_factor:.2f} < {RUBRIC['min_profit_factor']}"
        )

    if reasons:
        return ScreeningResult(status="FAIL", reasons=tuple(reasons), rubric=dict(RUBRIC))

    if oos_role == "full_sample":
        return ScreeningResult(
            status="OOS_PENDING",
            reasons=("no held-out OOS export — re-export per protocol",),
            rubric=dict(RUBRIC),
        )

    return ScreeningResult(status="PASS", reasons=(), rubric=dict(RUBRIC))


# ----- artifact writers -------------------------------------------------------


def _records_to_dataframe(records: list[TvTradeRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_number": r.trade_number,
                "entry_time": r.entry_time,
                "exit_time": r.exit_time,
                "net_profit": r.net_profit,
                "hold_seconds": r.hold_seconds,
            }
            for r in records
        ]
    )


def _stats_to_jsonable(stats: StrategyStats) -> dict[str, Any]:
    d = asdict(stats)
    d["date_start"] = stats.date_start.isoformat()
    d["date_end"] = stats.date_end.isoformat()
    return d


def _ci_to_dict(ci: ConfidenceInterval) -> dict[str, float]:
    return {"low": ci.low, "high": ci.high}


def _mc_result_to_jsonable(result: MonteCarloResult) -> dict[str, Any]:
    return {
        "firm": result.firm,
        "n_simulations": result.n_simulations,
        "eval_pass_count": result.eval_pass_count,
        "funded_breach_count": result.funded_breach_count,
        "max_payout_count": result.max_payout_count,
        "eval_pass_rate": result.eval_pass_rate,
        "eval_pass_ci": _ci_to_dict(result.eval_pass_ci),
        "funded_breach_rate": result.funded_breach_rate,
        "funded_breach_ci": _ci_to_dict(result.funded_breach_ci),
        "funded_breach_after_pass_rate": result.funded_breach_after_pass_rate,
        "funded_breach_after_pass_ci": _ci_to_dict(result.funded_breach_after_pass_ci),
        "max_payout_rate": result.max_payout_rate,
        "max_payout_ci": _ci_to_dict(result.max_payout_ci),
        "mean_payouts": result.mean_payouts,
        "mean_trader_payouts": result.mean_trader_payouts,
        "mean_net_ev": result.mean_net_ev,
        "median_net_ev": result.median_net_ev,
        "ev_stddev": result.ev_stddev,
        "ev_stderr": result.ev_stderr,
        "ev_ci": _ci_to_dict(result.ev_ci),
    }


def write_strategy_artifacts(
    meta: StrategyMeta,
    records: list[TvTradeRecord],
) -> Path:
    out_dir = STRATEGIES_DIR / meta.strategy_id
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_payload = {
        "strategy_id": meta.strategy_id,
        "display_name": meta.display_name,
        "source_file": meta.source_file,
        "oos_role": meta.oos_role,
        "pair_key": meta.pair_key,
        "stats": _stats_to_jsonable(meta.stats),
        "screening": {
            "status": meta.screening.status,
            "reasons": list(meta.screening.reasons),
            "rubric": meta.screening.rubric,
        },
        "ingested_at": meta.ingested_at,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta_payload, indent=2))
    _records_to_dataframe(records).to_parquet(out_dir / "trades.parquet", index=False)
    return out_dir


def write_mc_artifacts(
    strategy_id: str,
    firm_label: str,
    result: MonteCarloResult | SequentialMCResult,
    config: dict[str, Any],
) -> Path:
    out_dir = MC_RUNS_DIR / strategy_id / firm_label
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = result.mc_result if isinstance(result, SequentialMCResult) else result
    (out_dir / "summary.json").write_text(json.dumps(_mc_result_to_jsonable(summary), indent=2))
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, default=str))
    return out_dir


def rebuild_registry_index() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if STRATEGIES_DIR.exists():
        for meta_path in sorted(STRATEGIES_DIR.glob("*/meta.json")):
            data = json.loads(meta_path.read_text())
            stats = data["stats"]
            rows.append(
                {
                    "strategy_id": data["strategy_id"],
                    "display_name": data["display_name"],
                    "source_file": data["source_file"],
                    "oos_role": data["oos_role"],
                    "pair_key": data.get("pair_key"),
                    "n_trades": stats["n_trades"],
                    "date_start": stats["date_start"],
                    "date_end": stats["date_end"],
                    "net_pnl": stats["net_pnl"],
                    "sharpe_daily": stats["sharpe_daily"],
                    "sortino_daily": stats["sortino_daily"],
                    "profit_factor": stats["profit_factor"],
                    "max_drawdown_usd": stats["max_drawdown_usd"],
                    "max_single_day_share": stats["max_single_day_share_of_profit"],
                    "screening_status": data["screening"]["status"],
                    "screening_reasons": "; ".join(data["screening"]["reasons"]),
                    "ingested_at": data["ingested_at"],
                }
            )
    df = pd.DataFrame(rows)
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(STRATEGIES_DIR / "registry.parquet", index=False)
    return df


def rebuild_mc_index() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if MC_RUNS_DIR.exists():
        for summary_path in sorted(MC_RUNS_DIR.glob("*/*/summary.json")):
            firm_label = summary_path.parent.name
            strategy_id = summary_path.parent.parent.name
            data = json.loads(summary_path.read_text())
            cfg_path = summary_path.parent / "config.json"
            cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "firm": firm_label,
                    "n_simulations": data["n_simulations"],
                    "block_size": cfg.get("block_size"),
                    "stopped_reason": cfg.get("stopped_reason"),
                    "iterations": cfg.get("iterations"),
                    "eval_pass_rate": data["eval_pass_rate"],
                    "eval_pass_ci_lo": data["eval_pass_ci"]["low"],
                    "eval_pass_ci_hi": data["eval_pass_ci"]["high"],
                    "funded_breach_rate": data["funded_breach_rate"],
                    "funded_breach_after_pass_rate": data["funded_breach_after_pass_rate"],
                    "max_payout_rate": data["max_payout_rate"],
                    "mean_payouts": data["mean_payouts"],
                    "mean_trader_payouts": data["mean_trader_payouts"],
                    "mean_net_ev": data["mean_net_ev"],
                    "median_net_ev": data["median_net_ev"],
                    "ev_ci_lo": data["ev_ci"]["low"],
                    "ev_ci_hi": data["ev_ci"]["high"],
                    "completed_at": cfg.get("completed_at"),
                }
            )
    df = pd.DataFrame(rows)
    MC_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(MC_RUNS_DIR / "index.parquet", index=False)
    return df


# ----- orchestration ----------------------------------------------------------


def ingest_xlsx(
    xlsx_path: Path,
    *,
    cost_per_trade: float = DEFAULT_COST_PER_TRADE,
) -> tuple[StrategyMeta, list[TvTradeRecord], list[ReplayDay]]:
    """Parse one xlsx, compute stats + screening, return meta + ledger + replay."""
    records = load_tv_trade_records_xlsx(xlsx_path)
    if not records:
        raise ValueError(f"no trades in {xlsx_path.name}")
    replay_days = load_tv_strategy_replay_days_xlsx(
        xlsx_path,
        risk_amount=DEFAULT_RISK_AMOUNT,
        include_no_trade_weekdays=True,
    )

    strategy_id = _hash_records(records)
    oos_role, pair_key = _parse_oos_role(xlsx_path.name)
    stats = compute_strategy_stats(records, replay_days, cost_per_trade=cost_per_trade)
    screening = screen_strategy(stats, oos_role)

    meta = StrategyMeta(
        strategy_id=strategy_id,
        display_name=_display_name(xlsx_path.name),
        source_file=str(xlsx_path.relative_to(PROJECT_ROOT)),
        oos_role=oos_role,
        pair_key=pair_key,
        stats=stats,
        screening=screening,
        ingested_at=datetime.now(timezone.utc).isoformat(),
    )
    return meta, records, replay_days


def run_mc_for_strategy(
    replay_days: list[ReplayDay],
    *,
    n_init: int = DEFAULT_N_INIT,
    n_step: int = DEFAULT_N_STEP,
    n_max: int = DEFAULT_N_MAX,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seed: int = DEFAULT_SEED,
    risk_amount: float = DEFAULT_RISK_AMOUNT,
    cost_per_trade: float = DEFAULT_COST_PER_TRADE,
    p_pass_threshold: float = DEFAULT_P_PASS_THRESHOLD,
    ev_threshold_usd: float = DEFAULT_EV_THRESHOLD_USD,
) -> dict[str, tuple[SequentialMCResult, dict[str, Any]]]:
    """Run sequential MC at TopStep 50K + LucidFlex 50K. Returns {firm_label: (result, config)}."""
    out: dict[str, tuple[SequentialMCResult, dict[str, Any]]] = {}

    sizing_fn = FixedSizing(eval_size=risk_amount, funded_size=risk_amount)
    stopping = StoppingConfig(
        p_pass_threshold=p_pass_threshold, ev_threshold_usd=ev_threshold_usd
    )
    base_cfg: dict[str, Any] = {
        "n_init": n_init,
        "n_step": n_step,
        "n_max": n_max,
        "block_size": block_size,
        "seed": seed,
        "risk_amount": risk_amount,
        "cost_per_trade": cost_per_trade,
        "sizing": "tv_net_replay_fixed",
        "p_pass_threshold": p_pass_threshold,
        "ev_threshold_usd": ev_threshold_usd,
        "completed_at": None,
    }

    # TopStep 50K
    ts_seq = sequential_replay_mc(
        replay_days,
        firm="topstep",
        n_init=n_init,
        n_step=n_step,
        n_max=n_max,
        block_size=block_size,
        seed=seed,
        sizing_fn=sizing_fn,
        topstep_payout_path=TopStepPayoutPath.CONSISTENCY,
        topstep_use_daily_loss_limit=False,
        topstep_max_back2funded_reactivations=3,
        eval_cost_per_trade=cost_per_trade,
        funded_cost_per_trade=cost_per_trade,
        payout_cap=5,
        stopping=stopping,
    )
    ts_cfg = {
        **base_cfg,
        "ruleset": "TopStepNoFee50K",
        "payout_path": "consistency",
        "payout_cap": 5,
        "max_back2funded_reactivations": 3,
        "stopped_reason": ts_seq.stopped_reason,
        "iterations": ts_seq.iterations,
        "n_run": ts_seq.n_run,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    out["topstep_50k"] = (ts_seq, ts_cfg)

    # LucidFlex 50K
    lf_seq = sequential_replay_mc(
        replay_days,
        firm="lucidflex",
        n_init=n_init,
        n_step=n_step,
        n_max=n_max,
        block_size=block_size,
        seed=seed,
        lucidflex_eval_risk=risk_amount,
        lucidflex_funded_risk=risk_amount,
        eval_cost_per_trade=cost_per_trade,
        funded_cost_per_trade=cost_per_trade,
        stopping=stopping,
    )
    lf_cfg = {
        **base_cfg,
        "ruleset": "LucidFlex50K",
        "stopped_reason": lf_seq.stopped_reason,
        "iterations": lf_seq.iterations,
        "n_run": lf_seq.n_run,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    out["lucidflex_50k"] = (lf_seq, lf_cfg)

    return out


def build_registry(
    *,
    tv_dir: Path = TV_EXPORTS_DIR,
    n_init: int = DEFAULT_N_INIT,
    n_step: int = DEFAULT_N_STEP,
    n_max: int = DEFAULT_N_MAX,
    block_size: int = DEFAULT_BLOCK_SIZE,
    skip_mc: bool = False,
    only_screened_pass: bool = False,
) -> dict[str, Any]:
    """Walk TVExports, ingest each xlsx, run MC, persist artifacts. Returns summary."""
    xlsx_files = sorted(p for p in tv_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    summary: dict[str, Any] = {"strategies": [], "skipped": [], "mc_runs": []}

    for xlsx_path in xlsx_files:
        try:
            meta, records, replay_days = ingest_xlsx(xlsx_path)
        except Exception as exc:
            summary["skipped"].append({"file": xlsx_path.name, "error": str(exc)})
            continue

        write_strategy_artifacts(meta, records)
        summary["strategies"].append(
            {
                "strategy_id": meta.strategy_id,
                "display_name": meta.display_name,
                "screening_status": meta.screening.status,
                "n_trades": meta.stats.n_trades,
            }
        )

        if skip_mc:
            continue
        if only_screened_pass and meta.screening.status not in ("PASS", "OOS_PENDING"):
            continue

        try:
            mc_outputs = run_mc_for_strategy(
                replay_days,
                n_init=n_init,
                n_step=n_step,
                n_max=n_max,
                block_size=block_size,
            )
        except Exception as exc:
            summary["mc_runs"].append(
                {"strategy_id": meta.strategy_id, "firm": "*", "error": str(exc)}
            )
            continue

        for firm_label, (seq_result, cfg) in mc_outputs.items():
            write_mc_artifacts(meta.strategy_id, firm_label, seq_result, cfg)
            summary["mc_runs"].append(
                {
                    "strategy_id": meta.strategy_id,
                    "firm": firm_label,
                    "n_run": seq_result.n_run,
                    "stopped_reason": seq_result.stopped_reason,
                    "eval_pass_rate": seq_result.mc_result.eval_pass_rate,
                    "mean_net_ev": seq_result.mc_result.mean_net_ev,
                }
            )

    rebuild_registry_index()
    rebuild_mc_index()
    return summary
