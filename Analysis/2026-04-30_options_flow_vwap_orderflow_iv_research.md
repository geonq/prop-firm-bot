---
type: targeted literature note
date: 2026-04-30
author: Codex
status: first-pass; short findings only
scope: options flow, VWAP, order flow / L2, realized standard deviation, implied volatility
---

# Options-Flow / L2 / Volatility Research Note

## Bottom Line

Georg's preference is now explicit: do not treat ORB/TORB as the preferred strategy path. The next strategy research should start from options-flow / implied-volatility / realized-volatility / Level-2 order-flow features, then test whether those features create a prop-firm-compatible path distribution.

The evidence is not equal across inputs:

1. **Options flow is the most interesting alpha source**, but only if we can get useful initiator/imbalance data. Several papers find option volume/order imbalance predicts underlying returns, but the strongest signals often require non-public or participant-class data.
2. **Implied-realized volatility spread is a serious regime feature**, not automatically an entry signal. The variance-risk-premium literature depends on model-free IV and accurate high-frequency realized variance.
3. **L2 order-flow imbalance is mathematically strong at very short horizons**, but the edge horizon can be only a few price changes. That makes data quality, latency, spread, and slippage decisive.
4. **VWAP is weak as standalone alpha.** The serious literature mainly treats VWAP as an execution benchmark / tracking problem. It may still help as a state variable: price relative to anchored/session VWAP, VWAP slope, or participation-volume context.
5. **"True standard deviation" should mean realized volatility from high-frequency returns**, not chart-platform band folklore. Realized log standard deviations and returns scaled by realized volatility have strong empirical support.

## Paper-Level Findings

| Area | Source | Accurate Finding | Use / Reject |
|---|---|---|---|
| Options volume | Pan & Poteshman (2006), RFS | Buyer-initiated open-position option put-call ratios predict future stock returns; low ratios outperform high ratios by >40 bps next day and >1% over next week in their sample. The key data is not ordinary public option volume. | Use as core evidence that options flow can contain informed directional information. Data availability is the blocker. |
| Options-induced order imbalance | Hu (2014), JFE | Option-market-maker hedging transmits option transaction imbalance into stock order imbalance; the option-induced component predicts future stock returns, while non-option stock imbalance is more transitory. | Strong conceptual bridge from options flow to underlying index/futures movement. Need a tradable proxy for option-induced delta pressure. |
| Option volume imbalance | Michael, Cucuringu & Howison (2022), arXiv/SSRN | Normalized option-volume imbalance predicts excess overnight equity-market returns; strongest signals are from market-maker volumes, with much predictability from high-IV contracts and more from put volume than call volume. | Very relevant to an NQ/NDX thesis, but participant-class volume is likely not retail-accessible. Use if a data vendor exposes it. |
| Index option imbalance | Sensoy & Omole (2022), IREF | In Borsa Istanbul index options, call/put order imbalance links to spot index returns; higher call imbalance predicts negative next-week index returns, consistent with dealer hedging pressure. | Supports index-option-flow research, but market is not NDX/NQ. Treat as mechanism evidence, not direct calibration. |
| Option order imbalance commonality | Omole, Sensoy & Gulay (2022), Borsa Istanbul Review | Finds option order-imbalance commonality, but little incremental explanatory power for underlying returns versus equity order imbalance. | Important caution: options imbalance is not automatically superior to underlying order flow. |
| L2 order-flow imbalance | Cont, Kukanov & Stoikov (2014), JFEconometrics | Short-interval price changes are mainly driven by order-flow imbalance at the best bid/ask; relation is approximately linear with slope inversely related to depth. Volume alone is noisier. | Best simple L2 feature candidate: OFI, depth-normalized OFI, and OFI shocks. |
| Deep OFI | Kolm, Turiel & Westray (2023), Mathematical Finance | Neural nets using stationary order-flow inputs outperform raw order-book-state models for Nasdaq stocks; effective stock-specific forecast horizon is about two average price changes. | Promising but operationally hard. For prop-firm NQ, this is only useful if we have tick/L2 data and can execute fast enough. |
| Universal price formation | Sirignano & Cont (2019), Quantitative Finance | Large-scale deep learning finds a stable relation between order-flow history and price-move direction across US equities. | Confirms order-flow history has signal. Does not prove a retail NQ strategy after costs. |
| VWAP | Cartea & Jaimungal (2016), SIAM J. Financial Math; Mitchell/Bialkowski/Tompaidis (2020) | VWAP papers mainly solve optimal execution / tracking, not directional alpha. Volume-volatility relationship matters for execution quality. | Use VWAP as a context/execution feature, not as the main edge. |
| Realized volatility | Andersen, Bollerslev, Diebold & Labys (2003), Econometrica | High-frequency intraday returns provide realized volatility measures linked to quadratic variation; simple long-memory models forecast log realized volatility well. | Use realized vol / realized std as canonical volatility state. |
| Realized std distribution | Andersen, Bollerslev, Diebold & Ebens (2001), JFE | Realized variances are right-skewed; log standard deviations are approximately Gaussian; returns scaled by realized standard deviations are also approximately Gaussian. | Supports normalizing NQ returns/trade outcomes by realized std before feeding prop-firm simulator. |
| Variance risk premium | Bollerslev, Tauchen & Zhou (2009), RFS | Implied-realized variance spread explains time-series variation in future aggregate stock returns; result depends on model-free IV and accurate high-frequency realized variance. | Use IV-RV spread as a regime selector. Do not use crude Black-Scholes IV as if equivalent. |
| VIX/VXN methodology | Cboe methodology pages | VIX-style indices aggregate weighted option prices across strikes to estimate 30-day expected volatility; official VIX/VXN-style data is preferable to hand-rolled IV if licensing permits. | Trust official Cboe/Nasdaq volatility indices before building our own IV surface. Hand-rolled IV is a later task. |

