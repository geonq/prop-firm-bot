---
type: literature review
date: 2026-04-30
author: Codex
status: first-pass; primary sources and publisher/official pages only
scope: barrier math, convex/asymmetric payoff structures, implied volatility, NQ/MNQ futures, and intraday futures strategy hypotheses
---

# Literature Review: Barriers, Volatility, and NQ Futures

## Executive Conclusion

The best mathematical framing for this project is not "find a high win-rate strategy." It is a finite-horizon, path-dependent first-passage problem with capped fee downside, a moving/trailing lower barrier, a profit-target upper barrier, and phase-dependent payout rules. The strongest literature support is:

1. First-passage / gambler's-ruin math explains why pass probability depends on barrier distance, step distribution, variance, drift, and time-to-absorption.
2. Asymmetric payoffs are dangerous to reason about with simple win-rate/R:R intuition. Holding EV constant, payoff skew changes ruin probability and game duration.
3. Drawdown constraints change optimal sizing; they are not just a post-hoc risk check.
4. NQ/MNQ is a legitimate target because CME identifies NQ as a liquid benchmark contract and the academic futures literature finds E-mini equity-index futures are important price-discovery venues.
5. Implied volatility should enter the engine as a regime variable and risk scaler, not as proof of edge. The most testable feature is the gap between implied and realized variation, plus short-dated NDX option-implied volatility around weekly expiries.
6. The most promising initial strategy families to test are opening-range breakout, intraday momentum, volatility-scaled trend following, and conditional overnight-gap/opening-hour momentum/reversal.

No paper found gives a direct "prop firm payout extraction" formula. The edge has to come from combining these literatures with exact prop-firm rules and strict out-of-sample validation.

## Papers and Sources Read

| Source | What It Adds | Direct Use In Engine |
|---|---|---|
| Whelan (2025), `Ruin Probabilities for Strategies with Asymmetric Risk` | Directly studies repeated asymmetric win/loss payoffs with target and ruin states. Shows payoff asymmetry changes ruin probability, expected final wealth, and duration even at constant EV. | Calibration sanity checks for zero/positive/negative EV synthetic trade distributions. Supports replacing naive "higher RR is better" or "higher WR is better" with barrier-aware optimization. |
| Redner (2023), `A First Look at First-Passage Processes` | General first-passage foundations: splitting probabilities, finite intervals, first-passage times. | The simulator's eval pass/breach logic is a first-passage system. Use this as the conceptual model for tests around target hit, MLL hit, and timeouts. |
| Lorek (2017), `Generalized Gambler's Ruin Problem` | Explicit formulas for generalized ruin probabilities via Markov-chain duality. | Useful if we later want exact Markov-chain benchmarks for discrete account-state grids instead of only Monte Carlo. |
| Cherny & Obloj (2013), `Portfolio optimisation under non-linear drawdown constraints` | Drawdown constraints can be transformed into modified utility / optimal policy problems. | Supports treating `size(...)` as a first-class policy optimized under drawdown, not a fixed risk-per-trade constant. |
| Alexander & Baptista (2006), `Portfolio selection with a drawdown constraint` | Shows drawdown constraints materially alter mean-variance-efficient portfolios. | Warning: maximizing EV alone is wrong under prop rules; drawdown state must be in the objective. |
| Broadie, Chernov & Johannes (2009), `Understanding Index Option Returns` | Nonlinear option payoffs create extreme sampling uncertainty. Apparent option-return edges can vanish under model-consistent comparison. | Prevents overfitting. Prop-firm payouts are also nonlinear; historical Sharpe/pass-rate estimates need simulation confidence intervals and stress tests. |
| Bollerslev, Tauchen & Zhou (2009), `Expected Stock Returns and Variance Risk Premia` | Model-free implied-vs-realized variation predicts future aggregate returns; accurate realized variation needs high-frequency intraday data. | Add implied-realized volatility spread and realized intraday variance as regime features for NQ strategies. |
| Cboe Nasdaq-100 Implied Volatility Index methodology (2025) | Official construction of short-dated NDX implied volatility indices from weekly NDX options. | Use Cboe CNIV/VXN-style data as external volatility regime input. Avoid copying restricted index content; use properly licensed data. |
| CME NQ/MNQ contract specs | NQ = `$20 x Nasdaq-100`, 0.25 tick; MNQ = `$2 x Nasdaq-100`, 0.25 tick. | Correct P&L, sizing, and tick math. MNQ is likely better for fine-grained sizing under drawdown constraints. |
| Kurov & Lasser (2009), `Price Dynamics in the Regular and E-Mini Futures Markets` | E-mini S&P 500 and Nasdaq-100 futures appear to initiate price discovery; local/informed trades matter. | Supports focusing on NQ/MNQ as primary trade venue rather than QQQ if execution access is futures-only. |
| Yu, Rentzler & Wolf (2005), `Nasdaq-100 Index Futures: Intraday Momentum or Reversal?` | Nasdaq-100 futures show both intraday momentum and reversal conditional on prior day/night returns and Monday effects. | Test conditional opening-hour rules: yesterday return, overnight return, day-of-week, bull/bear regime. |
| Gao, Han, Li & Zhou (2015), `Intraday Momentum` | First half-hour return predicts last half-hour return; effect is stronger on volatile, high-volume, recession, and macro-news days. | Test first-30/60-min NQ return as a feature for later-session directional bias; combine with volatility/volume filters. |
| Holmberg, Lonnback & Lundstrom (2013), `Assessing profitability of intraday ORB strategies` | ORB can be tested using OHLC assumptions and bootstrap; profitability may be regime/time sensitive. | Build ORB backtest with bootstrap/permutation significance tests, not just raw P&L. |
| Tsai et al. (2019), `Timely Opening Range Breakout on Index Futures Markets` | One-minute index-futures data; active hours aligned to underlying stock market; TORB reportedly works across DJIA, S&P 500, NASDAQ, HSI, and TAIEX. | Strong candidate for Phase 4 NQ baseline: optimize opening-range probing time, but validate out-of-sample and after costs. |
| Moskowitz, Ooi & Pedersen (2012), `Time Series Momentum` | Time-series momentum exists across liquid futures at 1-12 month horizons; performs best during extreme markets. | Not directly intraday, but supports trend/momentum as a futures risk premium. Add volatility scaling and avoid assuming intraday edge from long-horizon evidence. |

