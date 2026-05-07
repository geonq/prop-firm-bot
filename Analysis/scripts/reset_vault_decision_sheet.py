"""Phase 3.5 step 3 — reset/vault economics decision sheet.

For each of the 5 named profiles selected in
``Analysis/2026-05-06_target_cell_catalog.md``, re-run Monte Carlo with
ruleset variants that net in commercial economics not modeled in the
default catalog:

  - LucidFlex: eval_fee in {98 (default 30% coupon), 84 (40% vault), 70 (50% vault)}
  - TopStep:   DLL on/off; Back2Funded reactivations in {0, 1, 3}; capped (5) vs uncapped

Reuses adaptive sizing parameters already discovered by the full catalog
(`Analysis/output/target_cell_catalog/cells.csv`) so we don't redo the
adaptive search.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.monte_carlo import run_monte_carlo
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K, TopStepPayoutPath
from src.sizing.dynamic import AdaptiveSizing, FixedSizing
from src.strategies.parametric import StateAwareBernoulliStrategy

CATALOG_CSV = REPO_ROOT / "Analysis" / "output" / "target_cell_catalog" / "cells.csv"
OUT_DIR = REPO_ROOT / "Analysis" / "output" / "reset_vault_decision_sheet"

# Named profiles from the catalog writeup. firm/sizing are the catalog winner;
# we still test all three firms here so the decision sheet can surface a flip.
PROFILES = [
    ("Patient swing",   0.40, 2.50, 1, "Adaptive"),
    ("Low-WR breakout", 0.30, 3.00, 5, "Adaptive"),
    ("Balanced edge",   0.50, 1.50, 3, "Adaptive"),
    ("Robust trend",    0.45, 2.00, 3, "Adaptive"),
    ("High-WR scalp",   0.65, 0.75, 3, "Fixed"),
]

LUCIDFLEX_FEE_VARIANTS = [98, 84, 70]  # default coupon, 40% vault, 50% vault
TOPSTEP_DLL_VARIANTS = [False, True]
TOPSTEP_B2F_VARIANTS = [0, 1, 3]
N_SIMS = 1000


def load_adaptive_params(wr: float, rr: float, freq: int, payout_path: str) -> dict:
    """Pull adaptive sizing params for this exact cell from the catalog CSV."""
    with CATALOG_CSV.open() as f:
        for row in csv.DictReader(f):
            if (
                row["study"] == "sizing"
                and row["sizing"] == "Adaptive"
                and row["strategy_variant"] == "iid"
                and float(row["win_rate"]) == wr
                and float(row["rr_ratio"]) == rr
                and int(row["trades_per_day"]) == freq
                and row["payout_path"] == payout_path
            ):
                return {
                    "eval_base": float(row["adaptive_eval_base"]),
                    "funded_base": float(row["adaptive_funded_base"]),
                    "buffer_full_frac": float(row["adaptive_buffer_full_frac"]),
                    "buffer_floor": float(row["adaptive_buffer_floor"]),
                    "post_payout_shrink": float(row["adaptive_post_payout_shrink"]),
                }
    raise KeyError(f"no Adaptive row for {wr}/{rr}/{freq}/{payout_path}")


def make_strategy(wr: float, rr: float, freq: int, sizing: str, path: str):
    if sizing == "Fixed":
        sizing_fn = FixedSizing(eval_size=250.0, funded_size=250.0)
    else:
        params = load_adaptive_params(wr, rr, freq, path)
        sizing_fn = AdaptiveSizing(**params)
    return StateAwareBernoulliStrategy(
        win_rate=wr,
        rr_ratio=rr,
        sizing_fn=sizing_fn,
        trades_per_day=freq,
        eval_cost_per_trade=5.0,
        funded_cost_per_trade=5.0,
    )


def run_one(strategy, firm, *, lf_rules=None, ts_rules=None,
            payout_path=TopStepPayoutPath.STANDARD, dll=False, b2f=0,
            payout_cap=5, seed=42):
    return run_monte_carlo(
        strategy,
        firm=firm,
        n_simulations=N_SIMS,
        seed=seed,
        lucidflex_ruleset=lf_rules,
        topstep_ruleset=ts_rules,
        topstep_payout_path=payout_path,
        topstep_use_daily_loss_limit=dll,
        topstep_max_back2funded_reactivations=b2f,
        max_eval_days=90,
        max_funded_days=180,
        payout_cap=payout_cap,
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.perf_counter()

    for name, wr, rr, freq, default_sizing in PROFILES:
        print(f"\n=== {name} (WR={wr} R={rr} freq={freq}) ===")

        # ---- LucidFlex eval-fee variants ----
        for fee in LUCIDFLEX_FEE_VARIANTS:
            strat = make_strategy(wr, rr, freq, default_sizing, "lucidflex")
            lf = replace(LucidFlex50K(), eval_fee=fee)
            res = run_one(strat, "lucidflex", lf_rules=lf)
            rows.append({
                "profile": name, "firm": "lucidflex",
                "variant": f"eval_fee={fee}",
                "sizing": default_sizing,
                "wr": wr, "rr": rr, "freq": freq,
                "mean_ev": res.mean_net_ev,
                "ev_low": res.ev_ci.low,
                "ev_high": res.ev_ci.high,
                "p_pass": res.eval_pass_rate,
                "p_breach_after_pass": res.funded_breach_after_pass_rate,
                "p_max_payout": res.max_payout_rate,
            })
            print(f"  lucidflex eval_fee={fee}: mean={res.mean_net_ev:.0f} ev_low={res.ev_ci.low:.0f}")

        # ---- TopStep Standard variants ----
        for dll in TOPSTEP_DLL_VARIANTS:
            for b2f in TOPSTEP_B2F_VARIANTS:
                strat = make_strategy(wr, rr, freq, default_sizing, "topstep_standard")
                res = run_one(strat, "topstep",
                              payout_path=TopStepPayoutPath.STANDARD,
                              dll=dll, b2f=b2f)
                rows.append({
                    "profile": name, "firm": "topstep_standard",
                    "variant": f"dll={dll} b2f={b2f}",
                    "sizing": default_sizing,
                    "wr": wr, "rr": rr, "freq": freq,
                    "mean_ev": res.mean_net_ev,
                    "ev_low": res.ev_ci.low,
                    "ev_high": res.ev_ci.high,
                    "p_pass": res.eval_pass_rate,
                    "p_breach_after_pass": res.funded_breach_after_pass_rate,
                    "p_max_payout": res.max_payout_rate,
                })
                print(f"  topstep_std dll={dll} b2f={b2f}: mean={res.mean_net_ev:.0f} ev_low={res.ev_ci.low:.0f}")

        # ---- TopStep Consistency variants ----
        for dll in TOPSTEP_DLL_VARIANTS:
            for b2f in TOPSTEP_B2F_VARIANTS:
                strat = make_strategy(wr, rr, freq, default_sizing, "topstep_consistency")
                res = run_one(strat, "topstep",
                              payout_path=TopStepPayoutPath.CONSISTENCY,
                              dll=dll, b2f=b2f)
                rows.append({
                    "profile": name, "firm": "topstep_consistency",
                    "variant": f"dll={dll} b2f={b2f}",
                    "sizing": default_sizing,
                    "wr": wr, "rr": rr, "freq": freq,
                    "mean_ev": res.mean_net_ev,
                    "ev_low": res.ev_ci.low,
                    "ev_high": res.ev_ci.high,
                    "p_pass": res.eval_pass_rate,
                    "p_breach_after_pass": res.funded_breach_after_pass_rate,
                    "p_max_payout": res.max_payout_rate,
                })
                print(f"  topstep_con dll={dll} b2f={b2f}: mean={res.mean_net_ev:.0f} ev_low={res.ev_ci.low:.0f}")

    # ---- Sensitivity: leader profile uncapped TopStep ----
    leader = ("Robust trend", 0.45, 2.00, 3, "Adaptive")
    name, wr, rr, freq, sz = leader
    print(f"\n=== Sensitivity: {name} uncapped TopStep ===")
    for path_name, path_enum in [
        ("topstep_standard", TopStepPayoutPath.STANDARD),
        ("topstep_consistency", TopStepPayoutPath.CONSISTENCY),
    ]:
        strat = make_strategy(wr, rr, freq, sz, path_name)
        res = run_one(strat, "topstep", payout_path=path_enum,
                      dll=False, b2f=0, payout_cap=None)
        rows.append({
            "profile": name + " (uncapped)",
            "firm": path_name,
            "variant": "dll=False b2f=0 uncapped",
            "sizing": sz,
            "wr": wr, "rr": rr, "freq": freq,
            "mean_ev": res.mean_net_ev,
            "ev_low": res.ev_ci.low,
            "ev_high": res.ev_ci.high,
            "p_pass": res.eval_pass_rate,
            "p_breach_after_pass": res.funded_breach_after_pass_rate,
            "p_max_payout": res.max_payout_rate,
        })
        print(f"  {path_name} uncapped: mean={res.mean_net_ev:.0f} ev_low={res.ev_ci.low:.0f} p_max={res.max_payout_rate:.2f}")

    elapsed = time.perf_counter() - started
    print(f"\n[done] {len(rows)} rows in {elapsed:.1f}s")

    csv_path = OUT_DIR / "decision_sheet.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "n_rows": len(rows),
        "n_sims_per_row": N_SIMS,
        "elapsed_seconds": round(elapsed, 2),
        "profiles": [p[0] for p in PROFILES],
        "lucidflex_fee_variants": LUCIDFLEX_FEE_VARIANTS,
        "topstep_dll_variants": TOPSTEP_DLL_VARIANTS,
        "topstep_b2f_variants": TOPSTEP_B2F_VARIANTS,
    }
    with (OUT_DIR / "manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[done] wrote {csv_path}")


if __name__ == "__main__":
    main()
