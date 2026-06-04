# Order-Flow / L2 Research Track

Parked future research direction as of 2026-06-04.

## Status

The prop-firm bot repo is parked. This track remains the most plausible future path if Georg returns to automated futures work, but it is not active work right now.

Reason: order-flow/L2 inputs are more objective than discretionary SMT, daily bias, and chart-selection rules, but the next life priority is not an abstract L2 study phase. Resume only when there is a concrete mechanical rule or live observation set worth capturing and replaying.

## Data Contract

Minimum useful capture:

- Instruments: `NQ` and `ES`
- Feed: Rithmic preferred
- Platform: Quantower, R|Trader Pro, Sierra Chart, ATAS, Jigsaw, Bookmap, or equivalent
- Streams: trades/tape plus Level 2 depth
- Depth: top 10 levels minimum; MBO if available
- Timestamps: millisecond precision preferred
- Sessions: RTH plus key open windows

## First Features

- multi-level queue imbalance
- order-flow imbalance
- aggressive buy/sell delta
- absorption near recent highs/lows
- depth replenishment after sweep
- ES/NQ confirmation and divergence

## Gate

Do not build a bot from this track until a captured-data signal produces a dated trade distribution that survives prop-firm replay with documented IS/OOS separation.

Project-level return condition: one mechanical entry rule with at least 30 live trades and plausible Profile 4 geometry: 40-50% win rate, reward/risk at least 2.0, and roughly 2-4 trades per day.
