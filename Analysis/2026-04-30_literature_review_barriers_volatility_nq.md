---
type: literature review
date: 2026-04-30
compressed: 2026-05-05
status: compact conclusions only
---

# Barriers, Volatility, And NQ Futures — Compact Review

## Conclusion

Model prop-firm accounts as finite-horizon, path-dependent first-passage
problems with capped fee downside, moving lower barriers, profit targets, and
phase-dependent payout rules. No paper found gives a direct prop-firm payout
formula; the edge must be validated by exact rule simulation plus strict
out-of-sample tests.

## Keep These Takeaways

- Pass/breach/timeout is first-passage math, not normal backtest scoring.
- Zero-EV strategies do not have one universal pass rate; skew, overshoot,
  time limits, trailing drawdown, and consistency rules change outcomes.
- High-WR / low-R:R is incomplete: too-small wins can timeout before target.
- Sizing is part of the strategy because drawdown constraints alter optimal
  policy.
- Nonlinear payoff systems are easy to overfit; require bootstrap, walk-forward,
  shuffled-trade Monte Carlo, cost sensitivity, and adverse-regime stress.
- NQ/MNQ are valid primary venues; CME specs and futures price-discovery
  literature support using the futures contract directly.
- Volatility/IV belongs first as regime and sizing context, not proof of edge.

## Source Map

- First-passage / ruin: Whelan 2025, Redner 2023, Lorek 2017.
- Drawdown constraints: Cherny & Obloj 2013; Alexander & Baptista 2006.
- Nonlinear payoff caution: Broadie, Chernov & Johannes 2009.
- IV/RV regime: Bollerslev, Tauchen & Zhou 2009; Cboe CNIV/VXN methodology.
- NQ/MNQ contract math: CME official specs.
- NQ futures behavior: Kurov & Lasser 2009; Yu/Rentzler/Wolf 2005;
  Gao/Han/Li/Zhou 2015.
- ORB/TORB papers were reviewed, but Georg rejected ORB/TORB as candidate
  strategy; keep only as simulator falsification baseline.

## Current Application

The project moved from Level-1 opening-range ideas to L2/order-flow tests.
Use this review only for conceptual framing. Current empirical state lives in:

- `Analysis/2026-05-05_l2_event_study.md`
- `Analysis/scripts/databento_l2_event_study.py`
- `Dashboard/app.py`
