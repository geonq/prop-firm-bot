# LucidFlex — Compiled Encoding Reference

> **Pulled:** 2026-04-30
> **Purpose:** Fills the gaps in `LucidFlex Rules.md` (the original paste) so that `src/rules/lucidflex.py` can be encoded in Phase 1 without unanswered questions.
> **Reading order:** Original `LucidFlex Rules.md` for the rule structure (eval, funded, drawdown, payout cycles), then this file for pricing and approved products.
> **Verification rule:** Any fact tagged `[VERIFY]` was sourced from a third-party review (proptradingvibes.com), because Lucid's official site (lucidtrading.com and support.lucidtrading.com) returned 403 to WebFetch — likely Cloudflare. The Phase 1 Reviewer session should confirm against the live Lucid dashboard.

---

## 1. Pricing

### Eval purchase price (one-time, non-rebilling) `[VERIFY]`

| Account | LucidFlex Eval Price |
|---------|---------------------|
| 25K | $75 |
| 50K | **$175** |
| 100K | $345 |
| 150K | $345 |

> **Note on the 100K / 150K both showing $345:** the third-party source listed both at the same price. This is suspicious — most prop firms scale price with account size. Either the source has a typo, or Lucid genuinely runs flat pricing above 100K. Reviewer must confirm. If wrong, the optimizer's net-EV math for 150K accounts will be off.

### Reset cost `[VERIFY]`

The original LucidFlex Rules paste references "purchase a reset" but doesn't state the price. Per third-party source, resets cost approximately **30–40% of the original eval price**:

| Account | Estimated Reset Cost |
|---------|---------------------|
| 25K | ~$26 |
| 50K | **~$61** |
| 100K | ~$121 |
| 150K | ~$121 |

Same caveat as above — these are *estimates* based on a percentage range. The actual reset price visible in Lucid's dashboard at purchase time is what matters. Reviewer pass should confirm before encoding.

### No activation fee

The original paste confirms there is **no activation fee** to upgrade from LucidFlex Evaluation to LucidFlex Funded. So the eval price is the *only* upfront cost to enter the funded phase, plus optional reset costs if the eval is failed and retried.

---

## 2. Approved Products

`[VERIFY-list]` Sourced from a third-party review article. Lucid's official approved-products help article returned 403. The list below is what the third-party claimed but it doesn't fully match its own claimed total of "36 contracts" (the listed items add up to ~33). Reviewer must confirm against Lucid dashboard or support before encoding any product-specific logic.

### Equity Index Futures

| Code | Name | Commission per side |
|------|------|---------------------|
| ES | E-mini S&P 500 | $1.75 |
| NQ | E-mini Nasdaq-100 | $1.75 |
| RTY | E-mini Russell 2000 | $1.75 |
| YM | E-mini Dow Jones | $1.75 |
| MES | Micro S&P 500 | $0.50 |
| MNQ | Micro Nasdaq-100 | $0.50 |
| M2K | Micro Russell 2000 | $0.50 |
| MYM | Micro Dow Jones | $0.50 |
| NKD | Nikkei 225/USD | $1.75 |

### Foreign Exchange Futures

All at $2.40 commission per side:
6A (AUD), 6B (GBP), 6C (CAD), 6E (EUR), 6J (JPY), 6S (CHF), 6N (NZD)

> Note: Micro forex contracts (M6E, M6A, M6B etc.) are NOT permitted at Lucid per the source, despite being available on CME and at TopStep.

### Energy Futures

| Code | Name | Commission per side |
|------|------|---------------------|
| CL | Crude Oil | $2.00 |
| MCL | Micro Crude Oil | $0.50 |
| QM | E-mini Crude Oil | $2.00 |
| NG | Natural Gas | $2.00 |
| QG | E-mini Natural Gas | $1.30 |

### Metals Futures

| Code | Name | Commission per side |
|------|------|---------------------|
| GC | Gold (100 oz) | $2.30 |
| MGC | Micro Gold | $0.80 |
| SI | Silver (5,000 oz) | $2.30 |
| PL | Platinum | $2.30 |
| HG | Copper | $2.30 |

> Note: Palladium (PD) is NOT permitted.

### Agricultural Futures

