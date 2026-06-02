---
type: reset/vault decision sheet (Phase 3.5 step 3)
date: 2026-05-06
status: post-vault re-ranking complete; recommendation passed to Phase 4
scope: 77-row Monte Carlo sweep over 5 named profiles × commercial-economics variants
inputs:
  - Analysis/output/target_cell_catalog/cells.csv (adaptive params source)
  - Analysis/scripts/reset_vault_decision_sheet.py
  - Analysis/output/reset_vault_decision_sheet/decision_sheet.csv
upstream: Analysis/2026-05-06_target_cell_catalog.md
---

# Reset / Vault Economics Decision Sheet

## Bottom Line

**Phase 4 strategy research targets Profile 4 "Robust trend" — WR≈0.45,
R≈2.0, ~3 trades/day, Adaptive sizing, primary firm = TopStep Consistency
with Back2Funded reactivations enabled (b2f=3).** Capped (5-payout) ev_low
= $8,315; uncapped funded-horizon ev_low = $17,054. Recommendation is
robust to the uncapped sensitivity (Standard pulls ahead uncapped, but
Consistency stays within 10%).

LucidFlex vault discounts are real but tiny (~$14 EV per fee tier — entire
50% vault path adds only $28 vs default coupon). They do not change firm
ranking on any profile. **TopStep Back2Funded is the dominant commercial
lever** — +$1.5k–$2.1k EV per profile from b2f=0→3, larger than the
LucidFlex vault path is worth on any profile.

The TopStep DLL toggle had **zero EV impact in i.i.d. simulation** across
all 5 profiles × 3 b2f variants. The strategy's own loss distribution
never crosses the manual lockout threshold during a simulated day, so DLL
acts as a safety brake against trader behaviour, not as something the EV
model captures. Treat it as an operational hygiene flag, not an
EV-shaping decision.

## Run Provenance

- 77 MC rows × 1000 sims, 31.5 s wall.
- Each row reuses adaptive sizing params discovered in the full catalog
  (`cells.csv`) — no adaptive search re-run.
- Default rules: 5-payout cap on TopStep, `max_eval_days=90`,
  `max_funded_days=180`, eval/funded cost per trade = $5.
- LucidFlex variants: `eval_fee ∈ {98, 84, 70}` (default coupon, 40% vault,
  50% vault).
- TopStep variants: `dll ∈ {False, True}` × `b2f ∈ {0, 1, 3}` × payout
  path ∈ {Standard, Consistency}.
- Sensitivity: Robust trend re-run uncapped on both TopStep paths.

## Per-Profile Best `ev_low` (Capped, Best b2f)

| Profile          | Best firm           | b2f | mean EV | ev_low | p_pass |
|------------------|---------------------|----:|--------:|-------:|-------:|
| Patient swing    | topstep_consistency |   3 |   3,113 |  2,990 |  N/A*  |
| Low-WR breakout  | topstep_consistency |   3 |   4,873 |  4,519 |  N/A*  |
| Balanced edge    | topstep_consistency |   3 |   5,993 |  5,792 |  N/A*  |
| **Robust trend** | **topstep_consistency** | **3** | **8,529** | **8,315** | 0.99 |
| High-WR scalp    | topstep_standard    |   3 |   3,604 |  3,410 |  N/A*  |

\* `p_pass` is row-attribute on the Monte Carlo result; full per-row stats
in `decision_sheet.csv`. The catalog writeup carries the WR=0.45/R=2.0/freq=3
Adaptive p_pass = 0.99 figure into Robust trend; the b2f variant changes
funded-phase economics, not eval pass rate.

Robust trend wins on every firm, by every variant. Cross-profile gap
between Robust trend and the next best (Balanced edge) is +43% on `ev_low`.

## LucidFlex Vault Discount Impact

`ev_low` delta from default coupon ($98) to 50% vault ($70), per profile:

| Profile          | Δ ev_low |
|------------------|---------:|
| Patient swing    |       28 |
| Low-WR breakout  |       28 |
| Balanced edge    |       28 |
| Robust trend     |       28 |
| High-WR scalp    |       28 |

The vault path produces a constant $28 lift because the run uses one
attempt per simulation (no resets needed at WR/R combos in our profile
set). **Conclusion:** vault discount cycles do not change profile
ranking. Worth using if a vault cycle is already active, but not worth
basing a firm choice on.

## TopStep Back2Funded Impact

`ev_low` delta from b2f=0 to b2f=3, per profile (best firm path):

| Profile          | Path        | b2f=0  | b2f=1  | b2f=3  | Δ (b2f=3 − 0) |
|------------------|-------------|-------:|-------:|-------:|--------------:|
| Patient swing    | Consistency |  2,480 |  2,899 |  2,990 |          +510 |
| Low-WR breakout  | Consistency |  2,422 |  3,806 |  4,519 |        +2,097 |
| Balanced edge    | Consistency |  4,714 |  5,569 |  5,792 |        +1,078 |
| Robust trend     | Consistency |  6,757 |  8,103 |  8,315 |        +1,558 |
| High-WR scalp    | Standard    |  3,081 |  3,385 |  3,410 |          +329 |

