"""Tamper-guard tests for src/live/config.py.

Reviewer Fix 2 (2026-07-18, live-money): the original single `PARAMS_HASH`
guard reuses `src.optimizer.walk_forward.params_hash`, which only hashes 7
of `ORBParams`' 23 fields (or_minutes, entry_mode, stop_mode, target_r,
vol_percentile_min, rel_volume_min, slippage_ticks). Changing
`time_stop_minutes` -- a field FROZEN_PARAMS actually depends on for exit
behavior -- silently passed `verify_params_hash()` before this fix. These
tests prove the NEW `FULL_CONFIG_HASH` guard actually catches that class of
drift, using `dataclasses.replace` on a local copy so the real
`src.live.config` module (and its real FROZEN_PARAMS/PARAMS_HASH/
FULL_CONFIG_HASH constants) are never mutated.
"""

from __future__ import annotations

import dataclasses
import json
import hashlib

import pytest

from src.live import config as live_config
from src.live.config import (
    FROZEN_PARAMS,
    FULL_CONFIG_HASH,
    MNQ,
    PARAMS_HASH,
    RISK_PER_TRADE_USD,
    ParamsHashMismatch,
    compute_full_config_hash,
    compute_params_hash,
    verify_params_hash,
)


def _hash_of_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def test_current_frozen_config_passes_both_guards():
    """Sanity: the real, unmodified FROZEN_PARAMS/MNQ/RISK_PER_TRADE_USD must
    pass both guards right now -- this is the "nothing is tampered" baseline
    every other test in this file diffs against.
    """
    assert compute_params_hash() == PARAMS_HASH
    assert compute_full_config_hash() == FULL_CONFIG_HASH
    verify_params_hash()  # must not raise


def test_holdout_provenance_hash_is_blind_to_time_stop_minutes():
    """Documents the KNOWN, ACCEPTED blind spot of the 7-field hash (this is
    not a bug to fix in walk_forward.py -- the spec says do not edit it).
    Changing time_stop_minutes must NOT change the 7-field hash, since that
    field isn't one of the 7.
    """
    mutated = dataclasses.replace(FROZEN_PARAMS, time_stop_minutes=999)
    from src.optimizer.walk_forward import params_hash as walk_forward_params_hash

    assert walk_forward_params_hash(mutated) == walk_forward_params_hash(FROZEN_PARAMS)


def test_full_config_hash_catches_time_stop_minutes_mutation():
    """The actual reviewer-mandated regression test: a config with
    time_stop_minutes changed must produce a DIFFERENT full-config hash than
    the recorded FULL_CONFIG_HASH -- this is the tamper this fix exists to
    catch.
    """
    mutated = dataclasses.replace(FROZEN_PARAMS, time_stop_minutes=60)
    payload = {
        "orb_params": dataclasses.asdict(mutated),
        "instrument_point_value": MNQ.point_value,
        "instrument_tick_size": MNQ.tick_size,
        "risk_per_trade_usd": RISK_PER_TRADE_USD,
    }
    mutated_hash = _hash_of_payload(payload)
    assert mutated_hash != FULL_CONFIG_HASH


def test_full_config_hash_catches_doji_threshold_mutation():
    mutated = dataclasses.replace(FROZEN_PARAMS, doji_threshold=0.5)
    payload = {
        "orb_params": dataclasses.asdict(mutated),
        "instrument_point_value": MNQ.point_value,
        "instrument_tick_size": MNQ.tick_size,
        "risk_per_trade_usd": RISK_PER_TRADE_USD,
    }
    assert _hash_of_payload(payload) != FULL_CONFIG_HASH


def test_full_config_hash_catches_tick_size_mutation():
    """Instrument tick_size (MNQ.tick_size) mutation must also be caught --
    this constant lives outside ORBParams entirely, so it's the clearest
    proof the guard covers more than just the backtest's own dataclass.
    """
    payload = {
        "orb_params": dataclasses.asdict(FROZEN_PARAMS),
        "instrument_point_value": MNQ.point_value,
        "instrument_tick_size": 1.0,  # mutated from 0.25
        "risk_per_trade_usd": RISK_PER_TRADE_USD,
    }
    assert _hash_of_payload(payload) != FULL_CONFIG_HASH


def test_full_config_hash_catches_risk_per_trade_mutation():
    payload = {
        "orb_params": dataclasses.asdict(FROZEN_PARAMS),
        "instrument_point_value": MNQ.point_value,
        "instrument_tick_size": MNQ.tick_size,
        "risk_per_trade_usd": 800.0,  # mutated from 400.0
    }
    assert _hash_of_payload(payload) != FULL_CONFIG_HASH


def test_verify_params_hash_raises_when_full_config_hash_constant_is_stale(monkeypatch):
    """End-to-end guard behavior: if the MODULE's recorded FULL_CONFIG_HASH
    constant goes stale relative to FROZEN_PARAMS (simulating "someone
    edited FROZEN_PARAMS.time_stop_minutes and forgot to update
    FULL_CONFIG_HASH"), verify_params_hash() must raise ParamsHashMismatch,
    not silently pass. Uses monkeypatch on the live_config module's own
    FROZEN_PARAMS/FULL_CONFIG_HASH attributes (restored automatically at
    teardown) rather than mutating shared global state.
    """
    tampered_params = dataclasses.replace(FROZEN_PARAMS, time_stop_minutes=30)
    monkeypatch.setattr(live_config, "FROZEN_PARAMS", tampered_params)
    # PARAMS_HASH (7-field) is untouched and will still match -- only the
    # full-config guard should catch this, proving fix 2 actually adds
    # coverage the original single guard lacked.
    assert live_config.compute_params_hash() == live_config.PARAMS_HASH
    with pytest.raises(ParamsHashMismatch, match="Full-config hash mismatch"):
        live_config.verify_params_hash()


def test_verify_params_hash_raises_on_holdout_provenance_mismatch(monkeypatch):
    """Symmetric check: tampering with a field the 7-field hash DOES cover
    (e.g. target_r) must be caught by the FIRST guard, and the error message
    must name the right guard.
    """
    tampered_params = dataclasses.replace(FROZEN_PARAMS, target_r=10.0)
    monkeypatch.setattr(live_config, "FROZEN_PARAMS", tampered_params)
    with pytest.raises(ParamsHashMismatch, match="holdout-provenance hash mismatch"):
        live_config.verify_params_hash()
