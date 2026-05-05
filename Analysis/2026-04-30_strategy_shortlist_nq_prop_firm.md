---
type: retired strategy shortlist
date: 2026-04-30
compressed: 2026-05-05
status: superseded by L2/order-flow track
---

# NQ/MNQ Strategy Shortlist — Compact State

The original long shortlist was removed for token discipline. Its main outcome
was not a strategy to build; it was a warning that Level-1 ORB-style strategies
are likely too blunt for this project.

## Settled Points

- ORB/TORB is rejected as a candidate strategy by Georg.
- ORB-like probes remain only falsification baselines for simulator behavior.
- The optimal prop-firm risk geometry is expected to sit around the middle
  rather than extreme high-R:R or extreme high-WR grinding.
- Strategy selection must start from measurable variables that can survive
  train/holdout and prop-firm path simulation.

## Current Candidate Track

Priority is L2/order-flow first:

- Databento GLBX.MDP3 MBP-10 for MNQ/NQ order-book features
- static depth imbalance
- rolling depth pressure
- spread/time-of-day filters
- session-normalized train/holdout event studies
- later: regime filters and prop-firm replay only if raw signal survives

Options-flow remains parked until paid OPRA/ThetaData-style data is justified.

## Pointers

- Current result: `Analysis/2026-05-05_l2_event_study.md`
- L2 batch report: `Analysis/scripts/databento_mbp10_batch_report.py`
- Event study: `Analysis/scripts/databento_l2_event_study.py`
- Dashboard: `Dashboard/app.py`
