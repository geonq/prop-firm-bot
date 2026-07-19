# ORB Walk-Forward Verdict — 2026-07-17

## Frozen strategy (selected on 2020→mid-2025, holdout-blind)

15-min opening range (09:30–09:45 ET), enter at 09:45 bar open in the direction of the
OR candle (doji skip), stop at opposite OR extreme, 4R target or EoD flat, no filters,
1 trade/day max. Costs: 2-tick slippage per side (adverse), $4.50/side commission.
Risk $200/trade. Params hash `5313c781556f704a`; selection basis:
`Analysis/output/orb/walk_forward_results.csv` (216 configs, 8 rolling folds,
36 admissible, this config #1/#2 on every firm with positive worst-fold means).

## Walk-forward result (8 OOS folds, 2020→2025-06)

Median net-EV lower-CI per pipeline attempt: LucidFlex $500, TopStep $604,
Apex-EOD $561, Apex-Intraday $637. Worst fold positive on all four firms.
Notable: **every filtered config (vol percentile / relative volume) failed
admissibility** — filters improve raw R but starve trade frequency, which the
prop pipeline punishes harder (slower eval progress, more timeouts). The naked
ORB is the right shape for this payoff structure even though it is the weaker
market strategy — consistent with the engine-first thesis, contra the equity
literature's filter-is-the-edge finding.

## Holdout (2025-07-01 → 2026-07-15, evaluated ONCE, now sentinel-locked)

222 trades, WR 36.9%, mean R +0.037 (vs ~+0.12 in-search — honest decay, the
vol-regime dependence the literature warned about; 2025-26 was calm).

| Firm | net EV/attempt [95% CI] | P(pass eval) | mean days | **EV/month** (lowCI) |
|---|---|---|---|---|
| LucidFlex 50K | $127 [114, 140] | 28.5% | 65 | **$41** ($37) |
| TopStep 50K | $101 [87, 114] | 28.6% | 63 | **$34** ($29) |
| Apex 50K EOD | $95 [78, 112] | 28.5% | 66 | **$30** ($25) |
| Apex 50K Intraday | $167 [150, 184] | 28.5% | 66 | **$53** ($48) |

Record: `Analysis/output/orb/holdout_5313c781556f704a.json`.

## Verdict vs the €500/month target

**Positive EV, target missed on a single account.** The strategy survives true
OOS with positive expectancy on all four firm products after honest friction —
a real result against the Mesfin (2025/26) MNQ null — but single-account
extraction is **~€30–53/month**, an order of magnitude below €500.

Paths that could close the gap (in order of credibility):
1. **Parallel accounts.** Apex explicitly permits up to 20 funded accounts;
   same-direction signal copying is standard practice there. ~10 Apex-Intraday
   accounts ≈ $530/month EV. Caveats: outcomes are perfectly correlated (all
   accounts breach together — EV adds, variance multiplies), per-account
   activity/payout rules must each be satisfied, and the **automation-ban-on-PA
   claim is still unverified** — verify with Apex before building anything.
2. **Risk scaling.** EV does not scale linearly with risk-per-trade (breach
   probability rises nonlinearly); a risk sweep on pre-holdout data could find
   a better point than $200 but the holdout is burned — any re-optimized risk
   number is an in-sample claim now.
3. **Regime gating.** The edge is vol-dependent; a live rule "trade only in
   elevated-vol regimes" was rejected by the walk-forward for frequency
   starvation on single accounts, but interacts differently with a multi-account
   structure (idle months cost activity-rule compliance, not fees).

## Addendum (2026-07-17 afternoon) — risk & sizing sweeps (pre-holdout evidence only)

The holdout is burned; everything below is fold/pooled pre-holdout evidence
(`risk_sweep.json`, `sizing_sweep.json`), to be validated on H2-2026 data.

**Risk sweep (flat risk $100–$400):** $200 was far from optimal. Pooled
EV/month rises monotonically through $400 (TopStep $357, LucidFlex $299,
Apex-Intraday $294 vs ~$105–136 at $200). $100 risk is EV-negative everywhere —
the eval structure rewards aggression; the fee is the capped downside doing its
job. P(pass) peaks near $250 (~43%) but EV/month keeps climbing because failed
attempts also resolve faster. Firm divergence under pressure: TopStep's worst
fold stays strongly positive at $400 (+$279); Apex-EOD's worst fold goes
negative from $250 up.

**AdaptiveSizing sweep (108 cells):** does NOT beat flat $400 on pooled
EV/month (best adaptive cell $283 vs flat $294 Apex-Intraday; TopStep $243 vs
$357). Its value is worst-regime robustness on Apex: the
(eval $400 / funded $300, buffer_full_frac 0.02, floor 0.5, post-payout shrink
0.6) cell turns Apex-EOD's worst fold positive (+$5) and lifts Apex-Intraday's
to +$77 — the only configuration where ALL four firm-variants have positive
worst folds.

**Updated bottom line (holdout-regime scaled ≈0.39×):** flat $400 on
TopStep/LucidFlex ≈ $115–140/month/account; adaptive on Apex ≈ $95–110 with
positive worst folds. €500/month plausibly needs **4–5 parallel accounts**
(vs ~10 at the original $200 flat) — Apex's 20-account allowance is the
structural fit, TopStep's per-account EV is higher but its account cap is
lower. All of this is fold-level evidence pending fresh OOS data and the Apex
automation-policy answer.

## Addendum 2 (2026-07-17 evening) — round-2 exit overlays (fold evidence)

Literature-backed exit overlays searched (18 combos, 8 folds, $400 risk,
`round2_search.json`; backtester extensions reviewer-approved, entry-neutral):

**Winner — VWAP-trail-after-2R + 120-min time stop — dominates the frozen
baseline on EVERY firm on BOTH median and worst fold** (per-attempt mean EV):
LucidFlex 837/166 vs 774/95; TopStep 1670/437 vs 1520/279; Apex-EOD 898/+35 vs
769/−50 (worst fold flips positive); Apex-Intraday 975/108 vs 845/23. Uniform
improvement, not a traded-off peak. Mechanism per papers: the time stop kills
no-progress trades before they bleed to EoD (Howard 2026); the VWAP trail lets
capped runners extend while protecting profit (Zarattini SPY 2024).

**Rejected by the data:** hold_into_close (Baltussen overlay) — near-zero
effect in all variants (few trades survive to 15:30 with the cap binding);
60-min time stop — raises worst folds but cuts medians ~35% (too aggressive).

**Round-2 candidate frozen:** or=15 / first_candle / or_opposite / 4R /
slip 2 + vwap_trail_after_r=2.0 + time_stop_minutes=120, flat $400 risk.
Rough effect: ~+10% median EV and ~+55% worst-fold vs baseline → TopStep
pre-holdout ~$390/month/account, holdout-regime-scaled ~$150. €500/month ≈
**4 accounts**. Evidence level: fold-only (18-combo selection, pre-registered
1-2-knob mechanisms). MUST be validated on H2-2026 data before deployment.

## Addendum 3 (2026-07-17 night) — round 3: firm-specific risk, ladder exit, overfitting correction

**Firm-specific risk re-sweep (under round-2 exits, `risk_sweep_v2.json`):** the
$400 "one risk fits all" framing was itself suboptimal. Worst-fold discipline
shows a REAL per-firm ceiling, not a search artifact (monotonic across 6 risk
levels each):
- **TopStep tolerates far more risk than the other three** — worst fold keeps
  RISING through $800 tested (worst-fold mean $438→$460→$488 at $400/$600/$800).
  Best pooled pre-holdout EV/month at $800: **$553**.
- LucidFlex / Apex-Intraday: worst-fold peaks at $400 (own risk optimum);
  pushing further trades worst-fold for median.
- **Apex-EOD is fragile — worst-fold goes NEGATIVE above $300 risk.** Keep this
  product's risk conservative regardless of the other three.
Recommended per-firm risk: TopStep $600-800, LucidFlex/Apex-Intraday $400-500,
Apex-EOD $300.

**Laddered partial-exit overlay (`round3_ladder_search.json`, friction-bug
found and fixed by review before this run) — REJECTED.** All 9 tested configs
(partial_exit_r ∈ {1.5,2.0,3.0} × fraction ∈ {0.33,0.5,0.67}) raise median EV
but LOWER the worst fold on EVERY firm, with zero exceptions across the full
grid. Mechanism: this strategy's edge is right-tail-dependent (low win rate,
large winners do the work — literature-consistent since round 1); a partial
exit structurally caps the tail that rescues bad regimes. Do not add laddering
to the frozen config. This is a clean negative result, not noise.

