# MNQ strategy parameter deep dive — 2026-07-20

## Executive conclusion

The TradingView behavior is not a charting mystery. The deployed rule is intentionally configured as `entry_mode="first_candle"`: after observing 09:30–09:35 ET, it enters at the 09:35 bar open in the direction of that candle. It does **not** require an opening-range high/low breakout. Apart from a doji/body threshold, there is no entry filter.

That rule is more accurately described as an **opening-drive / first-candle momentum strategy**, not a conventional ORB. The repository and live-engine comments confirm this explicitly.

A new chronological 70/30 test was run on independent Yahoo Finance `MNQ=F` five-minute data, 2026-05-08 through 2026-07-17. The first 33 sessions were used for selection and the final 15 sessions were untouched OOS. Ten small, literature-anchored candidates were registered before OOS comparison.

**No tested replacement produced credible improvement.** The deployed opening-drive rule remained the IS winner, but its conservative IS score was still negative and it lost **-3.877R** in OOS. A true range-breakout variant lost **-3.376R** OOS, only 0.501R less, after already losing IS. The hindsight-best OOS filter lost **-3.043R**, but it was not IS-selected and therefore is not evidence for deployment.

The honest answer is: recent results are bad, but changing to the obvious paper-inspired filters is not supported by this 70/30 test. Keep trading stopped and collect/acquire a longer fresh dataset before approving any parameter change.

## Actual live parameters

Source: `src/live/config.py::FROZEN_PARAMS`, `src/backtest/orb.py`, and `src/live/engine.py`.

- Instrument: MNQ.
- RTH opening range: 09:30–09:35 ET (five completed one-minute bars live; one five-minute bar in the TradingView analogue).
- Entry mode: `first_candle`, not `breakout`.
- Direction: long when the first range closes above its open; short when it closes below.
- Doji rejection: skip only when `abs(close-open)/(high-low) < 0.10`.
- Entry: modeled at the 09:35 bar open, one tick adverse slippage.
- Stop: opposite extreme of the first five-minute range.
- Target: 4R.
- Time stop: after 120 minutes, exit next bar open only if completed-bar close MFE never reached +1R.
- Otherwise: end-of-day flat.
- Frequency: maximum one trade per session.
- Entry filters disabled: prior-volatility percentile, relative opening volume, overnight-gap/ATR, weekday, trend, VWAP, news, order flow, and breakout confirmation.
- Risk budget: $400 per trade, whole-contract floor, maximum 20 MNQ contracts. Wide stops can result in zero contracts.
- Live MNQ commission placeholder: $0.74/contract/side; one tick slippage/side.

The 4R/120-minute rule is not a verbatim paper specification. It was selected in the repository's prior NQ optimization. The prior artifacts are now missing from this checkout; only the verdict narrative and scripts remain.

## Why TradingView entries can look strange

1. The strategy does not wait for a breakout. A bullish first candle buys immediately at 09:35 even when price never trades above the opening-range high afterward. A bearish candle similarly shorts immediately.
2. The stop width changes with the first candle's full high-low range, so identical-looking directional entries can have very different risk and target distances.
3. A 4R target makes the payoff strongly right-tail-dependent. Most trades stop near -1R; a small number of large winners must pay for them.
4. The 120-minute exit is conditional: touching +1R on a completed-bar-close basis permanently exempts the trade from the time stop, even if it later reverses.
5. TradingView order timing and commission settings can differ from the Python model. Exact reconciliation requires the actual Pine source, chart timezone/session settings, `process_orders_on_close` setting, commission/slippage settings, and a trade export.

## Important live-execution discrepancy found

`LiveBarFeed` serves completed one-minute bars. At approximately 09:35:02 it serves the completed 09:34 bar. The engine does not finalize the OR then; it waits until the completed 09:35 bar is served at approximately 09:36:02, and then models the entry at that bar's **09:35 open**. A live order cannot be placed retroactively at that price.

The code acknowledges real-fill/model-fill drift but describes it as small slippage. It can include roughly one minute of market movement. Stop is anchored to the OR extreme, while target and time-stop MFE are based on the modeled entry. This is a material paper/live parity issue and another reason not to activate live trading before a redesign and paper reconciliation.

