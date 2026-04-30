---
type: data feasibility note
date: 2026-04-30
status: first pass
scope: NQ/MNQ L2, NDX/QQQ options flow, IV/RV inputs
---

# Data Feasibility: L2 / Options Flow / IV-RV

## Bottom Line

The dashboard-first thesis workflow is feasible, but not with TradingView
OHLCV alone.

Best first path after TickTradingData became unavailable/offline:

1. Use **Databento GLBX.MDP3** as the first clean API-backed NQ/MNQ L2 sample
   path. Pull `MBP-10` for top-10 depth first; only use `MBO` if queue/order
   identity becomes necessary.
2. Use **Sierra Chart Denali** as the budget/manual fallback if Databento cost
   is unacceptable. It can download CME historical market-depth data, but export
   requires ACSIL/custom-study work rather than a normal CSV button.
3. Use **ThetaData Options Standard** as the first realistic NDX/QQQ options
   data candidate because it exposes tick-level option data, chain snapshots,
   trade/quote request types, and OPRA NBBO quote coverage at retail pricing.
4. Use **Nasdaq VOLQ / Cboe-style methodology** for IV/RV regime framing before
   trying to hand-roll a full IV surface.
5. Keep **Bookmap/dxFeed/Rithmic** as live visual/replay tools, not the primary
   historical research backend unless export/API access is confirmed.

## Feasibility Matrix

| Need | Candidate | What It Provides | Cost Signal | First-Pass Verdict |
|---|---|---|---|---|
| NQ/MNQ historical L2 | Databento GLBX.MDP3 | CME Globex MDP 3.0, `MBP-10` top-10 market depth, `MBO` full order book, trades, Python/API/CSV/DBN output | Usage-based historical pricing, public free credits advertised | New first choice. Cleanest backend for dashboard ingestion and repeatable tests. Start with 1-3 RTH sessions of `MBP-10`, then scale only after schema works. |
| NQ/MNQ budget/manual L2 | Sierra Chart Denali | CME market-depth history through Sierra Chart, with recent historical depth available for download/display | Platform + exchange fees; cheaper than institutional feeds if already used | Viable fallback if Georg can tolerate manual setup. Normal export does not include depth; needs ACSIL/custom extraction into CSV/Parquet. |
| Real-time / historical DOM platform | Bookmap with dxFeed or Rithmic | Live full-depth CME futures visualization; dxFeed advertises full-depth futures and limited historical depth add-ons; Rithmic provides CME MBO into Bookmap | Platform/data monthly fees | Good for discretionary visual validation and recording forward. Use as research backend only if we confirm export/API access for depth events. |
| Cheap futures tick, not L2 | Kibot | Tick data with bid/ask at transaction time | Paid packages; samples available | Not enough for DOM thesis. Kibot says it does not record bid/ask volume; reject for L2 order-flow imbalance. |
| Legacy cheap L2 target | TickTradingData | Advertised CME tick data with trades/quotes and 10 depth levels | Previously cheapest visible path | Treat as unavailable unless Georg confirms it is reachable again. Do not block on it. |
| Options flow / chain / IV | ThetaData Options Standard | US index/stock options, 8 years, tick-level data, option chain snapshots, every OPRA NBBO quote, trade/quote endpoint | $80/month retail | Best first options-flow candidate. Need verify NDX/QQQ coverage, Greeks/IV fields, and whether trade direction can be inferred robustly. |
| Options aggregates / IV / OI | Polygon / Massive options plans | US options tickers, historical aggregates, Greeks/IV/OI on paid tiers | Starter around $29/month, Developer around $79/month in current public pricing | Useful cheaper fallback for aggregates. Likely weaker than ThetaData for tick-level flow / trade-quote reconstruction. |
| Official IV benchmark | Nasdaq VOLQ | 30-day implied volatility of Nasdaq-100 based on NDX options | Methodology public; data access/licensing separate | Strong conceptual IV benchmark for NQ/NDX regime view. Use before hand-rolling IV if data is available. |
| VIX-style methodology | Cboe VIX methodology | Model-free 30-day expected-vol framework using option prices across strikes | Methodology public; VIX is SPX not NDX | Use as methodology reference. Do not substitute VIX for NDX/NQ regime without testing. |

## Immediate Data Tests

### Test A: NQ/MNQ L2 Sample

Goal: prove whether we can compute a clean depth-normalized OFI series.

Minimum sample:

- 5 to 20 active RTH sessions
- NQ or MNQ front contract
- trades
- top-of-book bid/ask
- 10-level depth updates