**Backtest-overfitting correction (`overfitting_correction.json`):** having
now tested 234 total parameter configurations against the same 8 folds,
Deflated Sharpe Ratio = 68.4% (probability the round-2 winner's edge beats the
best-of-234-under-pure-luck benchmark) — likely somewhat optimistic since the
variance estimate feeding it only had data from 54/234 trials (180 round-1
configs were IS-pruned before full OOS evaluation and their fold data was
never computed). Bonferroni cross-check on the winner's raw per-trade
significance (p=0.0033, T=1173 real trades) fails badly once multiplied by
234 (p=0.77) — but Bonferroni assumes trial independence, which is false here
(configs share folds/instrument/strategy family), so this is a deliberately
harsh floor, not the true answer. **Honest range: real signal exists, exact
confidence is genuinely uncertain between these two bounds.** This is the
reason H2-2026 fresh-data validation remains mandatory, not optional, before
any capital scales up.

**Round-3 frozen recommendation:** round-2 config (vwap_trail_after_r=2.0,
time_stop_minutes=120), NO ladder, risk set per-firm as above. No further
parameter search recommended on this data — diminishing/uncertain returns per
the overfitting correction; next real evidence requires either H2-2026 data or
costly full-grid re-evaluation of the 180 pruned round-1 configs (not done).

