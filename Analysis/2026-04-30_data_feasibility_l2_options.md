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

Best first path:

1. Use **TickTradingData** as the cheapest NQ/MNQ L2 sample to prototype DOM /
   OFI visuals and ingestion.
2. Use **ThetaData Options Standard** as the first realistic NDX/QQQ options
   data candidate because it exposes tick-level option data, chain snapshots,
   trade/quote request types, and OPRA NBBO quote coverage at retail pricing.
3. Use **Nasdaq VOLQ / Cboe-style methodology** for IV/RV regime framing before
   trying to hand-roll a full IV surface.
4. Keep **Databento** and **dxFeed/Bookmap/Quantower** as higher-quality or
   live/replay candidates, not the cheapest starting point.

## Feasibility Matrix

| Need | Candidate | What It Provides | Cost Signal | First-Pass Verdict |
|---|---|---|---|---|
| NQ/MNQ historical L2 | TickTradingData | CME futures tick data, trades/quotes, 10 levels of order-book depth, CSV/Parquet/NRD, NQ and MNQ listed | EUR 5 for 1 month, EUR 200 full history per instrument, free MNQ month advertised | Best cheap first sample. Must quality-check timestamps, depth reconstruction, and contract rollover handling before trusting results. |
| NQ full-depth institutional replay | Databento GLBX.MDP3 | CME Globex MDP 3.0, full order book / MBO data, historical API, Python client, nanosecond timestamps | Usage/licensing based; new-user credit advertised | Best API-quality path if cheap samples are insufficient. More serious than needed for first visual prototype. |
| Real-time / historical DOM platform | dxFeed retail via ATAS / Quantower / Bookmap | Market depth, historical charting, DOM/order-book visualization for CME futures depending on platform | Platform/data prices from about $19/month; Bookmap from about $37/month | Good for discretionary visual validation and live DOM feel. API/export suitability must be confirmed before using as research backend. |
| Cheap futures tick, not L2 | Kibot | Tick data with bid/ask at transaction time | Paid packages; samples available | Not enough for DOM thesis. Kibot says it does not record bid/ask volume; reject for L2 order-flow imbalance. |
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

1. a free or one-month MNQ/NQ L2 sample
2. one month of options data if needed
3. static dashboard views using sampled data or mock data with the exact target
   schema

Only scale spend after the dashboard proves that the variables are interpretable
and the tests are well-formed.

## Sources

- TickTradingData. Historical CME futures tick data, 10 levels depth, pricing,
  NQ/MNQ catalog. https://www.ticktradingdata.com/
- Databento. CME Globex MDP 3.0 dataset and historical API. https://databento.com/datasets/GLBX.MDP3
- Databento docs. GLBX.MDP3 feed details and CME MDP 3.0 normalization. https://databento.com/docs/venues-and-datasets/glbx-mdp3
- dxFeed. Market data platforms and CME market-depth availability. https://choose.dxfeed.com/
- Kibot support. Tick data limitation: no bid/ask volume recording. https://www.kibot.com/Support.aspx
- ThetaData pricing. Options Standard includes tick-level data, chain snapshots,
  and OPRA NBBO quote coverage. https://www.thetadata.net/pricing
- ThetaData docs. Trade quote endpoint pairs OPRA trades with NBBO. https://docs.thetadata.us/operations/option_history_trade_quote.html
- Polygon / Massive options data pricing and feature tiers. https://polygon.io/options/
- Nasdaq. Nasdaq-100 Volatility Index VOLQ methodology guide. https://www.nasdaq.com/docs/2021/02/11/Nasdaq-100_Volatility_Index_VOLQ_Methodology_Reference_Guide.pdf
- Cboe. VIX methodology. https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf
