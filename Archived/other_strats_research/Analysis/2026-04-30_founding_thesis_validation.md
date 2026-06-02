---
type: analysis
date: 2026-04-30
author: Claude Code (Opus 4.7)
inputs: Sources/2026-04-30_youtube_prop_firm_thesis.md, Rulesets/TopStep/TopStep NoFee.md
script: Analysis/scripts/founding_thesis_sanity_check.py
status: first-pass; results override the transcript-derived calibration targets in PROJECT_CONTEXT.md
---

# Founding-Thesis Validation Against TopStep 50K Combine

## Question

The YouTube transcript (`Sources/2026-04-30_youtube_prop_firm_thesis.md`) makes three load-bearing empirical claims:

1. **Quantitative:** at 4:1 RR / 20% WR, zero-EV strategies pass TopStep 50K Combine ~37% of the time.
2. **Qualitative:** pass rate increases monotonically as risk geometry shifts toward higher win rate / lower R:R, holding EV at zero.
3. **Calibration:** an ORB-shaped low-RR / high-WR real strategy hits ~50% pass rate; published TopStep 2024 pass rate is 12.4%; FPFX Tech reports ~14% across 300K real accounts.

Do these hold up against the actual TopStep ruleset?

## Method

Standalone Python Monte Carlo (`Analysis/scripts/founding_thesis_sanity_check.py`), 20,000 sims per cell, no project-engine dependencies, stdlib only.

Models actual TopStep 50K Combine mechanics from `Rulesets/TopStep/TopStep NoFee.md`:

- Start $50,000, target $53,000 (+$3K), initial MLL $48,000 (-$2K)
- MLL trails highest **end-of-day** balance by $2,000, locks at $50,000
- MLL monitored intraday — breach if balance dips to/below current MLL during the day
- Combine consistency rule: best day < 50% of total profit at the moment of pass
- Pass = balance reaches $53,000 intraday AND consistency holds

Strategy model: i.i.d. trades, +R on win (prob W), -1 on loss (prob 1-W), with R = (1-W)/W to enforce zero EV exactly. Six (W, RR) pairs from the transcript: (0.20, 4.0), (0.25, 3.0), (0.33, 2.0), (0.50, 1.0), (0.67, 0.5), (0.80, 0.25).

Four scenarios swept to check sensitivity to bet-sizing and rule-modeling assumptions.

## Results

### Scenario A — realistic baseline ($200 = 0.4% bet, 5 trades/day, 60-day cap, consistency ON)

| WR | RR | pass% | fail MLL% | fail cons% | timeout% |
|---:|---:|---:|---:|---:|---:|
| 0.20 | 4.0 | **10.4%** | 70.4% | 19.3% | 0.0% |
| 0.25 | 3.0 | 19.7% | 71.4% | 8.8% | 0.0% |
| 0.33 | 2.0 | **27.6%** | 69.3% | 3.1% | 0.0% |
| 0.50 | 1.0 | 26.8% | 72.3% | 0.0% | 1.0% |
| 0.67 | 0.5 | 19.5% | 64.2% | 0.0% | 16.2% |
| 0.80 | 0.25 | **7.9%** | 41.2% | 0.0% | **50.9%** |

### Scenario B — same as A but consistency rule OFF (mirrors transcript's bare GBM)

| WR | RR | pass% |
|---:|---:|---:|
| 0.20 | 4.0 | 29.6% |
| 0.25 | 3.0 | 28.6% |
| 0.33 | 2.0 | 30.6% |
| 0.50 | 1.0 | 26.8% |
| 0.67 | 0.5 | 19.5% |
| 0.80 | 0.25 | 7.9% |

### Scenario C — small-bet high-frequency ($50 bet, 10 trades/day, 90-day cap, consistency OFF)

| WR | RR | pass% | timeout% |
|---:|---:|---:|---:|
| 0.20 | 4.0 | 24.9% | 4.3% |
| 0.50 | 1.0 | 4.6% | 63.8% |
| 0.80 | 0.25 | 0.01% | 98.6% |

### Scenario D — small-bet high-frequency with consistency ON

Essentially identical to C (consistency only bites when high-RR strategies actually reach target; with small bets they rarely do).

## Findings

### 1. The transcript's specific 37% pass rate at (0.20, 4:1) does not reproduce.

Closest: **29.6% in scenario B** (consistency rule off, $200 bet, 5 trades/day). At realistic bet sizing with the consistency rule enforced, pass rate is **10.4%**. The 37% number is plausible only under a specific combination of rule simplifications (no consistency check) and bet-sizing assumptions that the transcript does not state explicitly.