## Addendum 4 (2026-07-18) — full-scope run: 2015-2025 data, 18 folds. THE HEADLINE FINDING.

At Georg's request, extended history back to 2015-01-01 (Databento, $6.23,
`DataLocal/nq_ohlcv_1m_2015-01-01_2026-07-16.parquet`, 4,014,174 bars) and
re-ran the full pipeline (fresh entry/target grid, exit-overlay search,
firm-specific risk resweep, overfitting correction) on 18 rolling folds
(vs the original 8). Full run: 4.44 hours. **Holdout untouched.**

**Automated Stage A/B selection was unreliable and was overridden by manual
review.** The raw #1-ranked candidate (or=5, first_candle, no fixed target,
120min time stop) is admissible on LucidFlex only, has worst-fold negative
at every risk level on every firm, and an extremely fat-tailed return
distribution (kurtosis 31.9) — rejected. A broader Stage-B candidate (or=5,
first_candle, 4R target, 120min time stop, admissible on 3/4 firms in the
raw pass) was also evaluated and is a better shape, but still fails
worst-fold robustness once risk-swept.

**The decisive test: the ORIGINAL round-2/3 winner (or=15, vwap_trail=2.0,
time_stop=120) was re-evaluated directly against the full 18-fold set — it
had never actually been tested against 2015-2019 data before.** Result:
**collapses to LucidFlex-only admissible**; TopStep — the single strongest,
most risk-tolerant firm in rounds 2-3 (worst-fold +$437 at $800 risk on the
8-fold sample) — now fails admissibility outright (worst-fold -$116).

**Per-fold breakdown reveals the mechanism cleanly, not noise:**
- **Every one of the 10 folds spanning 2016-07 through 2020-01 is negative**
  on every firm, no exceptions.
- **Every one of the 8 folds from 2021-07 onward is strongly positive**, no
  exceptions.
- This is a clean volatility-regime split, exactly matching round-1's own
  literature warning (Lundström 2014/2017/2020: ORB profit is a
  high-volatility-regime phenomenon, near-zero/negative in calm markets).
  2016-2019 was one of the calmest stretches in market history; 2021-2025
  has been one continuous chain of high-realized-vol regime shocks
  (meme-stock mania, 2022 hiking cycle, 2023 banking crisis, 2024-25 AI
  melt-up).
