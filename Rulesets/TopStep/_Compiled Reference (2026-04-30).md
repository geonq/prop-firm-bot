# TopStep — Compiled Encoding Reference

> **Pulled:** 2026-04-30
> **Purpose:** Single source of truth for `src/rules/topstep.py` Phase 1 encoding. Aggregates the original `TopStep NoFee.md` paste plus dollar amounts and mechanics that lived behind links not included in that paste.
> **Reading order:** This file first, then `TopStep NoFee.md` for the prose context.
> **Verification rule:** Any fact tagged `[VERIFY]` was sourced from a third-party review, not TopStep's official help center directly (because the relevant primary article was either gated behind images, returned 403/404 to WebFetch, or wasn't otherwise accessible). The Phase 1 Reviewer session should sanity-check these against TopStep's live dashboard or by emailing support.

---

## 1. Pricing

### Trading Combine subscription (recurring monthly)

| Account | Standard Path | No Activation Fee Path |
|---------|---------------|------------------------|
| 50K | $49/mo | $109/mo |
| 100K | (not pulled — verify) | (not pulled — verify) |
| 150K | (not pulled — verify) | (not pulled — verify) |

- Both paths rebill every 30 days from sign-up date.
- Subscription auto-stops when you pass the Combine.
- **`[VERIFY]` Note**: TopStep introduced lower pricing on the No Activation Fee path on **2026-04-28** (two days before this doc was written). Verify that $109 is current — it may have dropped.

### Activation Fee (paid once when XFA is activated)

| Path | Activation Fee |
|------|----------------|
| Standard | **$129** (was $149 before recent change — verify which is current) |
| No Activation Fee | **$0** |

The NoFee path is what the original TopStep paste covers. That is the path Georg should default to in the model unless explicitly comparing both.

### Trading Combine Reset (manual purchase)

| Account | Reset Cost |
|---------|------------|
| 50K | **$49** `[VERIFY]` |
| 100K | $99 `[VERIFY]` |
| 150K | $149 `[VERIFY]` |

Resets are also accumulated as "Reset Credits" — one credit added each time the subscription rebills. Manual purchase is for traders who want to reset before a credit accrues.

### Back2Funded reactivation (XFA only, before first payout, max 2 reactivations per XFA)

| Account | Reactivation Cost |
|---------|-------------------|
| 50K | **$599** |
| 100K | $699 |
| 150K | $829 |

Once first payout taken from an XFA, that XFA is no longer Back2Funded-eligible. After a rule violation, trader has **7 days** to reactivate or the offer expires.

---

## 2. Maximum Loss Limit (MLL) — the breach rule

### Dollar amounts (sourced from official help center)

| Account | MLL |
|---------|-----|
| 50K | **$2,000** |
| 100K | $3,000 |
| 150K | $4,500 |

### Trailing mechanism

Trails the **highest end-of-day balance**, never moves down. Updates at end of each trading day. Monitored real-time during the day (so intraday balance <below MLL triggers immediate breach), but the *trail point itself* moves only at session end.

### Trading Combine — lock point

50K Trading Combine starts at $50,000 → MLL begins at $48,000. As balance grows, MLL rises by the gain (capped at the daily increase). **Once MLL has trailed up to the original starting balance ($50,000 for 50K), it locks there permanently.**

So the MLL ceiling for 50K Combine is $50,000. Trail occupies the range $48,000 → $50,000.

**Source example (verbatim):** "Starting a $50K Trading Combine at $50,000, the MLL begins at $48,000. After gaining $500 on day one (balance: $50,500), the MLL rises to $48,500. A $500 loss the next day drops the balance to $50,000, but the MLL remains at $48,500."

### Express Funded Account — lock point

XFA 50K starts with $0 displayed balance and MLL at -$2,000. As you earn profit, MLL trails up. **Once balance reaches the initial MLL distance ($2,000 for 50K), MLL locks at $0 permanently.**

So the XFA 50K MLL ceiling is $0 (i.e. you can lose all profits but not the starting amount).

After taking a payout, **MLL is reset to $0** regardless of where it was, and the trader must accumulate fresh winning days for the next payout.

**Source example (verbatim):** "A $50K XFA starts with $0 balance and MLL at -$2,000. After earning $1,000 (balance: $1,000), the MLL trails to -$1,000. After another $1,000 gain (balance: $2,000), the MLL locks at $0 and stays there permanently."

### Hitting the MLL — consequences

| Phase | Consequence |
|-------|-------------|
| Trading Combine | Account liquidated for that day; ineligible for funding until reset |
| XFA | Account permanently closed. Back2Funded available if no payout taken yet. |
| Live Funded | Account permanently closed at end of trading day |

