---
type: phase3 seed sensitivity audit
date: 2026-05-06
status: complete
scope: Profile 4 TopStep Consistency b2f=3 capped replay
---

# Phase 3 Seed Sensitivity

Profile 4 target cell re-run across independent seeds using the tracked
Adaptive sizing fallback: WR=0.45, R=2.0, freq=3, TopStep Consistency,
Back2Funded=3, payout_cap=5, 1000 sims per seed.

| seed | mean EV | ev_low | ev_high | p_pass | p_breach_after_pass | p_max_payout |
|-----:|--------:|-------:|--------:|-------:|---------------------:|-------------:|
| 0 | 8,505 | 8,290 | 8,719 | 0.978 | 0.253 | 0.731 |
| 101 | 8,523 | 8,308 | 8,738 | 0.980 | 0.254 | 0.731 |
| 202 | 8,513 | 8,298 | 8,729 | 0.982 | 0.260 | 0.727 |
| 303 | 8,597 | 8,382 | 8,812 | 0.983 | 0.252 | 0.735 |
| 404 | 8,577 | 8,362 | 8,792 | 0.987 | 0.259 | 0.731 |

## Read

- Mean EV range: $8,505 to $8,597.
- Lower-CI EV range: $8,290 to $8,382.
- Lower-CI spread across seeds: $92.
- All seeds keep ev_low materially positive, so the target-cell choice is
  not a single-seed artifact at this audit resolution.

## Limits

- This validates sampling stability for the selected synthetic cell only.
- It does not validate real strategy stationarity, slippage, or deferred
  news/price-limit rules.