## Important Mathematical Takeaways

### 1. The prop-firm eval is a first-passage problem.

The account path terminates when it first hits an upper target or lower loss barrier, except TopStep/Lucid add path-dependent rules: trailing MLL, consistency, daily/session boundaries, payout cycles, and funded resets. So the engine should be tested using first-passage language:

- splitting probability: probability of hitting target before breach
- first-passage time: distribution of days/trades until pass or breach
- survival probability: probability of neither pass nor breach by max days
- overshoot: account value when a trade crosses target or MLL
- moving barrier: MLL as function of highest end-of-day balance

### 2. Zero-EV strategies do not have one universal pass rate.

For symmetric zero-EV random walks with fixed barriers, success probability is roughly starting buffer divided by total target interval. But asymmetric jumps, overshoot, time limits, and consistency rules break the simple intuition. Whelan's asymmetric-ruin paper supports Claude's simulation result: skew changes time-to-absorption and ruin behavior even when expected value is held constant.

### 3. The high-WR / low-RR thesis is incomplete.

High-WR / low-RR reduces trade-level variance, which helps avoid the lower barrier. But if each win is too small, the strategy times out before target or needs many trades, accumulating commission/slippage and regime risk. The project should search for the optimal middle, not a corner.

### 4. Sizing is part of the strategy.

The drawdown literature supports treating the sizing function as a policy under constraints. A fixed `$ risk per trade` backtest is insufficient. For prop firms, optimal sizing likely changes with:

- remaining MLL buffer
- distance to target
- consistency state
- days/trades left in evaluation window
- funded payout eligibility
- current volatility / implied volatility regime
- contract granularity: MNQ enables smoother sizing than NQ

### 5. Nonlinear payoff systems are easy to overfit.

Broadie, Chernov & Johannes are a warning for this project: nonlinear payoffs can generate extreme historical returns and unstable samples. For us, a 30-50% pass-rate estimate from one backtest is not enough. Every candidate strategy needs:

- bootstrap confidence intervals
- reshuffled-trade Monte Carlo
- walk-forward validation
- cost/slippage sensitivity
- adverse-regime stress tests
- independent validation on a later period

