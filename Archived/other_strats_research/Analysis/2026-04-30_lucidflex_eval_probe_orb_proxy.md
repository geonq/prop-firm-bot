---
type: simulation result
date: 2026-04-30
author: Codex
status: first synthetic LucidFlex eval probe
ruleset: LucidFlex 50K evaluation only
script: Analysis/scripts/lucidflex_eval_strategy_probe.py
---

# LucidFlex Eval Probe: Synthetic ORB-Like Profiles

## What Was Tested

This is not a historical ORB backtest. No NQ/MNQ price data was used. The probe tests whether ORB-like one-trade-per-day distributions can survive LucidFlex 50K evaluation mechanics:

- $50,000 starting balance
- $3,000 profit target
- $2,000 end-of-day trailing max loss limit
- MLL locks at $50,100 after the account reaches the initial trail balance
- no daily loss limit
- eval consistency modeled as largest day / total profit <= 52%, matching the documented 50% requirement plus the 50K cushion example
- 90-day max horizon for opportunity-cost comparison, even though LucidFlex has no fixed evaluation deadline

The test intentionally starts with ORB/TORB because it is a simple falsification baseline. Georg flagged that ORB is probably unprofitable; this probe agrees that ORB-like path geometry has immediate complications.

## Command Run

```bash
python3 Analysis/scripts/lucidflex_eval_strategy_probe.py
```

## Results

10,000 simulations per cell. One trade per day. Placeholder cost: $5/trade.

| WR | RR | Risk/Trade | EV/Trade | Pass | Breach | Timeout | Median Days To Pass | Median PnL |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.35 | 2.00 | $150 | $2.50 | 15.00% | 49.31% | 35.69% | 59 | -$130 |
| 0.40 | 1.50 | $150 | -$5.00 | 4.67% | 50.39% | 44.94% | 65 | -$700 |
| 0.45 | 1.25 | $150 | -$3.10 | 3.94% | 40.68% | 55.38% | 71 | -$450 |
| 0.50 | 1.00 | $150 | -$5.00 | 1.62% | 36.19% | 62.19% | 77 | -$450 |
| 0.45 | 1.50 | $150 | $13.80 | 23.58% | 21.25% | 55.17% | 64 | $1,050 |
| 0.50 | 1.25 | $150 | $13.80 | 19.26% | 14.17% | 66.57% | 65 | $1,238 |
| 0.55 | 1.00 | $150 | $10.00 | 10.54% | 12.14% | 77.32% | 73 | $750 |
| 0.45 | 1.50 | $250 | $26.20 | 48.46% | 44.82% | 6.72% | 41 | $2,050 |
| 0.50 | 1.25 | $250 | $26.20 | 49.44% | 38.52% | 12.04% | 47 | $2,925 |
| 0.55 | 1.00 | $250 | $20.00 | 41.24% | 36.36% | 22.40% | 54 | $1,550 |

## Interpretation

The first complication appears immediately: the safe-looking $150-risk profiles mostly timeout. They can survive, but they do not reach the $3,000 target fast enough within a practical 90-day horizon.

The $250-risk profiles reach the target much more often, but the pass/breach tradeoff becomes harsh. The two strongest cells pass around 48-49%, but breach around 39-45%. That can still be mathematically interesting in a convex payoff system, but only if funded-phase payout EV is large enough and real-world strategy quality survives costs, slippage, and clustering.

This supports Georg's skepticism about ORB as a standalone edge. ORB/TORB should remain the first baseline because it is easy to test and falsify, not because it is expected to be the final strategy.

## What This Does Not Prove

- It does not prove ORB is profitable.
- It does not prove the selected win rates are attainable on NQ/MNQ.
- It does not model clustered losses, bad fills, spread widening, macro news behavior, or TradingView fill assumptions.
- It does not model LucidFlex funded payouts yet.
- It does not compare to London sweep, momentum, reversal, or volatility-regime variants.

## Next Test

The next useful test is not another synthetic ORB grid. It is one of:

1. Implement the raw TORB/ORB strategy from `Analysis/strategy_specs/torb_orb_v0.md` in TradingView or Python and export real trade sequences.
2. Add a second synthetic probe for opening-hour conditional momentum/reversal, using clustered win/loss regimes instead of i.i.d. Bernoulli trades.
3. Encode the LucidFlex funded payout phase so the high-breach/high-pass eval profiles can be scored on net EV, not pass rate alone.

The most rigorous sequence is: finish LucidFlex eval/funded rules, then test the real ORB/TORB export through the full pipeline.
