---
type: target cell catalog (Phase 3.5 step 2)
date: 2026-05-06
status: catalog full run done; named profiles selected; downstream is reset/vault economics decision sheet
scope: 5940-row Monte Carlo sweep of (firm × payout_path × WR × R × freq × sizing × variant)
inputs:
  - Analysis/output/target_cell_catalog/cells.csv
  - Analysis/output/target_cell_catalog/manifest.json
  - Analysis/scripts/target_cell_catalog.py
---

# Target-Cell Catalog

## Bottom Line

Strategy research must hit one of five named profiles below. Anything outside
them is either trivially saturated against the 5-payout cap (no information) or
sits in the noisy edge where mean EV is positive but lower-CI is negative —
i.e. not a real edge once eval/reset fees compound across simulated reps.

The 5-payout-capped engine produces a **structural ceiling** of ~$8.9k for
LucidFlex and TopStep Standard and ~$13.4k for TopStep Consistency. Picking a
firm is therefore a function of the cell, not of overall "best firm". Consistency
has the higher ceiling; Standard wins more cells per WR/R combo at the marginal
frontier.

`BufferAware` sizing is dominated under capped rules: it adds drawdown
protection that rarely matters when the simulation terminates after five
payouts. `Adaptive` and `Fixed` split wins ~50/50 on LucidFlex/TopStep Standard;
`Adaptive` clearly wins on TopStep Consistency (187 vs 140 of 334 non-saturated
cells).

## Run Provenance

