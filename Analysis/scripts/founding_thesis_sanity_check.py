"""
Founding-thesis sanity check.

Reproduces (or refutes) the YouTube transcript's numerical claims about
prop firm pass rates by simulating the actual TopStep 50K Combine ruleset
under zero-EV synthetic strategies with various (win_rate, R:R) pairs.

Transcript claims being tested (Sources/2026-04-30_youtube_prop_firm_thesis.md):
  - At 4:1 RR / 20% WR (zero EV): pass rate ~37%
  - Pass rate increases monotonically as RR decreases / WR increases at zero EV
  - Low-RR / high-WR ORB-shaped strategy: pass rate ~50%
  - Quoted TopStep public 2024 pass rate: 12.4%
  - Industry data (FPFX Tech, 300K accounts): 14% pass rate

This script does NOT use the project src/ engine (Phase 1 not started yet).
It is a standalone, stdlib-only sanity check to inform Phase 3 calibration.

Run: python3 founding_thesis_sanity_check.py
"""

import random
import statistics
from dataclasses import dataclass

# TopStep 50K Combine rules used here.
# Source: Rulesets/TopStep/TopStep NoFee.md (encoded reference table)
START_BALANCE = 50_000
PROFIT_TARGET = 53_000  # +$3,000
INITIAL_MLL = 48_000    # -$2,000
MLL_LOCK = 50_000       # MLL trails up but locks at starting balance
MLL_TRAIL_DISTANCE = 2_000

# Simulation knobs
TRADES_PER_DAY = 5
MAX_DAYS = 60
N_SIMS = 20_000
LOSS_SIZE = 200.0  # dollars risked per trade (10 NQ ticks at $20/tick)

# Zero-EV (W, RR) pairs from the transcript
ZERO_EV_PAIRS = [
    (0.20, 4.00),  # transcript's high-RR / low-WR end (claimed ~37% pass)
    (0.25, 3.00),
    (0.333, 2.00),
    (0.50, 1.00),  # symmetric
    (0.667, 0.50),
    (0.80, 0.25),  # transcript's high-WR / low-RR end
]


@dataclass
class SimResult:
    passed: bool
    failed_mll: bool
    failed_consistency: bool
    timed_out: bool
    days_used: int


def simulate_one(
    win_rate: float,
    rr_ratio: float,
    rng: random.Random,
    *,
    loss_size: float,
    trades_per_day: int,
    max_days: int,
    enforce_consistency: bool,
) -> SimResult:
    """One TopStep 50K Combine attempt with a (win_rate, rr_ratio) zero-EV strategy."""
    balance = START_BALANCE
    mll = INITIAL_MLL
    daily_pnl: list[float] = []  # P&L per day, used for consistency check at pass
    win_size = rr_ratio * loss_size

    for day in range(1, max_days + 1):
        day_open_balance = balance
        for _ in range(trades_per_day):
            if rng.random() < win_rate:
                balance += win_size
            else:
                balance -= loss_size

            # Real-time MLL check (TopStep monitors intraday).
            if balance <= mll:
                return SimResult(False, True, False, False, day)

            # Did we hit the profit target intraday?
            if balance >= PROFIT_TARGET:
                if enforce_consistency:
                    day_pnl_at_pass = balance - day_open_balance
                    day_pnls_for_check = daily_pnl + [day_pnl_at_pass]
                    total_profit = balance - START_BALANCE
                    largest_day = max(day_pnls_for_check)
                    if total_profit > 0 and largest_day / total_profit > 0.50:
                        return SimResult(False, False, True, False, day)
                return SimResult(True, False, False, False, day)

        # End of day: record P&L, trail MLL on EOD highs.
        daily_pnl.append(balance - day_open_balance)
        candidate_mll = balance - MLL_TRAIL_DISTANCE
        if candidate_mll > mll:
            mll = min(candidate_mll, MLL_LOCK)

    return SimResult(False, False, False, True, max_days)