---

## 3. Daily Loss Limit (DLL) — exists in XFA + Live, NOT in Trading Combine

### Dollar amounts `[VERIFY]` (third-party source — primary article URL returned 404)

| Account | DLL (XFA) |
|---------|-----------|
| 50K | **$1,000** |
| 100K | $2,000 |
| 150K | $3,000 |

### Behavior

- Calculated on intraday running net P&L (running loss for that trading session).
- **Hitting DLL deactivates the account for that trading day only — does NOT permanently close the account.**
- Account becomes available again at the next session start (5:00 PM CT next weekday).
- DLL is distinct from MLL: hitting MLL = permanent closure; hitting DLL = day timeout.

### After payout

`[VERIFY]` Behavior of DLL post-payout not confirmed in pulled docs. Likely follows MLL reset to $0 (and DLL stays at the original $1,000/2,000/3,000 since DLL is a per-day flat amount not balance-trailing). Confirm during reviewer pass.

---

## 4. Scaling Plan (XFA only — replaces Trading Combine's Maximum Position Size)

`[VERIFY]` Numbers below are from third-party source (h2tfunding.com), since TopStep's official scaling plan article only displays graphs as images. Reviewer must confirm these match TopStep's current dashboard.

### 50K XFA

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 2 lots (= 2 minis or 20 micros) |
| $1,500 – $2,000 | 3 lots |
| Above $2,000 | 5 lots (cap) |

### 100K XFA `[VERIFY-cap]`

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 3 lots |
| $1,500 – $2,000 | 4 lots |
| $2,000 – $3,000 | 5 lots |
| $3,000 – $4,500 | 10 lots (cap, per Combine max) |
| Above $4,500 | 10 lots (capped) |

> The h2tfunding source listed "Above $4,500 → 15 lots" for the 100K, but that contradicts the Trading Combine cap of 10 for 100K accounts. Treat 100K as capped at **10 lots**. Reviewer to verify.

### 150K XFA

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 3 lots |
| $1,500 – $2,000 | 4 lots |
| $2,000 – $3,000 | 5 lots |
| $3,000 – $4,500 | 10 lots |
| Above $4,500 | 15 lots (cap) |

### Scaling Plan rules

- Updates at end-of-day, NOT intraday. Profit during the session does not unlock more contracts that day.
- Errors corrected within 10 seconds are ignored.
- On TopstepX: 1 mini = 10 micros (10:1 ratio). On third-party platforms: 1 micro = 1 lot.
- Special weights: Micro Silver (SIL) = 5:1 vs Silver. Micro Bitcoin (MBT) and Micro Ether (MET) are capped at mini-equivalent sizing, not micro scaling.

### Trading Combine Maximum Position Size (NOT scaling — flat ceiling)

| Combine Account | Max Position Size |
|-----------------|-------------------|
| 50K | 5 minis or 50 micros |
| 100K | 10 minis or 100 micros |
| 150K | 15 minis or 150 micros |

Trading Combine has no scaling — these are flat ceilings throughout the eval.

---

## 5. Trading Hours, Products, and Position Rules

### Trading day definition

A trading day at TopStep = **5:00 PM CT through 3:10 PM CT** of the next calendar day. Trades after 5:00 PM CT count toward the *next* day's activity. Asia-session hours roll into the same trading day as the subsequent morning session.

### Daily flatten requirement

**All positions must be closed before 3:10:00 PM Central Time, Monday through Friday.** No exceptions for XFA. This is the auto-flatten cutoff.

### Reopen times

- Trading resumes at **5:00 PM CT** weekdays
- Sunday open at 5:00 PM CT
- Friday close at 3:10 PM CT

### Overnight / swing

**No swing trading allowed in XFA or Trading Combine.** Positions cannot carry overnight. Live Funded Accounts allow swing trading separately.

### News trading

`[VERIFY]` The article on permitted products did not address news trading restrictions explicitly. The original NoFee paste implies automated strategies are permitted broadly, but specific news-event restrictions weren't fetched. Reviewer to check the "Prohibited Conduct" article.

### Permitted products (full list pulled from official help center)

- **CME Equity:** ES, MES, NQ, MNQ, RTY, M2K, YM, MYM, NKD, MBT, MET
- **Forex:** 6A, 6B, 6C, 6E, 6J, 6S, E7, M6E, M6A, 6M, 6N, M6B
- **Agricultural:** HE, LE, ZC, ZW, ZS, ZM, ZL
- **Energy & Metals:** CL, QM, NG, QG, MCL, RB, HO, PL, MNG, GC, SI, HG, MGC, SIL, MHG
- **Interest Rates:** ZT, ZF, ZN, TN, ZB, UB