- Aggregate: negative-regime folds sum to -$572 (lucidflex); positive-regime
  folds sum to +$5,119 — the edge is real and large in aggregate, but
  **27.6% of ALL 10 years' profit comes from a single fold (2024 H2)**, and
  ~64% comes from the final 18 months of the entire sample (folds 15-17,
  2024-2025). The recent-history result that rounds 1-3 validated was real,
  but was earned almost entirely inside an unusually volatile 18-month
  window, not a representative decade.

**Overfitting correction (this round) — methodology bug, do not trust the
DSR=0.000 outputs.** The trial-Sharpe proxy used for the SR_0 benchmark
computation produced implausible magnitudes (sr_0 as high as 76.9 — no real
58-config search ceiling looks like that), a units mismatch against the
winner's real per-trade Sharpe (~0.04-0.05). This is a different, cruder
proxy than the ORIGINAL 2026-07-17 correction's careful units-consistent
approach (which is why that one's DSR=0.684 is more trustworthy than
anything produced tonight). The self-referential PSR(0) values (which do NOT
depend on the broken trial comparison) are usable: 99.75% and 98.2% for the
two Stage-B candidates — strong standalone evidence of positive Sharpe, but
NOT yet corrected for the 58-config search.

**Verdict: no candidate — original or new — clears worst-fold-across-all-
regimes robustness on the full 2015-2025 sample. The one-shot holdout was
NOT spent tonight** on any of these candidates; doing so would waste it on
a config that fails its own in-sample robustness bar. Two honest paths
forward, neither pursued tonight given scope:
1. **Regime-conditional deployment**: trade only when realized volatility is
   elevated (the vol_percentile_min filter already exists in the grid but
   was never re-tested at the higher risk levels / broader fold set found
   useful today — worth a dedicated pass, since the calm-regime folds are
   precisely what a vol filter would suppress).
2. **Accept the strategy as regime-dependent, not all-weather** — size and
   deploy only during identified high-vol windows, accept it goes dormant
   (or is paused) during calm stretches, and do not expect the smooth
   always-on EV/month figures from rounds 1-3 to hold through a 2016-2019-
   style regime if one recurs.

## Addendum 5 (2026-07-18) — round-4 holdout SPENT, at Georg's explicit direction

Georg reviewed the caveats above (no candidate cleared worst-fold-across-
all-regimes; TopStep failed admissibility in every configuration tested on
the full decade) and explicitly directed a holdout evaluation anyway. Ran
the one-shot holdout on the best-tested round-4 candidate: or=5min,
first_candle, or_opposite stop, 4R target, 1-tick slip, 120min time stop, NO
vwap_trail, $400 risk/trade (params_hash `8afbe6259cab2dd2`, first and only
holdout look for this hash, sentinel now locked, see
`Analysis/output/orb/full_scope/holdout_8afbe6259cab2dd2.json`).