## NQ/MNQ-Specific Notes

Official CME contract math:

- NQ contract multiplier: `$20 x Nasdaq-100 Index`.
- NQ tick: 0.25 index points = `$5` per tick.
- MNQ contract multiplier: `$2 x Nasdaq-100 Index`.
- MNQ tick: 0.25 index points = `$0.50` per tick.

Implementation implication: start all strategy research on MNQ-equivalent sizing, then map to NQ only if account rules or target speed require it. MNQ lets the engine tune risk more precisely around MLL and consistency constraints.

Academic support for using the futures venue:

- Kurov & Lasser find price discovery appears to be initiated in E-mini index futures for S&P 500 and Nasdaq-100.
- Yu/Rentzler/Wolf find Nasdaq-100 futures opening-hours behavior has conditional momentum/reversal structure.

This supports using NQ/MNQ as the primary instrument rather than treating futures as a thin derivative of QQQ.

## Implied Volatility / Volatility Data Thesis

The volatility literature suggests a clean feature set:

1. Realized intraday volatility from 1-minute NQ/MNQ returns.
2. Short-term implied volatility from NDX options, using Cboe VXN/CNIV-style methodology if licensed data is available.
3. Implied-realized spread: implied volatility minus recent realized volatility.
4. Volatility regime: low/medium/high realized vol, low/medium/high implied vol.
5. Volatility shock: change in VXN/CNIV or short-dated NDX IV from prior day.
6. Event flags: FOMC, CPI, NFP, major earnings concentration days for Nasdaq mega-cap components.

Hypothesis: prop-firm pass probability improves when strategy parameters are conditioned on volatility regime. High-volatility days may help target speed but increase MLL breach risk; low-volatility days may improve survival but cause timeout. The engine should optimize this tradeoff directly.

## Strategy Hypotheses To Test

### H1: Timely Opening Range Breakout on NQ

Use first `x` minutes after cash equity open to define range. Enter breakout only if range width, volume, and volatility filters are acceptable. Sweep `x` across 1, 3, 5, 10, 15, 30 minutes. Test fixed RR, volatility-scaled target/stop, and time exit.

Required validation:

- pre/post-2020 split
- high/low VXN or CNIV regime split
- macro-event vs non-event split
- commission/slippage sensitivity
- prop-firm pipeline Monte Carlo, not just raw strategy P&L

### H2: First-30/60-Minute Intraday Momentum

Following Gao et al., test whether early-session NQ return predicts later-session NQ return. Adapt for futures: compare overnight close-to-open return, first 30 minutes, first 60 minutes, and final 30/60/120-minute windows.

Filters:

- high realized vol days
- high volume days
- macro-news days
- Monday / day-of-week effects
- prior-day trend and overnight gap direction

### H3: Opening-Hour Conditional Momentum/Reversal

Following Yu/Rentzler/Wolf, test conditional behavior based on:

- prior regular-session return
- overnight Globex return
- sign and size of opening gap
- day of week
- bull/bear regime from longer moving average

This may be more robust than a single universal ORB rule because Nasdaq-100 futures can show both momentum and reversal depending on state.

### H4: Volatility-Scaled Time-Series Momentum

Long-horizon TSMOM literature is not an intraday edge by itself, but volatility scaling matters. Test whether scaling position size by recent realized volatility improves pass probability and reduces MLL breach probability versus fixed risk-per-trade.

### H5: Implied-Realized Volatility Regime Switch

Use short-dated NDX implied volatility or VXN/CNIV proxy to choose between:

- breakout mode when implied and realized vol are high and expanding
- mean-reversion/no-trade mode when implied vol is high but realized intraday movement is failing
- grinder mode when vol is low but range behavior is clean

This is a strategy-selection layer, not a standalone signal.

## Data Requirements

Minimum viable Phase 4 data:

- 1-minute NQ and MNQ OHLCV, continuous front contract, correctly rolled.
- Session labels: Globex, pre-cash, cash open, lunch, cash close, settlement.
- Contract metadata from CME: tick size, tick value, multiplier, hours.
- Commission/slippage model for NQ and MNQ.

High-quality validation data:

