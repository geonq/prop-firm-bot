---
type: dashboard spec
date: 2026-04-30
compressed: 2026-05-05
status: compact workflow decision
---

# Research Thesis Dashboard v0 — Compact

## Purpose

The dashboard is a research instrument. It must help decide whether a market
thesis is observable, testable, and compatible with prop-firm payoff mechanics
before anyone codes entries/exits.

## Workflow

1. collect serious external findings
2. translate them into measurable variables
3. visualize the variables
4. run falsifiable tests
5. translate surviving signals into prop-firm path metrics
6. only then encode strategy logic

## Thesis Families

- L2/order-flow pressure into NQ/MNQ
- IV/RV regime filters
- realized-volatility normalization
- options-flow pressure into NQ, parked until paid data is justified
- VWAP only as context, not standalone alpha

## Required Views

- Evidence board with thesis status
- L2 workbench with spread, depth imbalance, rolling pressure, and forward-return
  comparison
- Volatility/regime view
- Options-flow view only after data access
- Prop-firm translation: win rate, R:R, holding time, breach probability,
  payout odds, mean/median EV

## Non-Goals

- No QuantPad cloning
- No ORB/TORB candidate work
- No Level-1 OHLCV-only strategy search by default
- No strategy logic before variables survive train/holdout tests
