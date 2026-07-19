"""Direct test: does the ORIGINAL round-2/3 winner hold up on 2015-2025 data?

Today's Stage A/B search never actually re-tested the exact combination that
won rounds 2-3 (or=15, first_candle, or_opposite, 4R, slip=2, vwap_trail=2.0,
time_stop=120) against the extended 18-fold dataset -- Stage B only crossed
exit overlays with Stage A's own top-3 entries, which all turned out to be
5-minute variants. This is the single most informative missing comparison:
whether the earlier winner generalizes to 5 additional, previously-unseen
years, or whether it was specific to the 2020-2025 regime.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Analysis" / "scripts"))

import pandas as pd

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import (
    DEFAULT_RISK_PER_TRADE_USD,
    HOLDOUT_START,
    REPLAY_FIRMS,
    _evaluate_candidate_oos,
    make_folds,
    params_hash,
)

import orb_full_scope_run as fsr

OUT = ROOT / "Analysis" / "output" / "orb" / "full_scope"

ORIGINAL_WINNER = ORBParams(
    or_minutes=15,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=2.0,
    vwap_trail_after_r=2.0,
    time_stop_minutes=120,
)


def main() -> None:
    bars = pd.read_parquet(fsr.DATA_PATH)
    folds = make_folds("2015-01-01", HOLDOUT_START, is_months=18, oos_months=6, step_months=6)
    print(f"original winner params_hash={params_hash(ORIGINAL_WINNER)}")

    t0 = time.monotonic()
    result = _evaluate_candidate_oos(
        bars, ORIGINAL_WINNER, folds, firms=REPLAY_FIRMS,
        n_simulations=2000, block_size=5, risk_per_trade_usd=DEFAULT_RISK_PER_TRADE_USD, seed=0,
    )
    print(f"re-evaluated on 18 EXTENDED folds in {time.monotonic()-t0:.0f}s")
    row = fsr._candidate_row(result)
    print(f"result: {row}")

    fsr.OUT = OUT
    c_out = fsr.stage_c_risk_resweep(bars, ORIGINAL_WINNER, folds)
    (OUT / "stage_c_ORIGINAL_risk_resweep.json").write_text(json.dumps(c_out, indent=2))

    per_fold_r = []
    for f in result.fold_results:
        vals = {firm: f.firm_summaries[firm].net_ev_mean for firm in REPLAY_FIRMS if firm in f.firm_summaries}
        per_fold_r.append({"fold_index": f.fold_index, "trade_count": f.trade_count, **vals})
    out = {"row": row, "per_fold": per_fold_r}
    (OUT / "stage_original_winner_extended_check.json").write_text(json.dumps(out, indent=2, default=str))
    print("\nPER-FOLD net_ev_mean (does the winner hold up across ALL 18 regimes, not just the median?):")
    for pf in per_fold_r:
        print(f"  fold {pf['fold_index']:2d} (n={pf['trade_count']:4d}): "
              f"lucid={pf.get('lucidflex', float('nan')):8.1f} topstep={pf.get('topstep', float('nan')):8.1f} "
              f"apexEOD={pf.get('apex_eod', float('nan')):8.1f} apexIntra={pf.get('apex_intraday', float('nan')):8.1f}")
    print("\nORIGINAL WINNER EXTENDED-DATA CHECK COMPLETE")


if __name__ == "__main__":
    main()
