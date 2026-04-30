---
type: data quality note
date: 2026-05-01
status: first pass complete
scope: Databento GLBX.MDP3 MBP-10, MNQ.FUT sample
---

# Databento MBP-10 Quality Check

## Bottom Line

The downloaded Databento file is usable for the first L2/order-book thesis pass.
It contains a dense, readable MNQ top-10 book for the requested RTH window and
supports best bid/ask, spread, depth-at-level, depth imbalance, trade counts,
trade volume, and forward-return alignment at 1/5/15/60 seconds.

This is not a strategy signal validation yet. One session is enough to prove the
schema and feature path, not robustness.

## File Checked

- Job: `GLBX-20260430-DVSGY84WKT`
- File: `TVExports/l2_sample/GLBX-20260430-DVSGY84WKT/glbx-mdp3-20260427.mbp-10.dbn.zst`
- Dataset/schema: `GLBX.MDP3` / `mbp-10`
- Request: `MNQ.FUT`, parent symbol, `stype_out=instrument_id`
- Window: `2026-04-27 13:30:00Z` to `20:00:00Z`

## Instrument Selection

The parent symbol resolved to multiple contracts/spreads. Use `MNQM6` for this
sample; it dominates the file and is the active outright.

| Symbol | Records |
|---|---:|
| `MNQM6` | 21,003,475 |
| `MNQU6` | 1,022,839 |
| `MNQM6-MNQU6` | 27,596 |
| `MNQZ6` | 19,435 |
| `MNQM7` | 531 |
| `MNQH7` | 505 |

## Content Sanity

- MNQM6 event coverage: `2026-04-27 13:29:59.999939187Z` to `19:59:59.999772145Z`
- MNQM6 actions: `A=9,735,343`, `C=9,348,427`, `M=1,372,686`, `T=547,019`
- Invalid/crossed spread records after quote check: `67` out of `21,003,475`
- One-second rows generated: `23,401`
- Seconds with events: `23,397`
- Median events per active second: `677`
- Median spread: `0.25`; max spread: `1.00`
- Trade records: `547,018`; trade volume: `1,093,843`

## Derived Feature Proof

The extraction generated:

- mid price and spread
- event, trade, and trade-volume counts per second
- bid/ask depth at levels `1`, `3`, `5`, and `10`
- normalized depth imbalance at levels `1`, `3`, `5`, and `10`
- rolling depth-pressure proxies at `5`, `15`, and `60` seconds
- forward mid-price changes at `1`, `5`, `15`, and `60` seconds

Derived feature CSV:

`TVExports/l2_sample/GLBX-20260430-DVSGY84WKT/derived/mnqm6_1s_l2_features.csv`

Depth medians and imbalance ranges looked sane after casting unsigned size
fields before subtraction:

| Depth | Median Bid | Median Ask | Imbalance Range |
|---|---:|---:|---:|
| L1 | 6 | 6 | `-0.9444` to `0.9649` |
| L3 | 34 | 34 | `-0.7458` to `0.9097` |
| L5 | 67 | 67 | `-0.6658` to `0.8056` |
| L10 | 161 | 162 | `-0.6276` to `0.6909` |

## First Forward-Return Alignment

Simple one-session correlations between last-per-second depth imbalance and
forward mid-price change are small, which is expected at this stage.

| Horizon | L1 | L3 | L5 | L10 |
|---|---:|---:|---:|---:|
| 1s | `0.0334` | `0.0138` | `0.0112` | `0.0108` |
| 5s | `0.0045` | `-0.0091` | `-0.0068` | `0.0055` |
| 15s | `0.0110` | `-0.0109` | `-0.0163` | `0.0003` |
| 60s | `0.0052` | `-0.0149` | `-0.0040` | `0.0254` |

Forward mid-price changes are nonzero on most seconds:

| Horizon | Std Dev | Nonzero Seconds |
|---|---:|---:|
| 1s | `1.1343` | `91.99%` |
| 5s | `2.5352` | `96.91%` |
| 15s | `4.2211` | `98.04%` |
| 60s | `8.1379` | `99.11%` |

Rolling depth-pressure proxy correlations are also computable. In this first
single-day pass they are still small-to-moderate and not strategy-grade:

| Horizon | L1 | L3 | L5 | L10 |
|---|---:|---:|---:|---:|
| 5s | `-0.0231` | `-0.0168` | `-0.0071` | `-0.0005` |
| 15s | `-0.0136` | `-0.0158` | `-0.0313` | `-0.0370` |
| 60s | `-0.0477` | `-0.1073` | `-0.0691` | `-0.1043` |

## Practical Issues

- Parent-symbol data must be filtered to the active outright (`MNQM6` here);
  otherwise spreads and deferred contracts contaminate features.
- The raw compressed file is large enough that all future ingestion should use
  chunked reads.
- MBP-10 gives top-10 book snapshots/updates, but not full order identity. Use
  MBO later only if queue-position/order-identity features become necessary.
- Trade side labels exist, but buy/sell aggressor interpretation should be
  confirmed against Databento schema docs before using signed trade flow as a
  thesis variable.
- This one-day sample proves data viability, not signal stability. The next
  empirical step needs multiple sessions and regime buckets.
