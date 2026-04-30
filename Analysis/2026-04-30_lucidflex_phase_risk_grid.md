# LucidFlex Phase-Risk Grid Search

Date: 2026-04-30

Script: `Analysis/scripts/lucidflex_phase_risk_grid.py`

Command:

```bash
.venv/bin/python Analysis/scripts/lucidflex_phase_risk_grid.py
```

## Purpose

The previous phase-sizing probe showed that eval risk and funded risk should be separated, but it only tested a few hand-picked cells. This run performs a small grid search over eval risk and funded risk for three synthetic WR/R:R profiles.

This is still a synthetic distribution search. It ranks risk geometry under assumed trade distributions; it does not prove that ORB/TORB or any real NQ/MNQ strategy can produce those distributions.

## Setup

- Ruleset: LucidFlex 50K, canonical account state machine.
- Simulations per cell: 5,000.
- Max eval horizon: 90 days.
- Max funded horizon: 180 days.
- Eval risks tested: `$100`, `$150`, `$200`, `$250`, `$300`.
- Funded risks tested: `$100`, `$125`, `$150`, `$200`, `$250`, `$300`.
- Profiles tested:
  - `45% WR / 1.50R`
  - `50% WR / 1.25R`
  - `55% WR / 1.00R`

Column notes:

- `fund br/a` means funded breach across all eval attempts.
- `fund br/p` means funded breach conditional on passing eval.
- `mean EV` is trader payouts minus the `$175` eval fee.
- `med EV` is the median attempt result.

## Top Cells By Mean Net EV

```text
   WR    RR   evalR   fundR  eval pass fund br/a fund br/p   max po  avg po  avg paid   mean EV   med EV
--------------------------------------------------------------------------------------------------------
 0.50  1.25     300     300  52.14%  47.10%  90.33%   5.04%    0.86       573       398     -175
 0.45  1.50     250     300  48.78%  44.66%  91.55%   4.12%    0.74       548       373     -175
 0.50  1.25     300     250  52.04%  46.84%  90.01%   5.18%    0.91       543       368     -175
 0.50  1.25     250     300  49.60%  45.00%  90.73%   4.60%    0.81       543       368     -175
 0.45  1.50     300     300  48.70%  45.10%  92.61%   3.60%    0.73       540       365     -175
 0.50  1.25     300     200  51.90%  46.02%  88.67%   5.78%    0.96       523       348     -175
```

The top mean-EV cells are aggressive. They pass eval around 49-52%, but about 89-93% of accounts that pass eval breach funded before completing the max payout path. Mean EV is carried by a small right tail; the median result remains `-$175`.

## Lower-Risk Positive-EV Cells

The following rows passed the filter: mean EV above zero, conditional funded breach below 85%, and max-payout rate above 1%.

```text
   WR    RR   evalR   fundR  eval pass fund br/a fund br/p   max po  avg po  avg paid   mean EV   med EV
--------------------------------------------------------------------------------------------------------
 0.50  1.25     300     125  51.80%  41.24%  79.61%   5.66%    0.99       482       307     -175
 0.50  1.25     250     125  49.68%  39.00%  78.50%   5.82%    0.98       474       299     -175
 0.45  1.50     250     125  48.86%  41.34%  84.61%   4.58%    0.89       444       269     -175
 0.45  1.50     300     125  48.58%  40.60%  83.57%   4.60%    0.89       442       267     -175
 0.50  1.25     200     150  38.56%  32.76%  84.96%   4.82%    0.75       378       203     -175
 0.45  1.50     200     125  40.90%  34.52%  84.40%   4.06%    0.75       375       200     -175
 0.50  1.25     200     125  38.66%  31.14%  80.55%   4.10%    0.73       356       181     -175
```

These are not clean enough to call a final strategy. The useful result is narrower: for these assumptions, eval risk in the `$250-$300` band with funded risk around `$125` is a candidate geometry. It preserves most of the mean EV of the aggressive cells while reducing post-pass funded breach by roughly 10 percentage points.

## Interpretation

The grid supports three working conclusions:

1. LucidFlex still behaves like a right-tail product. Positive mean EV can coexist with a losing median attempt.
2. Eval and funded risk should be decoupled. The best mean-EV eval risk is usually higher than the funded risk that keeps the funded path survivable.
3. The next real test should replay actual TORB/ORB trades through this geometry instead of continuing to trust synthetic Bernoulli paths.

The current most defensible candidate for the first real replay is:

- Eval risk: `$250-$300`
- Funded risk: `$125`
- Target distribution to look for: roughly `45-50% WR` with `1.25-1.50R`, one trade/day or close to it

## Guardrail

This result does not validate ORB/TORB. It only says what trade distribution and phase-risk geometry would be worth testing first if a real NQ/MNQ strategy can reproduce the synthetic profile after slippage, commissions, session filters, and trade clustering.
