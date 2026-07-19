"""Frozen-trade replay models for Tradeify Lightning 50K and MFFU Rapid 50K.

Rules were checked against the firms' official help centres on 2026-07-19.
These are economics models, not broker adapters: a result says what the dated
ORB distribution would have earned subject to the encoded rules; it does not
authorise a live order or replace each firm's current terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.strategies.replay import ReplayDay


@dataclass(frozen=True)
class ReplayFirmResult:
    """Common, deliberately small result surface for alternative firm replays."""

    net_ev: float
    trader_payouts: float
    payout_count: int
    eval_days: int
    funded_days: int
    eval_passed: bool
    funded_breached: bool

    @property
    def total_days(self) -> int:
        return self.eval_days + self.funded_days


def simulate_tradeify_lightning_50k(
    replay_days: Sequence[ReplayDay], *, risk_per_trade: float = 400.0
) -> ReplayFirmResult:
    """Replay a post-2025 Tradeify Lightning 50K account.

    Sources: official Lightning account, drawdown, DLL, pricing, and payout
    policy pages (checked 2026-07-19). The one-time $492 purchase is charged
    immediately. It is not reset after a breach: this is EV per purchased
    account, not an unlimited capital/rebuy model.
    """
    if risk_per_trade <= 0:
        raise ValueError("risk_per_trade must be positive")

    balance = 50_000.0
    floor = 48_000.0
    purchase_cost = 492.0
    payouts = 0.0
    payout_count = 0
    cycle_pnls: list[float] = []
    funded_days = 0

    for day in replay_days:
        funded_days += 1
        daily_pnl = sum(r * risk_per_trade for r in day.r_multiples)
        balance += daily_pnl
        if balance <= floor:
            return ReplayFirmResult(-purchase_cost + payouts, payouts, payout_count, 0, funded_days, True, True)

        # The drawdown is enforced intraday but moves only from completed-day
        # balances. With one ORB trade/day, the replay-day close is the only
        # observable intra-day point in this input.
        if balance >= 52_100.0:
            floor = 50_100.0
        else:
            floor = max(floor, balance - 2_000.0)
        cycle_pnls.append(daily_pnl)

        next_count = payout_count + 1
        consistency_limit = 0.20 if next_count == 1 else 0.25 if next_count == 2 else 0.30
        profit_goal = 3_000.0 if next_count == 1 else 2_000.0
        cycle_profit = sum(cycle_pnls)
        consistency_ok = cycle_profit > 0 and max(cycle_pnls, default=0.0) <= consistency_limit * cycle_profit
        if cycle_profit >= profit_goal and consistency_ok:
            cap = 2_000.0 if next_count <= 3 else 2_500.0
            gross = min(cycle_profit, cap)
            if gross >= 1_000.0:
                balance -= gross
                payouts += 0.90 * gross
                payout_count += 1
                cycle_pnls.clear()
                if balance <= floor:
                    return ReplayFirmResult(-purchase_cost + payouts, payouts, payout_count, 0, funded_days, True, True)

    return ReplayFirmResult(-purchase_cost + payouts, payouts, payout_count, 0, funded_days, True, False)


def simulate_mffu_rapid_50k(
    replay_days: Sequence[ReplayDay], *, risk_per_trade: float = 400.0
) -> ReplayFirmResult:
    """Replay MFFU Rapid 50K: eval then simulated funded stage.

    The $109 evaluation price is charged once and the $157 reset is *not*
    assumed after a failed evaluation. Funded payouts preserve the published
    $2,100 buffer and pay 90% of the amount above it. The model intentionally
    stops before a discretionary/live transition; that transition changes the
    account geometry and cannot be inferred from the sim rules.
    """
    if risk_per_trade <= 0:
        raise ValueError("risk_per_trade must be positive")

    eval_balance = 50_000.0
    eval_floor = 48_000.0
    eval_days = 0
    eval_pnls: list[float] = []
    index = 0
    for index, day in enumerate(replay_days):
        eval_days += 1
        pnl = sum(r * risk_per_trade for r in day.r_multiples)
        eval_balance += pnl
        eval_pnls.append(pnl)
        if eval_balance <= eval_floor:
            return ReplayFirmResult(-109.0, 0.0, 0, eval_days, 0, False, False)
        eval_floor = max(eval_floor, eval_balance - 2_000.0)
        total_profit = eval_balance - 50_000.0
        consistency_ok = total_profit > 0 and max(eval_pnls, default=0.0) <= 0.50 * total_profit
        if eval_days >= 2 and total_profit >= 3_000.0 and consistency_ok:
            index += 1
            break
    else:
        return ReplayFirmResult(-109.0, 0.0, 0, eval_days, 0, False, False)

    balance = 0.0
    peak = 0.0
    floor = -2_000.0
    locked = False
    payouts = 0.0
    payout_count = 0
    funded_days = 0
    for day in replay_days[index:]:
        funded_days += 1
        # MFFU Rapid trailing loss is intraday. The ORB input has a single
        # closed trade/day, so closed P&L is the conservative observable path.
        balance += sum(r * risk_per_trade for r in day.r_multiples)
        peak = max(peak, balance)
        if not locked:
            if peak >= 2_100.0:
                floor = 100.0
                locked = True
            else:
                floor = peak - 2_000.0
        if balance <= floor:
            return ReplayFirmResult(-109.0 + payouts, payouts, payout_count, eval_days, funded_days, True, True)
        if balance >= 2_600.0:
            gross = balance - 2_100.0
            payouts += 0.90 * gross
            payout_count += 1
            balance -= gross

    return ReplayFirmResult(-109.0 + payouts, payouts, payout_count, eval_days, funded_days, True, False)
