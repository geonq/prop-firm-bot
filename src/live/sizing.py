"""Pure position-sizing math for the live MNQ runner.

Deliberately separate from the backtest, which works entirely in R-multiples
and never converts risk into contracts (see src/optimizer/walk_forward.py
DEFAULT_RISK_PER_TRADE_USD docstring — the backtest/replay-MC pipeline feeds
a fixed dollar risk straight into the prop-firm account simulators without
ever quantizing to whole contracts). Live trading has no fractional
contracts, so this module exists to do that quantization for the paper/live
runner only. Known model gap (documented, Tasks/todo.md "Known gaps to
carry"): live MNQ P&L will not exactly equal risk_per_trade_usd * r_multiple
because of this floor.
"""

from __future__ import annotations

import math


def contracts_for(
    stop_points: float,
    *,
    risk_per_trade_usd: float,
    point_value: float,
    max_contracts: int,
) -> int:
    """Number of whole contracts such that stop_points * point_value * contracts <= risk budget.

    Returns 0 if a single contract's risk already exceeds the budget (the
    caller must skip the trade in that case — this function never rounds up
    past the risk budget). Result is clamped to `max_contracts` regardless of
    how much the risk budget would otherwise allow (fat-finger / tamper
    guard, not a strategy parameter).

    `stop_points` must be a positive finite distance from entry to stop, in
    the same point units as `point_value` (e.g. NQ/MNQ index points).
    """
    if not math.isfinite(stop_points) or stop_points <= 0:
        raise ValueError(f"stop_points must be positive and finite, got {stop_points!r}")
    if risk_per_trade_usd <= 0:
        raise ValueError(f"risk_per_trade_usd must be positive, got {risk_per_trade_usd!r}")
    if point_value <= 0:
        raise ValueError(f"point_value must be positive, got {point_value!r}")
    if max_contracts <= 0:
        raise ValueError(f"max_contracts must be positive, got {max_contracts!r}")

    risk_per_contract = stop_points * point_value
    contracts = math.floor(risk_per_trade_usd / risk_per_contract)
    return max(0, min(contracts, max_contracts))