Derived fields:

- best bid / best ask / spread
- depth at levels 1, 3, 5, 10
- bid-depth minus ask-depth
- normalized depth imbalance
- order-flow imbalance over rolling windows
- forward return at 1, 5, 15, 60 seconds

Falsifier:

- no stable relation between OFI/depth shocks and forward return after spread
  and slippage
- signal horizon shorter than realistic execution latency
- data cannot reconstruct book state reliably

### Test B: QQQ/NDX Options Flow Sample

Goal: prove whether options-flow pressure can be mapped into NQ futures
movement or regime changes.

Minimum sample:

- QQQ and preferably NDX option chain snapshots
- trades with NBBO at time of trade
- open interest
- IV and Greeks, or enough fields to compute them
- NQ/MNQ returns aligned by timestamp

Derived fields:

- put/call volume imbalance
- volume by expiry bucket and moneyness bucket
- premium-weighted imbalance
- delta-weighted pressure proxy
- IV change by bucket
- forward NQ return and realized volatility

Falsifier:

- imbalance cannot be directionally inferred
- signal only appears after NQ already moved
- effect disappears when filtered to liquid contracts / realistic timestamps

### Test C: IV/RV Regime

Goal: decide whether implied-realized volatility spread is useful as a
strategy filter.

Minimum sample:

- realized NQ volatility from intraday returns
- VOLQ/VXN/CNIV-style IV proxy or options-derived IV
- forward NQ volatility and forward trade outcome buckets

Derived fields:

- realized standard deviation by session and rolling intraday window
- IV-RV spread
- regime buckets: cheap IV, neutral, rich IV
- prop-firm outcomes by regime: breach, timeout, payout-positive

Falsifier:

- regime buckets do not change forward distribution or prop-firm outcome odds
- IV proxy is too noisy or unavailable for the intended test horizon

## First Implementation Decision

Do not buy a large dataset first.

Start with:

1. 1-3 active RTH sessions of Databento `GLBX.MDP3` `MBP-10` for MNQ or NQ
2. one month of options data if needed
3. static dashboard views using sampled data or mock data with the exact target
   schema

Only scale spend after the dashboard proves that the variables are interpretable
and the tests are well-formed.

## Sources

- Databento. CME Globex MDP 3.0 dataset and historical API. https://databento.com/datasets/GLBX.MDP3
- Databento docs. GLBX.MDP3 feed details and CME MDP 3.0 normalization. https://databento.com/docs/venues-and-datasets/glbx-mdp3
- Databento docs. `MBP-10` market-depth and `MBO` full-book schemas. https://databento.com/docs/schemas-and-data-formats
- Databento pricing. Usage-based historical data and free signup credits. https://databento.com/pricing/
- Sierra Chart. Market Depth Historical Graph / historical market-depth access. https://www.sierrachart.com/index.php?page=doc%2FMarketDepthHistoricalGraph.php
- Sierra Chart support. Normal export does not export market-depth data; use programmatic access. https://www.sierrachart.com/SupportBoard.php?ThreadID=78406
- NinjaTrader. Market Replay data contains synchronized Level I and Level II data. https://ninjatrader.com/support/helpGuides/nt8/set_up12.htm
- dxFeed. Market data platforms and CME market-depth availability. https://choose.dxfeed.com/
- Bookmap/dxFeed. Full-depth futures data and historical-depth add-on notes. https://bookmap.com/en/partner/dxfeed
- Bookmap/Rithmic. CME futures full-depth/MBO notes. https://bookmap.com/en/partner/rithmic
- TickTradingData. Previously listed historical CME futures tick data with 10 levels depth; currently unavailable for Georg. https://www.ticktradingdata.com/
- Kibot support. Tick data limitation: no bid/ask volume recording. https://www.kibot.com/Support.aspx
- ThetaData pricing. Options Standard includes tick-level data, chain snapshots,
  and OPRA NBBO quote coverage. https://www.thetadata.net/pricing
- ThetaData docs. Trade quote endpoint pairs OPRA trades with NBBO. https://docs.thetadata.us/operations/option_history_trade_quote.html
- Polygon / Massive options data pricing and feature tiers. https://polygon.io/options/
- Nasdaq. Nasdaq-100 Volatility Index VOLQ methodology guide. https://www.nasdaq.com/docs/2021/02/11/Nasdaq-100_Volatility_Index_VOLQ_Methodology_Reference_Guide.pdf
- Cboe. VIX methodology. https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf
