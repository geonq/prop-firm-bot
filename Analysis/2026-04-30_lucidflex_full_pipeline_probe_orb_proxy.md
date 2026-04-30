---
type: simulation result
date: 2026-04-30
author: Codex
status: first synthetic full-pipeline LucidFlex probe
ruleset: LucidFlex 50K eval plus funded payout scaffold
script: Analysis/scripts/lucidflex_pipeline_strategy_probe.py
---

# LucidFlex Full-Pipeline Probe: Synthetic ORB-Like Profiles

## What Was Tested

This is still not a historical ORB backtest. It is a full account-pipeline probe using synthetic one-trade-per-day win/loss distributions.

The pipeline now covers:

- eval fee
- LucidFlex 50K evaluation pass, breach, or timeout
- funded account start after eval pass
- funded trading with the same synthetic trade distribution
- 5 profitable-day payout eligibility
- 50% of simulated profit payout request, capped at $2,000
- 90/10 trader split
- max 5 simulated payouts
- funded breach and funded timeout

The purpose is to test whether ORB-like path geometry can create positive account EV once funded payouts are included.

## Command Run

```bash
.venv/bin/python Analysis/scripts/lucidflex_pipeline_strategy_probe.py
```

## Results

10,000 simulations per cell. One trade per day. Eval horizon 90 days. Funded horizon 180 days. Placeholder cost: $5/trade.

| WR | RR | Risk/Trade | EV/Trade | Eval Pass | Funded Breach | Max Payouts | Avg Payout Count | Avg Trader Paid | Mean Net EV | Median Net EV |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.35 | 2.00 | $150 | $2.50 | 16.21% | 15.40% | 0.69% | 0.19 | $106 | -$69 | -$175 |
| 0.40 | 1.50 | $150 | -$5.00 | 5.39% | 5.20% | 0.10% | 0.05 | $23 | -$152 | -$175 |
| 0.45 | 1.25 | $150 | -$3.10 | 3.88% | 3.62% | 0.11% | 0.04 | $20 | -$155 | -$175 |
| 0.50 | 1.00 | $150 | -$5.00 | 1.55% | 1.01% | 0.00% | 0.00 | $0 | -$175 | -$175 |
| 0.45 | 1.50 | $150 | $13.80 | 23.56% | 20.76% | 2.37% | 0.42 | $221 | $46 | -$175 |
| 0.50 | 1.25 | $150 | $13.80 | 19.98% | 17.00% | 2.41% | 0.40 | $200 | $25 | -$175 |
| 0.55 | 1.00 | $150 | $10.00 | 11.01% | 2.83% | 0.00% | 0.00 | $0 | -$175 | -$175 |
| 0.45 | 1.50 | $250 | $26.20 | 48.31% | 44.08% | 4.23% | 0.77 | $507 | $332 | -$175 |
| 0.50 | 1.25 | $250 | $26.20 | 50.14% | 45.02% | 5.12% | 0.86 | $520 | $345 | -$175 |
| 0.55 | 1.00 | $250 | $20.00 | 42.17% | 38.37% | 3.79% | 0.71 | $400 | $225 | -$175 |

## Interpretation

Including funded payouts changes the story from "pass rate only" to "lottery-like payout distribution."

The strongest synthetic profiles now show positive mean net EV:

- 0.50 WR / 1.25 RR / $250 risk: mean EV about $345
- 0.45 WR / 1.50 RR / $250 risk: mean EV about $332
- 0.55 WR / 1.00 RR / $250 risk: mean EV about $225

But every tested profile has median EV of `-$175`, meaning the typical attempt still loses the evaluation fee. The positive mean comes from the right tail: a minority of attempts pass eval, survive funded long enough, and collect payouts.

That is exactly the asymmetric-payoff thesis, but it is not proof of a real edge. The assumed trade distribution must be historically validated. If real ORB cannot produce the assumed WR/RR/cost profile after slippage and clustering, the positive mean EV disappears.

## Practical Takeaway

The project should not optimize for "highest pass rate" alone. A high pass-rate profile can still have poor payout behavior, and a lower pass-rate profile can have better mean EV if it reaches funded payouts more efficiently.

However, the median-loss result is a serious deployment warning. This kind of system would require:

- many independent attempts or accounts
- strict fee budgeting
- confidence that the real strategy distribution matches the synthetic assumption
- phase-aware sizing to reduce funded breach after eval pass

## Next Step

Add phase-aware sizing before interpreting the strategy family:

- eval risk can be higher to clear target
- funded risk probably needs to drop after passing
- payout-cycle state should affect sizing

Then rerun this same full-pipeline probe with `PhaseSizing(eval_loss_size, funded_loss_size)` or an equivalent strategy wrapper.
