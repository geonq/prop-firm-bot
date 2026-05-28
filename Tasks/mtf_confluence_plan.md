# Plan v2: Model A MTF Confluence — OTE TF Stack + SMC Layer

> **Status:** v1 superseded after geonq feedback 2026-05-26. v1 treated OTE as a generic H1-only confluence; the model's actual edge is **OTE zones stacking across TFs** at the same price. v2 promotes OTE to the primary scoring layer and keeps the v1 SMC features as a secondary layer.

---

## What changed from v1

| | v1 | v2 |
|--|----|-----|
| OTE check | H1 only, single feature | M1 / M3 / M5 / H1 stacked, primary edge driver |
| SMC features | Mixed in with OTE | Separated as Layer B, kept intact |
| Score ceiling | 0–10 | 0–21 |
| Default threshold | 7 | 11 |
| Comment format | `sc=N` | `sc=N A=N B=N` (layer breakdown in CSV) |

## Why OTE TF stacking is the right primary layer

Model A's edge is **price retracing into an OTE fib zone (0.618 / 0.705 / 0.786) at a key open level**. When the same price aligns with OTE on M5, M3, and M1 (and ideally H1) at the same instant, the discretionary "this is clean" read fires. v1 missed this entirely — it scored H1 EMA trend, M5 sweep, M1 wick. Those are valid SMC features but secondary to OTE alignment.

---

## Scoring v2

### Layer A — OTE TF Stack (max 14)
For each TF, compute swing-high / swing-low over the configured lookback. Calculate the 0.618 / 0.705 / 0.786 fib levels. Check whether the M15 entry price (`bestLong` / `bestShort`) sits within `oteToleranceAtr × M15_ATR` of any fib on the correct side.

| Pts | Condition |
|----:|-----------|
| +3 | M5 OTE alignment at entry price |
| +3 | M3 OTE alignment at entry price |
| +2 | M1 OTE alignment at entry price |
| +4 | H1 OTE alignment at entry price |
| +2 | 3+ TFs align (stack bonus) |

H1 gets the highest single weight because H1 retracement to the same price is rare and institutional. M5 + M3 are weighted equally because they're the intraday momentum scale closest to M15. M1 is lower because it's noisiest. The stack bonus rewards genuine multi-TF confluence over a single-TF coincidence.

### Layer B — SMC Confluence (max 7, kept from v1)

| Pts | Condition |
|----:|-----------|
| +2 | H1 EMA-50 slope agrees with setup direction |
| +2 | M5 liquidity sweep + recovery on opposing side |
| +1 | M5 FVG on entry side within 2× M5 ATR of entry |
| +1 | M1 rejection wick on entry side |
| +1 | H1 / Daily ATR ratio in [0.3, 1.8] (regime healthy) |

Dropped from v1: "H1 close in upper half of swing" — redundant with H1 OTE alignment + H1 EMA slope.

### Total: 0–21

---

## Threshold guidance

| Threshold | Profile |
|-----------|---------|
| ≥ 8  | Loose — 1 TF OTE + 2–3 SMC, or all SMC, no TF OTE |
| ≥ 11 | Moderate (default) — 2 TFs OTE + ~half SMC, or 1 TF OTE + most SMC |
| ≥ 14 | Tight — 3+ TFs OTE + stack bonus + some SMC |
| ≥ 17 | Extreme — full TF stack + nearly all SMC fires |

Sweep these thresholds against the export and pick the WR-vs-frequency-vs-Profile-4-fit elbow.

---

## TF swing lookbacks (inputs)
- M1: 60 bars (1h) — micro retracement, fast-moving
- M3: 40 bars (2h) — intraday momentum
- M5: 24 bars (2h) — OTE swing scale
- M5: 10 bars (50min) — separate, for sweep detection only
- H1: 20 bars (20h) — macro retracement context

OTE tolerance: 0.5 × M15 ATR (input, tunable). With M15 ATR ~5–8 pts, tolerance is 2.5–4 pts — same scale as the existing `alignmentPts=3.0` for key-open / fib alignment, which is the right granularity.

---

## Implementation tasks
- [x] Replace MTF inputs block (new defaults + per-TF swing lookbacks + OTE tolerance)
- [x] Extend `request.security` pulls — M1 / M3 / M5 / H1 swings + ATR; D ATR
- [x] Add `f_ote_long` / `f_ote_short` helpers
- [x] Compute Layer A (OTE) and Layer B (SMC); sum to total
- [x] Update entry comment to `sc=N A=N B=N` for per-layer debugging in CSV
- [x] Update analysis script to parse `A=` / `B=` for per-layer ablation
- [ ] Run Deep Backtest at default threshold (11) in TV; export CSV
- [ ] Sweep thresholds 8 / 11 / 14 / 17
- [ ] Compare to v1 results (488 trades / -$30k / PF 0.73)
- [ ] Per-layer ablation: which features in Layer B actually predict WR? Drop dead weight.

---

## Exit criteria
Same as v1: PF ≥ 1.0 AND MC mean EV ≥ 0 AND ≥ 60 trades over 2019–2026 at some threshold.

## Pass/pivot logic
If v2 still doesn't cross PF 1.0 at any threshold, the OTE-stack hypothesis is wrong (or the v1 score-8 result was noise). At that point: per-layer ablation reveals whether any single feature has stand-alone signal, and either trim the scoring to the predictive subset or pivot back to hard-stop execution.
