"""Target-cell catalog (Phase 3.5).

Sweeps `(firm × payout_path × WR × R × trades_per_day)` and runs Monte Carlo
through the engine to produce a ranked CSV of net-EV-positive cells. The
output constrains downstream strategy research to a named distribution
profile (the only point of strategy work is to land in a cell this catalog
flagged as positive-EV under corrected economics).

Two sub-studies, written to the same CSV with a `study` column:

  - "sizing"     : i.i.d. Bernoulli × {Fixed, BufferAware, Adaptive}.
                   Adaptive sweeps the sizing grid per cell and reports the
                   best parameter combo.
  - "robustness" : {i.i.d., autocorrelated, regime-switching} × Fixed only.
                   Tests sensitivity of the same (WR, R, freq) cell to
                   non-i.i.d. trade sequences with sizing held constant.

Why split: `Fixed/BufferAware/Adaptive` are sizing functions consumed only by
`StateAwareBernoulliStrategy` (i.i.d. by construction). The autocorrelated
and regime-switching strategies hardcode loss sizes per phase, so they only
combine cleanly with Fixed. Lifting `sizing_fn` into them is a separate
refactor; the two-study split is honest about what the engine can express
today without claiming a 3 × 3 grid that doesn't exist.

Footnote on `regime-switching`: the existing strategy samples a regime per
trade, so it is mathematically a mixture distribution, not a regime with
persistence. The robustness study reads it as a WR-uncertainty stress, not a
regime-clustering stress.

Default mode (`smoke`): ~minutes. `--full` flag runs the production grid.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.monte_carlo import FirmName, MonteCarloResult, run_monte_carlo
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import AdaptiveSizing, BufferAwareSizing, FixedSizing
from src.strategies.parametric import (
    AutocorrelatedPhaseAwareBernoulliStrategy,
    RegimeSwitchingPhaseAwareBernoulliStrategy,
    StateAwareBernoulliStrategy,
    StrategyRegime,
)


DEFAULT_OUTPUT_DIR = REPO_ROOT / "Analysis" / "output" / "target_cell_catalog"

Study = Literal["sizing", "robustness"]
SizingName = Literal["Fixed", "BufferAware", "Adaptive"]
VariantName = Literal["iid", "autocorrelated", "regime_switching"]
PayoutPathName = Literal["lucidflex", "topstep_standard", "topstep_consistency"]


@dataclass(frozen=True)
class GridSpec:
    win_rates: tuple[float, ...]
    rr_ratios: tuple[float, ...]
    trades_per_day: tuple[int, ...]
    payout_paths: tuple[PayoutPathName, ...]
    n_sims: int
    eval_bases_search: tuple[float, ...]
    funded_bases_search: tuple[float, ...]
    buffer_full_fracs_search: tuple[float, ...]
    buffer_floors_search: tuple[float, ...]
    post_payout_shrinks_search: tuple[float, ...]
    autocorrelation: float = 0.3
    regime_wr_spread: float = 0.10  # +/- around the headline WR
    fixed_eval_base: float = 250.0
    fixed_funded_base: float = 250.0
    max_eval_days: int = 90
    max_funded_days: int = 180
    topstep_use_daily_loss_limit: bool = False
    topstep_max_back2funded_reactivations: int = 0
    # Simulation stop for TopStep only. LucidFlex already terminates after its
    # fifth simulated payout, so capping TopStep at 5 keeps cross-firm rankings
    # on the same finite funded runway by default.
    payout_cap: int | None = 5

    def cell_count(self) -> int:
        wr_r_freq = len(self.win_rates) * len(self.rr_ratios) * len(self.trades_per_day)
        firms = len(self.payout_paths)
        sizing_rows = 3  # Fixed, BufferAware, Adaptive (iid only)
        robustness_rows = 2  # autocorrelated, regime_switching (iid×Fixed already in sizing study)
        return wr_r_freq * firms * (sizing_rows + robustness_rows)

    def adaptive_search_size(self) -> int:
        return (
            len(self.eval_bases_search)
            * len(self.funded_bases_search)
            * len(self.buffer_full_fracs_search)
            * len(self.buffer_floors_search)
            * len(self.post_payout_shrinks_search)
        )


@dataclass(frozen=True)
class AdaptiveSearchWinner:
    eval_base: float
    funded_base: float
    buffer_full_frac: float
    buffer_floor: float
    post_payout_shrink: float
    result: MonteCarloResult


SMOKE_GRID = GridSpec(
    win_rates=(0.30, 0.40, 0.50, 0.60, 0.70, 0.80),
    rr_ratios=(0.20, 0.30, 0.50, 1.0, 2.0, 3.0),
    trades_per_day=(1, 5),
    payout_paths=("lucidflex", "topstep_standard", "topstep_consistency"),
    n_sims=200,
    eval_bases_search=(150.0, 300.0),
    funded_bases_search=(150.0, 300.0),
    buffer_full_fracs_search=(0.04,),
    buffer_floors_search=(0.25,),
    post_payout_shrinks_search=(1.0,),
)


FULL_GRID = GridSpec(
    win_rates=(0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80),
    rr_ratios=(0.20, 0.30, 0.50, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0),
    trades_per_day=(1, 3, 5, 10),
    payout_paths=("lucidflex", "topstep_standard", "topstep_consistency"),
    n_sims=1000,
    eval_bases_search=(150.0, 250.0, 400.0),
    funded_bases_search=(150.0, 250.0, 400.0),
    buffer_full_fracs_search=(0.04,),
    buffer_floors_search=(0.25,),
    post_payout_shrinks_search=(0.7, 1.0),
)


CSV_COLUMNS = [
    "study",
    "firm",
    "payout_path",
    "sizing",
    "strategy_variant",
    "topstep_use_daily_loss_limit",
    "topstep_max_back2funded_reactivations",
    "payout_cap",
    "win_rate",
    "rr_ratio",
    "trades_per_day",
    "n_sims",
    "mean_ev",
    "ev_low",
    "ev_high",
    "ev_stderr",
    "p_pass",
    "p_pass_low",
    "p_pass_high",
    "p_breach_after_pass",
    "p_breach_after_pass_low",
    "p_breach_after_pass_high",
    "p_max_payout",
    "p_max_payout_low",
    "p_max_payout_high",
    "mean_payouts",
    "mean_trader_payouts",
    "adaptive_eval_base",
    "adaptive_funded_base",
    "adaptive_buffer_full_frac",
    "adaptive_buffer_floor",
    "adaptive_post_payout_shrink",
]


def _firm_and_path(name: PayoutPathName) -> tuple[FirmName, TopStepPayoutPath | None]:
    if name == "lucidflex":
        return "lucidflex", None
    if name == "topstep_standard":
        return "topstep", TopStepPayoutPath.STANDARD
    if name == "topstep_consistency":
        return "topstep", TopStepPayoutPath.CONSISTENCY
    raise ValueError(f"unknown payout path: {name}")


def _cell_seed_base(
    seed: int, firm: FirmName, path: PayoutPathName, wr: float, rr: float, freq: int
) -> int:
    firm_offset = 100_000_000 if firm == "topstep" else 0
    path_offset = {"lucidflex": 0, "topstep_standard": 1, "topstep_consistency": 2}[path]
    return int(
        seed
        + firm_offset
        + path_offset * 10_000_000
        + wr * 10_000
        + rr * 1_000
        + freq * 17
    )


def _row_template(grid: GridSpec) -> dict[str, object]:
    row = {col: "" for col in CSV_COLUMNS}
    row["topstep_use_daily_loss_limit"] = grid.topstep_use_daily_loss_limit
    row["topstep_max_back2funded_reactivations"] = (
        grid.topstep_max_back2funded_reactivations
    )
    row["payout_cap"] = "" if grid.payout_cap is None else grid.payout_cap
    return row


def _fill_mc_columns(row: dict[str, object], result, n_sims: int) -> None:
    row["n_sims"] = n_sims
    row["mean_ev"] = result.mean_net_ev
    row["ev_low"] = result.ev_ci.low
    row["ev_high"] = result.ev_ci.high
    row["ev_stderr"] = result.ev_stderr
    row["p_pass"] = result.eval_pass_rate
    row["p_pass_low"] = result.eval_pass_ci.low
    row["p_pass_high"] = result.eval_pass_ci.high
    row["p_breach_after_pass"] = result.funded_breach_after_pass_rate
    row["p_breach_after_pass_low"] = result.funded_breach_after_pass_ci.low
    row["p_breach_after_pass_high"] = result.funded_breach_after_pass_ci.high
    row["p_max_payout"] = result.max_payout_rate
    row["p_max_payout_low"] = result.max_payout_ci.low
    row["p_max_payout_high"] = result.max_payout_ci.high
    row["mean_payouts"] = result.mean_payouts
    row["mean_trader_payouts"] = result.mean_trader_payouts


def _run_iid_state_aware(
    *,
    sizing_fn,
    wr: float,
    rr: float,
    freq: int,
    firm: FirmName,
    payout_path: TopStepPayoutPath | None,
    n_sims: int,
    seed_base: int,
    grid: GridSpec,
):
    strategy = StateAwareBernoulliStrategy(
        win_rate=wr,
        rr_ratio=rr,
        sizing_fn=sizing_fn,
        trades_per_day=freq,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )
    return run_monte_carlo(
        strategy,
        firm=firm,
        n_simulations=n_sims,
        seed=seed_base,
        max_eval_days=grid.max_eval_days,
        max_funded_days=grid.max_funded_days,
        topstep_payout_path=payout_path or TopStepPayoutPath.STANDARD,
        topstep_use_daily_loss_limit=grid.topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=grid.topstep_max_back2funded_reactivations,
        payout_cap=grid.payout_cap,
    )


def _run_autocorrelated(
    *,
    wr: float,
    rr: float,
    freq: int,
    eval_loss: float,
    funded_loss: float,
    autocorrelation: float,
    firm: FirmName,
    payout_path: TopStepPayoutPath | None,
    n_sims: int,
    seed_base: int,
    grid: GridSpec,
):
    strategy = AutocorrelatedPhaseAwareBernoulliStrategy(
        win_rate=wr,
        rr_ratio=rr,
        eval_loss_size=eval_loss,
        funded_loss_size=funded_loss,
        trades_per_day=freq,
        autocorrelation=autocorrelation,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )
    return run_monte_carlo(
        strategy,
        firm=firm,
        n_simulations=n_sims,
        seed=seed_base,
        max_eval_days=grid.max_eval_days,
        max_funded_days=grid.max_funded_days,
        topstep_payout_path=payout_path or TopStepPayoutPath.STANDARD,
        topstep_use_daily_loss_limit=grid.topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=grid.topstep_max_back2funded_reactivations,
        payout_cap=grid.payout_cap,
    )


def _run_regime_switching(
    *,
    wr: float,
    rr: float,
    freq: int,
    eval_loss: float,
    funded_loss: float,
    spread: float,
    firm: FirmName,
    payout_path: TopStepPayoutPath | None,
    n_sims: int,
    seed_base: int,
    grid: GridSpec,
):
    good_wr = min(1.0, wr + spread)
    bad_wr = max(0.0, wr - spread)
    regimes = (
        StrategyRegime(name="good", probability=0.5, win_rate=good_wr, rr_ratio=rr),
        StrategyRegime(name="bad", probability=0.5, win_rate=bad_wr, rr_ratio=rr),
    )
    strategy = RegimeSwitchingPhaseAwareBernoulliStrategy(
        regimes=regimes,
        eval_loss_size=eval_loss,
        funded_loss_size=funded_loss,
        trades_per_day=freq,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )
    return run_monte_carlo(
        strategy,
        firm=firm,
        n_simulations=n_sims,
        seed=seed_base,
        max_eval_days=grid.max_eval_days,
        max_funded_days=grid.max_funded_days,
        topstep_payout_path=payout_path or TopStepPayoutPath.STANDARD,
        topstep_use_daily_loss_limit=grid.topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=grid.topstep_max_back2funded_reactivations,
        payout_cap=grid.payout_cap,
    )


def _run_adaptive_search(
    *,
    wr: float,
    rr: float,
    freq: int,
    firm: FirmName,
    payout_path: TopStepPayoutPath | None,
    seed_base: int,
    grid: GridSpec,
):
    """Sweep AdaptiveSizing at the actual frequency and return the best cell."""
    best: AdaptiveSearchWinner | None = None
    combo_idx = 0
    for eval_base in grid.eval_bases_search:
        for funded_base in grid.funded_bases_search:
            for buffer_full_frac in grid.buffer_full_fracs_search:
                for buffer_floor in grid.buffer_floors_search:
                    for post_payout_shrink in grid.post_payout_shrinks_search:
                        sizing = AdaptiveSizing(
                            eval_base=eval_base,
                            funded_base=funded_base,
                            buffer_full_frac=buffer_full_frac,
                            buffer_floor=buffer_floor,
                            post_payout_shrink=post_payout_shrink,
                        )
                        result = _run_iid_state_aware(
                            sizing_fn=sizing,
                            wr=wr,
                            rr=rr,
                            freq=freq,
                            firm=firm,
                            payout_path=payout_path,
                            n_sims=grid.n_sims,
                            seed_base=seed_base + 10_000 + combo_idx * 1_000_003,
                            grid=grid,
                        )
                        candidate = AdaptiveSearchWinner(
                            eval_base=eval_base,
                            funded_base=funded_base,
                            buffer_full_frac=buffer_full_frac,
                            buffer_floor=buffer_floor,
                            post_payout_shrink=post_payout_shrink,
                            result=result,
                        )
                        if best is None or result.mean_net_ev > best.result.mean_net_ev:
                            best = candidate
                        combo_idx += 1

    if best is None:
        raise RuntimeError("adaptive search grid produced no candidates")
    return best


def run_catalog(grid: GridSpec, seed: int = 0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for path_name in grid.payout_paths:
        firm, payout_path = _firm_and_path(path_name)
        for wr in grid.win_rates:
            for rr in grid.rr_ratios:
                for freq in grid.trades_per_day:
                    seed_base = _cell_seed_base(seed, firm, path_name, wr, rr, freq)

                    # ---- Sizing study (i.i.d. only) ----

                    # Fixed
                    fixed = FixedSizing(
                        eval_size=grid.fixed_eval_base, funded_size=grid.fixed_funded_base
                    )
                    res = _run_iid_state_aware(
                        sizing_fn=fixed,
                        wr=wr,
                        rr=rr,
                        freq=freq,
                        firm=firm,
                        payout_path=payout_path,
                        n_sims=grid.n_sims,
                        seed_base=seed_base,
                        grid=grid,
                    )
                    row = _row_template(grid)
                    row.update({
                        "study": "sizing",
                        "firm": firm,
                        "payout_path": path_name,
                        "sizing": "Fixed",
                        "strategy_variant": "iid",
                        "win_rate": wr,
                        "rr_ratio": rr,
                        "trades_per_day": freq,
                    })
                    _fill_mc_columns(row, res, grid.n_sims)
                    rows.append(row)

                    # BufferAware
                    buffer_aware = BufferAwareSizing(
                        eval_base=grid.fixed_eval_base,
                        funded_base=grid.fixed_funded_base,
                    )
                    res = _run_iid_state_aware(
                        sizing_fn=buffer_aware,
                        wr=wr,
                        rr=rr,
                        freq=freq,
                        firm=firm,
                        payout_path=payout_path,
                        n_sims=grid.n_sims,
                        seed_base=seed_base + 1,
                        grid=grid,
                    )
                    row = _row_template(grid)
                    row.update({
                        "study": "sizing",
                        "firm": firm,
                        "payout_path": path_name,
                        "sizing": "BufferAware",
                        "strategy_variant": "iid",
                        "win_rate": wr,
                        "rr_ratio": rr,
                        "trades_per_day": freq,
                    })
                    _fill_mc_columns(row, res, grid.n_sims)
                    rows.append(row)

                    # Adaptive (search per cell, report best)
                    best_opt = _run_adaptive_search(
                        wr=wr,
                        rr=rr,
                        freq=freq,
                        firm=firm,
                        payout_path=payout_path,
                        seed_base=seed_base,
                        grid=grid,
                    )
                    row = _row_template(grid)
                    row.update({
                        "study": "sizing",
                        "firm": firm,
                        "payout_path": path_name,
                        "sizing": "Adaptive",
                        "strategy_variant": "iid",
                        "win_rate": wr,
                        "rr_ratio": rr,
                        "trades_per_day": freq,
                        "adaptive_eval_base": best_opt.eval_base,
                        "adaptive_funded_base": best_opt.funded_base,
                        "adaptive_buffer_full_frac": best_opt.buffer_full_frac,
                        "adaptive_buffer_floor": best_opt.buffer_floor,
                        "adaptive_post_payout_shrink": best_opt.post_payout_shrink,
                    })
                    _fill_mc_columns(row, best_opt.result, grid.n_sims)
                    rows.append(row)

                    # ---- Robustness study (Fixed sizing only) ----
                    # iid×Fixed already covered above; only autocorr + regime here.

                    res = _run_autocorrelated(
                        wr=wr,
                        rr=rr,
                        freq=freq,
                        eval_loss=grid.fixed_eval_base,
                        funded_loss=grid.fixed_funded_base,
                        autocorrelation=grid.autocorrelation,
                        firm=firm,
                        payout_path=payout_path,
                        n_sims=grid.n_sims,
                        seed_base=seed_base + 3,
                        grid=grid,
                    )
                    row = _row_template(grid)
                    row.update({
                        "study": "robustness",
                        "firm": firm,
                        "payout_path": path_name,
                        "sizing": "Fixed",
                        "strategy_variant": "autocorrelated",
                        "win_rate": wr,
                        "rr_ratio": rr,
                        "trades_per_day": freq,
                    })
                    _fill_mc_columns(row, res, grid.n_sims)
                    rows.append(row)

                    res = _run_regime_switching(
                        wr=wr,
                        rr=rr,
                        freq=freq,
                        eval_loss=grid.fixed_eval_base,
                        funded_loss=grid.fixed_funded_base,
                        spread=grid.regime_wr_spread,
                        firm=firm,
                        payout_path=payout_path,
                        n_sims=grid.n_sims,
                        seed_base=seed_base + 4,
                        grid=grid,
                    )
                    row = _row_template(grid)
                    row.update({
                        "study": "robustness",
                        "firm": firm,
                        "payout_path": path_name,
                        "sizing": "Fixed",
                        "strategy_variant": "regime_switching",
                        "win_rate": wr,
                        "rr_ratio": rr,
                        "trades_per_day": freq,
                    })
                    _fill_mc_columns(row, res, grid.n_sims)
                    rows.append(row)

    return rows


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(
    *,
    path: Path,
    grid: GridSpec,
    mode: str,
    seed: int,
    elapsed_s: float,
    n_rows: int,
) -> None:
    payload = {
        "mode": mode,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "seed": seed,
        "elapsed_seconds": round(elapsed_s, 2),
        "n_rows": n_rows,
        "grid": {
            "win_rates": list(grid.win_rates),
            "rr_ratios": list(grid.rr_ratios),
            "trades_per_day": list(grid.trades_per_day),
            "payout_paths": list(grid.payout_paths),
            "n_sims": grid.n_sims,
            "fixed_eval_base": grid.fixed_eval_base,
            "fixed_funded_base": grid.fixed_funded_base,
            "autocorrelation": grid.autocorrelation,
            "regime_wr_spread": grid.regime_wr_spread,
            "adaptive_search": {
                "eval_bases": list(grid.eval_bases_search),
                "funded_bases": list(grid.funded_bases_search),
                "buffer_full_fracs": list(grid.buffer_full_fracs_search),
                "buffer_floors": list(grid.buffer_floors_search),
                "post_payout_shrinks": list(grid.post_payout_shrinks_search),
                "combinations_per_cell": grid.adaptive_search_size(),
            },
            "max_eval_days": grid.max_eval_days,
            "max_funded_days": grid.max_funded_days,
            "topstep_use_daily_loss_limit": grid.topstep_use_daily_loss_limit,
            "topstep_max_back2funded_reactivations": (
                grid.topstep_max_back2funded_reactivations
            ),
            "payout_cap": grid.payout_cap,
        },
        "studies": {
            "sizing": "iid × {Fixed, BufferAware, Adaptive}",
            "robustness": "{autocorrelated, regime_switching} × Fixed (iid×Fixed shared with sizing study)",
        },
        "known_limitations": [
            "RegimeSwitching strategy samples regime per trade, so it is a "
            "WR-uncertainty mixture, not a regime-persistence stress.",
            "Sizing × strategy is non-orthogonal: BufferAware/Adaptive "
            "currently only combine with iid because the autocorrelated and "
            "regime-switching strategies hardcode loss sizes per phase.",
            "LucidFlex vault discount cycles and reset economics are "
            "not modeled here. Phase 3.5 step 3 handles that downstream.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(payload, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use the production grid (slow). Default is the smoke grid.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--n-sims",
        type=int,
        default=None,
        help="Override simulations per catalog row for quick validation runs.",
    )
    parser.add_argument(
        "--topstep-dll",
        action="store_true",
        help="Enable TopStep optional daily-loss-limit lock in TopStep rows.",
    )
    parser.add_argument(
        "--topstep-back2funded",
        type=int,
        default=None,
        help="Override max TopStep Back2Funded reactivations for TopStep rows.",
    )
    parser.add_argument(
        "--payout-cap",
        type=int,
        default=None,
        help="Optional simulation payout cap for finite cross-firm comparisons.",
    )
    parser.add_argument(
        "--uncapped-topstep",
        action="store_true",
        help="Run TopStep through the full funded horizon instead of capping payouts.",
    )
    args = parser.parse_args()

    grid = FULL_GRID if args.full else SMOKE_GRID
    overrides = {}
    if args.n_sims is not None:
        overrides["n_sims"] = args.n_sims
    if args.topstep_dll:
        overrides["topstep_use_daily_loss_limit"] = True
    if args.topstep_back2funded is not None:
        overrides["topstep_max_back2funded_reactivations"] = args.topstep_back2funded
    if args.payout_cap is not None:
        overrides["payout_cap"] = args.payout_cap
    if args.uncapped_topstep:
        overrides["payout_cap"] = None
    if overrides:
        grid = replace(grid, **overrides)

    mode = "full" if args.full else "smoke"
    print(f"[catalog] mode={mode} cells={grid.cell_count()} n_sims={grid.n_sims}")
    print(
        f"[catalog] adaptive search per cell = {grid.adaptive_search_size()} combinations"
    )

    start = time.perf_counter()
    rows = run_catalog(grid, seed=args.seed)
    elapsed = time.perf_counter() - start
    print(f"[catalog] {len(rows)} rows produced in {elapsed:.1f}s")

    csv_path = args.output_dir / "cells.csv"
    manifest_path = args.output_dir / "manifest.json"
    _write_csv(rows, csv_path)
    _write_manifest(
        path=manifest_path,
        grid=grid,
        mode=mode,
        seed=args.seed,
        elapsed_s=elapsed,
        n_rows=len(rows),
    )
    print(f"[catalog] wrote {csv_path}")
    print(f"[catalog] wrote {manifest_path}")


if __name__ == "__main__":
    main()
