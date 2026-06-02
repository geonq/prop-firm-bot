---
type: strategy candidate spec
date: 2026-05-06
status: Phase 4 candidate; unvalidated until TradingView export replay passes Profile 4 gates
target_profile: Robust trend
---

# NQ Robust Trend V0

## Target Cell

This candidate exists only to test the Phase 3.5 target cell:

- WR: 0.40-0.50
- Average winner / average loser: 1.7-2.3, target 2.0R
- Frequency: 2-4 trades per RTH session
- Outcome autocorrelation: lag-10 win/loss autocorr <= 0.3
- Primary replay: TopStep Consistency, Back2Funded=3, payout_cap=5, Adaptive sizing from `Analysis/output/target_cell_catalog/cells.csv`

The catalog row is:
`study=sizing, sizing=Adaptive, win_rate=0.45, rr_ratio=2.0, trades_per_day=3, payout_path=topstep_consistency`.
Fallback params for fresh checkouts without ignored `Analysis/output/`: `eval_base=150`, `funded_base=400`, `buffer_full_frac=0.04`, `buffer_floor=0.25`, `post_payout_shrink=1.0`.

## Hypothesis

NQ has enough intraday continuation after volatility-normalized directional
impulses to support a low-to-mid WR, 2R payoff profile without needing order
book or options-flow data for the first falsification pass.

This is not ORB/TORB. It does not key off a fixed opening range. It trades
only when trend direction, normalized momentum, and ATR regime agree.

## TradingView Candidate

Local draft: `PineScripts/nq_robust_trend_v0.pine` (gitignored by policy).

Recommended first chart setup:

- Symbol: `CME_MINI:NQ1!` or `CME_MINI:MNQ1!`
- Timeframe: 5 minutes first, then 15 minutes as a robustness check
- Session: RTH only, `0835-1455` exchange time
- Commission/slippage: configure realistically in TradingView Strategy Tester
- Export: Strategy Tester trade list XLSX into `TVExports/`

Core logic:

- Direction filter: EMA fast vs EMA slow
- Entry trigger: close-to-lookback ROC normalized by ATR crosses a threshold in trend direction
- Volatility filter: ATR/close must sit inside a configurable band
- Risk model: ATR stop, fixed 2R target, optional time stop, one open position, cooldown between trades

## Pass / Fail Gate

After export, run:

```bash
.venv/bin/python Analysis/scripts/tv_topstep_replay_probe.py \
  --xlsx TVExports/<export>.xlsx \
  --risk-amount <dollar-risk-if-export-has-no-R-column>
```

Pass only if the probe prints:

- `profile4=True`
- TopStep result is not `combine_breach` or `combine_timeout`
- Payout result survives both capped default and `--uncapped` sensitivity

If `profile4=False`, tune only the strategy parameters that affect the miss:

- WR too high / R too low: widen target or tighten entry filter
- WR too low / R acceptable: add regime filter before increasing risk
- Frequency too low: shorten momentum/EMA lengths or lower threshold
- Frequency too high or autocorr too high: increase cooldown or session filters

Do not optimize directly on TopStep EV before the raw distribution lands inside
the target cell; otherwise the process overfits account mechanics instead of
finding a replayable market distribution.