### Price Limit rule

Cannot trade within 2% of CME Price Limit. Equity Products (ES/MES/NQ/MNQ/RTY/M2K/YM/MYM) overnight Price Limits are 7%; daytime 5%. So during overnight session, NQ stops at 5% net change up or down (7% − 2% threshold).

---

## 6. Payout Policy

### Two paths (chosen at XFA activation, locked per account)

#### Standard Path
- 5 winning days (Net P&L ≥ $150 each)
- Days don't need to be consecutive
- Payout cap (50K): **$2,000** per request
- Payout cap (100K): $3,000
- Payout cap (150K): $5,000
- 90/10 split (90% trader, 10% TopStep)

#### Consistency Path
- 3 trading days minimum (at least 1 trade per day)
- Largest single day's profit ≤ 40% of total net profit (the consistency calc)
- Payout cap (50K): **$3,000** per request
- Payout cap (100K): $4,000
- Payout cap (150K): $6,000
- 90/10 split

> **Note on the NoFee paste table at line 425:** the "$5000* / $6,000*" numbers shown there are the *maximum* cap across all account sizes (i.e. the 150K row). The asterisk note clarifies this. For 50K specifically, caps are $2,000 (Standard) and $3,000 (Consistency).

### Per-payout request mechanics
- Minimum payout request: **$125**
- Each request capped at 50% of account balance (subject to the per-size dollar caps above)
- After payout: MLL set to **$0**, fresh cycle begins (5 new winning days for Standard or 3 new days at 40% consistency for Consistency)

### Payout request hours
- Sunday 5:00 PM CT – Friday 5:00 PM CT (CME market hours)
- Excluding designated holidays
- Approval: 1–3 business days
- Funds arrive: within 10 business days
- $30 processing fee on ACH and Wire payouts (Aeropay no TopStep fee, but third-party may charge)

---

## 7. Tick values for the most-likely-to-trade contracts (CME standard)

These are CME contract specs, not TopStep policy. Stable and won't change.

| Contract | Tick size | Tick value | Point value |
|----------|-----------|------------|-------------|
| NQ (E-mini Nasdaq-100) | 0.25 | $5.00 | $20 |
| MNQ (Micro E-mini Nasdaq-100) | 0.25 | $0.50 | $2 |
| ES (E-mini S&P 500) | 0.25 | $12.50 | $50 |
| MES (Micro E-mini S&P 500) | 0.25 | $1.25 | $5 |
| YM (E-mini Dow) | 1.0 | $5.00 | $5 |
| MYM (Micro E-mini Dow) | 1.0 | $0.50 | $0.50 |
| GC (Gold) | 0.10 | $10.00 | $100 |
| MGC (Micro Gold) | 0.10 | $1.00 | $10 |
| CL (Crude Oil) | 0.01 | $10.00 | $1,000 |
| MCL (Micro Crude Oil) | 0.01 | $1.00 | $100 |

For the Phase 1 encoding, NQ + MNQ are the priority (matches Georg's discretionary system context and the project plan's Pine Script strategies).

---

## 8. Verification checklist for Phase 1 Reviewer pass

The Reviewer session must confirm the following against TopStep's live dashboard or support before encoding is signed off:

- [ ] DLL dollar amounts ($1,000 / $2,000 / $3,000) — primary article URL returned 404
- [ ] Trading Combine reset costs ($49 / $99 / $149)
- [ ] Standard path Activation Fee — is it $129 (post-2026-04-28 change) or $149?
- [ ] No Activation Fee subscription monthly cost — confirm $109 is current after 2026-04-28 update
- [ ] 100K and 150K Trading Combine subscription costs (not pulled)
- [ ] Scaling Plan numbers — third-party source; verify against TopStep dashboard
- [ ] 100K scaling plan cap — should be 10, third-party source said 15 (likely error)
- [ ] News trading specific restrictions
- [ ] DLL behavior post-payout (does it persist or reset?)

---

## Sources used for this compiled reference

Primary (TopStep official help center):
- Maximum Loss Limit: https://help.topstep.com/en/articles/8284204
- Permitted Products and Trading Hours: https://help.topstep.com/en/articles/8284206
- Payout Policy: https://help.topstep.com/en/articles/8284233
- Trading Combine Parameters: (in original `TopStep NoFee.md` paste)
- XFA Parameters: (in original paste)

Third-party (used where primary was inaccessible — flagged `[VERIFY]`):
- h2tfunding.com TopStep Scaling Plan article (scaling tier numbers)
- tradecovex.com 2026 TopStep guide (DLL values, reset costs)
- Search results on luxalgo.com, propfirmapp.com, h2tfunding.com (subscription pricing)
