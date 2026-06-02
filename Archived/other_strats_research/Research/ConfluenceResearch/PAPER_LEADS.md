# Paper Leads For Confluence Research

These are starting points, not endorsements. The objective is to extract measurable features and test whether they improve the Sweep Reclaim M3 benchmark under IS/OOS discipline.

## Current Benchmark

`P4_Sweep_Reclaim_v0 M3`:

- WR 35.83%
- R 1.92
- Frequency 3.65/replay day
- Lag10 autocorr 0.01
- Net PnL +$139.6k
- Sortino about 1.43
- Weak TopStep MC as-is: mean EV +$78, median -$95, eval pass 11.9%, breach-after-pass 87.5%

## Priority Leads

### 1. Order Flow Imbalance As Price-Impact Core

Source: Rama Cont, Arseniy Kukanov, Sasha Stoikov, "The Price Impact of Order Book Events"  
Link: https://academic.oup.com/jfec/article/12/1/47/816163  
Alt: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822

Why it matters: OFI is a simple, testable microstructure feature: best bid/ask additions, cancellations, and marketable flow. The paper argues short-horizon price changes are mainly driven by OFI and that the slope depends on market depth.

Feature candidates:

- OFI over 1s/5s/15s/60s windows.
- OFI normalized by top-of-book depth.
- OFI sign agreement with sweep/reclaim direction.
- OFI divergence after a liquidity sweep: price makes new extreme but OFI does not confirm.
- Depth-adjusted OFI as a regime filter: trade only when impact per unit imbalance is high.

Data path: Rithmic/Quantower depth + trades, or Databento MBP-10 if available.

### 2. Multi-Level Order Flow Imbalance

Source: Ke Xu, Martin Gould, Sam Howison, "Multi-Level Order-Flow Imbalance in a Limit Order Book"  
Link: https://ideas.repec.org/p/arx/papers/1907.06230.html  
PDF: http://arxiv.org/pdf/1907.06230

Why it matters: our prior L2 work was shallow. This paper suggests deeper book levels add explanatory power versus best-level-only imbalance.

Feature candidates:

- MLOFI vector at levels 1-5 or 1-10.
- Level-weighted OFI decay curve.
- Sweep/reclaim only valid when deeper MLOFI flips before/after the reclaim.
- Liquidity vacuum feature: top-level sweep with weak replenishment behind it.

Data path: Rithmic depth snapshots or Databento MBP-10.

### 3. Deep Order Flow Imbalance

Source: Petter Kolm, Jeremy Turiel, Nicholas Westray, "Deep Order Flow Imbalance: Extracting Alpha at Multiple Horizons from the Limit Order Book"  
Link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141  
Journal DOI: https://doi.org/10.1111/mafi.12413

Why it matters: they find stationary order-flow-derived inputs beat raw book states for high-frequency return prediction. We likely do not need the deep model first; the useful part is feature engineering around stationary OFI.

Feature candidates:

- Stationary OFI transformations instead of raw depth.
- Multi-horizon labels: next 2 price changes, next 30s, next 2m.
- OFI feature as confirmation, not standalone strategy.
- "Information-rich" regime proxy: trade only when order flow has unusually high explanatory power over recent windows.

Data path: Rithmic/Quantower or Databento.

### 4. Queue Imbalance

Source: Martin Gould, Julius Bonart, "Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book"  
Link: https://www.worldscientific.com/doi/abs/10.1142/S2382626616500064

Why it matters: queue imbalance is simpler than full OFI and may be easier to test live from Quantower/Rithmic.

Feature candidates:

- `(bid_size - ask_size) / (bid_size + ask_size)` at L1.
- Multi-level queue imbalance.
- Reclaim only valid if queue imbalance flips with entry direction.
- Fade only when queue imbalance is extreme but price fails to continue.

Data path: live DOM/depth snapshots.

### 5. E-mini Futures Return / OFI Dynamics

Source: Makoto Takahashi, "Returns and Order Flow Imbalances: Intraday Dynamics and Macroeconomic News Effects"  
Link: https://ideas.repec.org/p/arx/papers/2508.06788.html

Why it matters: this is directly on S&P 500 E-mini futures at one-second frequency and emphasizes intraday variation/news effects. Even if we trade NQ, ES order flow can act as cross-index confirmation.

Feature candidates:

- Exclude or separately model macro-news windows.
- Time-of-day-specific OFI thresholds.
- ES OFI as confirmation for NQ sweep/reclaim.
- Cross-market divergence: NQ sweep without ES confirmation may be lower quality.