### 2. The transcript's monotonic claim is wrong.

Pass rate does **not** increase monotonically as risk geometry shifts toward higher WR / lower RR. The actual relationship is **inverted-U with peak around 1:1 to 2:1 RR**, then collapses back toward zero as high-WR / low-RR strategies time out. At (0.80, 0.25) under realistic bet sizing, **51% of attempts time out** — the strategy can't grind to the profit target fast enough.

This matters because the transcript's pitch — "high-WR / low-RR maximally exploits the convex payoff" — is a one-sided summary of the math. The full picture is that **finite time horizon punishes low-variance grinders** the same way the trailing MLL punishes high-variance swingers. The optimum sits in the middle.

### 3. The industry baseline numbers are internally consistent and consistent with our model.

The transcript's quoted "TopStep 12.4% 2024" matches FPFX Tech's reported "14% pass rate across 300K accounts" (industry-wide). Our model produces 7-28% pass rates across zero-EV configurations. If real retail traders run at small negative EV with poor sizing (the dominant failure mode reported in industry data: over-leverage and revenge trading, not strategy edge), our model is consistent with the 12.4-14% empirical baseline.

### 4. Real-money implications

- **A "good enough" real strategy probably needs ~50% WR and 1:1 RR with disciplined sizing to hit ~25% pass rate per attempt.** That's roughly double the industry baseline and a very plausible target.
- **The convex-payoff thesis is still correct in direction** — strategies don't need positive raw EV to be net-EV-positive over many attempts because the eval fee caps downside. But the magnitude is much smaller than the transcript implies, and the optimal risk geometry is not what the transcript claims.

## Implications for the Engine

These findings should override the transcript-derived calibration targets in `PROJECT_CONTEXT.md`. Updated calibration targets for Phase 3 Monte Carlo:

- At zero EV, pass rate should peak around 1:1–2:1 RR, not at either extreme.
- (0.20, 4:1) zero-EV pass rate should land in the **10–30% range** depending on rule-modeling assumptions, NOT 37%.
- Pass rate of any zero-EV strategy at TopStep 50K should be in the **5–30% band** under realistic bet-sizing and consistency rule enforcement.
- Industry 12.4-14% real-trader pass rate is the right empirical anchor for "small-negative-EV with bad sizing" scenarios.

If our Phase 3 engine reproduces these qualitative findings (inverted-U, 5-30% pass-rate band at zero EV, peak around 1:1–2:1 RR) then the simulator is behaving correctly. If it produces monotonic improvement to 50%+ at high WR / low RR, that's evidence we are missing the time-horizon / consistency-rule dynamics.

## Limitations of This Analysis

These are the main reasons to treat the absolute numbers as soft, not hard:

1. **Trade i.i.d. assumption.** Real strategies cluster wins and losses (autocorrelation, regime persistence). Clustering generally widens the variance of cumulative P&L paths, which would reduce pass rates further for the high-WR / low-RR strategies that depend on steady grinding.
2. **No slippage or commission.** TopStep micros are roughly $1.20-2.00 round-trip per micro contract. At small per-trade P&L, commissions matter — they push real strategies toward negative EV and reduce pass rates further.
3. **5–10 trades/day is a guess.** Real day-trading strategies vary widely. Sensitivity not exhaustively explored.
4. **Single fixed bet size per strategy.** The whole project is about dynamic sizing — this analysis intentionally uses fixed sizing for clarity. Dynamic sizing should improve outcomes (Phase 3 will quantify).
5. **No DLL.** TopStep DLL is optional in Combine; not applied here.
6. **Consistency rule simplified.** Checked at pass-attempt only, not real-time blocked. TopStep blocks the rule real-time, which slightly changes path dynamics.
7. **No reset economics.** Each pass-attempt is independent; in reality you can buy resets and amortize the eval cost.

## Sources

- Karl Whelan, "Ruin Probabilities for Strategies with Asymmetric Risk" — `karlwhelan.com/Papers/Ruin.pdf` (cited but not fully read; PDF text extraction failed locally — worth reading manually).
- Hunter et al. (2008) generalized gambler's ruin with jumps — referenced in the search results above.
- S. Redner, "A First Look at First-Passage Processes" — `arxiv.org/pdf/2201.10048` (standard reference for first-passage problems).
- FPFX Tech report on 300K real prop accounts: ~14% pass rate, ~7% reach payout, average payout ~4% of account size.
- TopStep 50K Combine ruleset: `Rulesets/TopStep/TopStep NoFee.md`.
