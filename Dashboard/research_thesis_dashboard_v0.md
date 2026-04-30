---
type: dashboard spec
date: 2026-04-30
status: v0 workflow decision
scope: thesis-first research dashboard before strategy coding
---

# Research Thesis Dashboard v0

## Purpose

The dashboard is now a research instrument, not a late-stage reporting layer.
Before coding a strategy, it must help Georg and the agents understand whether
a thesis from papers / experienced traders / market microstructure research is
observable, testable, and compatible with prop-firm payoff constraints.

The workflow mirrors Georg's ICT swing-strategy process:

1. collect serious external findings
2. translate them into our own thesis
3. map the thesis to measurable variables
4. visualize whether the variables behave as claimed
5. falsify weak claims before strategy implementation
6. only then encode a mechanical strategy

## Core Principle

No source is treated as authority. Papers, trader experience, QuantPad-style
ideas, and microstructure literature are inputs for hypothesis formation. A
claim becomes useful only after it is mapped to data we can access and a test
that can disprove it.

## Thesis Card Model

Each candidate thesis should have one compact card:

- thesis: one sentence
- source basis: paper, trader idea, or observed market behavior
- measurable variables: exact features we can compute
- data requirement: required feed and minimum resolution
- expected behavior: what should happen if the thesis is true
- falsifier: what result kills the thesis
- prop-firm relevance: why the path distribution might survive MLL, DLL,
  consistency, payout, and flatten rules

## First Thesis Families

1. **Options-flow pressure into NQ.** NDX/QQQ options imbalance, high-IV
   contract activity, put/call pressure, and VXN/CNIV-style IV changes should
   reveal directional or regime information before NQ futures move.
2. **Depth-normalized L2 order-flow imbalance.** Best bid/ask event flow and
   visible depth should predict the next few ticks/minutes after spread and
   slippage. Reject quickly if the horizon is too short to trade manually/API
   within prop-firm constraints.
3. **IV/RV regime filter.** Implied-realized volatility spread should decide
   when a strategy is allowed to trade, not necessarily create entries by
   itself.
4. **Realized-standard-deviation normalization.** Stops, targets, and R-multiple
   replay should be expressed in realized-vol units instead of fixed NQ points.
5. **VWAP context only.** Session/anchored VWAP distance and slope can act as
   context or execution quality variables, but not as a standalone strategy
   until it proves incremental signal.

## Required Views

### Evidence Board

Shows all thesis cards with status:

- `unmapped`: still a paper/trader idea
- `mapped`: variables and data feed identified
- `visualized`: charted on historical data
- `stat-tested`: prediction test run
- `sim-tested`: path distribution run through prop-firm simulator
- `rejected`: falsifier triggered

### Market Microstructure View

For L2/order-flow theses:

- price ladder / top-of-book depth over time
- bid/ask depth imbalance
- order-flow imbalance shocks
- next-tick / next-minute forward return
- spread, slippage estimate, and fill-risk warnings

### Volatility Regime View

For IV/RV theses:

- realized NQ volatility / realized standard deviation
- VXN/CNIV or model-free IV proxy
- IV-RV spread
- forward realized volatility and forward return distribution
- prop-firm outcome split by regime

### Options-Flow View

For NDX/QQQ options-flow theses:

- put/call volume and open-interest imbalance
- volume by moneyness / expiry bucket
- IV changes by bucket
- proxy delta-pressure series if greeks are available
- forward NQ returns and path outcomes after signal events

### Prop-Firm Translation View

Every promising signal must be translated into:

- win rate, payoff ratio, frequency, holding time
- drawdown clustering
- MLL/DLL breach probability
- consistency-rule risk
- time-to-target and time-to-payout
- net EV and median EV after fees

## Build Order

1. Add data-feasibility table for NQ/MNQ tick/L2 and NDX/QQQ options-flow
   sources.
2. Create static mock dashboard from existing synthetic outputs and the thesis
   cards above.
3. Add ingestion only for data sources Georg can actually access.
4. Add statistical tests and prop-firm replay after the data layer exists.

## Non-Goals

- Do not copy QuantPad branding, proprietary UI, or workflow structure.
- Do not implement ORB/TORB as a candidate strategy.
- Do not code entries/exits before thesis variables are visualized.
- Do not treat Level-1 OHLCV as enough to test the L2/options-flow thesis.
