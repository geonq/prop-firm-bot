# Phase 4 Research Pivot

## Finding

The first Profile 4 sweep did not find a deployable strategy, but it did produce a useful signal: `P4_Sweep_Reclaim_v0` on M3 is the first candidate with a real positive-shape distribution. It has 8,583 trades, WR 35.83%, R 1.92, frequency 3.65/replay day, lag10 autocorr 0.01, net PnL +$139,600, PF 1.08, and Sortino about 1.43. It fails the synthetic Profile 4 WR floor, but it is not random dead weight.

## Interpretation

The project is not failing because five published-style strategies decayed. That decay was foreseeable. Published concepts are not meant to be replicated one-for-one; they are feature sources. The useful lesson is that isolated concepts rarely hold all three constraints at once. NQ can produce high WR at low frequency, or adequate R/frequency at mid-30s WR, but the current seed pack does not produce WR >= 40%, R >= 1.7, and freq >= 2 together.

## Research Direction

The next phase should stop treating papers as complete strategies and use them as a confluence library:

- Extract paper-backed features: trend regime, volatility regime, session timing, VWAP displacement, compression/expansion, opening drive, mean reversion, continuation.
- Translate ICT/discretionary concepts into mechanical features: liquidity sweep, reclaim, displacement/FVG, break of structure, order-block retest, premium/discount, killzone/session filter.
- Search for repeatable confluences that create "fake discretion": a rule-based approximation of waiting for several independent pieces of evidence.
- Test across multiple timeframes and instruments, then promote only if IS/OOS and regime splits survive.

## Guardrails

- Use full-range exports only for falsification and feature diagnosis. Do not tune from full-sample winners.
- For candidate promotion, predeclare IS/OOS before tuning. Default NQ deep-history split: IS 2000-2018, OOS 2019-present; adjust only if TV history starts later.
- Track ablations. A confluence only matters if each component's contribution is visible.
- Limit combination search to named feature families; unconstrained threshold mining will overfit.
- Keep `P4_Sweep_Reclaim_v0 M3` as the benchmark distribution until a new candidate beats it on raw shape and prop-firm replay.
