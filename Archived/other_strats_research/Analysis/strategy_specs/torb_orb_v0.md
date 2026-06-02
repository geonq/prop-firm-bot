---
type: retired strategy spec
date: 2026-04-30
compressed: 2026-05-05
status: rejected as candidate; keep only as falsification baseline
---

# TORB / ORB V0 — Retired Baseline

Georg explicitly rejected ORB/TORB as a strategy candidate. Do not spend new
work implementing or optimizing it. The prior long implementation contract was
removed for token discipline.

## Why This File Remains

The ORB/TORB idea is still useful as a known-weak baseline for simulator sanity:

- low-risk ORB-like synthetic profiles tend to timeout
- higher-risk ORB-like profiles can pass more often but breach too often
- it helps confirm the account simulator handles target, timeout, consistency,
  and drawdown dynamics

## Do Not Do

- Do not propose ORB/TORB as the next strategy.
- Do not replace it with another Level-1 OHLCV-only strategy by default.
- Do not use this file as an implementation source.

## Current Direction

Use the L2/order-flow track first. See:

- `Analysis/2026-05-05_l2_event_study.md`
- `Analysis/scripts/databento_l2_event_study.py`
- `Dashboard/app.py`