Data path: Rithmic/Quantower ES + NQ depth/trades.

### 6. DeepLOB / Representation Learning

Source: Zihao Zhang, Stefan Zohren, Stephen Roberts, "DeepLOB: Deep Convolutional Neural Networks for Limit Order Books"  
Link: https://ideas.repec.org/p/arx/papers/1808.03668.html  
PDF: http://arxiv.org/pdf/1808.03668

Why it matters: not a first implementation target, but useful for understanding which LOB structures transfer across instruments. The model's sensitivity analysis may point to robust depth/flow features.

Feature candidates:

- Start with handcrafted analogues: depth imbalance, OFI, short-window change in depth, spread, volatility.
- Later: train only after a clean feature baseline exists.
- Use model uncertainty as a no-trade filter if we ever go ML.

Data path: requires high-quality aligned LOB sequences; not Pine-first.

### 7. OFI Forecasting With Hawkes Processes

Source: Aditya Nittur Anantha, Shashi Jain, "Forecasting High Frequency Order Flow Imbalance"  
Link: https://ideas.repec.org/p/arx/papers/2408.03594.html

Why it matters: event clustering matters for order flow. A Hawkes framing may help us detect when a sweep is likely to continue versus mean-revert.

Feature candidates:

- Recent event-intensity imbalance.
- Buy/sell event excitation decay.
- "Exhaustion" after one-sided event burst.
- No-trade filter when excitation remains aligned against the proposed reversal.

Data path: trades/depth events from Rithmic or Databento.

### 8. VPIN / Toxicity As A Cautionary Filter

Sources:

- Easley / VPIN line of work, plus critiques such as "VPIN and the Flash Crash"  
  Link: https://www.sciencedirect.com/science/article/pii/S1386418113000189
- "From PIN to VPIN: An introduction to order flow toxicity"  
  Link: https://www.sciencedirect.com/science/article/pii/S2173126812000344

Why it matters: toxicity metrics may help avoid bad liquidity regimes, but the literature is contested. Treat VPIN-like features as filters, not alpha, and validate hard.

Feature candidates:

- Volume-bucketed buy/sell imbalance.
- Avoid reversal entries during high toxicity unless testing continuation.
- Toxicity regime as a volatility/slippage guard.

Data path: trade classification required.

## ICT / Discretionary Concepts To Mechanize

These are not academic papers, but they map naturally onto measurable features:

- Liquidity sweep: prior high/low breach by N ticks, then close back inside within M bars.
- Displacement: body >= X ATR, close in top/bottom Y% of range.
- Fair value gap: three-candle gap width >= X ticks or ATR fraction.
- Market structure shift: swing break after sweep/displacement.
- Order block: last opposite candle before displacement, retested before invalidation.
- Premium/discount: price location inside prior session/day/week range or anchored VWAP band.
- Killzone: fixed exchange-time session windows.
- Balanced price range / consolidation: compression before expansion.
- Absorption: high volume/delta into a level without price continuation.

## First Candidate Directions

1. Sweep Reclaim + OFI Flip
   - Base: `P4_Sweep_Reclaim_v0 M3`
   - Add: OFI/queue imbalance must flip in reclaim direction within N seconds/minutes after sweep.
   - Goal: lift WR without destroying freq below 2/day.

2. Sweep Reclaim + FVG/Displacement Confirmation
   - Base: sweep and close back inside.
   - Add: displacement candle and FVG after reclaim; entry on retrace to FVG midpoint/order-block zone.
   - Goal: improve entry quality and R distribution.

3. Sweep Reclaim + Cross-Market Confirmation
   - Base: NQ sweep.
   - Add: ES does not confirm the new extreme, or ES OFI flips first.
   - Goal: identify false breaks in NQ.

4. VWAP Stretch + Liquidity Sweep + Session Filter
   - Base: VWAP reversion and sweep/reclaim.
   - Add: NY AM/PM killzone and volatility regime.
   - Goal: convert high-WR low-freq behavior into enough trades without diluting quality.

5. Trend-Day Continuation With Order-Flow Pullback
   - Base: Trend Day Stack.
   - Add: pullback has negative/positive delta exhaustion against trend and queue imbalance recovers.
   - Goal: keep R/freq while improving WR.

## Immediate Research Tasks

1. Ingest Georg's ICT/raw video material into processed notes.
2. Pull the papers above into source notes only if public/licensed; otherwise keep URLs and summaries.
3. Build `ICT_FEATURE_LIBRARY.md` with mechanical definitions.
4. Write one candidate spec in `specs/` before any Pine or order-flow code.
