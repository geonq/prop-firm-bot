---
type: strategy shortlist
date: 2026-04-30
author: Codex
status: first-pass research-to-test plan
source_review: Analysis/2026-04-30_literature_review_barriers_volatility_nq.md
---

# NQ/MNQ Strategy Shortlist for the Prop-Firm Payoff Model

## Executive Decision

The literature does not provide a direct "prop-firm extraction strategy." It provides the math for the account path problem and several NQ/MNQ strategy families worth testing. The right research target is not maximum raw Sharpe and not maximum win rate. The target is the account path shape that best exploits the asymmetric payoff:

- hit the profit target before the loss barrier
- avoid slow timeout
- avoid one-trade consistency violations
- keep drawdown survivable through bad streaks
- preserve enough upside in funded mode to collect payouts

Georg's current warning is important: plain ORB is probably unprofitable as a standalone edge. The current best first build is still a conditional opening-range / opening-hour strategy stack, but only as a fast falsification baseline:

1. Use volatility and opening-range filters to decide whether the day is tradable.
2. Use timely opening range breakout as the primary entry model.
3. Add conditional momentum/reversal state from prior regular-session return, overnight gap, first 30/60 minute return, and day-of-week.
4. Size with MNQ-equivalent granularity and let the simulator optimize phase-aware risk.

This fits the project better than a generic high-win-rate grinder or a high-R:R lottery. The founding-thesis sanity check already showed the likely optimal region is the middle: roughly 1:1 to 2:1 risk/reward, with enough variance to reach the target but not so much that consistency and drawdown rules dominate. The first LucidFlex synthetic probe (`Analysis/2026-04-30_lucidflex_eval_probe_orb_proxy.md`) confirms the main complication: lower-risk ORB-like profiles tend to timeout, while higher-risk profiles pass more often but breach at uncomfortable rates.

## Ranking

| Rank | Candidate | Role | Why It Fits The Prop-Firm Path | Main Risk |
|---:|---|---|---|---|
| 1 | Conditional Timely Opening Range Breakout | Primary strategy family | Produces clean finite-horizon trades, can reach target quickly, parameterizes naturally by opening range width, volatility, stop, and target. | False breakouts during noisy opens; may overfit opening window. |
| 2 | Opening-Hour Conditional Momentum/Reversal | State selector | Literature says Nasdaq-100 futures can show momentum or reversal depending on prior day/night state. This can decide whether ORB should trade continuation, fade, or stand down. | More features means higher overfit risk. |
| 3 | First-30/60-Minute Intraday Momentum | Secondary signal | Simple testable feature: early-session return predicts later-session direction in related literature. Useful as confirmation or afternoon trade, not necessarily as the only strategy. | Late-session entries may be too slow for eval target speed. |
| 4 | Volatility-Scaled Momentum | Sizing/risk layer | Drawdown and first-passage literature supports making size state-dependent. Volatility scaling may reduce breach probability without killing target speed. | Can shrink position exactly when the account needs target speed. |
| 5 | Implied-Realized Volatility Regime Switch | Meta-filter | IV/RV spread can choose between breakout, reversal, and no-trade modes. This is a regime layer, not a standalone entry. | Requires licensed/clean IV data and careful timestamp alignment. |

## Strategy 1: Conditional Timely Opening Range Breakout

### Thesis

Opening range breakout is the best first strategy to test because it directly matches the finite-horizon barrier problem. It creates a bounded decision window, clear stop geometry, and enough intraday movement to potentially reach prop-firm targets without requiring hundreds of small wins.

### Backtestable Rule Template

Define the opening range from the regular cash equity open at 09:30 New York time.

For each candidate opening window `x`, compute:

- `range_high`: highest NQ/MNQ price from 09:30 to 09:30 + `x`
- `range_low`: lowest NQ/MNQ price from 09:30 to 09:30 + `x`
- `range_width_points`: `range_high - range_low`
- `opening_return`: return from prior regular-session close to end of opening window
- `realized_vol_open`: realized volatility over the opening window

Enter long when price breaks above `range_high + buffer_ticks` after the range window. Enter short when price breaks below `range_low - buffer_ticks`.

Base exit:

- stop at opposite side of range, midpoint of range, or ATR-based stop
- target at `rr * stop_distance`
- time exit at fixed clock time if neither stop nor target hits
- max one completed trade per day for the first pass

### Parameter Sweep