All at $2.80 commission per side:
ZS (Soybeans), ZC (Corn), ZW (Wheat), ZL (Soy Oil), ZM (Soy Meal), LE (Live Cattle), HE (Lean Hogs)

> Source claims 10 ag contracts but only 7 are listed. Reviewer to confirm.

### Explicitly Excluded

- **Treasury futures:** ZN (10Y), ZB (30Y), ZF (5Y), ZT (2Y), TN, UB — all excluded
- **Crypto futures:** BTC, MBT — excluded
- **Volatility:** VIX futures — excluded
- **Soft commodities:** Cotton, cocoa, coffee, sugar — excluded
- **Palladium (PD)** — excluded
- **Micro forex contracts** — excluded despite CME availability

### What this means for the project

Both ES and NQ (and their micros MES, MNQ) are permitted, so the Pine Script strategies in Phase 4 can target NQ exactly as planned. No product-restriction conflict.

---

## 3. Tick values (CME standard, applies identically across all firms)

Same table as in TopStep compiled reference — CME contract specs are firm-agnostic:

| Contract | Tick size | Tick value | Point value |
|----------|-----------|------------|-------------|
| NQ | 0.25 | $5.00 | $20 |
| MNQ | 0.25 | $0.50 | $2 |
| ES | 0.25 | $12.50 | $50 |
| MES | 0.25 | $1.25 | $5 |

For the Phase 1 encoding, NQ + MNQ are the priority.

---

## 4. Cross-reference with the original paste — what's already covered

The original `LucidFlex Rules.md` paste (already in this folder) covers in detail:

- ✅ Eval account profit targets, max loss limits, consistency rule, max sizes per account size
- ✅ Funded account drawdown mechanics (EOD trail until Initial Trail Balance, then locks at Locked MLL Balance)
- ✅ Specific dollar amounts for 50K: $3,000 profit target, $2,000 MLL, $52,100 Initial Trail, $50,100 Locked MLL
- ✅ 50% consistency formula with cushion table
- ✅ Scaling plan in funded (2/3/4 minis at $0/$1K/$2K profit thresholds for 50K)
- ✅ Payout: 90/10 split, $150 minimum daily profit on 5+ days, positive net profit, $500 min payout, 50% of profit up to $2,000 max for 50K, 5 max payouts before live transition
- ✅ Trading hours: close 4:45 PM EST, reopen 6:00 PM EST Sun-Thu
- ✅ News trading allowed without restriction
- ✅ Genuine scalping allowed; microscalping (>50% profit from <5sec trades) prohibited
- ✅ HFT prohibited; Hedging strictly prohibited (across own accounts, between users, between firms)
- ✅ Inactivity policy: 30 days = abandoned/deleted
- ✅ Restricted countries list (Germany not on it)
- ✅ Live (legacy and new) transition details — out of scope for Phases 1–5

What was missing from the original paste and is filled here:
- ✅ Eval purchase price and reset cost
- ✅ Approved products list (which contracts can actually be traded)
- ⚠️ "Velocity logic" — mentioned in the news trading section of the original paste but not defined. Still unresolved. Reviewer should check Lucid help center for "velocity logic" definition during Phase 1 — it could affect slippage modeling in Phase 3.

---

## 5. Verification checklist for Phase 1 Reviewer pass

- [ ] Eval purchase prices (50K = $175 specifically, plus 25K/100K/150K)
- [ ] Reset costs (50K ≈ $61) — pull from Lucid dashboard at trader login
- [ ] Whether 100K and 150K really both cost $345 (or if the third-party source has an error)
- [ ] Approved products list (cross-check against Lucid's official help article)
- [ ] Total approved-product count claim of "36" vs. what's actually listed
- [ ] "Velocity logic" definition and its impact on news-trading P&L
- [ ] Whether MES is really included as a permitted product (third-party listed it; verify)

---

## Sources used for this compiled reference

Primary (Lucid official) — **all returned 403 to WebFetch**:
- support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions
- lucidtrading.com (pricing page)

Third-party (used in lieu of primary access — flagged `[VERIFY]`):
- proptradingvibes.com/blog/lucid-trading-reset-cost
- proptradingvibes.com/blog/lucid-trading-approved-products

The 403 from Lucid's own site means Reviewer pass MUST verify against the live dashboard Georg can log into directly — the third-party data is likely accurate but is one degree removed from primary source.