## Literature findings and what was tested

### Zarattini, Barbon, and Aziz (2024), U.S. equities

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284

Their modern base ORB is a true directional breakout: first-candle direction determines the allowed side, but entry occurs only when price breaches the opening-range high/low. Their stock strategy uses an ATR-scaled stop, end-of-day runner, and relative-volume/"Stocks in Play" selection. The paper reports 5-minute ranges outperforming longer ranges in its cross-sectional stock universe.

Caveat: the strongest filter is cross-sectional news/relative activity among thousands of stocks. It does not transfer directly to one continuous MNQ series.

Tested here: directional breakout; OR-opposite and 5%/10% ATR stops; EOD and 4R/120 exits; relative opening volume >=100%.

### Zarattini and Aziz (2023/2024), QQQ/TQQQ

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622

This earlier paper includes the simplified second-candle opening-drive rule that resembles the deployed code. Its base target was 10R, and its later parameter study favored tight ATR stops and letting profits run to EOD. The deployed 4R/opposite-OR/120-minute combination is therefore a repository-derived hybrid, not the paper's final optimum.

### Lundström, volatility states

Source: https://www.diva-portal.org/smash/get/diva2:732318/FULLTEXT02.pdf

The study finds ORB performance strongly conditional on volatility: low-volatility states were negative and high-volatility states positive for S&P 500 and crude-oil futures. This agrees with the repository's older 18-fold finding that 2016–2019 folds were consistently negative while 2021+ folds were positive.

Tested here: prior realized-volatility percentile >=50%. It reduced losses in OOS but was negative in IS, had only 12 IS trades, and was not selected.

### Tsai et al. (2019), timely ORB on index futures

Source: https://doi.org/10.1109/access.2019.2899177

TORB uses one-minute information, aligns the strategy with the underlying cash-market active hours, and finds relatively short probe windows for U.S. index futures. It is a breakout rule, not an unconditional second-candle entry.

Tested here: directional breakouts with a 10:30 ET entry cutoff.

### Zarattini, Aziz, and Barbon (2024/2025), SPY intraday momentum

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172

This is a different strategy family: a 14-day, time-of-day-dependent noise area with decisions at half-hour intervals and dynamic band/VWAP exits. It is conceptually stronger filtration than a naked ORB but should not be grafted onto MNQ without a separate long-sample study.

## New 70/30 experiment

Data:

- Yahoo Finance `MNQ=F`, unadjusted five-minute bars.
- 48 complete RTH sessions from 2026-05-08 to 2026-07-17.
- Cross-check against Yahoo `NQ=F`: 13,291 common bars, close-return correlation 0.99878, median absolute level difference 0.5 points.
- IS: 33 sessions, 2026-05-08 through 2026-06-25.
- OOS: 15 sessions, 2026-06-26 through 2026-07-17.
- OOS was not used to select or alter candidates.
- Selection: highest IS mean trade R minus one standard error, minimum eight IS trades.
- Costs: one tick slippage/side and $0.74 MNQ commission/side.
- Conservative same-bar ordering: stop before target.

Results:

| Candidate | IS trades | IS total R | OOS trades | OOS total R | OOS max DD |
|---|---:|---:|---:|---:|---:|
| Deployed opening drive | 32 | +6.571 | 14 | -3.877 | 5.335R |
| True ORB, OR stop, 4R/120, cutoff 10:30 | 31 | -0.895 | 13 | -3.376 | 5.510R |
| True ORB, OR stop, EOD | 31 | -4.217 | 13 | -4.146 | 6.281R |
| True ORB, OR stop, EOD, relative volume >=1 | 12 | -0.083 | 5 | -3.327 | 3.327R |
| True ORB, 10% ATR stop, EOD, vol percentile >=50 | 12 | -1.801 | 9 | -3.043 | 5.912R |
| True ORB, 10% ATR stop, 4R/120 | 18 | -2.302 | 13 | -6.999 | 9.975R |
| True ORB, 10% ATR stop, EOD | 18 | -5.082 | 13 | -7.106 | 9.975R |
| True ORB, 5% ATR stop, EOD, relative volume >=1 | 12 | -12.428 | 5 | -5.137 | 5.137R |