| Parameter | Initial Values |
|---|---|
| Opening window `x` | 1, 3, 5, 10, 15, 30 minutes |
| Breakout buffer | 0, 1, 2, 4 ticks |
| Stop mode | opposite range side, range midpoint, 0.5x opening range, 1.0x ATR |
| Risk/reward | 0.75, 1.0, 1.25, 1.5, 2.0 |
| Time exit | 10:30, 11:30, 12:00, 15:45 New York |
| Max trades/day | 1 first; 2 only after baseline |
| Range-width filter | percentile 20-80, 30-70, 40-80 |
| Volatility filter | realized vol percentile buckets: low, medium, high |

### Required Data

- 1-minute NQ or MNQ OHLCV, continuous front contract, correctly rolled
- New York session labels
- tick size and multiplier
- commission/slippage assumptions
- optional: bid/ask spread around 09:30-10:30

### Validation Criteria

This strategy is worth keeping only if it survives all of these:

- positive or near-flat raw expectancy after realistic costs
- prop-firm simulator improves net EV versus random zero-EV baseline
- pass rate improvement is not caused by one huge outlier trade
- TopStep consistency rule is not regularly violated
- walk-forward results do not collapse after parameter selection
- shuffled-trade Monte Carlo preserves most of the pass-rate advantage

## Strategy 2: Opening-Hour Conditional Momentum/Reversal

### Thesis

The literature review found support for conditional momentum/reversal in Nasdaq-100 futures. That means a universal "always breakout" or "always fade" rule is probably too crude. The better model is a state machine that chooses continuation, reversal, or no-trade before the entry fires.

### Backtestable Rule Template

Before the cash open, compute:

- prior regular-session return
- overnight Globex return
- opening gap relative to prior regular-session close
- day of week
- longer regime: above/below moving average or recent multi-day return
- realized volatility percentile

Then classify the day:

- continuation mode: trade breakouts in direction of early pressure
- reversal mode: fade failed opening extension after a threshold move
- no-trade mode: skip when state is historically noisy or too expensive

The first version should use this only as a filter around Strategy 1. Do not build a fully separate complex model until the ORB baseline exists.

### Parameter Sweep

| Parameter | Initial Values |
|---|---|
| Prior-session return bucket | negative, flat, positive; also percentile buckets |
| Overnight return bucket | negative, flat, positive; also percentile buckets |
| Gap size | small, medium, large by rolling percentile |
| Day of week | Monday vs non-Monday first; then full weekday |
| Regime lookback | 5, 20, 60 trading days |
| Continuation trigger | ORB breakout, first 30-min continuation |
| Reversal trigger | failed breakout, return inside range, gap exhaustion |

### Required Data

- session-separated NQ/MNQ OHLCV
- regular-session close and overnight session boundaries
- day-of-week calendar
- enough years to avoid overfitting one volatility regime

### Validation Criteria

The state selector must beat the unconditional ORB baseline out of sample. If it only improves in sample, discard it or reduce it to a simpler volatility/range filter.

## Strategy 3: First-30/60-Minute Intraday Momentum

### Thesis

The first half-hour / first hour return can be tested as a clean, low-complexity directional feature. For this project, it is most useful as confirmation for ORB or as a second-session trade, not necessarily as the primary eval-passing engine.

### Backtestable Rule Template

Compute return from:

- 09:30 to 10:00
- 09:30 to 10:30
- Globex session open to 09:30

Enter in the direction of the early return if magnitude exceeds a threshold and volatility/volume filters agree. Exit by fixed target/stop or time exit into the final hour.

### Parameter Sweep

| Parameter | Initial Values |
|---|---|
| Signal window | first 30 minutes, first 60 minutes |
| Entry time | 10:00, 10:30, 11:00 |
| Signal threshold | top/bottom 30%, 20%, 10% of rolling early returns |
| Stop | ATR-based, previous swing, opening-range midpoint |
| Target | 1.0R, 1.5R, 2.0R |
| Time exit | 12:00, 15:30, 15:45 |

### Required Data

- 1-minute OHLCV
- volume percentile by time of day
- event calendar if available

### Validation Criteria

Keep it only if it adds incremental prop-firm EV after ORB is already in the model. If it increases trade count but worsens breach probability, reject it.

## Strategy 4: Volatility-Scaled Momentum

### Thesis

