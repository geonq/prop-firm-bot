---
type: phase3 deployment completion audit
date: 2026-05-06
status: complete for deployment-grade pre-strategy engine validation
scope: current-rule compliance helpers and export auditability
---

# Phase 3 Deployment Completion Audit

This closes Phase 3/3.5 at the stricter "deployment-prep" bar. The engine is
still not a live bot; it now exposes rule/compliance gates needed before any
strategy can be considered deployable.

## Fresh Rule Check

- TopStep news trading is not encoded as an EV rule; current public TopStep
  material does not impose a blanket news embargo in the checked sources.
- TopStep price-limit proximity is encoded via
  `TopStepNoFee50K.is_within_price_limit_buffer()`. Callers must pass current
  CME product/session limits because TopStep states limits vary and change.
- LucidFlex news trading is not encoded as a blocker; current checked Lucid
  material allows genuine scalping/news-style activity but prohibits HFT and
  microscalping.
- LucidFlex microscalping is encoded via 5-second / >50% positive-profit share
  helpers on `LucidFlex50K`.
- LucidFlex HFT is qualitative in public text, so the code exposes a
  configurable order-rate hard stop rather than inventing an official number.
- Source URLs checked: TopStep price limits
  `https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit`,
  TopStep trading hours
  `https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade`,
  Lucid permitted activities
  `https://support.lucidtrading.com/en/articles/11404728-permitted-activities`,
  Lucid allowed trading times
  `https://support.lucidtrading.com/en/articles/11404729-allowed-trading-times`,
  Lucid microscalping
  `https://support.lucidtrading.com/en/articles/11404742-prohibited-microscalping`,
  Lucid HFT
  `https://support.lucidtrading.com/en/articles/11404736-prohibited-high-frequency-trading`.

## Added Code

- `src/rules/topstep.py`: price-limit buffer helper.
- `src/rules/lucidflex.py`: microscalping and order-rate compliance helpers.
- `src/data/tv_trade_audit.py`: paired TradingView entry/exit parser exposing
  hold seconds and trade P&L.
- Tests cover all new helpers and German/English TV trade-audit rows.

## Current Export Compliance Snapshot

Using the M1/M5/M15 Robust Trend exports:

| TF | trades | fast-win count | fast-profit share | Lucid microscalping |
|---|---:|---:|---:|---|
| M1 | 9,062 | 76 | 2.38% | pass |
| M5 | 11,809 | 187 | 4.63% | pass |
| M15 | 6,948 | 208 | 9.57% | pass |

## Remaining Deployment Inputs

- TopStep price-limit guard requires live/current CME `price_limit_pct` and
  platform `% Net Change` at order time.
- Lucid HFT guard requires an operator-chosen max order rate until Lucid
  publishes a numeric threshold.
- Slippage, commissions, fill model, stationarity, and exchange outages remain
  strategy/bot deployment checks, not Phase 3 engine gaps.
