"""Reset-vs-fresh-account economics helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepNoFee50K


ResetFirm = Literal["lucidflex", "topstep"]


@dataclass(frozen=True)
class ResetDecision:
    firm: ResetFirm
    reset_cost: float
    fresh_cost: float
    net_savings_from_reset: float
    prefer_reset_before_friction: bool
    breakeven_nonprice_value: float


def lucidflex_reset_decision(
    *,
    ruleset: LucidFlex50K | None = None,
    current_eval_fee: float | None = None,
) -> ResetDecision:
    rules = ruleset or LucidFlex50K()
    fresh_cost = float(current_eval_fee if current_eval_fee is not None else rules.eval_fee)
    return _decision(
        firm="lucidflex",
        reset_cost=float(rules.reset_cost_estimate),
        fresh_cost=fresh_cost,
    )


def topstep_reset_decision(ruleset: TopStepNoFee50K | None = None) -> ResetDecision:
    rules = ruleset or TopStepNoFee50K()
    return _decision(
        firm="topstep",
        reset_cost=float(rules.nofee_reset_cost),
        fresh_cost=float(rules.nofee_monthly_fee),
    )


def _decision(*, firm: ResetFirm, reset_cost: float, fresh_cost: float) -> ResetDecision:
    net_savings = fresh_cost - reset_cost
    return ResetDecision(
        firm=firm,
        reset_cost=reset_cost,
        fresh_cost=fresh_cost,
        net_savings_from_reset=net_savings,
        prefer_reset_before_friction=net_savings > 0,
        breakeven_nonprice_value=max(0.0, reset_cost - fresh_cost),
    )
