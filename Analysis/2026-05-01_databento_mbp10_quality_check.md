---
type: data quality note
date: 2026-05-01
compressed: 2026-05-05
status: first pass complete; superseded by batch/event study
---

# Databento MBP-10 Quality Check — Compact

## Bottom Line

The first Databento GLBX.MDP3 `MBP-10` file was usable for L2/order-book
research. It proved that the pipeline can read MNQ top-10 book data, filter the
active outright, derive 1-second features, and align forward returns.

## Checked File

- Job: `GLBX-20260430-DVSGY84WKT`
- Window: `2026-04-27 13:30:00Z` to `20:00:00Z`
- Active symbol: `MNQM6`
- MNQM6 records: `21,003,475`
- Seconds generated: `23,401`
- Seconds with events: `23,397`
- Median active-second events: `677`
- Median spread: `0.25`
- Trade records: `547,018`

## Derived Features Proven

- mid price and spread
- event/trade/trade-volume counts
- bid/ask depth at levels `1`, `3`, `5`, `10`
- normalized depth imbalance
- rolling depth pressure at `5`, `15`, `60` seconds
- forward mid-price change at `1`, `5`, `15`, `60` seconds

## Practical Notes

- Parent-symbol requests include deferred contracts/spreads; always filter to
  active outright (`MNQM6` for this sample).
- Use chunked reads for raw DBN files.
- MBP-10 is enough for first L2 tests; use MBO only if order identity/queue
  features become necessary.
- This one-day check proved data viability only. Current signal state is in
  `Analysis/2026-05-05_l2_event_study.md`.