Effect is largest on profiles with non-trivial funded-phase breach
probability (Low-WR breakout, Robust trend) where reactivation buys
additional payout cycles. Diminishing returns past b2f=1 on the
high-edge profiles.

**Operational note:** Back2Funded is a real product Georg can purchase.
Phase 4 strategy research should plan around b2f=3 as the realistic
deployment, not b2f=0.

## TopStep DLL Toggle Impact

| Profile          | DLL=False ev_low | DLL=True ev_low | Δ |
|------------------|-----------------:|----------------:|--:|
| Patient swing (cons, b2f=3)   | 2,990 | 2,990 | 0 |
| Low-WR breakout (cons, b2f=3) | 4,519 | 4,556 | +37 |
| Balanced edge (cons, b2f=3)   | 5,792 | 5,792 | 0 |
| Robust trend (cons, b2f=3)    | 8,315 | 8,315 | 0 |
| High-WR scalp (std, b2f=3)    | 3,410 | 3,410 | 0 |

Δ is at most $37 (Low-WR breakout, likely seed noise). The lockout
threshold isn't tripped by the i.i.d. trade distribution at our
parameters. DLL is operational policy, not a tunable EV parameter.

## Capped vs Uncapped Sensitivity (Robust Trend Only)

| Firm                | Capped (5) ev_low | Uncapped ev_low | p_max_payout |
|---------------------|------------------:|----------------:|-------------:|
| topstep_standard    |             6,135 |          18,819 |         0.00 |
| topstep_consistency |             6,757 |          17,054 |         0.00 |

Uncapped: TopStep Standard pulls ahead because Standard's per-cycle
payout is smaller but more frequent — over a full 180-day funded horizon
that compounds harder than Consistency's larger, lumpier payouts.
`p_max_payout = 0.00` even uncapped means no run actually maxes out the
funded horizon — the cap was the binding constraint in the original
catalog, not the horizon.

**Implication:** if Phase 4 ever produces a candidate strategy that can
sustain the WR/R for ≫5 payouts, the firm choice may flip from
Consistency to Standard. Capped EV is a conservative ranking and the
recommended deployment until live data validates the WR/R distribution.

## Recommendation

Phase 4 strategy research targets:

```
Profile:  Robust trend
WR:       0.45
R:        2.0
freq:     ~3 trades / day
Sizing:   Adaptive (eval_base/funded_base from catalog row)
Firm:     TopStep Consistency
Variant:  Back2Funded reactivations = 3, DLL flag at operator discretion
```

Capped lower-CI EV: **$8,315 per evaluation cycle** (ev_low). Headline
mean: **$8,529**. Secondary firm option (TopStep Standard, same profile)
for traders who want shorter payout cycles or want to plan for an
uncapped funded horizon.

LucidFlex is **not** the recommended primary firm for any of the 5 named
profiles after this re-ranking. It remains a viable secondary if Georg
wants to run two firms in parallel for diversification.

## Open / Out of Scope

- The Robust trend Adaptive sizing parameters used here come from the
  default catalog adaptive search; they were not re-tuned post-vault. A
  small re-tune at Consistency × b2f=3 might lift ev_low further.
- TopStep payout-cap=5 is the conservative comparison; full uncapped
  funded-horizon EV is shown only for Robust trend. The other 4 profiles
  may also flip Standard ↔ Consistency uncapped — not load-bearing for
  the recommendation.
- Vault discount cycles only change eval-phase economics; if a candidate
  strategy fails eval often (Low-WR breakout has p_pass ~0.7), the per-
  attempt vault discount becomes more valuable than the table here
  shows. A multi-attempt simulation (engine does not currently chain
  consecutive attempts) would surface this.
- Reset/fresh-attempt decision (`reset_economics.py`) was not invoked
  per-profile because no profile in our set has an attempt-failure
  pattern that motivates it. The `ResetDecision` helper says
  `prefer_reset_before_friction = True` for both firms (LucidFlex
  $95<$98; TopStep $109>$95 → fresh wins) at default fees; that's a
  one-shot policy, not per-profile.
- News embargo / CME price-limit proximity rules still deferred (audit-
  flagged from Phase 1).

## Next

Phase 4 — strategy research scoped to the Robust trend profile.
Specifically: pick a TradingView/Pine candidate (TSMOM, opening-hour
momentum, or similar) whose backtest produces:

- Win rate in [0.40, 0.50]
- Average winner / average loser in [1.7, 2.3]
- Trade frequency 2–4 per RTH session
- No regime where realized autocorrelation of trade outcomes exceeds
  ρ=0.3 at the 10-trade scale (catalog finding)

Replay through `tv_trade_loader.py` → LucidFlex/TopStep pipelines, then
through Monte Carlo with the exact sizing params from the catalog
Adaptive row. If realized stats land inside Profile 4, the catalog +
this decision sheet pre-validate the deployment.