## First Research Hypotheses To Test

1. **NDX options-flow pressure -> NQ direction.** Proxy dealer/market-maker delta pressure from NDX/QQQ option volume imbalance, put/call imbalance, high-IV contract activity, and changes in VXN/CNIV-style IV.
2. **IV-RV regime switch.** Trade only when implied volatility is rich/cheap relative to realized NQ volatility and the realized-vol state historically improves target-before-breach odds.
3. **Depth-normalized NQ OFI.** Use Level-2 best-bid/best-ask order-flow imbalance and depth to predict the next few ticks/minutes; reject if edge disappears after spread/slippage.
4. **Realized-std normalization.** Express entries, stops, targets, and replay R-multiples in realized-standard-deviation units rather than fixed points.
5. **VWAP context only.** Test price distance from anchored/session VWAP and VWAP slope as filters. Do not build a VWAP-cross strategy unless data proves incremental value.

## Data Reality Check

Minimum honest data for this direction:

- NQ/MNQ tick or 1-second data, not only 1-minute OHLCV.
- NQ Level-2/top-of-book snapshots or event stream for OFI/depth.
- NDX or QQQ option chain history with volume, open interest, bid/ask, IV, greeks, and preferably trade direction / participant class.
- Official VXN/CNIV-style implied-volatility series if available; otherwise model-free IV calculation requires clean option surfaces and careful filtering.
- Event timestamps: CPI, FOMC, NFP, Fed speakers, and major Nasdaq-component earnings.

If only TradingView OHLCV is available, this research direction collapses back to realized-vol/VWAP filters and cannot honestly test the options-flow/L2 thesis.

## Current Priority

Do **not** choose a strategy yet. Next step is data feasibility:

1. Identify affordable sources for historical NQ L2/tick data.
2. Identify affordable sources for historical NDX/QQQ options flow with trade direction or at least volume/open-interest/IV by strike.
3. If both are too expensive, pivot to realized-vol / official VXN / 1-minute NQ features and explicitly mark options-flow/L2 as v2.

## Sources

- Pan, Jun and Poteshman, Allen M. `The Information in Option Volume for Future Stock Prices`, Review of Financial Studies, 2006. https://academic.oup.com/rfs/article/19/3/871/1646711
- Hu, Jianfeng. `Does Option Trading Convey Stock Price Information?`, Journal of Financial Economics, 2014. https://www.sciencedirect.com/science/article/pii/S0304405X13003048
- Michael, Nikolas; Cucuringu, Mihai; Howison, Sam. `Option Volume Imbalance as a predictor for equity market returns`, 2022. https://ideas.repec.org/p/arx/papers/2201.09319.html
- Sensoy, Ahmet and Omole, John. `Information content of order imbalance in the index options market`, International Review of Economics & Finance, 2022. https://www.sciencedirect.com/science/article/pii/S1059056021002367
- Omole, John; Sensoy, Ahmet; Gulay, Guzhan. `Order imbalance and commonality: Evidence from the options market`, Borsa Istanbul Review, 2022. https://www.sciencedirect.com/science/article/pii/S2214845021000946
- Cont, Rama; Kukanov, Arseniy; Stoikov, Sasha. `The Price Impact of Order Book Events`, Journal of Financial Econometrics, 2014. https://academic.oup.com/jfec/article/12/1/47/816163
- Kolm, Petter N.; Turiel, Jeremy; Westray, Nicholas. `Deep order flow imbalance: Extracting alpha at multiple horizons from the limit order book`, Mathematical Finance, 2023. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141
- Sirignano, Justin and Cont, Rama. `Universal features of price formation in financial markets: perspectives from deep learning`, Quantitative Finance, 2019. https://www.tandfonline.com/doi/full/10.1080/14697688.2019.1622295
- Cartea, Alvaro and Jaimungal, Sebastian. `A Closed-Form Execution Strategy to Target Volume Weighted Average Price`, SIAM Journal on Financial Mathematics, 2016. https://epubs.siam.org/doi/10.1137/16M1058406
- Mitchell, Daniel; Bialkowski, Jedrzej; Tompaidis, Stathis. `Volume-weighted average price tracking: A theoretical and empirical study`, IISE Transactions, 2020. https://ideas.repec.org/a/taf/uiiexx/v52y2020i8p864-889.html
- Andersen, Torben G.; Bollerslev, Tim; Diebold, Francis X.; Labys, Paul. `Modeling and Forecasting Realized Volatility`, Econometrica, 2003. https://www.econometricsociety.org/publications/econometrica/browse/2003/03/01/modeling-and-forecasting-realized-volatility
- Andersen, Torben G.; Bollerslev, Tim; Diebold, Francis X.; Ebens, Heiko. `The Distribution of Realized Stock Return Volatility`, Journal of Financial Economics, 2001. https://www.kellogg.northwestern.edu/faculty/research/detail/2001/the-distribution-of-realized-stock-return-volatility/
- Bollerslev, Tim; Tauchen, George; Zhou, Hao. `Expected Stock Returns and Variance Risk Premia`, Review of Financial Studies, 2009. https://econpapers.repec.org/RePEc:oup:rfinst:v:22:y:2009:i:11:p:4463-4492
- Cboe. `Cboe Volatility Index`, methodology/product resources. https://www.cboe.com/tradable-products/vix/
