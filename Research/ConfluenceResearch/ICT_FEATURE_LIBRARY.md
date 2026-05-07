# ICT / Confluence Feature Library

This is the living map from discretionary language to testable variables.

## Conversion Standard

Every feature must specify:

- definition
- input data required
- timeframe
- directionality
- invalidation
- expected role: entry, filter, exit, target, regime
- ablation test

## Seed Features

| Concept | Mechanical Draft | Data | Role | First Ablation |
|---|---|---|---|---|
| Liquidity sweep | Prior session/day/swing high or low breached by >= N ticks, followed by close back inside within M bars | OHLCV | Entry/filter | Sweep Reclaim base vs no sweep |
| Reclaim | Close back above swept low or below swept high after sweep | OHLCV | Entry | Reclaim same bar vs within M bars |
| Displacement | Candle body >= X ATR and close in top/bottom Y% of range | OHLCV | Confirmation | Require displacement after reclaim |
| Fair value gap | Three-candle gap with width >= X ticks or ATR fraction | OHLCV | Entry/zone | Entry at FVG midpoint vs market/close |
| Market structure shift | Post-sweep break of prior minor swing in reversal direction | OHLCV | Confirmation | MSS required vs optional |
| Order block | Last opposite candle before displacement; zone invalidated if broken by N ticks | OHLCV | Entry/stop zone | OB retest vs FVG retest |
| Premium/discount | Price percentile inside prior day/session/week range or anchored VWAP band | OHLCV | Filter | Only reversals from extremes |
| Killzone | Fixed exchange-time windows, e.g. NY AM/PM | Timestamp | Regime/filter | Session window ablation |
| VWAP stretch | Distance from session VWAP in ATR/std bands | OHLCV | Filter/target | Require stretch before mean reversion |
| OFI flip | Order-flow imbalance changes sign after sweep/reclaim | Depth/trades | Confirmation | Sweep Reclaim with/without OFI |
| Queue imbalance | `(bid_size - ask_size)/(bid_size + ask_size)` at L1 or weighted levels | Depth | Confirmation/filter | L1 vs multi-level |
| Absorption | High volume/delta at level without continuation beyond N ticks | Trades/depth | Reversal confirmation | Absorption required after sweep |
| Cross-market divergence | NQ sweeps a level while ES does not, or ES OFI confirms reversal first | NQ+ES OHLC/depth | Filter | NQ-only vs ES-confirmed |

## Data Availability Notes

- TradingView/Pine can test OHLCV/session/VWAP/structure/FVG features.
- Rithmic/Quantower can potentially provide live order-flow/depth features for TopStep/Lucid execution.
- Databento MBP-10 can support historical order-flow experiments if available.
- Order-flow features should be tested as confirmation/filter layers on top of the Sweep Reclaim M3 benchmark first.