def run_pair(
    win_rate: float,
    rr_ratio: float,
    n_sims: int,
    seed: int,
    *,
    loss_size: float,
    trades_per_day: int,
    max_days: int,
    enforce_consistency: bool,
) -> dict:
    rng = random.Random(seed)
    results = [
        simulate_one(
            win_rate, rr_ratio, rng,
            loss_size=loss_size,
            trades_per_day=trades_per_day,
            max_days=max_days,
            enforce_consistency=enforce_consistency,
        )
        for _ in range(n_sims)
    ]
    n = len(results)
    n_pass = sum(r.passed for r in results)
    n_mll = sum(r.failed_mll for r in results)
    n_consistency = sum(r.failed_consistency for r in results)
    n_timeout = sum(r.timed_out for r in results)
    days_used = [r.days_used for r in results]
    pass_days = [r.days_used for r in results if r.passed]
    return {
        "win_rate": win_rate,
        "rr_ratio": rr_ratio,
        "ev_per_trade": win_rate * rr_ratio * loss_size - (1 - win_rate) * loss_size,
        "n_sims": n,
        "pass_rate": n_pass / n,
        "fail_mll_rate": n_mll / n,
        "fail_consistency_rate": n_consistency / n,
        "fail_timeout_rate": n_timeout / n,
        "median_days_to_pass": statistics.median(pass_days) if pass_days else None,
        "median_days_overall": statistics.median(days_used),
    }


def run_scenario(label: str, *, loss_size: float, trades_per_day: int,
                  max_days: int, enforce_consistency: bool) -> None:
    print()
    print("=" * 110)
    print(f"SCENARIO: {label}")
    print(f"  Loss/trade ${loss_size:.0f} ({loss_size/START_BALANCE*100:.2f}% of acct) | "
          f"Trades/day {trades_per_day} | Max days {max_days} | "
          f"Consistency rule: {'ON' if enforce_consistency else 'OFF'}")
    print("=" * 110)
    header = (
        f"{'WR':>6} {'RR':>6} {'EV/trade':>10} {'pass%':>8} "
        f"{'fail MLL%':>10} {'fail cons%':>11} {'timeout%':>10} "
        f"{'med days pass':>14} {'med days all':>14}"
    )
    print(header)
    print("-" * len(header))
    for w, _ in ZERO_EV_PAIRS:
        rr_exact = (1 - w) / w
        result = run_pair(
            w, rr_exact, N_SIMS, seed=42,
            loss_size=loss_size,
            trades_per_day=trades_per_day,
            max_days=max_days,
            enforce_consistency=enforce_consistency,
        )
        print(
            f"{w:>6.3f} {rr_exact:>6.3f} {result['ev_per_trade']:>10.3f} "
            f"{result['pass_rate']*100:>7.2f}% "
            f"{result['fail_mll_rate']*100:>9.2f}% "
            f"{result['fail_consistency_rate']*100:>10.2f}% "
            f"{result['fail_timeout_rate']*100:>9.2f}% "
            f"{(result['median_days_to_pass'] or 0):>14} "
            f"{result['median_days_overall']:>14}"
        )


def main() -> None:
    print("Founding-thesis sanity check: TopStep 50K Combine, zero-EV strategies")
    print(f"Start ${START_BALANCE:,} | Target ${PROFIT_TARGET:,} | "
          f"Initial MLL ${INITIAL_MLL:,} | Lock ${MLL_LOCK:,} | "
          f"N sims per cell: {N_SIMS:,}")

    # Scenario A: realistic baseline. 1% bet, 5 trades/day, 60-day cap, consistency ON.
    run_scenario(
        "A — realistic baseline ($200 = 1% bet, consistency ON)",
        loss_size=200.0, trades_per_day=5, max_days=60, enforce_consistency=True,
    )

    # Scenario B: drop consistency to mirror transcript's bare GBM setup.
    run_scenario(
        "B — same as A but consistency OFF (mirrors transcript's bare GBM)",
        loss_size=200.0, trades_per_day=5, max_days=60, enforce_consistency=False,
    )

    # Scenario C: small-bet high-frequency (favors high-WR / low-RR grinders).
    run_scenario(
        "C — small-bet high-frequency ($50 = 0.1% bet, 10 trades/day, 90 days, consistency OFF)",
        loss_size=50.0, trades_per_day=10, max_days=90, enforce_consistency=False,
    )

    # Scenario D: same as C but consistency ON (best realistic apples-to-apples).
    run_scenario(
        "D — small-bet high-frequency with consistency ON (most realistic)",
        loss_size=50.0, trades_per_day=10, max_days=90, enforce_consistency=True,
    )

    print()
    print("Notes:")
    print("  - Zero EV enforced by snapping RR = (1 - WR) / WR.")
    print("  - Pass = balance reaches $53,000 intraday AND (consistency holds OR rule off).")
    print("  - Fail MLL = balance dips to/below current trailing MLL intraday.")
    print("  - Fail consistency = balance reaches target but largest day > 50% of profit.")
    print("  - Timeout = neither pass nor fail within max_days.")
    print("  - Trades are i.i.d.: real strategies cluster wins/losses (ignored here).")


if __name__ == "__main__":
    main()
