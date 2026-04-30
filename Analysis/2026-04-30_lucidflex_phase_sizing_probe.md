---
type: simulation result
date: 2026-04-30
author: Codex
status: first synthetic phase-aware sizing probe
ruleset: LucidFlex 50K canonical account state machine
script: Analysis/scripts/lucidflex_phase_sizing_probe.py
---

# LucidFlex Phase-Sizing Probe

## What Was Tested

This probe keeps the synthetic win-rate and R:R assumptions fixed while changing risk between evaluation and funded phases.

It now runs through the canonical `LucidFlexAccountState`, not the older separate eval/funded helper path.

The purpose is to isolate one question:

Can aggressive eval risk plus reduced funded risk improve net EV by keeping pass probability while lowering funded breach?

## Command Run

```bash
.venv/bin/python Analysis/scripts/lucidflex_phase_sizing_probe.py
```

## Results

10,000 simulations per cell. Eval horizon 90 days. Funded horizon 180 days. Placeholder cost: $5/trade.

| Case | WR | RR | Eval Risk | Funded Risk | Eval Pass | Funded Breach | Max Payouts | Avg Payouts | Avg Paid | Mean EV | Median EV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.45 | 1.50 | $250 | $250 | 48.40% | 44.34% | 4.06% | 0.75 | $490 | $315 | -$175 |
| funded_half | 0.45 | 1.50 | $250 | $125 | 48.40% | 40.51% | 4.76% | 0.88 | $439 | $264 | -$175 |
| funded_150 | 0.45 | 1.50 | $250 | $150 | 48.40% | 42.62% | 4.86% | 0.88 | $456 | $281 | -$175 |
| base | 0.50 | 1.25 | $250 | $250 | 49.07% | 43.92% | 5.15% | 0.87 | $524 | $349 | -$175 |
| funded_half | 0.50 | 1.25 | $250 | $125 | 49.07% | 38.81% | 5.74% | 0.97 | $469 | $294 | -$175 |
| funded_150 | 0.50 | 1.25 | $250 | $150 | 49.07% | 41.86% | 5.70% | 0.96 | $484 | $309 | -$175 |
| base | 0.55 | 1.00 | $250 | $250 | 41.26% | 37.57% | 3.67% | 0.70 | $396 | $221 | -$175 |
| funded_half | 0.55 | 1.00 | $250 | $125 | 41.26% | 7.18% | 0.00% | 0.00 | $0 | -$175 | -$175 |
| funded_150 | 0.55 | 1.00 | $250 | $150 | 41.26% | 10.63% | 0.00% | 0.00 | $0 | -$175 | -$175 |

## Interpretation

Lowering funded risk reduces funded breaches, but it does not automatically improve EV. In the tested cells, lower funded risk often slows payout collection enough to reduce mean EV despite better survival.

The 0.45/1.50 and 0.50/1.25 profiles still prefer funded risk near the original $250 in this simple model. That is because LucidFlex payout eligibility requires 5 days of at least $150 profit, and a much smaller funded risk can make qualifying days too slow or too rare.

The 0.55/1.00 profile shows the clearest failure mode: reducing funded risk lowers breach dramatically, but it also kills payout collection completely in the tested horizon, leaving mean EV at the lost evaluation fee.

## Practical Takeaway

Phase-aware sizing is necessary, but the optimum is not simply "risk less after passing." Funded risk must stay large enough to generate $150+ profitable days and reach payout thresholds.

The next sizing search should include payout-day constraints directly:

- eval risk controls pass/timeout/breach
- funded risk controls breach and payout velocity
- $150 minimum profitable day creates a lower bound on useful funded risk

## Next Step

Implement a small grid search over eval risk and funded risk for each WR/R:R profile:

- eval risk: $100, $150, $200, $250, $300
- funded risk: $100, $125, $150, $200, $250, $300

Rank by mean EV, median EV, funded breach rate, payout count, and max payout probability.