- bid/ask or top-of-book snapshots around entry/exit times.
- historical NDX option-implied volatility data, VXN, or Cboe CNIV-style short-dated IV.
- macro calendar: CPI, FOMC, NFP, PPI, major Fed speakers.
- Nasdaq mega-cap earnings calendar for high-index-weight names.

## What To Add To The Engine

1. `BarrierMathOracle`: deterministic tests for simple fixed-barrier random walks where closed forms exist.
2. `FirstPassageMetrics`: pass probability, breach probability, timeout probability, time-to-pass, time-to-breach, overshoot, and barrier touched first.
3. `RegimeFeatures`: realized volatility, volume percentile, opening range width, overnight gap, VXN/CNIV proxy, macro-event flag.
4. `StrategyFamily`: ORB, intraday momentum, conditional momentum/reversal, volatility-scaled momentum.
5. `ValidationProtocol`: bootstrap, walk-forward, Monte Carlo reshuffle, and prop-firm pipeline EV.

## Sources

- Whelan, Karl. `Ruin Probabilities for Strategies with Asymmetric Risk`, MPRA Paper 126349, 2025. https://mpra.ub.uni-muenchen.de/126349/1/MPRA_paper_126349.pdf
- Redner, Sidney. `A First Look at First-Passage Processes`, Physica A 631, 128545, 2023. https://arxiv.org/abs/2201.10048
- Lorek, Pawel. `Generalized Gambler's Ruin Problem: Explicit Formulas via Siegmund Duality`, Methodology and Computing in Applied Probability, 2017. https://link.springer.com/article/10.1007/s11009-016-9507-6
- Cherny, Vladimir and Obloj, Jan. `Portfolio optimisation under non-linear drawdown constraints in a semimartingale financial model`, Finance and Stochastics, 2013. https://arxiv.org/abs/1110.6289
- Alexander, Gordon J. and Baptista, Alexandre M. `Portfolio selection with a drawdown constraint`, Journal of Banking and Finance, 2006. https://experts.umn.edu/en/publications/portfolio-selection-with-a-drawdown-constraint
- Broadie, Mark, Chernov, Mikhail, and Johannes, Michael. `Understanding Index Option Returns`, Review of Financial Studies, 2009. https://academic.oup.com/rfs/article/22/11/4493/1568222
- Bollerslev, Tim, Tauchen, George, and Zhou, Hao. `Expected Stock Returns and Variance Risk Premia`, Review of Financial Studies, 2009. https://econpapers.repec.org/RePEc:oup:rfinst:v:22:y:2009:i:11:p:4463-4492
- Cboe Global Indices. `Cboe Nasdaq-100 Implied Volatility Index Series Methodology`, 2025. https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Nasdaq_100_Implied_Volatility_Index_Series_Methodology.pdf
- CME Group. `E-mini Nasdaq-100 Futures Contract Specs`. https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html
- CME Group. `Micro E-mini Nasdaq-100 Futures Contract Specs`. https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html
- Kurov, Alexander and Lasser, Dennis J. `Price Dynamics in the Regular and E-Mini Futures Markets`, Journal of Financial and Quantitative Analysis, 2009. https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/price-dynamics-in-the-regular-and-emini-futures-markets/7DFA66D1DDCE701D5713CA6B92E18DF2
- Yu, Susana, Rentzler, Joel, and Wolf, Avner. `Nasdaq-100 Index Futures: Intraday Momentum or Reversal?`, SSRN, 2005. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=712168
- Gao, Lei, Han, Yufeng, Li, Sophia Zhengzi, and Zhou, Guofu. `Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return`, SSRN, 2015. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752
- Holmberg, Ulf, Lonnback, Carl, and Lundstrom, Christian. `Assessing the profitability of intraday opening range breakout strategies`, Finance Research Letters, 2013. https://www.sciencedirect.com/science/article/abs/pii/S1544612312000438
- Tsai, Yi-Cheng et al. `Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets`, IEEE Access, 2019. https://ntut.elsevierpure.com/en/publications/assessing-the-profitability-of-timely-opening-range-breakout-on-i/
- Moskowitz, Tobias J., Ooi, Yao Hua, and Pedersen, Lasse Heje. `Time Series Momentum`, Journal of Financial Economics, 2012. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463