**Holdout (2025-07-01 to 2026-07-15, 245 trades, WR 32.2%, mean R +0.129 —
stronger than the original config's holdout mean R of +0.037):**

| Firm | net EV/attempt [95% CI] | P(pass eval) | mean days | **EV/month** (lowCI) |
|---|---|---|---|---|
| TopStep | $650 [596, 703] | 39.3% | 23.2 | **$587** ($539) |
| Apex Intraday | $682 [618, 746] | 40.6% | 28.3 | **$507** ($459) |
| Apex EOD | $608 [544, 672] | 40.6% | 28.3 | **$452** ($404) |
| LucidFlex | $449 [415, 482] | 38.9% | 21.1 | **$447** ($414) |

**Clears the €500/month target on TopStep alone (lower-CI $539/mo); every
firm is within range or over.** ~9-14x the original round-2/3 holdout result
($30-53/mo) — driven by higher per-trade edge (5-min entry, no capped-tail
truncation from vwap_trail), 2x risk, and a higher realized pass rate
(38.9-40.6% vs the original's 28.5%), compounding multiplicatively.

**Read this number correctly, not just optimistically:** the holdout window
(mid-2025 to mid-2026) falls inside a period this same analysis identified
as regime-favorable (elevated realized vol relative to the 2016-2019
baseline). This result proves the strategy performs very well when the
current-style regime holds; it does NOT prove robustness to a return to a
calm, 2016-2019-style stretch — no configuration tested today, including
this one, showed a positive worst-fold across the full decade. TopStep
posted the single best holdout number here while ALSO being the firm that
failed fold-level admissibility in every configuration tested against the
full 2015-2025 history — both facts are true simultaneously; this is a
regime bet that paid off on this specific unseen window, not evidence the
regime risk has gone away.

**Final round-4 status: frozen, holdout spent, sentinel locked.** No further
tuning of this params_hash is possible or appropriate. If the regime shifts,
expect this number to compress toward (or below) the original $30-53/mo
figure, consistent with the per-fold breakdown in Addendum 4.

## Protocol notes

- Holdout evaluated once for all four firms on the identical frozen trade list
  (documented deviation from per-firm single-hash guard; no re-tuning occurred).
  Sentinel prevents any further holdout run for this params hash.
- Known model gaps: stop exits fill at the stop price even when a bar gaps
  through it (entries handle gap-through correctly; mildly optimistic in
  high-gap regimes, baseline-symmetric so relative comparisons unaffected —
  reviewer 2026-07-17); $200 flat risk (no dynamic sizing — engine's AdaptiveSizing
  not wired into replay path); micro-contract rounding not modeled (R-multiples
  × $200 assumes divisible size; real MNQ sizing quantizes); Apex 4.0 specs
  third-party sourced, pending help-center verification; consistency-rule
  interaction with 1-trade/day profile is mild but unmodeled for LucidFlex eval.
- Full audit trail: reviewer reports in session transcript 2026-07-17; all code
  Writer/Reviewer'd; 312 tests green at freeze.

## Addendum 6 (2026-07-18) — Phase 6A-R: trend-persistence regime filters REJECTED (geonq directive)

Pre-registered study (grid frozen in `Tasks/todo.md` § 6A-R before the run): 2 causal
signal families — Kaufman ER on daily closes (lookback 10/20, thr 0.25/0.35) and
trailing shadow-ORB mean R (K 20/40, thr 0.0/0.05) — gating the frozen base config
(no base re-tuning), 18 folds × 4 firms at $400, replay MC, holdout untouched.
Acceptance: worst fold positive on all 18 AND ≥70% retention of 2021+ unfiltered EV.
Results: `Analysis/output/orb/regime_v2/regime_v2.{csv,json}`.

**Result: 0/36 (config × firm) admissible.** Worst folds stay −$33..−$208 in every
cell. Most filters INCREASE the count of negative folds (unfiltered 4-6/firm → filtered
8-16): gating removes profitable trade density faster than it removes losing folds —
frequency starvation, correctly priced by the replay pipeline (same mechanism that
killed the round-1 filters and the vol_percentile retest). Block rates are era-uniform
(best cell: 42.8% pre-2020 vs 34.4% post-2021) — neither family separates the calm
2016-19 regime from 2021+ at daily resolution. Near-miss for the record: `er20_t025`
on lucidflex fails a single fold (−$33, 2019-01 chop); topstep's closest blocker is
−$1.92 (fold 1) but its binding failure is −$70 (fold 5); both Apex variants fail 9-11
folds. Curiosity, not a pass: `trailR_k40_t000` retains >100% of 2021+ EV on 3 firms
(its blocked 2021+ trades were net losers) yet still fails worst-fold everywhere.

Reviewer verdict: **CONFIRM-NEGATIVE** — full pipeline independently reproduced from
scratch (0 trade-count mismatches, 18 folds × 2 configs), warmup-NaN blocking proven
exactly zero (signals fully seeded before every OOS window), signal math hand-verified
on the parquet, lookahead mutation tests proven non-vacuous, retention/era math
reconciled exactly. One implementer bug (trailing-R history clipped to OOS windows)
was caught and fixed mid-build; final numbers are post-fix. 431 tests green.

**Standing conclusion: the regime risk is NOT filterable at daily resolution with
trend-persistence or strategy-equity signals at pre-registered thresholds.** The
deployment decision remains a regime bet, exactly as stated in Addendum 5. The only
remaining validation instrument is forward data (H2-2026 paper-parallel). Any future
filter attempt needs a genuinely different signal class (e.g. intraday/orderflow-based
regime detection) and its own fresh holdout — do not re-grid these families.
