# Order-Flow / L2 Research Track

Active research direction as of 2026-06-02.

## Decision

Park discretionary Model A automation and prior paper/public-strategy attempts. Continue from measurable order-flow data instead of trying to encode subjective SMT, daily bias, and chart-selection rules.

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
