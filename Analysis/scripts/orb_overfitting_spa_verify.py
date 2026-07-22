"""Independent Hansen SPA verification for the ORB overfitting battery.

Requires the research-only ``arch`` package. It writes a separate artifact so
production dependencies and live strategy configuration remain untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arch import __version__ as arch_version  # noqa: E402
from arch.bootstrap import SPA  # noqa: E402

from Analysis.scripts.orb_mnq_70_30_research import (  # noqa: E402
    Candidate,
    _daily,
    _daily_features,
    _run,
    candidate_grid,
    sessions_from_bars,
)
from Analysis.scripts.orb_nq_multiyear_70_30 import RAW, load_databento_csv  # noqa: E402
from Analysis.scripts.orb_overfitting_battery import (  # noqa: E402
    OUT,
    opening_drive_neighborhood,
)


def main() -> dict:
    sessions = dict(sorted(sessions_from_bars(load_databento_csv(RAW)).items()))
    dates = list(sessions)
    features = _daily_features(sessions)
    next_open = Candidate(
        "opening_drive_t4_ts120_doji10_nextopen",
        "first_candle",
        target_r=4.0,
        time_stop_minutes=120,
        doji_threshold=0.10,
        first_candle_reference="next_open",
    )
    candidates = opening_drive_neighborhood() + [next_open] + [
        candidate for candidate in candidate_grid() if candidate.entry != "first_candle"
    ]
    trades = {candidate.name: _run(sessions, features, candidate) for candidate in candidates}
    matrix = np.column_stack(
        [_daily(trades[candidate.name], dates).to_numpy() for candidate in candidates]
    )

    rows = {}
    for bootstrap in ("stationary", "circular"):
        for block_length in (5, 10, 20):
            spa = SPA(
                np.zeros(len(dates)),
                -matrix,
                block_size=block_length,
                reps=5_000,
                bootstrap=bootstrap,
                studentize=True,
                seed=20260720 + block_length,
            )
            spa.compute()
            rows[f"{bootstrap}_{block_length}"] = {
                key: float(value) for key, value in spa.pvalues.items()
            }

    result = {
        "implementation": "arch.bootstrap.SPA",
        "arch_version": arch_version,
        "benchmark": "zero return; model losses are negative daily R",
        "strategies": int(matrix.shape[1]),
        "sessions": int(matrix.shape[0]),
        "bootstrap_repetitions": 5_000,
        "studentized": True,
        "spa": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "arch_spa_verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
