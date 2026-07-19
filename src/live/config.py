"""Frozen strategy + instrument config for the Phase 6A live runner.

`FROZEN_PARAMS` and `PARAMS_HASH` must never change without a new holdout
sign-off (see Analysis/output/orb/full_scope/holdout_8afbe6259cab2dd2.json,
Tasks/todo.md "Phase 6A").

TWO independent tamper guards are checked at runner startup
(`verify_params_hash()`), and each claims only what it actually covers
(reviewer Fix 2, 2026-07-18 — the original single guard's docstring implied
full-config protection it didn't provide):

1. `PARAMS_HASH` / `compute_holdout_provenance_hash()` — reuses
   `src.optimizer.walk_forward.params_hash` UNCHANGED (imported, not
   reimplemented, so it can never drift from the holdout script's own
   hash). This hash covers ONLY the 7 fields that function hashes
   (`or_minutes`, `entry_mode`, `stop_mode`, `target_r`,
   `vol_percentile_min`, `rel_volume_min`, `slippage_ticks`) — it proves
   "this is the exact config that was holdout-evaluated and recorded in
   Analysis/output/orb/full_scope/holdout_8afbe6259cab2dd2.json," nothing
   more. It is BLIND to every other `ORBParams` field (including
   `time_stop_minutes`, which FROZEN_PARAMS actually depends on for its
   exit behavior) and to the MNQ instrument/risk constants below.
2. `FULL_CONFIG_HASH` / `compute_full_config_hash()` — a second,
   independently-computed hash over EVERY `ORBParams` field
   (`dataclasses.asdict(FROZEN_PARAMS)`) plus the instrument constants
   this module adds on top (`MNQ.point_value`, `MNQ.tick_size`,
   `RISK_PER_TRADE_USD`) that the backtest/holdout never needed to hash
   because they don't exist there. This is the guard that actually catches
   "someone changed `time_stop_minutes`, `doji_threshold`, `tick_size`, or
   the live risk budget without updating the recorded hash."

`verify_params_hash()` checks BOTH and refuses to start on either mismatch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from src.backtest.orb import ORBParams
from src.optimizer.walk_forward import params_hash as _walk_forward_params_hash

# Frozen round-4 full-scope holdout config. Copied verbatim from
# Analysis/scripts/orb_holdout_eval_round4.py::FROZEN — do not edit without
# re-running and re-signing a new holdout.
FROZEN_PARAMS = ORBParams(
    or_minutes=5,
    entry_mode="first_candle",
    stop_mode="or_opposite",
    target_r=4.0,
    vol_percentile_min=None,
    rel_volume_min=None,
    slippage_ticks=1.0,
    vwap_trail_after_r=None,
    time_stop_minutes=120,
)

RISK_PER_TRADE_USD = 400.0


@dataclass(frozen=True)
class InstrumentConfig:
    """Contract economics for the instrument actually traded live (MNQ, not NQ).

    The backtest's R-multiples are point/risk ratios and are instrument-
    agnostic; `point_value` here is only used to convert stop distance (in
    points) into a dollar-risk-per-contract for live position sizing
    (src/live/sizing.py), and to convert fills into a paper P&L.
    """

    symbol: str = "MNQ"
    point_value: float = 2.00
    tick_size: float = 0.25


MNQ = InstrumentConfig(symbol="MNQ", point_value=2.00, tick_size=0.25)

# Hard ceiling on contracts per trade regardless of sizing math (tamper /
# fat-finger guard, not a strategy parameter). Configurable per call site.
DEFAULT_MAX_CONTRACTS = 20

# Kill-switch default: flatten and halt for the rest of the session if
# realized loss for the day reaches this many dollars.
DEFAULT_DAILY_LOSS_CAP_USD = 600.0

# PLACEHOLDER — verify against TopstepX published fee schedule before live.
# Per contract, per side (i.e. one full round trip charges 2x this per
# contract). Reviewer-adjudicated (2026-07-18): PaperBroker's gross fills
# stay exactly as-is (they're what makes parity exact — do not charge this
# inside PaperBroker/FilledTrade). This constant is used ONLY by the trade
# journal's additive net_pnl_usd/net_r columns (src/live/runner.py) to show
# what a trade would net after commission, without touching the gross P&L
# path anything else in this package depends on. Deliberately NOT the
# backtest's `ORBParams.commission_usd_per_side` ($4.50) — that figure is
# scaled for NQ ($20/point); charging it on MNQ ($2/point) would overcharge
# commission by roughly 10x.
MNQ_COMMISSION_USD_PER_SIDE = 0.74


class ParamsHashMismatch(RuntimeError):
    """Raised when either tamper guard (holdout-provenance or full-config) fails.

    If someone edits FROZEN_PARAMS, MNQ, or RISK_PER_TRADE_USD without
    updating the matching recorded hash constant (or vice versa), the
    runner must refuse to start rather than silently trade a config that
    was never holdout-validated / never re-hashed after a change. See the
    module docstring for exactly what each of the two guards does and does
    not cover.
    """


def compute_params_hash() -> str:
    """Recompute the HOLDOUT-PROVENANCE hash (7 fields only — see module docstring)."""
    return _walk_forward_params_hash(FROZEN_PARAMS)


def _full_config_payload() -> dict:
    return {
        "orb_params": asdict(FROZEN_PARAMS),
        "instrument_point_value": MNQ.point_value,
        "instrument_tick_size": MNQ.tick_size,
        "risk_per_trade_usd": RISK_PER_TRADE_USD,
    }


def compute_full_config_hash() -> str:
    """Recompute the FULL-CONFIG hash: every ORBParams field + live-only constants.

    Same hashing convention as `src.optimizer.walk_forward.params_hash`
    (sha256 of a sort_keys=True JSON payload, `default=str` for non-JSON
    types like ORBParams.allowed_weekdays' frozenset, truncated to 16 hex
    chars) but over a strictly larger payload — see module docstring for
    exactly why this second hash exists.
    """
    payload = json.dumps(_full_config_payload(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Recorded in Analysis/output/orb/full_scope/holdout_8afbe6259cab2dd2.json.
PARAMS_HASH = "8afbe6259cab2dd2"

# Computed once via compute_full_config_hash() on the FROZEN_PARAMS/MNQ/
# RISK_PER_TRADE_USD values above and recorded here (reviewer Fix 2,
# 2026-07-18). Unlike PARAMS_HASH, this is NOT tied to any holdout record —
# it exists purely so any future edit to ANY field on this page (not just
# the 7 PARAMS_HASH covers) is caught at runner startup.
FULL_CONFIG_HASH = "583f24ae460c9ed3"


def verify_params_hash() -> None:
    """Refuse to proceed if either tamper guard fails.

    Called at runner startup (see src/live/runner.py). Raises
    `ParamsHashMismatch` on any drift rather than returning a bool, so
    callers cannot accidentally ignore the result. Checks BOTH
    `PARAMS_HASH` (holdout-provenance, 7 fields) and `FULL_CONFIG_HASH`
    (every ORBParams field + MNQ + RISK_PER_TRADE_USD) — see module
    docstring for what each one actually guarantees.
    """
    computed_holdout = compute_params_hash()
    if computed_holdout != PARAMS_HASH:
        raise ParamsHashMismatch(
            f"FROZEN_PARAMS holdout-provenance hash mismatch: computed={computed_holdout!r} "
            f"recorded={PARAMS_HASH!r}. Refusing to start — this config was never "
            "holdout-validated. See Analysis/output/orb/full_scope/holdout_8afbe6259cab2dd2.json."
        )
    computed_full = compute_full_config_hash()
    if computed_full != FULL_CONFIG_HASH:
        raise ParamsHashMismatch(
            f"Full-config hash mismatch: computed={computed_full!r} recorded={FULL_CONFIG_HASH!r}. "
            "Refusing to start — FROZEN_PARAMS, MNQ, or RISK_PER_TRADE_USD changed without "
            "re-recording FULL_CONFIG_HASH in src/live/config.py. The 7-field holdout-provenance "
            "hash alone would NOT have caught this drift."
        )
