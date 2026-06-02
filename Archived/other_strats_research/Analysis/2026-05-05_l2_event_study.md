---
type: l2 event study
date: 2026-05-05
status: cheap context pass complete; no strict promotion
scope: Databento GLBX.MDP3 MBP-10, MNQM6 RTH 1-second features
---

# L2 Event Study

## Bottom Line

Do not write standalone L2-pressure strategy logic from this batch. Raw L2
pressure failed the earlier forward-return and target-before-stop gates.
Adding realized-volatility shape improved the target-only screen, especially
`close|tight|vol_contracting`, but zero rows survived the stricter promotion
gate once session-level target-before-stop stability was required. Adding VWAP
distance/slope context, including explicit 2nd and 3rd standard-deviation
bands, also produced no strict promotion. Prior RTH return and current session
gap context produced no target-only candidates.

## Setup

- Input: `Analysis/output/mbp10_batch/derived/*_1s.csv`
- Script: `Analysis/scripts/databento_l2_event_study.py`
- Duplicate-date handling: skipped one duplicate `20260427` file
- Spread filter: `spread <= 0.5`
- Rows after filter: `113,357`
- Train dates: `20260423`, `20260424`, `20260427`
- Holdout dates: `20260428`, `20260429`
- Third-pass outputs:
  - `Analysis/output/l2_event_study/session_coefficients.csv`
  - `Analysis/output/l2_event_study/bootstrap_intervals.csv`
  - `Analysis/output/l2_event_study/target_stop_events.csv`
  - `Analysis/output/l2_event_study/regime_target_stop_events.csv`
  - `Analysis/output/l2_event_study/regime_session_target_stop_events.csv`
- Cost-aware label: bid/ask approximated from mid/spread, target `2.0` points,
  stop `2.0` points.
- Regime filters tested: open/midday/close UTC buckets, tight/wide spread,
  rolling 60s realized-volatility buckets, realized-vol shape
  (`vol_contracting`, `vol_neutral`, `vol_expanding`), realized-vol slope,
  anchored session VWAP bands (`inside_1sd`, `above/below_1sd`,
  `above/below_2sd`, `above/below_3sd`), VWAP slope, and combined
  time|spread context buckets.
- Prior-session context tested: previous sampled RTH return sign and current
  session open gap sign, both standalone and combined with time|spread.

## Key Results

| Feature | Horizon | Side | Train hit | Holdout hit | Train mean | Holdout mean |
|---|---:|---|---:|---:|---:|---:|
| `depth_pressure_l10_60s` | 60s | long | 47.5% | 54.5% | -0.64 | +1.25 |
| `imbalance_l1_last` | 60s | long | 51.2% | 51.9% | +0.25 | +0.55 |
| `imbalance_l1_last` | 15s | long | 50.5% | 51.7% | +0.07 | +0.24 |
| `depth_pressure_l10_60s` | 60s | short | 48.2% | 47.4% | +0.28 | +0.57 |

Bootstrap on the best holdout forward-return rule looked superficially strong:
`depth_pressure_l10_60s` 60s-long had 95% bootstrap hit-rate interval
`52.9-55.9%` and mean directional move interval `+0.94` to `+1.57` points. This
does not override the train sign failure or the target-before-stop failure.

Top holdout target-before-stop labels all failed after spread approximation:

| Feature | Horizon | Side | Target rate | Stop rate |
|---|---:|---|---:|---:|
| `imbalance_l1_last` | 60s | long | 46.3% | 53.6% |
| `depth_pressure_l1_60s` | 60s | long | 45.1% | 54.8% |
| `depth_pressure_l10_60s` | 60s | long | 43.4% | 56.5% |

Regime-filtered target-before-stop also failed the promotion gate. Best holdout
cells were:

| Regime | Feature | Side | Holdout target | Train target |
|---|---|---|---:|---:|
| close / tight / low-vol | `imbalance_l10_last` | long | 56.2% | 47.1% |
| close / tight / low-vol | `depth_pressure_l10_15s` | long | 54.7% | 45.0% |
| close / wide / high-vol | `depth_pressure_l10_60s` | long | 52.1% | 39.0% |

No tested time/spread/60s-vol regime had both train and holdout
target-before-stop above 50%.

Realized-vol shape created target-only candidates, but none passed the full
gate with per-session stability:

| Regime | Feature | Side | Train target | Holdout target | Failure |
|---|---|---|---:|---:|---|
| close / tight / vol-contracting | `depth_pressure_l10_60s` | long | 61.5% | 60.0% | holdout occurred in only 1 session |
| close / tight / vol-contracting | `imbalance_l10_last` | long | 60.7% | 59.2% | one holdout session was 0% target-before-stop |
| close / tight / vol-contracting | `depth_pressure_l10_15s` | long | 60.4% | 58.8% | one train and one holdout session failed |
| midday / tight / vol-neutral | `depth_pressure_l10_60s` | long | 50.6% | 51.1% | train/holdout session minima below 50% |

VWAP bands were tested because Georg flagged the 2nd and 3rd standard deviations
as sensitive. The 2sd zones were observable; the 3sd zones were not broad enough
in this five-session sample:

| VWAP zone | Train rows | Holdout rows |
|---|---:|---:|
| above 2sd | 8,744 | 1,307 |
| below 2sd | 2,017 | 555 |
| above 3sd | 1 | 0 |
| below 3sd | 172 | 0 |

VWAP target-only candidates also failed the strict gate:

| Regime | Feature | Side | Train target | Holdout target | Failure |
|---|---|---|---:|---:|---|
| open / wide / above 1sd | `imbalance_l10_last` | long | 50.5% | 50.6% | train and holdout session minima below 50% |
| VWAP above 2sd | `depth_pressure_l10_60s` | long | 45.9% | 58.1% | train failed despite strong holdout |
| midday / tight / above 2sd | `depth_pressure_l10_15s` | long | 48.6% | 61.8% | train failed and holdout had only one session |

Prior RTH and current-session gap context did not help. Across 336 prior/gap
regime pairs, strict passes were `0` and target-only passes were also `0`.
Best-looking holdout rows still failed in train and usually had only one train
session in the regime.

## Interpretation

The L1 imbalance cells are more directionally consistent but too weak after
spread/slippage to carry a prop-firm strategy. The 60-second depth-pressure cells
are larger but sign-unstable across train and holdout. Time buckets also change
sign, with `depth_pressure_l10_60s` ranging from about `-0.095` to `+0.149`
correlation by 30-minute UTC bucket.

Decision: raw L2 pressure stays demoted from standalone alpha. Realized-vol
shape and VWAP 2sd bands are useful context clues, but this five-session sample
is not stable enough for strategy logic. The 3sd VWAP bands need more sessions
before they can be judged. Prior RTH/gap context does not rescue the signal.

## Next

Next research should either add more MNQ sessions if 3sd VWAP behavior is worth
measuring, or park raw L2 pressure and move to paid IV/options-flow context. A
rule only graduates if it survives session-level sign checks and cost-aware
target-before-stop labeling.
