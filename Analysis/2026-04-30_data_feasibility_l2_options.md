---
type: data feasibility note
date: 2026-04-30
compressed: 2026-05-05
status: compact decisions only
---

# L2 / Options / IV Data Feasibility — Compact

## Decision

TradingView OHLCV is not enough for the desired edge search. Use Databento
GLBX.MDP3 `MBP-10` as the first repeatable NQ/MNQ L2 backend. Options-flow is
parked until paid OPRA/ThetaData-style data is justified.

## Data Source Conclusions

- **Databento GLBX.MDP3:** first choice for repeatable CME L2 research. Start
  with `MBP-10`; use `MBO` only if queue/order identity becomes necessary.
- **Sierra Chart Denali:** budget/manual fallback; historical depth exists, but
  export likely needs ACSIL/custom extraction.
- **ThetaData Options Standard:** first realistic retail NDX/QQQ options-flow
  candidate if options-flow becomes worth paying for.
- **Polygon/Massive options:** possible aggregate fallback, weaker for tick-flow
  reconstruction.
- **Nasdaq VOLQ / Cboe VIX-style methodology:** useful IV/RV regime framing, but
  data licensing matters.
- **Bookmap/dxFeed/Rithmic:** useful for visual/live validation, not primary
  historical backend unless export/API is confirmed.
- **Kibot / unavailable TickTradingData:** not enough for current L2 thesis.

## Test Requirements

L2/order-flow:
- active NQ/MNQ outright only
- best bid/ask, spread, depth at levels 1/3/5/10
- normalized imbalance and rolling depth pressure
- forward returns at 1/5/15/60s
- falsify if relation is unstable after spread/slippage or too short to trade

Options-flow:
- QQQ/NDX trades with NBBO, chain snapshots, OI, IV/Greeks or enough data to
  compute them
- falsify if aggressor direction cannot be inferred or signal appears after NQ

IV/RV:
- realized NQ volatility, IV proxy, IV-RV spread, and prop-firm outcome buckets
- falsify if regime buckets do not change forward distribution or breach odds

## Current State

Databento sample and batch ingestion succeeded. See:

- `Analysis/2026-05-01_databento_mbp10_quality_check.md`
- `Analysis/2026-05-05_l2_event_study.md`