Every candidate's conservative IS selection score was below zero. The deployed rule won IS only in a relative sense; it did not establish a statistically reliable edge in this short sample.

The true-breakout 4R/120 variant lost 0.501R less than baseline OOS, but it was already negative IS. Calling that an improvement would be OOS hindsight selection.

## Recent-loss diagnosis

For the deployed rule over the 15-session OOS window:

- 14 trades: 10 stops, 3 EOD exits, 1 time-stop exit.
- Stops contributed -10.083R.
- Three EOD runners contributed +5.357R.
- Time-stop contributed +0.849R.
- Net: -3.877R.

For the latest ten sessions, 2026-07-06 through 2026-07-17:

- Net: -2.134R.
- IS-bootstrap expected ten-session result: +1.988R.
- Shortfall from that expectation: -4.122R, roughly -$1,649 at nominal $400 risk before contract-quantization effects.
- Percentile versus the IS bootstrap: 28.7th percentile.
- Fifth-percentile threshold: -8.241R.
- Percentile versus non-overlapping earlier rolling ten-session windows: 55.2nd percentile.

Therefore the last two weeks were materially below EV, but this model does **not** place them in the worst 5% tail. The full 15-session OOS result was around the 20th percentile of an IS resampling distribution, with a nominal expectation shortfall of about $2,752 at $400R. The right-tail payoff makes clusters of -1R stops normal; the bigger concern is that neither baseline nor replacements show reliable recent OOS edge.

If your TradingView run shows substantially worse dates or P&L, it is not reproducing this exact model. The next diagnostic input needed is its Pine source and Strategy Tester trade export.

## Recommendation

1. Do not deploy a new filter based on these OOS results; none passed the requested honest selection protocol.
2. Keep live mode locked.
3. Fix the completed-bar/live-entry timing discrepancy before any paper session is accepted as parity evidence.
4. Obtain at least several years of fresh MNQ/NQ one-minute data. Re-run a pre-registered chronological 70/30 study, then walk-forward stability checks inside the 70% before one final 30% evaluation.
5. Test only a small set of distinct hypotheses: true directional breakout, volatility/noise threshold, time-of-day cutoff, and dynamic EOD runner. Avoid another large grid on the already-consumed historical sample.
6. Reconcile TradingView exactly using the Pine source, timezone/session configuration, commission/slippage assumptions, and exported trades.

## Reproducibility

- Script: `Analysis/scripts/orb_mnq_70_30_research.py`
- Tests: `tests/test_orb_mnq_70_30_research.py`
- Raw MNQ data: `Analysis/output/orb_mnq_70_30/mnq_yahoo_5m_60d.csv`
- NQ cross-check: `Analysis/output/orb_mnq_70_30/nq_yahoo_5m_60d_crosscheck.csv`
- Results: `Analysis/output/orb_mnq_70_30/results.json`
- Trade list: `Analysis/output/orb_mnq_70_30/trades.csv`
- Compact generated report: `Analysis/output/orb_mnq_70_30/report.md`

Command:

`env -u PYTHONPATH .venv/Scripts/python.exe Analysis/scripts/orb_mnq_70_30_research.py`

## Multi-year follow-up and execution correction

The follow-up used a public third-party copy of Databento `NQ.c.0` continuous
five-minute bars from 2023-01-03 through 2026-05-07: 818 complete RTH sessions,
split chronologically into 572 IS sessions and 246 untouched OOS sessions.
Four contiguous folds inside IS supplied the stability gate. Candidate rules
were frozen before the final 30% was evaluated.