- Mode: `full` (manifest verified).
- Rows: 5940 (1188 base × 5: Fixed/BufferAware/Adaptive iid + autocorrelated/regime-switching Fixed).
- Sims per cell: 1000.
- Wall time: 6691 s (~1.86 h, single core).
- Git SHA: `92d4521`.
- Payout cap: 5 (TopStep capped to match LucidFlex's natural 5-payout terminal).
- Adaptive search: 18 combinations per cell (3×3×1×1×2).
- All EV figures are **net of eval/reset fees** as encoded in the per-firm rule
  modules; LucidFlex vault discount cycles are not yet modeled (handled in
  step 3).

## Aggregate Stats

`ev_low` distribution across the 1188 sizing-study cells per firm:

| Firm | p10 | median | p90 | max |
|---|---:|---:|---:|---:|
| lucidflex            | -98 |  525 |  8897 |  8902 |
| topstep_standard     | -95 |  400 |  8900 |  8905 |
| topstep_consistency  | -95 |  431 | 13203 | 13405 |

- **655–659 of 1188 cells** are robustly EV-positive (`ev_low > 0`) per firm —
  ~55% across all three. Almost identical pass-rates → the marginal frontier
  is firm-agnostic; the **ceiling** is what differs.
- 245–305 cells per firm hit the 5-payout cap (`p_max_payout ≥ 0.99`). Within
  that zone every (sizing, WR, R, freq) combo ties — ranking has no signal.

## Cross-Firm Cell Winners

For each WR/R/freq cell, holding sizing=Fixed iid: which firm produces the
highest `ev_low`?

| Winning firm | Cells won (of 396) |
|---|---:|
| topstep_standard    | 200 |
| topstep_consistency | 128 |
| lucidflex           |  68 |

TopStep Standard wins half the marginal frontier. LucidFlex loses per-cell
despite an identical capped ceiling — its eval fee + reset cycle is more
punitive in expectancy than TopStep's XFA at lower WR/R. Consistency wins
fewer cells but has the highest ceiling once you survive its tighter rules.

## Sizing Study

Best sizing per WR/R/freq cell, **excluding saturated cells** (where all
sizings tie at the cap):

| Firm | Fixed | BufferAware | Adaptive | non-sat cells |
|---|---:|---:|---:|---:|
| lucidflex            | 153 | 7 | 159 | 319 |
| topstep_standard     | 154 | 8 | 154 | 316 |
| topstep_consistency  | 140 | 7 | 187 | 334 |

`BufferAware` is dominated everywhere — it gates new size by remaining
buffer, which barely matters when the engine stops after 5 payouts.
**Recommendation:** drop BufferAware from downstream search unless
uncapped/long-horizon TopStep simulations are revisited. Adaptive's
edge is real but firm-specific (Consistency).

## Non-i.i.d. Sensitivity

Median `ev_low` degradation vs i.i.d. Fixed (per WR/R/freq cell, n=396 each):

| Firm | autocorr median Δ | autocorr max Δ | regime median Δ | regime max Δ | pos→neg flips |
|---|---:|---:|---:|---:|---:|
| lucidflex            | 43 | 2731 |  0 | 348 | 0 |
| topstep_standard     | 27 | 2808 |  0 | 213 | 1 |
| topstep_consistency  |  4 | 3172 |  0 | 454 | 2 |

- **Autocorrelation (ρ=0.3)** costs $0–43 in the median cell but up to
  ~$3.2k in worst-case cells. Worst hits are concentrated at WR=0.40–0.50 ×
  R=1.5–3.0 × freq=10. Daily turnover with marginal WR is the failure mode.
- **Regime-switching** (per-trade mixture, not persistent regime — see
  `target_cell_catalog.py` docstring) has near-zero median impact and at
  most a couple positive→negative flips per firm. The catalog is robust to
  per-trade WR uncertainty of ±0.10.
- Strategy research should treat **autocorrelation as the binding non-iid
  stress**, not regime-switching. Specifically: a strategy targeting
  freq=10 must have its per-day trade clustering measured and held ≤ ρ=0.3
  for the catalog ranking to apply.

## Noisy Edge

Cells that are mean-EV-positive but `ev_low ≤ 0` (i.e. a strategy with these
parameters loses the eval fee in one simulation lane often enough that the
95% CI lower bound is negative). 9–10 cells per firm sit here. Common
attractors:

- WR=0.40 R=1.5 freq=5–10 (mean +$20–66, ev_low –$10 to –$30, p_pass 15–25%, p_breach_after_pass 95–100%)
- WR=0.50 R=1.0 freq=5–10 (mean +$15–45, ev_low –$10 to –$25)

Strategy research must **not** target these — they are the obvious traps
where in-sample mean looks fine but the lower CI is below zero.

## Named Profiles for Strategy Research

Each profile has ≥ $1.5k `ev_low` on at least one firm under sizing=Adaptive
*and* survives the autocorrelation stress test (max Δ in our data ≤ 30% of
the headline ev_low). Pick a target before strategy research begins, then
verify the candidate strategy lands inside the named cell.

| # | Profile             | WR   | R    | freq | Sizing   | Best firm           | mean EV | ev_low | p_pass |
|---|---------------------|-----:|-----:|-----:|----------|---------------------|--------:|-------:|-------:|
| 1 | Patient swing       | 0.40 | 2.50 |    1 | Adaptive | lucidflex           |   2877  |  2683  |  0.85  |
| 2 | Low-WR breakout     | 0.30 | 3.00 |    5 | Adaptive | topstep_consistency |   2934  |  2620  |  0.70  |
| 3 | Balanced edge       | 0.50 | 1.50 |    3 | Adaptive | topstep_consistency |   4675  |  4442  |  0.96  |
| 4 | Robust trend        | 0.45 | 2.00 |    3 | Adaptive | topstep_consistency |   7326  |  7042  |  0.99  |
| 5 | High-WR scalp       | 0.65 | 0.75 |    3 | Fixed    | lucidflex           |   3133  |  2936  |  0.84  |

Profile selection rationale:

1. **Patient swing** — once-per-day asymmetric R. Lowest operational
   complexity; widest range of strategies likely to land here.
2. **Low-WR breakout** — designed for momentum/breakout strategies that
   catch the right tail. WR=0.30 means 7-of-10 trades lose; the R=3 must
   be real and not a backtest artifact.
3. **Balanced edge** — closest to "median trader" expectation;
   useful as a sanity check for any strategy claim.
4. **Robust trend** — best ev_low to mean ratio at moderate freq. The
   profile to aim for if a TSMOM-style or opening-hour-momentum candidate
   shows realistic numbers.
5. **High-WR scalp** — only profile where Fixed sizing wins on lucidflex
   and is competitive elsewhere. Useful sanity check that mean-reversion
   ideas can land here, not a recommendation to pursue.

Profile 4 (Robust trend) is the **primary research target** because its
lower-CI EV exceeds reset/vault costs by a factor of 5–10× and its
autocorrelation degradation is moderate.

## What This Doesn't Cover

- Reset/vault economics (LucidFlex vault discount cycles, TopStep DLL toggle,
  Back2Funded reactivations beyond default 0). Handled in Phase 3.5 step 3 via
  `src/optimizer/reset_economics.py` + `src/data/lucidflex_vault.py` per
  candidate cell.
- Uncapped TopStep horizon — the 5-payout cap was chosen for fair cross-firm
  comparison; TopStep's true ceiling is higher and worth a sensitivity pass
  before strategy research locks a profile.
- Sizing × non-iid combinations: BufferAware/Adaptive are only run i.i.d.
  because the autocorrelated/regime strategies hardcode loss sizes per
  phase. A future refactor could lift `sizing_fn` into them; not blocking.
- News embargo / CME price-limit proximity rules (audit-flagged, deferred).

## Next

1. Run `src/optimizer/reset_economics.py` and `src/data/lucidflex_vault.py`
   for each of the 5 named profiles to produce a per-firm reset/vault decision
   sheet (Phase 3.5 step 3).
2. Re-rank profiles after vault discounts and reset costs are netted.
3. Begin strategy research scoped to the post-step-3 winning profile.