This is not the first entry model. It is a risk policy. Drawdown-constrained portfolio literature supports changing risk based on volatility and current drawdown state. For a prop-firm account, this belongs in the sizing function and simulator, not only in TradingView performance metrics.

### Backtestable Rule Template

Take the signal from Strategy 1, 2, or 3. Scale risk per trade by:

- current realized volatility
- opening-range width
- remaining drawdown buffer
- distance to eval target
- days/trades left before timeout
- phase: eval vs funded

Use MNQ-equivalent risk units first, then map to NQ if account size and contract caps require it.

### Parameter Sweep

| Parameter | Initial Values |
|---|---|
| Base risk | 0.25%, 0.5%, 1.0% of account notional/eval fee-equivalent budget |
| Vol target lookback | 10, 20, 60 sessions |
| Vol floor/ceiling | clamp to avoid infinite size on low-vol days |
| Buffer multiplier | linear, square-root, step function |
| Phase risk | eval risk > funded risk, equal, funded risk > eval risk |

### Required Data

- same trade data as signal strategy
- realized volatility series
- exact firm contract caps and drawdown mechanics

### Validation Criteria

Volatility scaling is useful only if it improves account-level EV or reduces breach probability without causing timeout to dominate. Raw backtest Sharpe is secondary.

## Strategy 5: Implied-Realized Volatility Regime Switch

### Thesis

The IV/RV literature supports implied-realized volatility spread as a regime feature. In this project it should decide which strategy mode is allowed, not create entries by itself.

### Backtestable Rule Template

For each day, compute:

- recent realized intraday volatility
- short-dated NDX implied volatility proxy if licensed data exists
- IV minus RV spread
- day-over-day IV shock

Mode selection:

- breakout mode when realized and implied volatility are expanding and opening range is tradable
- reversal/no-trade mode when implied volatility is high but intraday realized movement is failing
- grinder/no-trade mode when volatility is too low to reach eval targets efficiently

### Parameter Sweep

| Parameter | Initial Values |
|---|---|
| RV lookback | 5, 10, 20 sessions |
| IV proxy | VXN, CNIV-style short-dated NDX IV, or licensed equivalent |
| IV/RV bucket | low, medium, high by rolling percentile |
| IV shock | 1-day change percentile |
| Mode mapping | breakout, reversal, no-trade |

### Required Data

- licensed NDX implied volatility series or approved proxy
- strict timestamp alignment so no future IV information leaks into signals
- realized volatility from intraday futures data

### Validation Criteria

This layer must improve walk-forward stability. If it only finds a prettier in-sample segmentation, discard it until more data is available.

## Prop-Firm Simulator Metrics Required For Every Candidate

Raw strategy metrics are insufficient. Every candidate must be scored through the account simulator with at least:

- pass probability
- breach probability
- timeout probability
- expected days to pass
- expected days to breach
- probability of violating consistency rule
- average largest winning day as percent of total profit
- net EV after eval fees, resets if modeled, and payout split
- funded-phase expected payout count before breach
- confidence interval across Monte Carlo seeds

The strategy should be rejected if it looks good only on raw P&L but fails on path metrics.

## Initial Research Sequence

1. Build the conditional TORB/ORB baseline first.
2. Run it without prop-firm sizing to measure raw trade distribution: win rate, average win, average loss, R:R, trade frequency, max losing streak, time-of-day behavior.
3. Feed the trade sequence into the prop-firm simulator with fixed MNQ-equivalent sizing.
4. Add phase-aware sizing and compare account-level EV.
5. Add conditional momentum/reversal filters and require out-of-sample improvement over baseline.
6. Add volatility regime filters only after the simple baseline is measured.

## What Not To Do

- Do not chase the highest win rate. Slow high-WR/low-R strategies can timeout before target.
- Do not chase huge R:R. High-R lottery behavior can pass sometimes but often violates consistency or breaches quickly.
- Do not optimize directly on the whole sample and then trust the best parameter cell.
- Do not use TradingView strategy tester P&L as the final objective. The final objective is prop-firm net EV.
- Do not build the execution bot until this shortlist has been tested through the simulator.

## Immediate Next Artifact

Before Pine Script or Python strategy code, create a compact strategy-spec file for the first baseline:

`Analysis/strategy_specs/torb_orb_v0.md`

It should define exact session times, entry triggers, stop/target rules, no-trade filters, parameter grid, and expected export fields. That spec becomes the contract for the first TradingView/Python implementation.