The IS-selected replacement, true ORB with the opposite OR extreme as stop,
EOD exit, 10:30 cutoff, and relative opening volume >=1, earned +53.583R IS
but **lost -3.237R OOS**. After correcting the incumbent research model to use
the executable OR-close reference, its OOS mean improvement versus the
deployed opening drive was -0.113R/session (paired-bootstrap 95% CI -0.299 to
+0.059; P(delta>0)=0.105). The unfiltered EOD true ORB also failed OOS at
-0.819R. The corrected deployed opening drive earned +24.591R OOS; its OOS
profit factor was 1.154 and maximum drawdown was 22.410R. Therefore no
replacement is approved.

The completed-bar timing flaw was corrected under TDD. The engine now emits
the entry immediately after receiving the final 09:34 OR bar rather than
waiting until approximately 09:36 for a completed 09:35 bar. Paper modeling
uses the 09:34 close plus configured slippage as the contemporaneous reference.
Live execution then replaces that reference with the broker-confirmed market
fill, recalculates the 4R target from the actual fill and fixed OR stop, and
resynchronizes engine state to the exchange-confirmed position. On the
multi-year data, first-OR close equaled the next five-minute open in only
21.03% of sessions; mean absolute boundary gap was 0.393 points and maximum
was 4.25 points, confirming that the old retroactive assumption was material.

Follow-up artifacts:

- Script: `Analysis/scripts/orb_nq_multiyear_70_30.py`
- Tests: `tests/test_orb_nq_multiyear_research.py`
- Report: `Analysis/output/orb_nq_multiyear/report.md`
- Machine results: `Analysis/output/orb_nq_multiyear/results.json`
- Source file: `Analysis/output/orb_nq_multiyear/nq_databento_5min.csv`

Full repository verification after the correction and overfitting battery: 549 passed, 21 skipped.
Live mode remains locked; no broker order or account mutation was performed.

## Formal overfitting battery

A retrospective 85-strategy matrix was reconstructed from 75 nearby
opening-drive configurations, the next-open execution sensitivity, and nine
true-ORB alternatives. The full 2023-2026 sample is already consumed, so this
is a stability/data-snooping diagnostic rather than a new holdout.

- Corrected incumbent: 755 trades, +55.111R, +0.0730R/trade, PF 1.101, and
  31.213R maximum drawdown.
- CSCV/PBO: 42.9%; sensitivity across six/eight/ten blocks was 40.0%-52.8%.
  This is near the 50% chance boundary and far from strong selection stability.
- Studentized White-style reality check: p=0.2066 for the best reconstructed
  strategy and family-wise p=0.5315 for the incumbent.
- Independent Hansen SPA using `arch` 8.0.0: consistent p-values 0.0630-0.1008
  across stationary/circular bootstraps and 5/10/20-session block lengths.
  None rejects the no-superior-strategy null at 5%.
- Deflated Sharpe: 77.5% using the heuristic correlation-spectrum effective
  trial count of 1.79, 17.9% using all 85 nominal reconstructed trials, and
  11.6% using 234 historically reported trials with reconstructed cross-trial
  variance. None reaches a 95% confirmation bar.
- Neighborhood: 57/75 configurations were profitable in aggregate, evidence
  of a broad weak effect; only 17/75 were profitable overall and in at least
  three calendar-year buckets, evidence of poor regime stability.
- Cost stress: +33.317R under two ticks/$1.25 per side, but -15.235R under four
  ticks/$2.50 per side.
- Block-bootstrap risk: 14.7% probability of a non-positive full-length total;
  95th-percentile maximum drawdown 78.03R and 99th percentile 100.44R.

The strengthened verdict is not "proven overfit" and not "proven robust."
Aggregate profitability and a wide positive neighborhood argue against a
single lucky parameter spike, but multiple-testing significance, selection
stability, regime stability, and cost robustness do not clear strong evidence
thresholds. Treat the strategy as a weak, regime-dependent research incumbent
with substantial overfitting risk, not as an authorized live edge.

Artifacts:

- `Analysis/scripts/orb_overfitting_battery.py`
- `Analysis/scripts/orb_overfitting_spa_verify.py`
- `Analysis/output/orb_overfitting_battery/report.md`
- `Analysis/output/orb_overfitting_battery/results.json`
- `Analysis/output/orb_overfitting_battery/arch_spa_verification.json`
