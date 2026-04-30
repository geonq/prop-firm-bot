# TopStep — Encoding Reference

> **Last updated:** 2026-04-30
> **Sources:** Original TopStep "No Activation Fee" paste (rule structure) + 2026-04-30 official help-center verification for pricing, MLL, DLL, Trading Combine parameters, XFA parameters, payout policy, trading hours/products, and Back2Funded. Items tagged `[VERIFY]` should be confirmed against TopStep's live dashboard during the Phase 1 Reviewer pass.
> **Status for Phase 1 encoding:** substantially complete for 50K encoding, with scaling-plan numeric graph values still requiring dashboard/image verification.

---

## Pricing

### Trading Combine subscription (recurring monthly)

| Account | Standard Path | No Activation Fee Path |
|---------|---------------|------------------------|
| 50K | $49/mo | **$95/mo** |
| 100K | $99/mo | $149/mo |
| 150K | $149/mo | $229/mo |

> TopStep introduced lower No Activation Fee pricing on **2026-04-28**. These are the current official post-change prices for new purchases.

### Activation fee (one-time, paid when XFA activates)

| Path | Activation Fee |
|------|----------------|
| Standard | $149 |
| **No Activation Fee** | **$0** |

The NoFee path is the project default unless explicitly comparing both.

### Trading Combine reset (manual purchase)

| Account | Standard Path Reset | No Activation Fee Path Reset |
|---------|---------------------|------------------------------|
| 50K | $49 | $109 |
| 100K | $99 | $159 |
| 150K | $149 | $209 |

Each subscription rebill also adds one Reset Credit automatically.

### Back2Funded reactivation (XFA — pre-first-payout only, max 2 per XFA)

| Account | Cost |
|---------|------|
| 50K | **$599** |
| 100K | $699 |
| 150K | $829 |

---

## Maximum Loss Limit (MLL) — the breach rule

### Dollar amounts (from official help center)

| Account | MLL |
|---------|-----|
| 50K | **$2,000** |
| 100K | $3,000 |
| 150K | $4,500 |

### Trailing mechanism

Trails the **highest end-of-day balance**, never moves down. Updates at end-of-day; monitored real-time during the day (intraday breach below MLL = immediate liquidation).

**Trading Combine (50K example):** starts at $50,000, MLL begins at $48,000. Day 1: +$500 → balance $50,500, MLL trails to $48,500. Day 2: −$500 → balance $50,000, MLL stays at $48,500 (never moves down). **Once MLL trails up to the original starting balance ($50,000 for 50K), it locks there permanently.**

**XFA (50K example):** starts $0 displayed balance, MLL at −$2,000. After +$1,000: balance $1,000, MLL trails to −$1,000. After another +$1,000: balance $2,000, **MLL locks at $0 permanently.**

After taking a payout in XFA, **MLL resets to $0** and a fresh winning-day cycle begins.

### Hitting MLL — consequences

| Phase | Consequence |
|-------|-------------|
| Trading Combine | Liquidated for the day; ineligible for funding until reset |
| XFA | Permanently closed (Back2Funded available if no payout taken) |
| Live | Closed at end of day |

---

## Daily Loss Limit (DLL) — optional in Trading Combine/XFA, automatic in Live

| Account | DLL |
|---------|-----|
| 50K | **$1,000** |
| 100K | $2,000 |
| 150K | $3,000 |

**Behavior:** intraday running net P&L. In Trading Combine or XFA, DLL can be selected permanently at checkout or configured manually in TopstepX risk settings. Hitting DLL **auto-liquidates/blocks trading for that session only — it is not a rule violation and does not permanently close the account.** Account becomes available again next session start (5:00 PM CT next weekday). Live Funded Accounts have DLL automatically. Materially different from MLL.

---

## Scaling Plan (XFA only — replaces Trading Combine's Maximum Position Size) `[VERIFY]`

Numbers below are third-party-sourced (TopStep's official scaling plan article shows graphs as images only). Reviewer to confirm against dashboard.

### 50K XFA

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 2 lots |
| $1,500 – $2,000 | 3 lots |
| Above $2,000 | 5 lots (cap) |

### 100K XFA

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 3 |
| $1,500 – $2,000 | 4 |
| $2,000 – $3,000 | 5 |
| $3,000 – $4,500 | 10 (cap, per Combine max) |
| Above $4,500 | 10 |

> Third-party listed "Above $4,500 → 15" for 100K but that contradicts the Combine cap of 10 — treat as 10. Reviewer to verify.

### 150K XFA

| End-of-Day Balance | Max Contracts |
|---------------------|---------------|
| Below $1,500 | 3 |
| $1,500 – $2,000 | 4 |
| $2,000 – $3,000 | 5 |
| $3,000 – $4,500 | 10 |
| Above $4,500 | 15 (cap) |

### Rules
- Updates at end-of-day. Mid-session profit doesn't unlock contracts that day.
- Errors corrected within 10 seconds are ignored.
- TopstepX: 1 mini = 10 micros (10:1). Third-party platforms: 1 micro = 1 lot.
- Special: Micro Silver = 5:1 vs Silver. Micro Bitcoin (MBT) and Micro Ether (MET) capped at mini-equivalent sizing, not micro scaling.

### Trading Combine Maximum Position Size (flat ceiling — no scaling)

| Combine | Max |
|---------|-----|
| 50K | 5 minis or 50 micros |
| 100K | 10 minis or 100 micros |
| 150K | 15 minis or 150 micros |

---

## Trading Hours, Products, Position Rules

- **Trading day:** 5:00 PM CT through 3:10 PM CT next calendar day. Trades after 5:00 PM CT count toward NEXT day's activity.
- **Daily flatten:** All positions must close before **3:10:00 PM CT, Monday–Friday.**
- **Reopen:** 5:00 PM CT weekdays / 5:00 PM CT Sunday.
- **Friday close:** 3:10 PM CT.
- **No swing trading in XFA or Trading Combine** — positions cannot carry overnight.
- **Price limit rule:** cannot trade within 2% of CME Price Limit (overnight equity Price Limits = 7%, daytime = 5%).

### Permitted products (full list, official help center)

- **CME Equity:** ES, MES, NQ, MNQ, RTY, M2K, YM, MYM, NKD, MBT, MET
- **Forex:** 6A, 6B, 6C, 6E, 6J, 6S, E7, M6E, M6A, 6M, 6N, M6B
- **Agricultural:** HE, LE, ZC, ZW, ZS, ZM, ZL
- **Energy & Metals:** CL, QM, NG, QG, MCL, RB, HO, PL, MNG, GC, SI, HG, MGC, SIL, MHG
- **Interest Rates:** ZT, ZF, ZN, TN, ZB, UB

NQ + MNQ permitted — Phase 4 Pine Scripts have no conflict.

---

## Payout Policy

### Two paths (chosen at XFA activation, locked per account)

| | Standard | Consistency |
|---|---|---|
| Eligibility window | 5 winning days (Net P&L ≥ $150 each, non-consecutive) | 3 trading days, largest day ≤ 40% of total profit |
| 50K cap per request | **$2,000** | $3,000 |
| 100K cap | $3,000 | $4,000 |
| 150K cap | $5,000 | $6,000 |
| Split | 90/10 | 90/10 |

> **Correction to original paste:** the table at line 425 of the original paste shows "$5000* / $6,000*" — those are the **150K row**, not 50K. The asterisk note in that table clarifies caps are per-account-size; for 50K specifically they're $2,000 (Standard) and $3,000 (Consistency).

### Per-request mechanics
- **Min payout request:** $125
- Each request capped at 50% of account balance, subject to per-size caps above
- After payout: MLL set to $0, fresh cycle begins (5 new winning days for Standard / 3 new days at 40% for Consistency)

### Request hours
- Sun 5:00 PM CT – Fri 5:00 PM CT (CME hours, excluding holidays)
- Approval: 1–3 business days; funds: within 10 business days
- $30 processing fee on ACH and Wire payouts

---

## Tick values (CME standard)

| Contract | Tick size | Tick value | Point value |
|----------|-----------|------------|-------------|
| NQ | 0.25 | $5.00 | $20 |
| MNQ | 0.25 | $0.50 | $2 |
| ES | 0.25 | $12.50 | $50 |
| MES | 0.25 | $1.25 | $5 |
| YM | 1.0 | $5.00 | $5 |
| GC | 0.10 | $10.00 | $100 |
| MGC | 0.10 | $1.00 | $10 |
| CL | 0.01 | $10.00 | $1,000 |
| MCL | 0.01 | $1.00 | $100 |

NQ + MNQ are Phase 1 priority.

---

## Verification checklist for Phase 1 Reviewer pass

- [ ] Scaling Plan numbers — third-party sourced, verify in dashboard
- [ ] 100K scaling cap — 10 not 15 (third-party error)
- [ ] News-trading specific restrictions in TopStep "Prohibited Conduct"

---

# 📄 Below: Original TopStep "No Activation Fee" paste (rule structure — verbatim)


# Level 1 & Level 2 Market Data
## What is the difference between Level 1 (Top of Book) Data and Level 2 (Depth of Market) Data?

Level 1 Data, also known as Top of Book Data, includes the best bid and best ask. If you are chart trading, this is the data you are using.

Level 2 Data, also known as Depth of Market Data, includes 5-10 of the best bid and ask prices so you can see sell and buy orders waiting to be placed. If you are DOM or Matrix trading, this is the data you are using.

## Why Are We Charging for Depth of Market Data?

The CME requires payment for all market data provided to simulated accounts. As a courtesy, Topstep will cover the cost of Top of Book Data of all four exchanges on our SIM accounts.

Traders who would like to receive Level 2 (Depth of Market) Data for all exchanges can upgrade from their dashboard (see below).

## When will I be charged for Depth of Market Data?

You will be charged for Depth of Market Data immediately when you upgrade, and you will be rebilled for your Depth of Market Data at the end of each month.

**If you already have Level 2 (Depth of Market) Data, you will continue to have it for all Trading Combines under the same username.**

## How do I purchase Level 2 Data?

To purchase Level 2 Data, visit your **Accounts** tab and then click **Add Ons** (shown below). After that, select _Depth of Market Bundle._
# Frequently Asked Questions:

**Why are you charging for Level 2 data now?**

The CME is now charging everyone for market data used in simulated trading accounts. We are making Level 1 Data (Top of Book) FREE to all traders and for all four exchanges on Topstep accounts.

If you would like Level 2 (Depth of Market) Data, you will need to upgrade your data subscription for $38/month.

**Can I cancel my Data?**

You can cancel your Level 2 Data subscription at any time. You can do so right from your **Billing** page. Please note: when you cancel your Level 2 Data subscription, you will lose access immediately. For this reason, we recommend canceling on the last day that you wish to use the subscription.

**Is Data pro-rated?**

No, Level 2 Data is not pro-rated. This means you'll be charged the full price regardless of when you purchase. You will be charged on the 28th of each month for the upcoming month, regardless of when you signed up initially. For example, if you sign up on the 26th of the month, you will still be charged on the 28th when the subscription renews.

**Can I get a refund for my Level 2 market Data purchase?**

No, we do not issue refunds for Level 2 Data purchases once the billing for your Data is processed. If you no longer need Level 2 Data, please cancel your subscription by the 27th of each month. Once the cancellation is processed, you will automatically be moved to Level 1 Data.

**Do I need to pay for Data if I am in an Express Funded Account?**

You do not need to pay for Level 1 Data in the Express Funded Account because Topstep makes it free for all simulated accounts. However, you do need to pay for Level 2 Data and can upgrade anytime right from your dashboard.

# Trading Combine Subscriptions

Covers billing, rebill dates, Resets, cancellations, and common questions about managing your Trading Combine subscription.

---

The Trading Combine is a monthly subscription that rebills automatically every 30 days from your original sign-up date. There is no time limit for passing. Your subscription remains active until you pass and earn an [Express Funded Account](https://intercom.help/topstep-llc/en/articles/8284215-express-funded-account-parameters), or until you cancel. To check your upcoming rebill date or manage your subscription, [click here](https://dashboard.topstep.com/dashboard/).



---

**Trading Combine Subscription FAQs**

Click any question below to expand the full answer.

### What does the Trading Combine cost?

  
Learn all about the cost of the Trading Combine here: [Topstep Pricing and Payment Information](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions)

### What payment methods are accepted?

  
You can pay for your Trading Combine with a credit card or debit card.

- Visa
    
- Mastercard
    
- American Express
    
- Discover
    

_*Prepaid credit cards and gift cards (including Cash App and Venmo cards) may not be valid payment methods. We recommend using a standard credit card or debit card._

All purchases, including Trading Combine fees, Resets, and Activation Fees, must be made using a payment method registered under your own name. Using a card that belongs to a spouse, friend, or any other individual is not permitted and is a violation of our [Terms of Use](https://www.topstep.com/terms-of-use/).

### How do I cancel my subscription?

  
To cancel your subscription, go to your Billing page and click the "x" next to the subscription you want to cancel. If you're unsure which subscription ID corresponds to the account you want to cancel, check your Accounts page first to locate it. Once you confirm the cancellation, you'll be prompted to review and agree to the cancellation terms.

For example, in the screenshot above, the Trading Combine account name 50KTC-V2-181429-15166904 corresponds to Subscription ID 149038.

From there, go to your **Billing** page and click the "x" next to that subscription ID to cancel it:

You'll be prompted to confirm you understand the terms of canceling the subscription next:

Please note that once you cancel in the new Dashboard, the action cannot be undone. There is no option to resubscribe. Additionally, you will no longer be able to purchase a Reset on that subscription.

### What happens to my subscription if I Reset my account or break a rule?

#### What happens to my subscription if I Reset my account or break a rule?

- Your Trading Combine does not automatically close or cancel if you break a rule. If you break a rule (hit the [Maximum Loss Limit](https://intercom.help/topstep-llc/en/articles/8284204-what-is-the-maximum-loss-limit)), that account becomes ineligible for funding until it is Reset, but your subscription rebill date does not change.
    
- Each time your subscription rebills, one Reset Credit is added to your Reset Bank based on your account size and path. If you purchase a Reset, your rebill date moves 30 days forward from the date of purchase. Example: rebill is Aug 30, Reset purchased Aug 28, new rebill date becomes Sep 29.
    
- The account will remain ineligible for funding until it is Reset, but you can still trade on it for practice once markets reopen. Your Practice Account is also available.

### Can I put my Trading Combine subscription on hold?

#### Can I put my Trading Combine subscription on hold?

- No, a Trading Combine cannot be paused or put on hold due to system limitations. The subscription rebills monthly until you pass the Trading Combine and earn your Express Funded Account, or until you decide to cancel.
    
- Since there's no time limit for completing the Trading Combine, you can keep your subscription active while you're away (remember, you'll still be billed monthly), or you can cancel it. If you cancel, any progress on the account will be lost, but you can sign up again when you're ready to trade.​

### When do I need to pass my Trading Combine to avoid being rebilled again?

#### When do I need to pass my Trading Combine to avoid being rebilled again?

  
If you want to avoid being rebilled after you pass your Trading Combine, your [Trade Report](https://intercom.help/topstep-llc/en/articles/8284127-what-is-a-trade-report-and-when-should-i-expect-it-to-update) needs to reflect that you've passed before your Trading Combine subscription rebill date. For example, if your rebill date is on the 5th of each month, you'll need to pass your Trading Combine before the trading day ends on the 4th to avoid being rebilled.

### If I pass the Trading Combine but can't pay the Activation Fee right away, will I be rebilled again?

#### If I pass the Trading Combine but can't pay the Activation Fee right away, will I be rebilled again?

  
You will not be rebilled for the monthly subscription fee after passing the Trading Combine. Once you pass the Trading Combine, your monthly rebill payments are automatically turned off.

### Can I have more than one Trading Combine at a time?

#### Can I have more than one Trading Combine at a time?

Yes, you can trade in more than one Trading Combine at a time.

- There is no limit to how many Trading Combines you trade in at one time.
    
- Opening a new Trading Combine will not close any existing ones.
    
- Always confirm which account you are trading in before placing trades. Topstep is not responsible for trades made in the wrong account.
    

**While we don’t limit the number of Trading Combines you can trade at one time, we do limit the number of new Trading Combines you can start each month to 20 accounts.** Having a limit helps developing traders avoid account churn.

The Trading Combine was developed to help you hone your skills and strategy, but remember, each account counts!

When you are account-churning at rapid fire, you aren’t learning from mistakes or getting the time to reflect and make improvements.

Focus on trading in one account until you have a proven strategy. And whether you trade one or multiple accounts, make sure to follow the [Dos and Don'ts of Responsible Trading](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program).

**Learn more about limits on new accounts [here](https://intercom.help/topstep-llc/en/articles/10370307-is-there-a-limit-to-the-number-of-accounts-i-can-purchase?q=how+many+accounts).**

### **What happens to my subscription after I pass the Trading Combine?**

Passing the Trading Combine triggers automatic changes to your subscription. Here's what to expect.

**Why did I receive a cancellation email after passing?**

When your Trading Combine is marked as Passed, the subscription for that account is automatically canceled. The cancellation email you receive is a standard notification confirming this — it does not indicate any problem with your account or your progress toward funding.

**Does passing cancel all of my subscriptions?**

No. Only the subscription tied to the passed Trading Combine is automatically canceled. If you have other active Trading Combine subscriptions, those will continue to rebill monthly until you manually cancel them.

To cancel other subscriptions, go to the **Billing** section of your dashboard and click the "x" next to each subscription you want to cancel.

Other active subscriptions will keep billing until you manually cancel them.

**I passed, but I'm still being charged. What should I do?**

Check your Billing page for any other active Trading Combine subscriptions that haven't been passed yet. These will continue to rebill automatically until you cancel them manually.

If you believe you're being charged in error for the passed account specifically, please contact support.

**Can I use reset credits on a canceled account?**

No. Reset credits can only be applied to Trading Combines with an active subscription. Once a subscription is canceled — whether automatically after passing or manually — reset credits can no longer be used on that account.

If you want to continue trading on that account, you'll need to purchase a new Trading Combine.

**Can I reactivate a canceled subscription?**

No. Once a subscription is canceled, it cannot be reactivated. You will need to purchase a new Trading Combine to continue trading.

# Practice Account

A risk-free way to test strategies and explore products without impacting your primary trading account.
## **Practice Account Details:**

- All Practice accounts will be **150K**, regardless of your active Trading Combine or Express Funded Account size.
    
- The Maximum Position size for all Practice Accounts will be **15 lots.**
    
- **You can have one (1) Practice Account** at a time.
    
- Practice Accounts will be **labeled “PRACTICE**” in the drop-down on your Dashboard and platform.
    

#### Traders with an active Trading Combine can access a Practice Account free of charge.

[![](https://downloads.intercomcdn.com/i/o/bjnr216i/2247037090/c6b62c6e7488cc9532c62643544a/image.png?expires=1777491900&signature=0d9ea3096e684ee8a7065569ccf4c5c8e0a0c7cad3770a6bbba9796e1d05db3e&req=diIjEcl9moFWWfMW1HO4zS3CMoypxR8Y8ZLikMHvVE9V%2BqQ2mhps%2F7%2FbIJ6i%0AHeBYBAf6tO7GsbxfAGo%3D%0A)](https://downloads.intercomcdn.com/i/o/bjnr216i/2247037090/c6b62c6e7488cc9532c62643544a/image.png?expires=1777491900&signature=0d9ea3096e684ee8a7065569ccf4c5c8e0a0c7cad3770a6bbba9796e1d05db3e&req=diIjEcl9moFWWfMW1HO4zS3CMoypxR8Y8ZLikMHvVE9V%2BqQ2mhps%2F7%2FbIJ6i%0AHeBYBAf6tO7GsbxfAGo%3D%0A)

The Practice Account allows you to have access to a second trading account that allows you to test strategies, products, etc., without affecting your primary account. If you hit or exceed your Maximum Loss Limit in a Practice Account, it can be reset at any time for no additional fee.

---

## **Practice Accounts on the new Topstep Dashboard**

Practice Accounts are available on the new Dashboard **with an active Topstep Trading Combine subscription.**

**To activate your Practice Account on the new Dashboard**, please follow these steps:

1. Log in to the new [Topstep Dashboard](https://dashboard.topstep.com/login)
    
2. Click “Accounts” on the left-hand side of your screen
    
3. Click "Add-ons" on the top left-hand side of your screen
    
4. A new page with the option to activate your TopstepX Practice Account will display
    
5. Click Activate
    

**To close your Practice Account on the new Dashboard**, simply follow the steps above, but the button will now say "unsubscribe". A new page will appear again, asking you to confirm the cancellation.

**If you're having trouble adding a new Practice Account or all of your Practice Accounts are closed**, click "Unsubscribe" from the Available Add-ons section.

**After clicking "Unsubscribe", click "Activate" to have a new Practice Account created.**

---

## **Troubleshooting access issues**

**I can't activate my Practice Account — what should I check?**

If the Activate button isn't available, an incomplete KYC (Know Your Customer) verification is most likely the cause. Check your email for the KYC form, submit it for approval, then return to the Add-Ons page and try again. Note that KYC is also required to purchase new Trading Combines, so completing it will unblock both.

---

## **Common questions**

**Does a Practice Account come automatically with a Trading Combine?**

No. A Practice Account is a free add-on, but it must be manually activated. Having an active Trading Combine subscription makes you eligible, but access isn't granted automatically — you need to activate it through the Add-ons section of your dashboard.

How long do I have access to a Practice Account?

As long as you have an active Trading Combine or Express Funded Account with Topstep, you'll have access to a Practice Account.

Practice Account resets are always free — hone in on your strategy without the cost.

---
# Trading Combine® Parameters

The Trading Combine has one rule and a few objectives standing between you and your Express Funded Account. Here's what you need to know to pass and what happens next.

---

As you probably know, becoming a successful intraday trader who consistently takes capital out of the market is no small task. Losing $1,000+ in intraday trading is a real thing that happens every day to traders. Our mission is to provide a safe experience so that traders can professionalize their passion. The Trading Combine® was designed to limit your personal risk.

The Trading Combine has one single rule and several objectives. Keep reading for more information on the rule and objectives, and some helpful resources as you get started.

If you meet these parameters and achieve the Profit Target for your account size, you'll progress to the [Express Funded Account](https://intercom.help/topstep-llc/en/articles/8284216-express-funded-account-live-funded-account-faq-s). Additionally, it's essential to understand the [Maximum Position Size](https://help.topstep.com/en/articles/8284197-trading-combine-parameters#h_11535c919e) and [Permitted Products and Trading Hours](https://intercom.help/topstep-llc/en/articles/8284206-when-and-what-products-can-i-trade).

---

# Rule:

- Do not allow your Account Balance to hit or go below the [Maximum Loss Limit](https://intercom.help/topstep-llc/en/articles/8284204)
    

# Objectives:

- Reach and maintain the profit target
    
- [Consistency Target](https://intercom.help/topstep-llc/en/articles/8284208): Best Day below 50% of total profits made
    


---

# Trading Combine FAQs

## Can I have more than one Trading Combine?

Yes, you can have more than one active Trading Combine at a time. There is no limit to how many active Trading Combines you can have at any given time.

If you do have multiple Trading Combines, make sure to double-check which account you're trading on before you begin trading. Topstep isn't responsible for any trades made on the wrong account.

While there is no limit to the number of Trading Combines you can have, there are limits to the number you can _purchase_ each month. [You can learn more here](https://intercom.help/topstep-llc/en/articles/10370307-is-there-a-limit-to-the-number-of-accounts-i-can-have?q=how+many+accounts).

**Single Account Policy**

Traders are not permitted to have multiple Topstep profiles, and the existence of multiple Topstep profiles for a single user is a violation of our [Terms of Use](https://www.topstep.com/terms-of-use/) that can potentially result in negative actions such as:

- Topstep profiles or Trading Combines being closed without warning
    
- A temporary or permanent suspension of your accounts
    

**All Trading Combines, Express Funded Accounts, and Live Funded Accounts must be opened using a single Topstep profile. Do not create a new Topstep profile when purchasing additional Trading Combines.**

- If you've opened an additional Trading Combine under a separate Topstep profile or opened more than one Topstep profile, please [contact our Trader Support Team](https://intercom.help/topstep-llc/en/articles/8284118-how-do-i-access-the-support-team).
    

- For updates to your name or email address, avoid making a new profile. See the full details here: [How do I change the name or email address on my account?](https://intercom.help/topstep-llc/en/articles/8301076-how-do-i-change-the-name-or-email-address-on-my-topstep-dashboard)
    

## Do I need to purchase data?

### Do I need to purchase data?

Level 1 (Top of Book) live real-time data is included in your Topstep® membership at no additional cost in the Trading Combine and Express Funded Account. Level 1 Data is sufficient for chart traders, and anyone trading from a DOM or Ladder can upgrade to Level 2 (Depth of Market) data.

You can learn more about the differences between Level 1 & Level 2 Data and step-by-step instructions on how to upgrade to Level 2 data in the [Level 1 & Level 2 Market Data](https://intercom.help/topstep-llc/en/articles/8284120) article.

## What happens after I pass the Trading Combine?

### What happens after I pass the Trading Combine?

Trade reports are updated in real time, so you can pass your Trading Combine and activate it immediately! You'll receive an email and be able to activate your new Express Funded Account right from your dashboard. **Please note:** it may take up to 30 minutes for your Trading Combine status to reflect that you've passed in the dashboard. You can learn more [here](https://intercom.help/topstep-llc/en/articles/8284217-express-funded-account-activation). If it has been more than 30 minutes and your status still shows **Active**, verify that your [Consistency Target](https://help.topstep.com/en/articles/8284208-what-is-the-consistency-target) has been met — your best day's profit must be 50% or less of your total profits for your account to flip to Passed.  
​

**Important:**

- Once you've been notified that you passed the Trading Combine, it's time to begin the Express Funded Account activation process. [Click here for step-by-step instructions](https://intercom.help/topstep-llc/en/articles/8284217-express-funded-account-activation-fee) on activating your Express Funded Account. The entire process only takes a few minutes!  
    ​
    
- If you pass your Trading Combine on a Friday after market close, you can pay the Activation Fee immediately, but your new Funded Account will not be available to trade until the markets reopen at 5 PM CT on Sunday.  
    ​
    
- **Trading day hours:** The trading day is defined as 5:00 PM CT through 3:10 PM CT on the next calendar day. Trades executed after 5:00 PM CT, such as a trade placed at 6:30 PM CT on a Tuesday, are recorded as part of Wednesday’s trading activity. Likewise, Asia‑session hours are attributed to the same trading day as the subsequent morning session, rather than the preceding calendar date.  
    ​
    
- Profits made in the Trading Combine _DO NOT_ transfer to the Express Funded Account.
    

## When will I receive my Funded Trader Certificate?

### When will I receive my Funded Trader Certificate?

You'll be able to access your Funded Trader Certificate right from your Topstep Dashboard, right from the Achievements tab!


## Can I change my account size?

### Can I change my account size?

- Account sizes cannot be changed or adjusted after purchase. If your purchase was made within the last 72 hours and your account has had no trading activity, please contact our [Trader Support Team](https://intercom.help/topstep-llc/en/articles/8284118-how-do-i-access-the-support-team) — we can review your account for a refund so you can purchase a new account at the correct size.
    
- If more than 72 hours have passed or any trading activity has occurred, we are unable to process a refund.
    

## Can automated trade strategies be used in the Trading Combine?

### Can automated trade strategies be used in the Trading Combine?

Yes, automated strategies are permitted, with a few things to note:

- Topstep cannot help set up or troubleshoot automated strategies and will not make exceptions for errant trades or malfunctions.
    
- Before getting started, we recommend testing on your Practice Account and reviewing our [Prohibited Conduct](https://help.topstep.com/en/articles/10296582-prohibited-conduct) and [Do's and Don'ts of SIM Fills](https://help.topstep.com/en/articles/10431370-the-do-s-and-don-ts-of-sim-fills) articles.
    

**Tip:** You can duplicate trades across multiple accounts using a trade copier. Learn more about our Trade Copier [here](https://intercom.help/topstep-llc/en/articles/8284140-what-is-a-trade-copier).

## What is the Maximum Position Size in the Trading Combine?

### Maximum Position Size

Maximum Position Size is the maximum number of contracts a Trader is allowed to hold open, per account, at one time. This limit helps ensure consistent risk management while you progress through the program.  
​  
Micros and minis are calculated at a 10:1 ratio toward the limit. On third-party platforms, micros count as full lots (1 micro = 1 lot).  
​  
Your Maximum Position Size is based on your account size:

- **$50K Trading Combine** → Up to **5 contracts or 50 micros**
    
- **$100K Trading Combine** → Up to **10 contracts or 100 micros**
    
- **$150K Trading Combine** → Up to **15 contracts or 150 micros**
    

This limit applies to your **total open position at any given time**. Exceeding the maximum position size may result in rejected orders, so it's important to monitor your position as you trade.

Traders are not required to trade the maximum -- they can always trade fewer contracts than their limit allows.

---
# Express Funded Account™ Parameters

Learn about each type of Express Funded Account and its objectives

Updated this week

**[Express Funded Account Information](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters#h_5da55f97b8)**

**[Choose Your Path to Payouts](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters#h_5967b945ef)**

**[Express Funded Account Standard: Rules and Objectives](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters#h_9d5dc242ba)**

**[Express Funded Account Consistency: Rules and Objectives](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters#h_82f0c00f72)**

**[Express Funded Account FAQs](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters#h_025892bb60)**

## **Express Funded Account Information**

- The Express Funded Account™, sometimes referred to as the "XFA", is the simulated Funded Level account that traders earn after passing the Trading Combine. After you’ve passed your Trading Combine and completed [the necessary steps](https://intercom.help/topstep-llc/en/articles/8284198-what-happens-after-i-complete-the-trading-combine), you can start taking Payouts from your Express Funded Account based on our [Payout Policy](https://intercom.help/topstep-llc/en/articles/8284233).
    
- Traders are allowed to have **up to five (5) Express Funded Accounts** active at the same time. Take a look at the full details here: [Multiple Express Funded Accounts](https://intercom.help/topstep-llc/en/articles/8284218-multiple-express-funded-accounts).
    
- Your Express Funded Account will show as having a $0 balance in your trading platform when you first start trading the account. The total number of contracts you're allowed in the Express Funded Account is determined by the [Scaling Plan](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters). Making additional profits will increase the number of contracts you're allowed to trade (up to the former Maximum Position Size from your Trading Combine).  
    ​
    

### Choose Your Path to Payouts

**Starting February 5, 2026,** you'll be able to choose between two types of Express Funded Accounts. Read below to learn more about the differences between the Express Funded Account Standard and Express Funded Account Consistency.

|   |   |
|---|---|
|**Standard Path**|**Consistency Path**|
|_Current payout policy_|_New payout option_|
|5 winning days of $150+|3 days traded with 40% consistency target|
|Request 50% of account balance<br><br>up to $5000*|Request 50% of account balance<br><br>up to $6,000*|
|90/10 split|90/10 split|

***Your payout cap is based on your account size and path. Learn more [here](https://help.topstep.com/en/articles/8284233-topstep-payout-policy).**  
​

## **Express Funded Account Standard: Rules and Objectives**

Your main objective in the Express Funded Account Standard is to work toward paying yourself by utilizing our simple [Payout Policy](https://intercom.help/topstep-llc/en/articles/8284233). Additionally, the [Scaling Plan](https://intercom.help/topstep-llc/en/articles/8284223-what-is-the-scaling-plan) is an objective that must be followed in the Express Funded Account to help protect your account. The [Scaling Plan](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) in the Express Funded Account™ replaces the [Maximum Position Size](https://help.topstep.com/en/articles/8284197-trading-combine-parameters#h_11535c919e) in the Trading Combine.

**Rules**

_There is only one (1) rule in Express Funded Accounts:_

- Do not allow your Account Balance to hit or exceed the [Maximum Loss Limit](https://intercom.help/topstep-llc/en/articles/8284204)
    

**Objectives**

- Payout Eligibility: [5 Winning Days of $150+](https://intercom.help/topstep-llc/en/articles/8284233)*
    
- Follow the [Scaling Plan](https://intercom.help/topstep-llc/en/articles/8284223)
    
- Do not hit or exceed the [Daily Loss Limit](https://intercom.help/topstep-llc/en/articles/8284207)** or your account will be deactivated for that trading day
    

Just like the Trading Combine, the Express Funded Account is traded in a simulated environment, but the key differences between these accounts are important to know.

- [Consistency Target](https://intercom.help/topstep-llc/en/articles/8284208-what-is-the-consistency-target) - There is no Consistency Target in the Express Funded Account Standard.
    
- [Profit Target](https://intercom.help/topstep-llc/en/articles/8284197-trading-combine-parameters) - Unlike your Trading Combine Account, there's no Profit Target in Funded Level Accounts
    

## **Express Funded Account Consistency: Rules and Objectives**

Your main objective in the Express Funded Account Consistency is to work toward paying yourself by utilizing our simple [Payout Policy](https://intercom.help/topstep-llc/en/articles/8284233). Additionally, the [Scaling Plan](https://intercom.help/topstep-llc/en/articles/8284223-what-is-the-scaling-plan) is an objective that must be followed in the Express Funded Account to help protect your account. The Scaling Plan in the Express Funded Account™ replaces the [Maximum Position Size](https://intercom.help/topstep-llc/en/articles/8284209) in the Trading Combine.

XFA Consistency is a new Express Funded Account (XFA) option designed to reward disciplined, repeatable trading while offering a faster path to payout eligibility. This article explains how XFA Consistency works, how it compares to XFA Standard, and what to expect depending on your trading program status.

**Rules**

_There is only one (1) rule in Express Funded Accounts:_

- Do not allow your Account Balance to hit or exceed the [Maximum Loss Limit](https://intercom.help/topstep-llc/en/articles/8284204)
    

**Objectives**

- Follow the [Scaling Plan](https://intercom.help/topstep-llc/en/articles/8284223)
    
- Payout Eligibility: 3 days with 40% consistency target
    
    - A minimum of 3 trading days
        
    - At least one trade per day
        
    

This is a shorter window compared to the 5 winning-day minimum under XFA Standard.

Just like the Trading Combine, the Express Funded Account is traded in a simulated environment, but the key differences between these accounts are important to know.

- [Profit Target](https://intercom.help/topstep-llc/en/articles/8284197-trading-combine-parameters) - Unlike your Trading Combine Account, there's no Profit Target in Express Funded Accounts.
    

##   
Express Funded Account Consistency FAQs  

### What Is Express Funded Account Consistency?

  
XFA Consistency offers an alternative payout policy available after passing a Trading Combine. When you qualify for an Express Funded Account, you can choose between:

- XFA Standard – our existing payout rules
    
- XFA Consistency – a new option that introduces a consistency calculation but allows payout eligibility in as few as 3 trading days
    

### How is Consistency Calculated?

  
Consistency = Largest Winning Day ÷ Current Total Net Profit

This means if your balance is negative, you don't have profit and will not see consistency tracking on your dashboard. You'll need to build positive profit to unlock consistency tracking.


### Why does the Express Funded Account Consistency exist?

  
XFA Consistency is designed to encourage strong trading habits that support long-term success. By focusing on balanced performance rather than outsized single-day wins, traders are rewarded for consistency while gaining access to earlier payout eligibility.

### Can I have a mix of both Consistency and Standard Express Funded Accounts?

  
As long as you are not in our Focused Trader Plan (FTP), you may maintain a mix of XFA Standard and XFA Consistency accounts, up to the overall XFA account limit.

### How do payouts affect Consistency?

  
After a payout is taken, your consistency calculation resets and applies only to profits earned after that payout.  
​

**Example Scenario:**

1. First payout window:
    
    - Day 1: $5,000 profit
        
    - Day 2: $5,000 profit
        
    - Day 3: $5,000 profit
        
    - Total profit: $15,000
        
    - Consistency: 33%  
        ​
        
    
2. Payout taken: $5,000
    
    - Remaining profit balance: $10,000  
        ​
        
    
3. New payout window begins:
    
    - Day 1: $100 profit
        
    - Day 2: $100 profit
        
    - Day 3: $100 profit
        
    

Consistency is now calculated only on the $300 earned after the payout, and eligibility must be met again before requesting another payout.

**Please note:** Once selected, the Express Funded Account type applies to that account and cannot be changed.

---

##   
**Express Funded Account FAQs**  

### Can I have more than one Funded Account?

  
​Yes, with a few rules to keep in mind:

- You can have up to 5 active Express Funded Accounts at the same time.
    
- If you pass a Trading Combine but have already reached your account limit, any new Express Funded Accounts will be on hold until an active account is closed due to a rule violation.
    
- If you have a [Shoulder Tap Express Funded Account](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters), you are limited to 1 Express Funded Account. If that account closes, you can have up to 5. Learn more here.
    
- Reminder: Only 1 Live Funded Account is permitted. When you receive one, all Express Funded Accounts are closed. Learn more [here](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters).
    

### What combinations of Funded Accounts can I have?

- Traders can have different account sizes for Express Funded Accounts. For example, you can have two (2) 50K Express Funded Accounts and three (3) 150K Express Funded Accounts at the same time.
    

- Traders can only have one (1) Live Funded Account when offered a Live trading account. The Live Funded Account parameters will be based on the largest account that is passed.
    

### Can I change the size of my Express Funded Account?

  
The size of your Express Funded Account will match the size of the Trading Combine you passed. You cannot change the size before you activate, or after.

### Why does the balance in my new Express Funded Account show $0 or N/A?

  
When you start trading in your new Express Funded Account, it will initially show a balance of zero ($0) or N/A in your trading platform. However, the buying power for this Express Funded Account remains the same as the corresponding Trading Combine account size you passed, whether it's 50K, 100K, or 150K.

### What are the fees for the Express Funded Account?

  
There’s no [monthly subscription](https://intercom.help/topstep-llc/en/articles/8284121-how-does-the-monthly-subscription-work) fee for an Express Funded Account since the subscription ends once you pass the Trading Combine.

The [Activation Fee](https://intercom.help/topstep-llc/en/articles/8284217) is required as a one-time payment per Express Funded Account on our [Standard Trading Combine Path](https://help.topstep.com/en/articles/9208217-topstep-pricing#h_1a6b716941). To prevent delays in receiving your Express Funded Account credentials, make sure to use the same email address associated with your Topstep.com account when paying the Activation Fee.

### Do I need to purchase data?

  
Level 1 (Top of Book) live real-time data is included in your Topstep® membership at no additional cost in the Trading Combine and Express Funded Account. Level 1 Data is sufficient for chart traders, and anyone trading from a DOM or Ladder can upgrade to Level 2 (Depth of Market) data.

You can learn more about the differences between Level 1 & Level 2 Data and step-by-step instructions on how to upgrade to Level 2 data in the [Level 1 & Level 2 Market Data](https://intercom.help/topstep-llc/en/articles/8284120) article.

### How long does it take to receive my Express Funded Account?

  
Once you pass the Trading Combine, you can complete the Express Funded Account Activation process and gain access to your new Funded Account within minutes. Click [here for step-by-step instructions](https://intercom.help/topstep-llc/en/articles/8284217-express-funded-account-activation-fee).

**Please note:** If you pass your Trading Combine on a Friday, you can pay the Activation Fee immediately, but your new Funded Account will not be available on your Dashboard or in your Trading Platform until the markets reopen at 5 PM CT on Sunday.

### How long do I have to pay the Activation Fee and get started with my Express Funded Account?

- If you have less than five (5) active Express Funded Accounts, you have 30 days _from passing your Trading Combine_ to pay your Activation Fee and get started with the Express Funded Account.
    

- If you pass a Trading Combine and already have a maximum of five (5) active Express Funded Accounts, your additional account will be on hold. You will have 30 days to pay the Activation Fee and get started the next time your active Express Funded Accounts _are below the maximum of 5 accounts._
    

### If I pass the Trading Combine but can't pay the Activation Fee right away, will I be rebilled again?

You will not be rebilled for the monthly subscription fee after passing the Trading Combine. Once you pass the Trading Combine, your monthly rebill payments are automatically turned off.

### What happens if I lose my Express Funded Account due to violating the Maximum Loss Limit?

  
If you break a rule, your Express Funded Account will be liquidated immediately and closed at the end of the trading day. Back2Funded gives you the option to Reactivate it up to 2 times, keeping the same account size and payout policy. Learn more [here](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works).

### How do I earn Payouts from a simulated account?

The Express Funded Account is a simulated account that allows you to earn from your trading without additional fees. Our [Payout Policy](https://intercom.help/topstep-llc/en/articles/8284233-topstep-payout-policy) explains how to earn Payouts depending upon which type of Express Funded Account you have.

### How do I request a Payout?

  
​[Our Payout Policy can be found here with information on how to request a payout.](https://intercom.help/topstep-llc/en/articles/8284233)

### Can automated strategies be used in the Express Funded Account?

  
Yes, automated strategies are permitted, with a few things to note:

- Topstep cannot help set up or troubleshoot automated strategies and will not make exceptions for errant trades or malfunctions.
    
- Before getting started, we recommend testing on your Practice Account and reviewing our [Prohibited Conduct](https://help.topstep.com/en/articles/10296582-prohibited-conduct) and [Do's and Don'ts of SIM Fills](https://help.topstep.com/en/articles/10431370-the-do-s-and-don-ts-of-sim-fills) articles.
    

**Tip:** You can duplicate trades across multiple accounts using a trade copier. Learn more [here](https://intercom.help/topstep-llc/en/articles/8284140-what-is-a-trade-copier).  
​

### Can I copy trade up to five Express Funded Accounts at once?

Yes, traders can now trade up to $750k of buying power at once!

### What are the benefits of trading multiple Express Funded Accounts?

Trading in multiple Express Funded Accounts enables you to refine your approach while learning at a flexible and advanced pace so you can continue to trade with confidence. Topstep is a safe space to trade, learn, and grow.

Here’s how you can benefit from trading multiple Express Funded Accounts:

- Trading different products and markets.
    
- Trading at different times of the day. (Examples: The open, economic releases, days of the week, etc.)
    
- Trading on different platforms.
    

**However, please note:** The following conduct is considered prohibited in Multiple Express Funded Accounts:

- Any activity that violates Topstep’s [Terms of Use](https://www.topstep.com/terms-of-use/).
    
- Taking the opposite trades across multiple accounts to “hedge.”
    
    - Learn more [here](https://help.topstep.com/en/articles/13747047-understanding-hedging)
        
    
- Trading similarly in partnership with other individuals. (i.e., placing the same trades in the same time increments), opposite strategy, hedging, or other activity.)  
    ​**Important:** At any time, Topstep has the right to deny multiple Funded Accounts to a user for any reason.
    

### Can I take a break from trading my Express Funded Account or put it on hold?

- You can take a break from trading your Express Funded Account for **less than 30 days** at a time.
    
- If there is no trading activity (no trades entered) on your Express Funded Account for **more than 30 days, it may be subject to closure due to inactivity**.
    
- It is never possible to put an Express Funded Account on hold.
    
- If you are traveling to an ineligible country or dealing with a medical emergency, please reach out to the Trader Support Team for additional assistance.
    

### What Happens When I Get Called Up to the Live Funded Account?

When Topstep determines that a trader has shown consistent success in the Express Funded Account, that trader will receive an email to move to a Live Funded Account. At that time, all open Express Funded Accounts will be closed. **Here’s how it works:**  
​

**1. How your Live Account size is set**

Your Live Funded Account size is based on the average account size of your active and eligible Express Funded Accounts.

- Only accounts with at least one payout are included
    
- The average is rounded up to the next tier of $50K, $100K, or $150K
    
- Your Live Funded Account maximum starting balance, rules, and limits are based on this capped size
    

**Example:**

You have four 50K XFAs and one 150K XFA.

**Step 1** — Calculate the average account size:

(50K + 50K + 50K + 50K + 150K) ÷ 5 = 350K ÷ 5 = 70K average

**Step 2** — Determine your Live Funded Account tier:

Your average of 70K rounds up to the **100K Live Funded Account tier.**

This becomes the maximum starting balance of your Live Funded Account and determines the rules and limits for your account.  
​

**2. How you scale in and scale up**

When you’re called up to Live, **20% of your Live Funded Account starting balance** is available to trade, and the remaining balance is set in Reserve. It then unlocks the remaining balance in in **25% performance-based milestones** until the full available balance is unlocked.

You can read all about our [Live Funded Account Parameters here.](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters)

### Can I move from the Express Funded Account to the Live Funded Account at any time?

Our Risk Managers monitor all traders in the Express Funded Account and may reach out to move you to the Live Account at any time. This decision is made at Topstep’s discretion, based on your performance. Approval is discretionary and based on overall trading behavior.

---

**Important Links**

- [Scaling Plan](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan)
    
- [Payout Policy](https://help.topstep.com/en/articles/8284233-topstep-payout-policy)
    
- [Maximum Loss Limit](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit)
    
- [Topstep Prohibited Conduct](https://help.topstep.com/en/articles/10296582-prohibited-conduct)
    
- [Multiple Express Funded Accounts](https://help.topstep.com/en/articles/8284218-multiple-express-funded-accounts)
    
- [Express Funded Account Activation](https://help.topstep.com/en/articles/8284217-express-funded-account-activation)
    

---

# Express Funded Account™ Activation

Everything you need to know about activating your Express Funded Account after passing your Trading Combine.

Updated over 3 weeks ago

### **Express Funded Account Activation**

Passing your Trading Combine is a big milestone! Once you pass, you will receive a confirmation email from Topstep, and your Trade Report will show a button to get started with your Express Funded Account. Depending on the Trading Combine path you chose, there may or may not be an activation fee, and you will have 30 days to complete the process. This article walks you through each step so you can move forward with confidence.

---

### **What to Expect after you pass the** Trading Combine

- You’ll receive an email from Topstep congratulating you for passing your Trading Combine.
    

- The Trade Report of the passed Trading Combine will have a button on the right-hand side that says “Start Express Funded Account!” Click that button to activate.  
    ​
    
- Next, you'll need to choose the type of Express Funded Account you'd like, check the agreement boxes to accept the terms of the Account and Activation Fee Payment. Once you confirm your shipping information and your payment is processed, you'll be redirected to a confirmation page stating "XFA Activation Fee Payment Successful!"  
    ​
    
- ​**Please note:** it may take up to 30 minutes for your Trading Combine status to reflect that you’ve passed in the dashboard.
    

Note: If you already have five (5) active Express Funded Accounts or a Live Funded Account, the blue button will be greyed out and you won’t be able to click “Start Express Funded Account”. This is because there is [a limit to the Express Funded Account](https://intercom.help/topstep-llc/en/articles/8284218-multiple-express-funded-accounts).

---

### **How do I Activate my** Express Funded Account?

Depending on the path you chose for your Trading Combine, there may or may not be an activation fee.

- If you chose the **Standard Path** Trading Combine, you will pay a one-time $149 activation fee.
    
- If you chose the **No Activation Fee** **Path** Trading Combine, there will be no activation fee upon passing.  
    ​
    
- You can learn more about each path [here](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions#h_2d4740f6d0).  
    ​
    
- The process for activating your Express Funded Account is very similar, regardless of the path you choose.
    

**Please note:** It is the trader's responsibility to make sure the correct Activation Fee is being paid. If you've passed multiple Trading Combines simultaneously, carefully confirm the account name and ensure it matches the one on your Trade Report before paying your Activation Fee. Topstep does not provide refunds or make exceptions for activating the wrong Express Funded Account.

**Steps to Activate**

1. Click the **“Activate Express Funded Account”** button from the Trade Report of the passed Trading Combine you want to activate. **If you have multiple passed Trading Combines, make sure you’re clicking on the correct account before activating.**  
    ​
    
    
    
2. You'll be asked to select your Express Funded Account path on the next page:  
    ​
    
    
    
    To learn more about each type of Express Funded Account, [go here](https://intercom.help/topstep-llc/en/articles/8284215-express-funded-account-parameters).
    
3. **Account Info:** Once you select your Express Funded Account type, you'll be directed to review the Trading Combine name you're activating again, just to confirm it's the correct one.  
    ​
    
4. **Review Agreement:** Next, you'll read the document on the Express Funded Account Agreement page and click **Continue**.  
    ​
    
5. **Agreement Signed:** From there, check both boxes to acknowledge that you’ve read and agree to the terms and conditions. **Click “Agree and Continue”** after checking both boxes.
    
6. **Activation Fee** **Paid:**
    
    1. If you have a **No Activation Fee** Trading Combine, you will simply hit continue. You'll skip over this section and be notified that your account has been created!
        
    2. If you have a **Standard Trading Combine**, you'll be directed to check all 3 boxes to acknowledge that you’ve read and agree to the terms of the activation fee.
        
        1. You’re now ready to pay your Activation Fee on the Activation Fee Payment page. Enter your payment information (you can use a credit card or debit card), and **click “Complete Payment to Activate".**
            
        
    
7. **Account Created**: For both Trading Combine paths, you’ll end with a page that says “Tips from our Coaches” with helpful tips and reminders as you start your new account. _On the left-hand side of the screen, you’ll see confirmations of everything you’ve completed during the activation process._ Click “**Finish**” to return to your dashboard and your new Express Funded Account.  
    ​
    

---

### **How long do I have to pay the Activation Fee and get started with my Express Funded Account?**

- If you have less than five (5) active Express Funded Accounts and do not have a Live Funded Account, you have 30 days from passing your Trading Combine to pay your Activation Fee and get started with the Express Funded Account.  
    ​
    
- If you pass a Trading Combine and already have a maximum of five (5) active Express Funded Accounts or an open Live Funded Account, your additional account will be on hold. You will have 30 days to pay the Activation Fee and get started the next time the Express Funded Account becomes available to you.

# What is the Scaling Plan?

Updated today

[What is the Scaling Plan?](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan#h_f048fcab9d)  
​[Why is the Scaling Plan important?](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan#h_5fa4d42464)

[Micros and Minis in the Scaling Plan](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan#h_d3b8ca7a1a)

[What happens if I accidentally put on more contracts than the Scaling Plan allows but then immediately correct it? Will it count as a rule violation for the day?](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan#h_1d1496dbdf)

[How can I avoid exceeding the Scaling Plan?](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan#h_09f90f492a)

### What is the Scaling Plan?

The Scaling Plan is an Express Funded Account objective that sets the maximum number of contracts (Maximum Position Size) a Trader is allowed to hold open at one time, based on their current account balance. The Scaling Plan is an objective in the Express Funded Account. It's evaluated each day when your Trade Report is updated.

Starting July 22nd, 2025, the Scaling Plan in the Live Funded Account has been replaced with [Dynamic Live Risk Expansion](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion). After this date, the Scaling Plan only applies to the Express Funded Account.

- **The Express Funded Account starts at a $0 balance. As you build or lose equity, your buying power will increase or decrease based on your end-of-day P&L, according to the graphs below.**
    
- The Scaling Plan is in place to ease Traders into the live market environment and build their equity consistently without taking unnecessary risks. Since we implemented the Scaling Plan, the longevity of our Traders has significantly increased.
    
- Traders will initially be required to scale their trading plans to survive an initial drawdown and to allow a true chance of success in the Express Funded Account.
    

### Why is the Scaling Plan important?

- Acts as a guide on how to responsibly leverage a growing account
    
- Over-leveraging causes the most damage to long-term success
    
- The graphs below are based on your account size. Inside the bar graph is your account balance, and to the right is the corresponding [Maximum Position Size.](https://help.topstep.com/en/articles/8284197-trading-combine-parameters#h_11535c919e)
    

[![XFA charts - hc.png](https://topstep-949ca9db770d.intercom-attachments-7.com/i/o/813170406/95c64a1874bfd81176cc2d57/19155321446035?expires=1777593600&signature=11ca9707718f70c5773c1d8a91c97ea25e9b2a56b3763e0b74ec56246d32fae7&req=fCEkF85%2BmYFZFb4V1XW4geRb9xLmrEyu9SHAauCkPOM4NMhyvd6BdRwf7iX2%0AV5x0VybAmwbdLrWOQUvh3GI9kw%3D%3D%0A)](https://topstep-949ca9db770d.intercom-attachments-7.com/i/o/813170406/95c64a1874bfd81176cc2d57/19155321446035?expires=1777593600&signature=11ca9707718f70c5773c1d8a91c97ea25e9b2a56b3763e0b74ec56246d32fae7&req=fCEkF85%2BmYFZFb4V1XW4geRb9xLmrEyu9SHAauCkPOM4NMhyvd6BdRwf7iX2%0AV5x0VybAmwbdLrWOQUvh3GI9kw%3D%3D%0A)

- **You are not required to trade the maximum number of contracts.** For example, you can trade 2 contracts at one time even though your account balance permits you to trade 3 contracts.
    

- Your maximum number of contracts allowed to trade under the scaling plan **does not increase throughout the trading day.** If your earnings meet or exceed the required amount to scale up, you still need to wait **_until the following session_** to trade the next Scaling Plan level. We recommend that you check [your Trade Report](https://dashboard.topstep.com/) each day after it is updated at 5 PM CT to see the number of contracts that are available for your account during the next trading session.
    

- If you have questions about how to calculate your net positions with simultaneous long and short positions in multiple products, please take a look at the example [here](https://intercom.help/topstep-llc/en/articles/8284209).
    

### Micros and Minis in the Scaling Plan

Micros and Minis are counted toward your Maximum Position Size differently depending on the trading platform.

**On** **TopstepX**, Micros and Minis are calculated using a 10:1 ratio:

- 1 Mini contract = 10 Micro contracts
    
- This ratio applies in both the Trading Combine and the Express Funded Account on TopstepX
    
- Your Scaling Plan limits are based on the mini-contract equivalent.
    

For example, on a $50K Express Funded Account on TopstepX, if your Scaling Plan allows 2 lots, that equals:

- 2 Mini contracts, or
    
- 20 Micro contracts, or
    
- Any combination that equals 2 Minis total
    

**On third-party platforms**, Micros are typically treated as full-sized lots for Scaling Plan purposes (1 Micro = 1 lot).

**Important reminder: Some products, such as Micro Silver, Micro Bitcoin, and Micro Ether, are weighted differently.**

- Micro Silver (SIL) → Silver (SI): 5:1. Micro Silver equals two of any other micro and uses a 5:1 ratio.
    
- Micro Bitcoin (MBT) → Bitcoin mini-equivalent sizing: special case. MBT is capped at the same lot sizes as minis rather than using the usual micro scaling.
    
- Micro Ether (MET) → Ether mini-equivalent sizing: special case. MET is also capped at the same lot sizes as minis rather than the usual micro scaling.
    

### What happens if I accidentally put on more contracts than the Scaling Plan allows, but then immediately correct it? Will it count as a rule violation for the day?

Traders should always be aware of their net position size and stay within the limits of the Scaling Plan. However, we understand accidents happen and are not in the business of penalizing traders who fat-finger a trade.

- **Errors in the Scaling Plan corrected in less than 10 seconds will be ignored.**
    

- If traders leave on too many contracts for 10 seconds or more, even if only by a few seconds, their account may be reviewed. Traders always need to know their net market exposure and should be able to correct errors in real time.
    

### How can I avoid exceeding the Scaling Plan?

If you need some tips to avoid exceeding the Scaling Plan, we recommend trying the following:

- Set up your trading platform workspace to include open positions and orders.
    
- Enable the Order Confirmation setting on your trading platform. This will require you to reconfirm an order before it is submitted. See instructions [here](https://intercom.help/topstep-llc/en/articles/8284148) on how to enable this for each platform.
    
- On the TopstepX™ platform, you can reduce your contract limits **by product** using the Contract Limits feature. Learn more [here](https://help.topstep.com/en/articles/9078173-topstepx-risk-settings#h_1593cf2bbe).

# How to ensure I am not trading within 2% of a Price Limit?

February 28, 2025

**Table of Contents:**

- **[What are CME Price Limits?](https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit#h_8b2bcc97-c5a2-4d89-a9bb-5499273c9c4b)**
    
- **[How do I know what the CME Price Limits are for the contracts I trade?](https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit#h_29362032-844e-4353-ab7c-48d0bae8aced)**
    
- **[How Do I Ensure I Don't Trade Within 2% of a Price Limit?](https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit#h_9d4c6498-4ab0-4ab4-b0f2-676fbf5e281f)**
    
- **[How to find the % Net Change for the contract I am trading?](https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit#h_948bcb04-c5e3-4263-b324-40b9e969d52f)**
    
- **[Why is Topstep enforcing this Prohibited Conduct in the Funded Account?](https://help.topstep.com/en/articles/8284225-how-to-ensure-i-am-not-trading-within-2-of-a-price-limit#h_6f994f86-b91f-4af3-82fb-2ccd449df669)**
    

## What are CME Price Limits?

A price limit is the maximum price range permitted for a futures contract in each trading session. When markets hit the price limit, different actions occur depending on the product being traded. Markets may temporarily halt until price limits can be expanded, remain in a limit condition, or stop trading for the day based on regulatory rules.

## How do I know what the CME Price Limits are for the contracts I trade?

- First off, it’s good to know that Price Limits are calculated based on the end-of-day settlement price and vary by product, contract month, and time of day (i.e. Overnight Price Limits differ from the Price Limits used during business hours).  
    ​
    
- The Price Limits are updated at 4:05 PM CT after each trading session and can be found on the **[CME Price Limits](https://www.cmegroup.com/trading/price-limits.html)** page.
    

|                                                                                                                         |
| ----------------------------------------------------------------------------------------------------------------------- |
| **Tip:** CME Price Limits are subject to change, so we recommend checking in on the CME website linked above regularly. |

Below is an example of Price Limits for the ESM0 contract during the 5/14/2020 trading session. They are based on the Settlement Price from 5/13/2020, which was 2814.00.



## How Do I Ensure I Don't Trade Within 2% of a Price Limit?

**Important Update(s):**

Equity Products ES, MES, NQ, MNQ, RTY, M2K, YM, and MYM overnight price limits have expanded from 5% to 7%.

One of the easiest ways to ensure you are not trading within 2% of any Price Limit would be to watch the **% Net Change** for the contract you are participating in via your trading platform quote board.

- **Example 1:** Assume you are trading the ESM0 contract between 5:00 PM CT on 5/13/2020 and 8:30 AM CT on 5/14/2020, the price limit is 5% up or down. You should not be trading ESM0 if the **% Net Change** on the day exceeds 3% up or down (5% Price Limit minus the 2% Topstep threshold).  
    ​
    
- **Example 2: Assume you are trading the ESM0 at 9:00 AM CT on 5/14/2020, the price limit is now 7% (down only). You should not be trading ESM0 if the % Net Change on the day exceeds 5% (7% Price Limit minus the 2% Topstep threshold) down.**
    

Another method to find your limits would be to calculate them based on the Settlement Price. You would need to know the previous day’s Settlement Price along with the % up and/or down that triggers the next Price Limit based on the time you are trading.

- **Example 1:** The Settlement Price for the ESM0 contract on 5/13/2020 was 2814.00. If you are trading when the Price Limit is 5% up and down you can make the following calculation to identify the levels that are within 2% of a Price Limit that you should stop trading at:
    
    - Level Above to Stop Trading: 2814*(1 + 5% - 2%) = 2,898
        
    - Level Below to Stop Trading: 2814*(1 - 5% + 2%) = 2,730
        
        ​
        
    
- **Example 2:** Again, the settlement price for ESM0 on 5/13/2020 was 2814.00. If you are trading when the Price Limit is 7% down, you can make the following calculation to identify the levels that are 2% within a Price Limit that you should stop trading at.
    
    - Level Above to Stop Trading: n/a
        
    - Level Below to Stop Trading: 2814*(1 - 7% + 2%) = 2673
        
    


The above image shows a hypothetical visual for ES with a 7% Price Limit. From the previous day's settlement, trading is allowed until ES reaches -5% net change on the day (2% away from the 7% Price Limit). If the net change on the day for ES has exceeded a 5% move, then no trading is allowed.

# How to find the % Net Change for the contract I am trading?

Your trading platform’s Quote Board/Radar Screen not only displays the “Net Change” on the day as prices move, but it can also display “Net Change” as a percentage or “% Net Change.” If the “% Net Change” is not currently displayed on your Quote Board, simply add that column to display how close your product is to the Price Limit.

# Why is Topstep enforcing this Prohibited Conduct?

In an effort to protect our firm and our traders, we will not allow market participation when a product is trading within 2% of a Price Limit.

In addition, all speculators assuming risk in a market should know that market intimately. It is important to be aware of the Contract Specifications and Price Limits for any product you trade.  
​  
For more information about your favorite products, please reference the [CME Group](https://www.cmegroup.com/) website. Click on your product from the home page for detailed information.

# Back2Funded: Rules, Guidelines, and How It Works

Updated over a week ago

Back2Funded gives you the option to pay for up to 2 Reactivations if you lose your Express Funded Account (XFA) before your first payout. Each Reactivation lets you keep the same account size and payout policy, giving you another chance to trade for a payout without starting over in the Trading Combine.

[Eligibility](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_90171ba33d)

[How to use Back2Funded](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_80cfc333bb)

[5 Express Funded Accounts Limit](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_25dfbb6d7f)

[Reactivation Limits and Pricing](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_a3cf72a805)

[Reactivation Window](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_babd640488)

[Frequently Asked Questions](https://help.topstep.com/en/articles/12060405-back2funded-rules-guidelines-and-how-it-works#h_46cc95890d)

## Eligibility

Back2Funded is available only for Express Funded Accounts that meet all of the following criteria:

- The Express Funded Account was originally earned through Topstep’s Trading Combine.
    
- The Express Funded Account was closed due to a rule violation **before** taking a payout. Once a payout is taken from an Express Funded Account, it is no longer eligible for Back2Funded.
    
- The Express Funded Account is on TopstepX in the new Topstep Dashboard.
    

- **Trader must be in good standing with no compliance concerns.**
    

- **​Traders on the Focused Trader Plan (FTP) are not able to reactivate an Express Funded Account with Back2Funded.**
    

## How to Use Back2Funded

1. Lose your Express Funded Account before your first payout.
    
2. Within 7 days, decide if you want to go Back2Funded.
    
3. Log in to the new Topstep Dashboard, select your account, and choose the Back2Funded option.
    
4. Pay the Reactivation fee for your Express Funded Account size (including sales tax).
    
5. Your account will be Reactivated and ready to trade at the start of the next trading session. For example, if you complete your Back2Funded purchase at 10 PM CT on a Tuesday, your account will become available when the _next trading session_ begins on Wednesday at 5 PM CT.
    

## 5 Express Funded Accounts Limit

- Traders can have a maximum of **5 active or pending** Express Funded Accounts at one time.
    
- Once you pay the Reactivation fee your account will be pending until the start of the next trading session and count toward the 5 Express Funded Account limit.
    
- A Back2Funded-eligible Express Funded Account remains **eligible for 7 calendar days** before expiring, but is not considered active or pending unless Reactivated.
    
- If you are at the 5 active or pending Express Funded Account limit, you cannot activate a new Express Funded Account.
    
- If no action is taken within 7 days, the Back2Funded offer expires and will be **automatically declined**.
    

### **💡 Back2Funded Pricing and Limitations:**

Lost your XFA before your first payout? You may be able to reactivate it instead of starting a new Trading Combine.

- Max 2 reactivations per Express Funded Account
    
- Reactivation must match the original account size
    
- Pricing excludes sales tax; each purchase is separate, final, and non-refundable
    

#### Pricing:

**$50K XFA → $599**

**$100K XFA → $699**

**$150K XFA → $829**

## Reactivation Window

You have seven calendar days from the time your Express Funded Account is closed to decide if you want to go Back2Funded. During this window, you cannot activate a new Express Funded Account until you decide whether to Reactivate. If you do not Reactivate within 7 days, the Back2Funded option expires, will be automatically declined, and you must return to the Trading Combine to earn a new Express Funded Account.

## Frequently Asked Questions

**What is Back2Funded?**

Back2Funded gives Traders up to 2 more opportunities to trade for a payout if they lose an Express Funded Account (XFA) before taking their first payout. Instead of starting over from the Trading Combine, you can pay to Reactivate the same XFA size and keep trading under the same payout rules.

**Which accounts are eligible for Back2Funded?**

- The Express Funded Account was originally earned through Topstep’s Trading Combine.
    
- The Express Funded Account was closed due to a rule violation before taking a payout.
    
- The Express Funded Account is on TopstepX in the new Topstep Dashboard.
    

Once a payout is taken from an Express Funded Account, it is no longer eligible for Back2Funded. The Trader must be in good standing with no Focused Trader Plan restrictions or compliance concerns.

**How does Back2Funded benefit me?  
​**With Back2Funded, you won’t have to lose your progress and start over just because you had one bad day in the market. Unlike common “straight to funded” options, Back2Funded lets you continue on toward a payout with the same 1 Step, 1 Rule payout policy and doesn’t layer on other rules like consistency targets or modified drawdowns.

**How do I use Back2Funded?**

1. Lose your Express Funded Account before your first payout.
    
2. Within 7 days, decide if you want to go Back2Funded.
    
3. Log in to the new Topstep Dashboard, select your account, and choose the Back2Funded option.
    
4. Pay the Reactivation fee for your Express Funded Account size (including sales tax).
    
5. Your account will be Reactivated (with the same size and payout policy) and ready to trade at the start of the next trading session.
    

**What happens if I don’t decide within 7 days?**

If you do not reactivate within 7 days, your Back2Funded option expires and you’ll need to return to the Trading Combine to earn another Express Funded Account.

**How many times can I reactivate an Express Funded Account?**

Each Express Funded Account can be Reactivated up to 2 times. Each Reactivation is purchased separately.

**Does the payout policy change?**

No, you keep the same simple payout rules.

**Where is Back2Funded available?**

Only on TopstepX inside the [new Topstep Dashboard](https://dashboard.topstep.com/login).

**Why didn’t you make a straight-to-funded option?**

We still believe in earning your funded account. It’s proven to help traders build the habits and discipline needed for long-term success. Back2Funded is the middle ground and skips the Trading Combine, but still requires you to prove consistency before payouts.

**Why can’t I Reactivate my Express Funded Account after 7 days?**

The 7-day window gives traders enough time to decide. If you don’t Reactivate within that time, you’ll need to return to the Trading Combine to earn another Express Funded Account.

**Will I keep my winning days?**

No. Back2Funded is a full account restart. You start fresh with a clean slate, including your winning days counter.

**How long after I Reactivate until my account is ready to trade again?**

Your Reactivated Express Funded Account will be ready to trade at the start of the next trading session after purchase.

**Why do I have to wait until the next session to trade my Reactivated Express Funded Account?**

This gives you the chance to not only restart your Express Funded Account progress, but yourself. Take a break and come back focused.

**What happened to my Express Funded Account stats?**

When you Reactivate, your previous stats, including P&L, trade history, and winning days, revert to zero. This is a new account state with the same payout rules.

**Why do I only get 2 Reactivations?**

If you need more than three chances with the same account, it might be a sign to go back to the Trading Combine and refocus on the habits and consistency that got you funded in the first place.

**How will Back2Funded work if I have 5 active Express Funded Accounts?**

If you have **5** active Express Funded Accounts and one or more become eligible for Back2Funded, you’ll have **7 calendar days** to decide if you want to Reactivate each of those accounts. If you take no action, Back2Funded eligibility will expire at the end of the 7 days for each account.  
​

During that 7-day window, your Back2Funded eligible Express Funded Accounts do not count toward your 5 active Express Funded Account limit until the Reactivation fee is paid.

**Can I apply this to my Live Funded Account?**

No, Back2Funded is available only for lost Express Funded Accounts.

**Is a Back2Funded Reactivation the same as a Reset?**

No, they are not the same. A Reactivation refers specifically to our Back2Funded program (which allows you to Reactivate an Express Funded Account under certain circumstances, for a fee), while Resets can only be used on active Trading Combine subscriptions. To learn more about Resets, click [here](https://help.topstep.com/en/articles/8284128-what-is-the-reset).  
​  
​**Can I purchase a Back2Funded** **Reactivation on both** **the Express Funded Account Standard and the Express Funded Account Consistency?**

Yes, you can Reactivate either type of Express Funded Account!

**Can I apply this to my Shoulder Tap Express Funded Account?**

No, Back2Funded is available only for lost Express Funded Accounts that are not associated with a Live Funded Account/Shoulder Tap Express Funded Account.

# What are the costs in the Live Funded Account?

Updated over 3 weeks ago

As a funded trader with Topstep, you are responsible for the costs associated with running a Professional Trading Business as outlined below:

- [CME Professional Data Subscription](https://help.topstep.com/en/articles/8284229-what-are-the-costs-in-the-live-funded-account#h_2e80a422-630d-4650-89be-48b7ae40b26d)
    
- [Round Turn Commissions and Fees](https://help.topstep.com/en/articles/8284229-what-are-the-costs-in-the-live-funded-account#h_01ERJD0VR56J311VM87KV3CVE0)
    
- [Platform License or Subscription](https://help.topstep.com/en/articles/8284229-what-are-the-costs-in-the-live-funded-account#h_6e55a33c-79a7-4073-831a-9a7472f578f3)
    

## CME Professional Data Subscription:

To trade live with Topstep, you need to subscribe to Professional Data from the Exchanges. Topstep collects these data fees monthly via credit card as the Exchanges debit us directly. Topstep does not profit from these fees. We are simply passing along the cost directly from the Exchange.

**Effective July 22, 2025, Topstep will cover the monthly data fee for all Live Funded traders for one exchange. By default, we will cover CME data. This will take effect at your next billing cycle. Fees for additional exchanges (NYMEX, COMEX, CBOT) still apply. If you'd like a different exchange covered by Topstep, please contact the Funding Team.  
​**

**The monthly data fee will be automatically billed to the credit card you used when setting up your first data fee payment after moving to a Live Funded Account. If you choose to add a second exchange, this is at your own expense, and the monthly data fee will be billed to you directly on the 26th of each month.**

## **Below is the cost _per exchange per month_, depending on the trading platform:**

|                   |                                                                              |                        |
| ----------------- | ---------------------------------------------------------------------------- | ---------------------- |
| #### **Exchange** | #### **Permitted Product**                                                   | #### **All Platforms** |
| #### **CME**      | #### ES, MES, NQ, MNQ, RTY, M2K, NKD, 6A, 6B, 6C, 6E, 6J, 6S, E7, HE, LE, GE | #### $133 per month    |
| #### **NYMEX**    | #### CL, QM, NG, QG                                                          | #### $133 per month    |
| #### **COMEX**    | #### GC, SI, HG                                                              | #### $133 per month    |
| #### **CBOT**     | #### ZC, ZW, ZS, ZM, ZL, YM, MYM, ZT, ZF, ZN, ZB, UB, TN                     | #### $133 per month    |

In the Trading Combine, you can trade all of our [Permitted Products](https://intercom.help/topstep-llc/en/articles/8284206). In the Live Funded Account, you would need to subscribe to CME, CBOT, NYMEX, & COMEX to trade all of the Permitted Products, which would cost $540 per month.

## How can I reduce the cost of Data Fees?

The tips below will help to reduce the cost of Data Fees.

1. Subscribe to one exchange to start: A lot of our traders decide to focus on specific products and start their Live Funded Account, subscribing to one exchange to reduce the monthly cost to $133. You can always add more data subscriptions as you build up your account.
    
2. #### **Starting July 22, 2025, Topstep will cover the monthly data fee for all Live Funded traders for one exchange. By default, we will cover CME data.** This will take effect at your next billing cycle. Fees for additional exchanges (NYMEX, COMEX, CBOT) still apply. If you'd like a different exchange covered by Topstep, please contact the Funding Team.  
    ​
    
3. Start your Live Funded Account on the 1st of the Month: The exchange does not pro-rate data fees. In other words, you cannot pay for a partial month. With that in mind, a lot of traders choose to start their accounts on the 1st of the month. If reducing cost isn't an issue for you, that is ok, and feel free to start mid-month. If you would like to start on the 1st of the month to reduce these fees, please still make your initial data subscription payment. Your data subscription will not start immediately after your payment. During your Live Funded Account onboarding, you will be asked when you would prefer to start your account. ​
    

## Why are the Data Subscription costs so high with Topstep?

Whenever you are trading live capital with us, you are considered a Professional Trader in the eyes of the Exchange, and their fee structure is different for Professionals and Non-Professionals. You can likely subscribe to cheaper data through your personal brokerage account because that account is classified as a Non-Professional. You will be classified as a Professional Trader whenever trading with us in the Live Funded Account.

## Round Turn Commissions and Fees

Below are the round-turn costs you will incur in the Live Funded Account, which are deducted from your brokerage account balance. This works similarly to the $3.70 round turn fee per lot calculated in the Trading Combine to emulate this professional trading cost.

- **Commissions & Fees:** These go to the brokerages and range from $ 0.72 to $ 2.04
    

- **Exchange Fees:** Set by the exchange and differ by instrument ranging from $2.46 to $4.30 for our permitted products.
    

- Examples:
    

1. E-mini S&P 500 (ES) - $2.66
    
2. E-mini NASDAQ 100 (NQ) - $ 2.66
    
3. Crude Oil (CL) - $3.00
    
4. Gold (GC) - $3.10
    

|   |
|---|
|Take a look at the article linked below to get a breakdown of round turn commissions and fees by platform and product to calculate the commissions and fees for your personal setup:<br><br>[What round-turn commissions and fees do I have to pay in the Live Funded Account?](https://intercom.help/topstep-llc/en/articles/8284231)|

## Platform License or Subscription

In the Trading Combine, Topstep covers the Platform fees for many of our supported platforms, _but the trader is responsible for covering the platform license cost in the Funded Account._


# Live Funded Account Parameters

Learn about the Live Funded Account starting balance and the Shoulder Tap Express Funded Account.

Updated yesterday

[Live Funded Account Starting Balance](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#h_2ce063c339)

[Expanded Example of Live Funded Account Starting Balance](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#h_15d4bdcd17)

[Shoulder Tap Express Funded Account](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#h_4660042154)

[Frequently Asked Questions](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#h_f4fc7d6b0f)

For details on what factors are considered for promotion to a Live Funded Account, click [here](https://help.topstep.com/en/articles/13747178-live-funded-account-call-up-and-call-down-process?q=live+funded+).

# Live Funded Account Starting Balance

Your Live Funded Account (LFA) includes two key values:  
​

## **1. Live Account Size**

Topstep allows traders to have one active Live Funded Account at a time. Your Live Funded Account size is based on the average account size of your active and eligible Express Funded Accounts.

- Only accounts with at least one payout are included in the Live Funded Account size calculation
    
- The average is rounded up to the next tier of $50K, $100K, or $150K
    
- Your Live Funded Account maximum starting balance, rules, and limits are based on this capped size
    

**Example:**

You have four 50K Express Funded Accounts and one 150K Express Funded Account.

**Step 1** — Calculate the average account size:

(50K + 50K + 50K + 50K + 150K) ÷ 5 = 350K ÷ 5 = 70K average

**Step 2** — Determine your Live Funded Account tier:

Your average of 70K rounds up to the **100K Live Funded Account tier.**

##   
**2. Starting Balance and Unlock Structure**

Your actual starting balance is based on the combined total balance of your eligible Express Funded Accounts, up to your Live Account Size outlined in Section 1.

At Live activation.

**Starting Balance Calculation (as of 2/19/26):**

- 20% of your combined total balance is available for trading **OR**
    
- A minimum of $10,000
    
    - If needed, additional capital may be provided from your Reserve Balance to ensure you have a stable starting cushion.
        
    
- **​Example:** Using the information from the above example with a 100k Live Funded Account, the actual starting capital (20%) would be $20,000, with $80,000 in your Live Funded Account Reserve. You can see an [expanded example here.](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#h_15d4bdcd17)
    

**Unlocking Structure:**

- The remaining Reserve Balance will be unlocked in increments through performance thresholds.
    
- Achieving each threshold releases 25% of your Reserve Balance. After reaching your 4th threshold, you will have successfully unlocked your full Reserve Balance for trading.
    
- Example: You are called up with 5 XFAs with a cumulative balance of $40,000, which would put your 20% starting balance at $8,000 with a $32,000 Reserve Balance. Given that the minimum starting balance for Live Funded Accounts is $10,000, Topstep will transfer an additional $2,000 from your Reserve Balance to your starting balance, and your new starting balance would be $10,000 with $30,000 in Reserve. Each subsequent threshold met will then unlock 25% of your Reserve balance:
    
    - 1st Threshold: $7,500
        
    - 2nd Threshold: $7,500
        
    - 3rd Threshold: $7,500
        
    - 4th Threshold: $7,500
        
    

### **Balance Expansion Through Performance**

Additional **available balance in reserve** becomes accessible through **net profit milestones** achieved in the Live Funded Account. These milestones are the same profit targets achieved in the Trading Combine.



### **Important:**

- Balance expansion does **not change payout eligibility rules**
    
- Net profit earned from your account's starting balance — and since your last expansion release — is required to unlock the next reserve balance increment.
    
- Our Risk Team will be reviewing once per week after market close on Monday. If you meet the criteria to unlock additional capital from your reserves, the funds will be transferred to your account within 1-2 business days.
    
- Capital expansion is reviewed by the Risk Team each Monday after market close, and is based on net performance and observed trading behavior from the prior week's trading activity (Monday-Friday)
    

Traders may continue unlocking Live Funded Account balance reserves until **100% of the account's Initial Account Balance has been made available for trading**.

### If your Live Funded Account balance drops below $1,000, the account will be liquidated immediately and closed at the end of the trading day. The remaining balance will be sent to you as a final payout before the account is closed.

---

## **Daily Loss Limit and Maximum Position Size**

Live Funded Accounts begin with a Daily Loss Limit based on account size:

- $2,000 for $50K accounts
    
- $3,000 for $100K accounts
    
- $4,500 for $150K accounts.
    

Regardless of account size:

- If the tradable balance reaches $10,000 or below, the **Daily Loss Limit will be set to $2,000 with a Maximum Position Size of 5.**
    
- If the tradable balance reaches $5,000 or below, the **Daily Loss Limit will be set to $1,000 with a Maximum Position Size of 3.**
    

**Example:**

If you have a 100K Live Funded Account and your end-of-day balance goes below $10,000, your Daily Loss Limit will be changed from $3,000 to $2,000 before the start of the next trading session. The DLL will return to $3,000 once your end-of-day balance rises above $10,000.

This objective is updated at the end of each active trading day. This safeguard is designed to **limit downside risk during lower-balance periods** while allowing traders to continue operating under the same risk framework across all Live account tiers. You can learn more [here](https://intercom.help/topstep-llc/en/articles/11748475-dynamic-live-risk-expansion).

---

## **Expanded Example of Live Funded Account Starting Balance**

In this example, you have:

- Two $50K Express Funded Accounts
    
- One $100k Express Funded Account
    
- One $150K Express Funded Account
    

**Step 1: Determine Live Account Size**

$50K + $50K + $100K + $150K = $350K

$350K ÷ 4 accounts = $87.5K average, which rounds up to a $100K account

Your Live Funded Account (LFA) size will be **$100K**.  
​

**Step 2: Calculate Combined Profits**

Your profit in each account:

- $10K in each $50K account
    
- $30K in one $100K account
    
- $25K in the other $150K account
    

$10K + $10K + $30K + $25K = **$75K total combined profit**  
​

**Step 3: Starting Balance and Reserve**

When transferring to Live:

- 20% is available immediately
    
- 80% is held in your Live Funded Account Reserve
    

20% of $75K = **$15K starting balance**

80% of $75K = **$60K in Reserve**

Your $100K Live Funded Account will start with **$15K available**, with **$60K held in Reserve**.  
​

**Step 4: Releasing Reserve Funds**

The Profit Target in each Live Funded Account is the same as the Profit Target in the Trading Combine:

- $50K account = $3,000 Profit Target
    
- $100K account = $6,000 Profit Target
    
- $150K account = $9,000 Profit Target
    

Since this example results in a $100K Live Funded Account:

- The Profit Target is **$6,000**.
    
- Each time you reach $6,000 in profit, **$15,000** is released from your Reserve.
    
- This continues until the full $75,000 balance has been unlocked.
    

**Important Note: Starting Live Account Size Cap**  
​

Your Live Funded Account starting balance is capped at your account size.

If the combined profit in your Express Funded Accounts exceeds $100,000, you will **not** transfer more than $100,000 into your $100K Live Funded Account as your starting balance.

---

# Shoulder Tap Express Funded Account

The Shoulder Tap Express Funded Account is a simulated funded account created after a call down from a Live Funded Account. The Shoulder Tap is part of the Live Funded Account risk framework. It provides a structured risk intervention process and, if needed, a clear path out of Live trading with the opportunity to return. The goal is to support long-term consistency and sustainability in live markets.

## **What Shoulder Tap Means**

The term Shoulder Tap comes from live trading floors, where risk managers step in during periods of drawdown to review performance and help traders refocus. At Topstep, a Shoulder Tap refers to Risk Team involvement when a Live Funded Account reaches defined drawdown thresholds, including a review of recent trading behavior and possible adjustments to reduce risk and stabilize performance.

## **Objective**

The objective is to demonstrate consistency and work toward returning to Live trading. Just like the initial call-up, approval is discretionary and based on overall trading behavior.

To learn more about Shoulder Tap Express Funded Accounts and what factors are at play when you are called up to/down from a Live Funded Account, [go here](https://intercom.help/topstep-llc/en/articles/13747178-live-account-call-up-call-down-process).

---

#   
Live Funded Account FAQs  

### Can I decline the invitation to move to a Live Funded Account and stay in the Express Funded Account instead?

  
No, it is not possible to stay in an Express Funded Account and decline to move to a Live Funded Account. Once our Risk Managers determine you're ready to move to a Live Funded Account, your options are to make the switch from Express to Live or close your Express Funded Account.

### How does trading Live benefit me over SIM?

  
Trading Live means managing real money, which helps develop discipline and skills under real market conditions, preparing you for real-world trading at Topstep and beyond.

### How Long Does It Take to Create a Live Funded Account?

  
Live Funded Accounts typically take 7-10 business days to set up. This timeframe can vary depending on the brokerage and the time required to activate your live data feed. During this time, we’ll keep you updated on your account's progress and notify you as soon as it’s ready. If you have any questions in the meantime, feel free to reach out to our Trader Support Team!

### If I lose my Live Funded Account, can I skip an Express Funded Account and go straight back to Live?

  
No, if you lose your Live Funded Account, you would need to pass a Trading Combine and show consistency in an Express Funded Account before being called up to Live again.

### Can I have more than one Live Funded Account?

  
You can only have one (1) Live Funded Account active. When you receive a Live Funded Account, all Express Funded Accounts are closed.

### What are the fees associated with the Live Funded Account?

  
You can view the full details for costs in the Live Funded Account here: [What are the costs in the Live Funded Account?](https://intercom.help/topstep-llc/en/articles/8284229-what-are-the-costs-in-the-live-funded-account)

### Will I start the Live Funded Account at my Maximum Position Size?

  
Yes, Live Funded Accounts start at the maximum position size allowed for your account level.

### Can I take payouts before unlocking all reserved capital?

  
Yes. Payout eligibility is not tied to capital expansion. You may take payouts while still trading with partial account access.

### Is live trading capital my money?

  
No. Live trading capital represents live trading capital of Topstep’s prop firm that becomes available for trading as you demonstrate consistent performance. It is not available for trading or margin use until it is officially unlocked. Portions of this capital may become eligible for withdrawal by you based on reaching certain performance metrics. Once withdrawn, the withdrawn funds are your money.

### Can I unlock multiple tiers of reserve capital with one large winning trade?

  
No. Capital expansion requires net profits since the last expansion, reviewed weekly. This prevents capital unlocks from being driven by a single oversized win.

### How often is capital expansion reviewed?

  
Capital expansion is reviewed by the Risk Team each Monday after market close, and is based on net performance and observed trading behavior from the prior week’s trading activity.

### After a review, when can I expect additional capital from my Reserve Balance to be deposited into my Live Account?

  
Once your account has been reviewed and you have successfully unlocked additional capital, you can expect the funds to be deposited into your Live Account by the end of the next trading day, on Tuesday.

### What happens if my performance stalls after an expansion?

  
If performance stalls, capital simply remains at the current level. There is no penalty for slower progress as long as the account rules are followed.

### Can capital expansion be delayed or denied?

  
Yes. Traders who engage in excessive or reckless risk behavior may have capital expansion delayed or declined at the discretion of the risk team.

### Why is Topstep making this change to Live Accounts?

  
These changes apply to any Live Funded Account funded and tradeable on or after February 10, 2026. This structure is designed to help you scale in safely, adapt to real market conditions, and work alongside the Risk Team with a clear path toward full account access.

### What happens when I hit the Live Funded Account cap in my Express Funded Account and haven’t been called up to Live?

Once you reach the maximum Live Funded Account balance cap in your Express Funded Account, you’ll continue trading and taking payouts while being evaluated for Live. The Live Account balance cap is in place to ensure traders are focusing on consistency and withdrawals rather than stacking up unrealized simulated profits.

### What happens to the rest of my balance in my Express Funded Account if I’m over the cap?

Any balance over the Live Funded Account cap size does not transfer to Live. The excess is forfeited.

### Will taking a payout impact my eligibility for unlocking the next Reserve tier?

  
No. Net P&L calculations are based on trading losses and do not include payouts.

### Once my funds are transferred to Live and I have 30 winning days, can I take a 100% payout?

  
Yes. Once you are called up to Live and your Live Funded Account is created, you are eligible to withdraw up to 100% of your unlocked balance. We encourage traders to take full advantage of the benefits of Live trading with Topstep, including unlimited growth potential and uncapped daily payouts. Please note that payouts can only be taken from your unlocked balance, not from your Live Funded Account Reserve.​

As you reach each profit target, additional funds are released from your Reserve into your unlocked balance. Once 100% of your balance has been unlocked, you may withdraw those funds as well.

### What happens if I lose my 20% starting balance?

  
If your Live Funded Account balance drops below $1,000, the account will be liquidated immediately and closed at the end of the trading day. The remaining balance will be sent to you as a final payout before the account is closed.

### How do I request a payout?

  
​[Our Payout Policy can be found here with information on how to request a payout.](https://intercom.help/topstep-llc/en/articles/8284233)

### Can I use automated strategies in the Live Funded Account?

  
Yes, automated strategies are permitted, with a few things to note:

- Topstep cannot help set up or troubleshoot automated strategies and will not make exceptions for errant trades or malfunctions.
    
- Automated trading through the ProjectX API is prohibited with Live Funded Accounts
    

**Tip:** You can duplicate trades across multiple accounts using a trade copier. Learn more [here](https://intercom.help/topstep-llc/en/articles/8284140-what-is-a-trade-copier).

---

# Dynamic Live Risk Expansion

February 17, 2026

[How Scaling Works](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_2100d1741e)

[Expanded Contract Sizing](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_55170c2a52)

[What is Expanded Contract Sizing?](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_e6ef85a51d)

[Who is Eligible for Expanded Contract Sizing?](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_419d0235fc)

[What is the Path to Reduction?](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_031d209de0)

[Risk Adjustments Outside the Path to Expansion](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_48a13c05db)

[What is Shoulder Tap?](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion#h_2e18458417)

**Topstep’s Dynamic Risk Expansion** system rewards consistent performance in the Live Funded Account by adjusting your Daily Loss Limit and max contract size as your profits grow. This system can give profitable traders more room to trade, manage risk, and stay consistent.

|   |   |   |
|---|---|---|
|**Buying Power**|**Profit**|**Daily Loss Limit**|
|Up to 100 lots|1M|Up to $100,000|
|Up to 70 lots|550K|Up to $50,000|
|Up to 50 lots|200K|Up to $20,000|
|Up to 30 lots|100K|Up to $10,000|
|—|50K|Up to $6,000|
|—|20K|Up to $5,500|
|—|15K|Up to $5,000|

- Expansion Criteria: 10 active trading days at each tier.
    
- Numbers reflect Daily Loss Limit in a $150K account size. Will vary for smaller account sizes.
    

### **How Scaling Works**

Every trader starts with a default Daily Loss Limit based on their account size:

- **50K Account: Starts with a $2,000 Daily Loss Limit**
    
- **100K Account: Starts with a $3,000 Daily Loss Limit**
    
- **150K Account: Starts with a $4,500 Daily Loss Limit**
    

As you earn profits in your Live Funded Account, your net profit determines your Tier, and each new Tier increases your Daily Loss Limit. **You must spend 10 Active Trading Days*** in each Tier before your Daily Loss Limit is increased.

---

Only profits made in the Live Funded Account count. Your Express Funded Account transfer balance and any payouts do not affect your Tier.

**To Increase:** Your Daily Loss Limit will increase at the end of the trading day after you’ve spent 10 Active Trading Days in the new Tier.  
​

**To Decrease**: If your net profit falls below your current Tier at the end of the day, your Daily Loss Limit will scale down that same day.  
​

If you reach a Tier but don’t hold it for 10 Active Trading Days, and your balance drops, the 10-day counter resets the next time you re-enter that Tier.

***Active Trading Days**

- There is no minimum P/L or trade size required to qualify a day as “active.”
    
- Even placing a single micro contract trade qualifies.
    
- You must move one Tier at a time. Skipping Tiers is not allowed.
    

### **Expanded Contract Sizing**

Topstep’s standard contract limits are designed to encourage disciplined growth and protect trader capital. As part of the Dynamic Live Risk Expansion, traders who have demonstrated consistent performance and account stability may request expanded contract sizing.

|   |   |   |   |
|---|---|---|---|
|**Net Profit**|**$50K Daily Loss Limit – $2000**|**$100K Daily Loss Limit – $3000**|**$150K Daily Loss Limit – $4500**|
|$15,000.00|$2,500|$3,500|$5,000|
|$20,000.00|$3,000|$4,000|$5,500|
|$50,000.00|$3,500|$4,500|$6,000|
|$100,000.00|Up to $10K|Up to $10K|Up to $10K|
|$200,000.00|Up to $20K|Up to $20K|Up to $20K|
|$550,000.00|Up to $50K|Up to $50K|Up to $50K|
|$1,000,000.00|Up to $100K|Up to $100K|Up to $100K|

### **What is Expanded Contract Sizing?**

Expanded contract sizing allows traders to request permission to trade more contracts than the standard limits defined by their account size and risk tier.

This is not granted automatically. All expanded sizing requests must be reviewed and approved by Topstep’s Risk Team.

### **Who is Eligible for Expanded Contract Sizing?**

To qualify, a trader must meet both of the following conditions:

- Be in Tier 4 or higher within the Dynamic Risk Expansion system
    
- Have a minimum account balance of $100,000 in their Live Funded Account
    

### **What is the Path to Reduction?**

The Path to Reduction is a tiered system that helps manage risk in a Live Funded Account during a drawdown. When your account experiences significant losses from your starting balance, our Risk Team will monitor your performance and eventually reach out for a Shoulder Tap.  
​

Payouts do **not** count as drawdown and do **not** impact your risk tier. Drawdown is based solely on losses from your Live Funded Account starting balance.

**Important:** Reckless or undisciplined trading in a Live Funded Account may result in the forfeiture of Live capital.

### **Risk Adjustments Outside the Path to Expansion**

In certain situations, the Risk Team may adjust risk parameters in a Live Funded Account based on net equity, even if the account has not yet progressed through the Path to Expansion.

**These adjustments are not automatic and are made at Risk’s discretion.**

**What is a risk adjustment?**

The Risk team monitors account performance to determine if an adjustment is needed to a trader’s account. These adjustments can be higher or lower than the defaults for your account size. Your Daily Loss Limit and Max Position Limit may be reduced to protect firm capital, or expanded following a trend of profitability in a Live Funded Account.

**Net Equity thresholds**

Risk adjustments may be considered once a Live Funded Account reaches the following net equity levels:

- $10,000 net equity in a $50,000 Live Funded Account
    
- $15,000 net equity in a $100,000 Live Funded Account
    
- $20,000 net equity in a $150,000 Live Funded Account
    

When these levels are reached, the Risk Team may review the account and adjust risk parameters to match the appropriate risk for the account balance.

## **Daily Loss Limit**

Live Funded Accounts begin with a Daily Loss Limit based on account size:

- $2,000 for $50K accounts
    
- $3,000 for $100K accounts
    
- $4,500 for $150K accounts.
    

Regardless of account size, if the tradable balance reaches $10,000 or below, the Daily Loss Limit will be set to $2,000.

**Example:**

If you have a 100k Live Funded Account and your end-of-day balance goes below $10,000, your Daily Loss Limit will be changed from $3,000 to $2,000 before the start of the next trading session. The DLL will return to $3,000 once your end-of-day balance rises above $10,000.

This safeguard is designed to **limit downside risk during lower-balance periods** while allowing traders to continue operating under the same risk framework across all Live account tiers.

### **What is a Shoulder Tap?**

The term comes from the trading pits, where risk managers would literally tap a trader on the shoulder during a drawdown to review what was happening and help them refocus.

To learn more about a Shoulder Tap, please [go here](https://intercom.help/topstep-llc/en/articles/13747178-live-account-call-up-call-down-process).

# Risk Lock-In

March 18, 2026

[What Is a Risk Lock-In?](https://help.topstep.com/en/articles/13461608-risk-lock-in#h_992fab081d)

[How Risk Lock-Ins Work](https://help.topstep.com/en/articles/13461608-risk-lock-in#h_e72ee23c56)

[Example Scenarios](https://help.topstep.com/en/articles/13461608-risk-lock-in#h_40b01e4788)

[Why Risk Lock-In Exists](https://help.topstep.com/en/articles/13461608-risk-lock-in#h_70ddfe0269)  
​  
​Once you reach a Live Funded Account, you are trading REAL firm-backed capital provided by Topstep. Because of that, the Risk Team actively monitors Live accounts and may step in to help protect strong performance, especially on large winning days.

  
Risk Lock-In is designed to protect profits during exceptional intraday performance while still allowing Traders room to continue trading responsibly.

###   
**What Is a Risk Lock-In?**

A Risk Lock-In occurs when the Risk Team sets a minimum profit level for the trading day after a Trader has achieved significant (realized or unrealized) gains. This minimum level helps protect profits and prevent a strong day from turning into a loss due to overtrading.

Risk Lock-In is not meant to stop you from trading or limit your upside. It exists to protect both firm capital and the progress you’ve already made on the day.

###   
**How Risk Lock-In Works**

When a Trader is significantly profitable relative to their starting Daily Loss Limit (DLL) or net equity, the Risk Team may establish a lock-in level.

That lock-in level allows a controlled drawdown from your current profit, typically set as a multiple of your starting Daily Loss Limit for the day (such as 1x, 1.5x, or 2x).  
​

The specific multiplier applied depends on several factors, including:

- Net P&L
    
- Starting Daily Loss Limit
    
- Account balance
    
- Recent trading behavior
    

As profits increase throughout the day, the Risk Team may adjust lock-in levels accordingly.  
​

When a lock-in level is set, you will be notified immediately via email or phone. Traders are expected to remain available for communication while actively trading, as outlined in the [Live Funded Account Trading Rules](https://www.topstep.com/live-funded-account-rules/).  
​

If your net P&L falls below the lock-in level, your account will be liquidated and locked for the remainder of the trading day. Trading may resume at 5:00 PM Central Time on the next trading day.

### **Example Scenarios**

**Your $50k Live Funded Account has $15,000.** Your starting Daily Loss Limit is $2,000. → You are trading well and are up $10,000 on the day. The Risk Team reaches out via email/phone and sets a lock-in level of $7,000. In other words, you now have $3,000 (1.5x your original Daily Loss Limit) in drawdown available. This means you can continue trading until your net P&L reaches $7,000. Below $7,000, your account will be liquidated, locked, and all orders will be canceled. You will be able to resume trading at 5 PM Central Time on the next trading day.

**Your $100k Live Funded Account has $75,000.** Your starting Daily Loss Limit is $3,000. → You are trading well and are up $20,000 on the day. The Risk Team reaches out via email/phone and sets a lock-in level of $14,000. In other words, you now have $6,000 (2x) your original Daily Loss Limit in drawdown available. This means you can continue trading until your net P&L reaches $7,000. Below $7,000, your account will be liquidated, locked, and all orders will be canceled. You will be able to resume trading at 5 PM Central Time on the next trading day.

**Your $150K Live Funded Account has $150,000. Y**our starting Daily Loss Limit is $4,500. → You are trading well and up $40,000 on the day. The Risk Team reaches out via email/phone and sets a lock-in level of $31,000. In other words, you now have $9,000 (2x your original Daily Loss Limit) in drawdown available. This means you can continue trading until your net P&L reaches $31,000. Below $31,000, your account will be liquidated, locked, and all orders will be canceled. You will be able to resume trading at 5 PM Central Time on the next trading day.

**You just received your $150K Live Funded Account with $15,000.** Your Daily Loss Limit is $4,500 → You are trading well and up $9,000 on the day. The Risk Team reaches out via email/phone and sets a lock-in level of $4,500. In other words, you now have $4,500 (1x your original Daily Loss Limit) in drawdown available. This means you can continue trading until your net P&L reaches $4,500. Below $4,500, your account will be liquidated, locked, and all orders will be canceled. You will be able to resume trading 5 PM Central Time on the next trading day.

### **Why Risk Lock-In Exists**

When a Trader is having an exceptional day and is significantly in profit, the Risk team shifts from "defensive" to "protective," and as you’re able to secure winning days and show net profitability in your account over time, your account will become eligible for Topstep’s [Live Account Performance Bonuses](https://www.topstep.com/live-performance-bonus/) and [Dynamic Risk Expansions](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion).

# Live Funded Account Call Up and Call Down Process

Details on what factors are considered when you are called up to a Live Funded Account, or called down to a Shoulder Tap Express Funded Account

February 26, 2026

[The Call Up (Moving to Live)](https://help.topstep.com/en/articles/13747178-live-funded-account-call-up-and-call-down-process#h_719315d213)

[The Call Down (The "Shoulder Tap")](https://help.topstep.com/en/articles/13747178-live-funded-account-call-up-and-call-down-process#h_5fbf904ab6)

[FAQs](https://help.topstep.com/en/articles/13747178-live-funded-account-call-up-and-call-down-process#h_1d90c2e6be)

---

# **📈 The Call Up (Moving to Live)**  

## **When will I be called up?**

Most Traders are moved to a Live Funded Account between their 3rd and 5th payout.

However, the Risk Team reviews each Trader individually and may contact you earlier or later based on your overall performance.  
​

## **How do we decide?**

We look at your full trading profile, not just one metric.

This includes things like:

- Consistency
    
- Risk management
    
- Position sizing
    
- Products traded
    
- Use of stops and risk tools
    
- Payout history
    
- Overall account behavior
    

Every Trader is different, so Topstep uses a comprehensive set of monitoring tools and our dedicated Risk Team to evaluate each trader individually. This ensures that call ups to Live are based on personalized performance rather than a one-size-fits-all process.  
​

## **What balance will I start with?**

Live Traders begin with:

- 20% of their cumulative XFA balance **_OR_**
    
- A minimum of $10,000
    

If needed, additional capital may be transferred from your Reserve Balance to ensure you have a stable starting cushion.

##   
**Why do we do it this way?**

The goal is simple: to give Traders enough room to trade consistently in Live markets within structured risk parameters.

---

# **📉 The Call Down (The “Shoulder Tap”)**  

## **What is it?**

A Call Down, also known as a “Shoulder Tap,” happens when a Live Trader is moved back to a simulated account to reset and rebuild consistency.

This is part of standard risk management at proprietary trading firms.

##   
**Why does it happen?**

A Shoulder Tap may occur if we see:

- Repeated loss limit breaches
    
- Significant inconsistency in performance
    
- Excessive risk-taking
    
- Large swings in position size
    
- Signs of loss of discipline
    

Every case is reviewed individually by the Risk Team.  
​

## **What account will I trade?**

You will transition to a single Shoulder Tap Express Funded Account:

- The balance will reflect your remaining Live capital
    
- The account follows standard [Express Funded Account](https://intercom.help/topstep-llc/en/articles/8284215-express-funded-account-parameters) parameters and [payout policy](https://intercom.help/topstep-llc/en/articles/8284233-topstep-payout-policy)
    

## **Can I move back to Live?**

Yes. The Risk Team continues to monitor performance. Once consistency and discipline are demonstrated again, you may be moved back to Live through the standard review process.  
​

## **Why do we do this?**

The goal is simple: to protect firm capital while giving Traders the opportunity to reset, rebuild discipline, and return stronger.

---

# **FAQs**

**Do I need five payouts to move to or return to Live?**

No. Three to five payouts is a general guideline. All decisions are based on overall performance and Risk Team review.  
​

**Can I trade multiple accounts while in a Shoulder Tap account?**

No. You are limited to one Shoulder Tap Express Funded Account.  
​

**Is Back2Funded available for Shoulder Tap accounts?**

No. Back2Funded Reactivation does not apply to Shoulder Tap accounts.  
​

**How long will I remain in a Shoulder Tap account?**

Until you are called back to Live or the account balance reaches zero.  
​

**Will I get a warning before I get a Shoulder Tap?**

There is no warning before being called down.  
​

**Is returning to Live guaranteed after a certain number of payouts?**

No. Returning to Live depends on demonstrated consistency and overall performance.  
​

**What happens if I lose my Shoulder Tap account?**

If the account balance reaches zero, any remaining Live reserve is forfeited.

# TopstepX™ Live Performance Bonus

Updated over 4 weeks ago

[How the Performance Bonus Works](https://help.topstep.com/en/articles/11177768-topstepx-live-performance-bonus#h_10f2109d2d)

[Frequently Asked Questions](https://help.topstep.com/en/articles/11177768-topstepx-live-performance-bonus#h_8d265664a6)

The TopstepX™ Live Performance Bonus is a new incentive program that allows consistently profitable Live Funded traders to earn over $250,000 in cash bonuses. Traders work their way up the bonus ladder one level at a time, unlocking a new cash bonus each calendar month they hit a qualifying profit target. This bonus is designed to reward consistency, discipline, and long-term growth.

|   |   |
|---|---|
|**Profit in Live Funded Account**|**Bonus Amount Deposited to Trader**|
|$15K|$1,000|
|$20K|$5,000|
|$50K|$10,000|
|$100K|$20,000|
|$200K|$40,000|
|$550K|$75,000|
|$1M|$100,000|

## How the Performance Bonus Works


- **One level at a time:** You can unlock one bonus per calendar month. No skipping or repeating levels.
    
- **One bonus per calendar month:** If you qualify for multiple levels, only the first available is paid.
    
- **Based on end-of-day profit:** To qualify, your net P&L at market close must meet or exceed your current level during a month without a prior bonus.
    
- **Profits start at $0 in each Live Account:** Only profits earned inside that Live Funded Account count, regardless of the account balance at the time they are called up to Live.
    
- **Payouts don’t reduce your progress:** Bonuses are based on net Live P&L, even if you’ve withdrawn funds.
    
- **Each level pays once per account:** You won’t receive the same bonus twice, even if your balance dips and returns.
    
- **Progress resets if the account closes:** A new Live Funded Account starts back at Level 1.
    
- **No minimum trading required:** If your profit level qualifies at the end of any trading day, you’re eligible even if you didn’t trade that day.
    

## Frequently Asked Questions

**What is the TopstepX Live Performance Bonus?**

- It’s a reward program for consistently profitable Live Funded traders. By hitting profit milestones each month, traders can earn over $250,000 in bonus cash, one level at a time.
    

**How do I qualify for a bonus?**

- You must hit a qualifying profit level based on your net P&L at market close during a month in which you haven’t already earned a bonus.
    

**Can I earn more than one bonus in the same month?**

- No, you can only unlock one bonus per calendar month, even if you qualify for multiple levels.
    

**Can I skip levels or repeat a level if I drop below the balance?**

- No, levels must be completed **in order**. You cannot skip or re-earn a level you’ve already unlocked.
    

**Do payouts reduce my bonus progress?**

- No, bonus progress is based on net profit in your Live Funded Account, even if you withdraw funds.
    

**Do profits from before I was called up to Live count?**

- No, all bonus progress starts from $0 net profit once you enter a Live Funded Account. Only profits earned inside the Live account count.
    
- When being called back up to Live from the Shoulder Tap Express Funded Account, your balance will be restored to a maximum of the starting balance in the account prior to being placed in the single Express Funded Account.
    

**What happens if my Live Funded Account is closed?**

- If your Live Funded Account is closed for any reason, you’ll need to start back at Level 1 in a new Live account.
    

**Do I need to trade every day to qualify?**

- No, there is no minimum trading activity required. If your balance qualifies on any trading day at the end of the month, you’re eligible.
    

**How do I know when I’ve unlocked a bonus?**

- You will receive an email letting you know that you’ve unlocked a bonus and providing details on when you will receive it.
    

**When will I receive my bonus?**

- Bonuses are typically issued within 1 to 3 business days after the day you qualify
    

**Can I withdraw my bonus without requesting a payout?**

- No. The only way to take money out of your trading account, including any bonuses you earn, is by qualifying for and requesting a payout. Bonuses are added to your account balance but can only be accessed through the standard payout process.
    

**If I earn a bonus on the last day of the month, and then qualify for the next level the very next day, can I receive back-to-back bonuses?**

- Yes, bonuses are based on calendar months, so if you hit a qualifying profit level during a new month, you can earn the next bonus even if your previous bonus was earned the day before. Just remember, only one bonus can be earned per calendar month.
    

**If I take a loss and recover, can I still qualify for a bonus or payout?**

- Yes, what matters is where your account balance finishes for the day. As long as your net profit reaches or holds the bonus level by the end of any trading day, you qualify even if you have a drawdown on the following day.
    

**Are the bonus tiers cumulative, or do they reset each month?**

- Each bonus level can only be earned once and earned in order.
    

**Do bonus profits reset each month or build over time?**

- Bonus profits build over time. Your account keeps progressing, and your bonuses stack up as you reach each level. One bonus per calendar month, one level at a time.
    

**Is the bonus only for traders on TopstepX?**

- Yes, the TopstepX Performance Bonus is exclusive to TopstepX at this time.
    

**What happens after I hit $1 million in profit?**

- First, congratulations! That’s elite territory. The bonus program currently caps at Level 7, which ends at the $1 million profit mark. If future levels are added, we’ll be the first to tell you.
    

**Can I withdraw my bonus like regular profits?**

- Yes, your bonus is added to your account balance and follows the same payout guidelines.
    

**How do I move to the next level or claim bonuses?**

- You qualify when your account hits or holds the next bonus level by the end of a trading day. There’s nothing you need to click or submit. You’ll be notified when you qualify, and your bonus will be added within 1 to 3 business days.
    

---

_Terms apply. Futures trading may result in loss. [See Terms](https://www.topstep.com/live-performance-bonus-disclaimer/)._

# Topstep Payout Policy

If you’re looking for information on Topstep’s Payout Policy, you’re in the right place.

Updated yesterday

Topstep has one of the best payout policies in the industry, allowing disciplined Traders to take weekly payouts. The best part? You can take payouts daily and access up to 100% of your profits after accumulating 30 winning trading days in a Live Funded Account.

---

## Express Funded Account Consistency vs Express Funded Account Standard

|   |   |
|---|---|
|### Standard Path|### Consistency Path|
|**5 winning days of $150+**|**3 days with 40% consistency target**|
|**Request 50% of the account balance**<br><br>**up to $5000***|**Request 50% of the account balance**<br><br>**up to $6,000***|
|**90/10 split**|**90/10 split**|

### Payout Cap Changes:

Starting April 28, Topstep is introducing lower pricing on the $50K and $100K No Activation Fee Trading Combine®. Along with the price change, these two account sizes will have updated payout caps — meaning the maximum amount you can request in a single payout will change. The $150K Trading Combine will also see a pricing update, but its payout cap structure will remain unchanged.

* **Your payout cap is based on your account size and path.**

|   |   |   |
|---|---|---|
||**Express Funded Account Standard**|**Express Funded Account Consistency**|
|**$50K**|$2000|$3000|
|**$100K**|$3000|$4000|
|**$150K**|$5000|$6000|

### Payout Cap Change FAQs

**What happens if I rebill after April 28?**

Rebilling an existing account keeps the same payout cap and will be rebilled at the original price point.

**What happens if I Reset my account after April 28?**

Resets completed after April 28 will follow the updated pricing, but the OLD payout cap will still apply.  
​  
​**What happens when I use a reset credit from an existing account to open a new Trading Combine after April 28?**

After April 28, any new Trading Combines created, even from prior reset credits, will follow the updated pricing.

**Are Live Funded Account payout caps updating?**

No. Live Funded Account payout caps are not affected by these updates.

**Does this impact Back2Funded?**

If your account already exists, your payout cap remains the same, including Back2Funded tied to that account. New accounts created after April 28 will follow the updated structure.  
​  
​**Will this affect my payout eligibility or rules?**

No. Payout rules and eligibility requirements remain the same. Only payout caps for new accounts are updated.

---

### **Examples**

#### **Example 1 — A brand new Trading Combine purchased after April 28**

- Trader purchases a new $50K No Activation Fee Trading Combine on or after April 28
    
- New pricing of $95/mo applies
    
- If the account passes, the updated payout cap of $2,000 per Payout (Standard) or $3,000 per Payout (Consistency) applies to the Express Funded Account
    

**Example 2 — Existing Trading Combine Rebills and Reset Credit is Used for New Account**

- Trader purchases a $50K No Activation Fee Trading Combine before April 28
    
- Reset Credit is granted during rebill at the OLD price
    
- Reset Credit activates new account that will have OLD payout cap
    

**Example 3 — Existing Trading Combine has Reset purchased Prior to Rebill**

- Trader purchases a $50K No Activation Fee Trading Combine before April 28
    
- Trader purchases a Reset on that account prior to the rebill
    
- The Reset costs the new price, but retains the old payout cap
    
- The upcoming rebill will now reflect the new price
    

**Example 4 — Existing Trading Combine Passed After April 28, Activating XFA after April 28**

- Trader purchases a $100K Trading Combine before April 28 and passes after April 28
    
- Trader has an active Express Funded Account after April 28 with the old payout cap
    
- Trader uses Back2Funded to Reactivate that account afterwards and retains the old payout cap upon reactivation
    

**Example 5 — $150K No Activation Fee Trading Combine Purchased After April 28**

- Trader purchases a new $150K No Activation Fee Trading Combine on or after April 28
    
- New pricing of $229/mo applies
    
- If the account passes, the payout cap is the same as before for $150k accounts
    
    - Standard: $5,000 per Payout
        
    - Consistency: $6,000 per Payout
        
    

---

## Payout Policy in the Express Funded Account Standard​

To request a payout from your Express Funded Account Standard, you'll need to:  
​

**1. Have at least five (5) winning trading days**

- A winning day means your Net P&L is **$150* or more**.
    
- The five days **do not** need to be consecutive.
    
- The trading day is not counted as completed until it is **locked in at 4:00 PM CT after market close.**
    
- Please note that the date your Payout is requested will not count toward your winning days for the next Payout.
    

**2. Eligible Payout Balance: Achieve a profit greater than $0 since your last payout**

- **Any amount** of total profit after your last payout qualifies, even one (1) cent.
    
- Your **first payout** does _not_ require this.
    
- See the example below to learn more!
    

Once eligible, you may request a payout of **up to $5,000** or **up to 50% of your account balance**, whichever is lower.

**Can my account move up or down between payouts?**

- Yes. Your account can move up or down as you trade and take payouts. You just need to be profitable ($.01 or more) since your last payout before you can request the next one.
    

**What happens after I take a payout?**

- After taking a payout, your Maximum Loss Limit will be set to $0. Additionally, a Trader must complete five _additional_ winning trading days from the date the most recent payout is requested before being eligible for their next payout. This is required for each payout request.
    

**How the Eligible Payout Balance Works**

  
​**First Payout**

**Current balance:** $6,000

✅ Five full winning days of $150+

✅ No profitability requirement for your first payout

**You qualify for a payout of 50% of your account balance (up to $5,000 in the Standard or $6,000 in the Consistency).**  
​

Take a **$3,000** payout → **your balance is now $3,000**.

This becomes your **new starting balance for future profitability**.

  
​**Second Payout**

**Current balance:** $4,000

**Starting balance after your last payout:** $3,000

✅ Five full winning days of $150+

✅ You are **profitable from your most recent payout** ($3,000 → 4,000)  
​**You qualify for a payout of 50% of your account balance (up to $5,000 in the Standard or $6,000 in the Consistency).**

  
Take a **$1,800** payout → **your balance is now $2,200**.

This becomes your **new starting balance for future profitability**.

  
​**Third Payout**

**Current balance:** $4,500

**Starting balance after your last payout:** $2,200

✅ Five full winning days of $150+

✅ You are **profitable since your most recent payout** ($2,200 → $4,500)  
​**You qualify for a payout of 50% of your account balance (up to $5,000 in the Standard or $6,000 in the Consistency).**

Take a **$2,000** payout → **your balance is now $2,500**.

This becomes your **new starting balance for future profitability**.

  
​**Fourth Payout**

**Current balance:** $1,800

**Starting balance after your last payout:** $2,500  
​

✅ Five full winning days of $150+

❌ You are **not profitable from your most recent payout** ($1,800 < $2,500)

**You do not qualify for a payout.**  
​**To qualify:** Continue trading until your balance is **above your post-payout starting balance of $2,500**.

---

## Eligible Payout Balance FAQs

**Does the eligible payout balance apply to my first payout?**

No. Your first payout on an account is not subject to this requirement. After your first payout, you must achieve a profit greater than $0 since your last payout to be eligible for your next payout.  
​

**Does the eligible payout balance apply to Live Funded Accounts?**

No. This payout objective applies only to the Express Funded Account.  
​

**Does account size change how the eligible payout balance is calculated?**

No. The calculation is the same for all Express Funded Account sizes. Traders must be profitable after their most recent payout, regardless of account size to be eligible for the next payout.  
​

**Why does Topstep have this payout objective?**

This payout objective reinforces habits that help Traders stay funded and take more consistent payouts. Remaining profitable after each payout encourages disciplined risk management, smoother equity curves, and fewer sharp drawdowns. The goal is to help Traders build a stronger base that can hold up through normal market swings and support long-term consistency.  
​

**Where can I see my payout progress in the dashboard?**

Your payout progress appears at the bottom of the Accounts dashboard. After your first payout request, a notification modal will also appear to help explain this payout objective for future payouts.

## Payout Policy in the Express Funded Account Consistency

To request a payout from your Express Funded Account Consistency, you'll need to:

1. **Have at least three (3) days following the 40% Consistency Target**

- Ensure that your largest single trading day does not exceed 40% of your total net profit during the payout window.  
    ​
    
    - **Example**:
        
        - Total net profit: $10,000
            
        - Maximum allowed largest day: $4,000 (40%)
            
        - If your largest single-day profit is greater than $4,000, you would not yet meet the consistency requirement.  
            ​
            
        
    
- Consistency is calculated using net profit, not gross profit.
    

Once eligible, you may request a payout of **up to $6,000** in the $150K account, or **up to 50% of your account balance**, whichever is lower. The payout cap differs depending on account size. Details are listed at the top of this article.

- The Consistency Target for the trading day is not counted as completed until it is **locked in at 4:00 PM CT after market close.**
    

### Can my account move up or down between payouts?

- Yes. Your account can move up or down as you trade and take payouts.
    

### What happens after I take a payout?

- After taking a payout, your Maximum Loss Limit will be set to $0. Additionally, you must complete a minimum of 3 _additional_ trading days from the date the most recent payout is requested (maintaining 40% consistency) before being eligible for your next payout. This is required for each payout request.
    

### Will I still Get My Payout if I hit the MLL After Taking a Payout?

- The key timing is when the funds are deducted from your account balance, not when the payout was submitted. Once the payout amount has been deducted from your account, hitting the Maximum Loss Limit will not affect that payout — it will continue through the normal approval process. If you have questions about the status of a payout, please contact our Support team.
    

## Payout Policy in the Live Funded Account

- Traders can request a payout of up to 50% of their account balance after accumulating five winning trading days per payout request. A winning trading day is counted when a day's Net PNL is $150 or more. The payout caps only apply to the Express Funded Accounts.
    
- After requesting a payout, Traders must restart the cycle of accumulating five winning days, as prior winning days do not apply to the next eligibility cycle.
    

- Winning days do not need to be consecutive days. After taking a payout, a Trader must complete five additional winning trading days from the date the most recent payout is requested before being eligible for their next payout. This is required for each payout request.
    

**Daily Payouts in the Live Funded Account:**

- Once a Live Funded Trader has accumulated 30 non-consecutive winning trading days (this means you've earned $150 or more Net PNL each day for 30 days in the Live Funded Account), you unlock Daily Payouts and can access up to 100% of your balance **in the Live Funded Account**. Winning days from the Express Funded Account do not count toward your 30-day total. Only Traders with a Live Funded Account can request daily payouts and access 100% of their balance.
    
- This means that for future payouts in the Live Funded Account, you can request up to 100% of your balance with each payout request. Payouts can be requested once a day (minimum payout request is $125) up to 100%!  
    ​
    
    - Keep in mind that if a full 100% payout is requested, the Live Funded Account will be closed since the balance will be brought to the Maximum Loss Limit.
        
    

- After accumulating 30 winning trading days in your Live Funded Account, if you'd like to request a payout of more than 50% of your total account balance, please [contact the Trader Support Team](https://intercom.help/topstep-llc/en/articles/8284118-how-do-i-contact-the-support-team). These requests are currently processed manually and cannot be submitted through the payout request form.
    

You should always pay yourself after a few winning days, but don't forget that trading isn't a one-and-done activity. Pay yourself while also positioning yourself for the long haul. Treat your account like a personal brokerage account, with the goal of building it as much as possible, so you are never in a situation where you can't trade the next day.

---

# Payout FAQs

### How can I request a Payout?

- Request payouts through [this form](https://dashboard.topstep.com/dashboard/payouts) in your dashboard, during CME market hours (Sunday 5 PM CT – Friday 5 PM CT, excluding holidays).
    
- Approval takes 1–3 business days; funds arrive within 10 business days.
    
- Once approved and the forms are submitted, funds are removed from your account and sent via your chosen payment method.
    
- Use your Topstep account email when submitting Adobe documents — a mismatch will delay your request. Only one banking form is needed unless your banking info or ID changes or expires.
    
- Topstep does not provide bank verification letters, but you can share your Express Funded Account Agreement for this purpose.
    
- Minimum payout request: $125.
    

### What does Topstep evaluate to Approve My Payout in the Express Funded Account?

  
Topstep has worked hard to create the easiest and most transparent payout policy in the industry! To help make this even more transparent, we'd like to give you an inside look at what our team looks for when checking for eligibility for a payout, including, but not limited to, the following:  
​

**Payout Policy**

The first step is to ensure you've met the requirements of our Payout Policy, which is outlined in this article, including a first-payout threshold based on your account type and a 50% account balance limit.  
​  
​**Code of Conduct Violations**

Checking to make sure you have not violated any of our Code of Conduct articles below. If any of these are violated, it can slow down or decline your payout.

- [Prohibited Conduct](https://help.topstep.com/en/articles/10296582-prohibited-conduct)
    
- [Terms of Use](https://www.topstep.com/terms-of-use/)
    
- [Professional Behavior](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep)
    

**Prohibited Trading Strategies**

While Topstep's rules and parameters help to promote responsible trading, we still see some traders attempting to game the system through strategies that are not indicative of live trading success. [The strategies listed here will be flagged and investigated](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep).

### What is the Profit Split?

All payouts follow a 90/10 profit split: Traders receive 90% of approved payouts, and Topstep retains 10%. This applies to all payouts and is calculated per Trader, not per account.  
​

**Note for Traders who joined before January 12, 2026:** You will continue to receive 100% of the first $10,000 in lifetime profits. After that threshold is met, the standard 90/10 split applies going forward.

### What Payout methods are available?

|   |   |   |
|---|---|---|
|**Method**|**Availability**|**Processing Time**|
|Aeropay|Coming Soon|—|
|Wise|International & domestic|1–3 business days|
|ACH|US banks only|1–3 business days|
|International Wire/SWIFT|International|Up to 5–10 business days|

Processing times are estimates and may be affected by additional reviews or requests from payment providers. Most providers do not process payments on weekends or public holidays. A $30 processing fee applies to ACH and Wire payouts. Aeropay has no fee from Topstep, though your bank or Aeropay may charge their own fees.

### Fees

**ACH or Wire:**

- $30 processing fee applies
    
- 90/10 profit split applies (Topstep retains 10%)
    
- Example: $500 payout request = $420 net ($50 retained via profit split + $30 processing fee deducted)
    

**Aeropay:**

- No fees charged by Topstep
    
- 90/10 profit split applies (Topstep retains 10%)
    
- Aeropay or your bank may charge its own transaction fees
    
- Contact Aeropay or your bank directly for details
    

### What is Wise?

Wise is an online money transfer service that allows you to send, receive, and manage your funds internationally with lower fees compared to traditional banking methods. With Wise, you can enjoy transparent and real exchange rates, ensuring that you receive the most value from your payouts. Please visit the [Wise Help Center](https://wise.com/help/) for any additional questions.

Here are a few benefits of using Wise:

1. Receive payouts within one (1) business day*
    
2. Payout options in either USD or your local currency**
    
3. No monthly fees and fixed transaction fees***
    

**Please Note:**  
* Different payment methods or routine checks may occasionally affect transfer [delivery times](https://wise.com/help/articles/2978029/how-long-does-it-take-to-receive-money-into-a-balance?origin=topic-1pXx5wZnF7Rp83VWwzGPUv). Wise will always keep you updated, and you can track each step in your account.

** You can check for the types of payments you're able to receive, depending on your local currency, from Wise [here](https://wise.com/help/articles/2784317/what-types-of-payments-can-i-receive-into-my-account?origin=topic-1pXx5wZnF7Rp83VWwzGPUv).

***Receive funds within one business with a small transaction fee of $0.39 for a USD to USD payout request. Other currencies will have a fixed fee and may receive a conversion fee. Additional information can be found [here](https://wise.com/us/pricing/).

**What if I don't have a Wise account?**

  
If you don't have a Wise account, you can still request your next payout to be with Wise. Once the payout process is complete, you should receive an email from Wise saying funds are available and to sign up to gain access to the funds. The signup steps will be included in the Wise email.  
​

**Will I need to create a Wise account each time I earn funding?**

  
No, you do not need to create a Wise account each time you earn funding. You will only need to create a Wise account once and the same Wise account will be used for all Funded Level Accounts. Please use the same email for your Topstep profile and Wise.  
​

**What if I already have a Wise account?**

  
If you already have a Wise account with the same email as your Topstep profile, no new sign-up will be required. If your Wise account is using a different email address, please contact our Support Team for further assistance.  
​

**Are there any hidden fees when using Wise?**

  
There are no monthly fees when using Wise. A fee may be charged by Wise when selecting a certain payout method or currency. Converting currency in your account will be subject to fees and vary by currency. Additional information can be found [here](https://wise.com/us/pricing/).  
​

**How long do I have to claim my funds?**

  
Wise provides 7 calendar days to create or log into your account and claim your funds from Topstep. Any funds that are unclaimed after 7 calendar days will be canceled and refunded to Topstep. If you are unable to claim your funds, [please contact our Trader Support Team for assistance](https://www.topstep.com/contact-support/).  
​  
​

### When can I take a Payout?

- You're eligible to take a payout only after passing the Trading Combine and opening your Express Funded Account.
    
- It's essential to check our [list of Ineligible Countries](https://intercom.help/topstep-llc/en/articles/8284116-eligibility-faq) before purchasing a Trading Combine, as citizens of these countries cannot take payouts.
    
- Payouts are exclusively available from Funded Level accounts, such as Express Funded or Live Funded Accounts, and are not available from any size of Trading Combine account. You can find further information about completing the Trading Combine and what happens next [here](https://intercom.help/topstep-llc/en/articles/8284198-what-happens-after-i-complete-the-trading-combine).
    
- Payout Requests can only be submitted during CME market hours between Sunday at 5 pm CT and Friday at 5 pm CT, excluding designated holidays.
    

### When should I start taking Payouts from my Funded Account?

- Check out the [When, How, and Why to Pay Yourself](https://www.topstep.com/blog/when-should-traders-take-a-withdrawal/) blog by our Risk Manager, Mick.
    
- To keep your account long-term and take regular payouts, we recommend bringing your Maximum Loss Limit (MLL) up to $0 before requesting a payout. To reach $0, you will need to hit the corresponding profit levels.
    

**Below is a list of each account size and its corresponding MLL for reference:**

|   |   |
|---|---|
|**Account Size:**|**Maximum Loss Limit:**|
|$50K|$2,000|
|$100K|$3,000|
|$150K|$4,500|

### How do payouts affect my account parameters?

  
Your payouts affect your account parameters in the following ways:

- Your Maximum Loss Limit will always be set to $0 after your first payout.
    
- If your limit has already reached $0 and you take a payout, your limit will remain at $0. At that point, the capital remaining in your account will be the maximum amount you will be able to lose.
    

### How do Payouts affect my trade copier settings?

If an Express Funded Account (XFA) is engaged in copy trading while a payout request is processing, the copy-trading connection will be automatically disabled. Once the payout deduction has been completed and the account balance has been updated, you must manually re-enable copy trading to resume activity.

### How do payouts impact my Maximum Position Size?

  
Payouts can impact your [Maximum Position Size](https://intercom.help/topstep-llc/en/articles/8284209-what-does-maximum-position-size-mean) in the following way:

- Payouts can impact how much leverage you have and the amount of risk you can take. The scaling plan will determine what impact your payout has on your Express Funded Account. If your payout brings you down a level, your account will be set to the corresponding buying power. This means that a payout could result in you not being able to trade as many contracts. [Read more about the Scaling Plan here.](https://intercom.help/topstep-llc/en/articles/8284223-what-is-the-scaling-plan)
    

### How does trading impact my Payout request while it is being processed?

In the new Topstep Dashboard, once you request a payout, the funds are moved right away so you can start trading again right away!

**Live Accounts:** Please note that after submitting a payout request, trading should be paused until the payout has been fully processed and the funds have been deducted from the account.

### How do Payouts work with multiple Express Funded Accounts?

- Each individual Funded Account will follow the same Payout Policy.
    
- Payout requests from each account do not affect one another.
    
- When a trader is called up to the Live Funded Account, all open Express Funded Accounts will be closed. The starting balance of the Live Funded Account will be based on the combined total balance of your eligible Express Funded Accounts, up to your Live Account Size. [Click here](https://help.topstep.com/en/articles/10657969-live-funded-account-starting-balance) to learn more.
    

### Which countries cannot request or receive payouts or earn funding with Topstep?

  
You must review Topstep's [Eligibility Requirements](https://intercom.help/topstep-llc/en/articles/8284116-eligibility-faq-who-is-eligible-to-participate) for the full details on which countries are eligible to trade and take Payouts with Topstep. The following countries cannot request or receive payouts or earn funding with Topstep: _Afghanistan, Algeria, Angola, Belarus, Burkina Faso (Upper Volta), Burma/Myanmar, Burundi, Chinese Military Companies, Cote d'Ivoire (Ivory Coast), Crimea (Region of Ukraine - North of Black Sea - Crimea, Donetsk, Luhansk, Kherson, Zaporizhzhia), Cuba, Democratic Republic of Congo, Haiti, Iran, Iraq, Kenya, Kosovo, Lebanon, Libya, Mali, Morocco, Nicaragua, Nigeria, North Korea, Pakistan, Russia, Somalia, South Sudan, Sudan and Darfur, Syria, Turkey (Turkiye), Ukraine, Venezuela, and Yemen._  
​

### My bank wants a verification letter stating why I'm requesting a payout/receiving a deposit. Do you have that?

  
Topstep does not provide verification letters for payouts, but you can provide your bank with a copy of your Express Funded Account Agreement for verification purposes.

### What does "RA" mean in payout references?

"RA" stands for Research Analyst. Topstep provides users the ability to learn the basics and nuances of trading in a simulated environment as a research analyst. When you receive a payout, it will be referenced as such.

### What tax forms are required to receive a payout?

Before your payout can be processed, you'll need to submit the applicable tax form: W-9 for US persons, or W-8BEN for non-US persons. These are submitted as part of the payout request process. Make sure your information is accurate to avoid delays.

### Can my payout be sent to a third-party bank account?

No. Payouts can only be sent to a bank account in your own name. We are unable to send funds to accounts belonging to another person, including family members.

### Which method is best for international users?

Wise is generally the fastest and most cost-effective option for international traders. It supports local currency conversion and typically processes within 1–3 business days. Wire/SWIFT transfers are also available but may take up to 5–10 business days and could incur additional fees from your bank.

---

**Important Reminder**

If an Express Funded Account (XFA) is engaged in copy trading while a payout request is processing, the copy-trading connection will be automatically disabled. Once the payout deduction has been completed and the account balance has been updated, you must manually re-enable copy trading to resume activity.

---

### Updates to the Payout Policy Effective July 22nd, 2025

We're making a few important updates to our Live Funded Account program to improve Trader experience and encourage long-term success in Live.

Winning days earned in the Express Funded Account will no longer carry over to the Live Funded Account.

- Only winning days earned in a Live account will now count toward daily payout eligibility and full balance access.
    
- This change applies only to new Live Funded Accounts created on or after **July 22, 2025**.
    
- Traders who were already in a Live account prior to this date will retain their existing winning day count.
    

Most Traders are called to Live after five Express Funded Account payouts (around 25 winning days), so this change helps keep the focus on staying consistent in Live.

# Payouts: When, How, and Why to Pay Yourself

Updated this week

[When should traders take a payout?](https://help.topstep.com/en/articles/8284237-payouts-when-how-and-why-to-pay-yourself#h_eb92ad8871)

[Payout examples](https://help.topstep.com/en/articles/8284237-payouts-when-how-and-why-to-pay-yourself#h_26b24f7a69)

[Payout parameter tables](https://help.topstep.com/en/articles/8284237-payouts-when-how-and-why-to-pay-yourself#h_b4251a8439)

## When should Traders take a payout?

This is a great question, and there is no “one size fits all” answer. Realistically, when you request a payout, how much you request is going to vary from Trader to Trader. The answer really depends on who you are and how you need to operate.

  
The goal of a Trader is one thing: to make money. It may sound greedy, but that is ultimately why we are here, to take money out of the markets and put it in our own pockets. As a Trader, you take risks in the markets to reap potential rewards, and like any other business, you want to be paying yourself. Trading is a business and should be treated as such.

There are a number of things one should consider when taking money out of their trading account, the most important consideration being survival. When you decide to pull money from your account, the first thing you should be thinking about is, “How will this affect my ability to continue operating in the markets?” In other words, you want to ensure that the money you pull out will not affect your ability to continue trading if you hit a rough patch. You should always feel comfortable with the amount you are pulling.

  
The best way to think about how much you should request would be to think about what percentage of your overall account you are pulling out. Am I pulling out 50% of my account, or am I paying myself 10% of the account balance?

  
Where the payouts vary for most people will depend on their risk tolerance, specifically how much they are willing to risk or lose in a single trading day or trading week. Usually, Traders like to maintain a certain account balance based on how much they need to keep in the account to post margin for their contract sizing. The other factor to consider is, “How much do I allow myself to draw down on my losing days?”

Traders who assume large risks will want to maintain a larger account balance to ensure they do not fully draw down their account in a single day(s) or even a single week. Traders who do not risk as much on any given trading day might not need to maintain as large an account balance. The amount a Trader maintains should be determined by the size of their maximum risk on their losing days.  
​

## Payout Examples

  
​**For example:** If I have a $10,000 trading account balance, can I request $5,000 of it?

- If I am a low-risk Trader who usually only risks $250 each day I trade, then I likely could take this $5,000 payout and safely operate with a $5,000 account balance. After all, it would take me 20, $250 losing days in a row to burn through that $5,000 balance. Odds are I won’t have 20 losing days in a row. Plus, my winning days are usually larger than my losing days.
    
- If I am a Trader who is willing to take larger risks, then maybe I shouldn’t be taking such a large payout and should maintain a larger account balance. If, on my losing days, I sometimes risk up to $1,000 trading, then I’m not setting myself up for survival if I request $5,000 and only leave $5,000 in the account. If I happen to have five $1,000 losing days, my account is at $0, and I can no longer trade. I should not risk losing my account over one bad trading week.
    

A Trader should always measure out how many losing days they could survive when thinking about how much to keep in their account and how much they should request.

The reality is that payouts do not need to be huge when you take them. There is nothing wrong with paying yourself in small amounts! Whether it’s a $100 payout you take or a $1,000 payout you take, you should make an effort to pay yourself often. Have a good trading month? Account balance over what you usually maintain? PAY YOURSELF! Have an unusually large winning day? PAY YOURSELF!

It feels good to turn those numbers you see on your computer screen that say “Account Balance” into something tangible that you can put in your hand to use in the real world. Whether it’s buying yourself a basic lunch, treating yourself to something nice, or paying the bills, THIS IS WHY YOU ARE HERE!

Paying yourself can and will also help with your money management when in the markets. Again, it lets you know that that Account Balance isn’t just a number on the computer screen; it's real money! It could also influence your decisions while in a trade for the better. If you’re up money on the week going into Friday and had intended to take a payout at the end of the week, well, you might be more conscious of hanging onto the money you’ve made and potentially get out of a trade you are unsure of to ensure you walk away up on the week.

For more insight and discussion around payouts and maintaining an account balance, click to watch Topstep’s [Coach’s Playbook: When, How, and Why to Pay Yourself](https://www.youtube.com/watch?v=1JgDcq-3Udw)! You can review Topstep's payout policy [here](https://intercom.help/topstep-llc/en/articles/8284233-topstep-payout-policy).

## **Payout Parameter Tables:**

**$5,000 Account Balance**

|   |   |   |   |
|---|---|---|---|
|Small<br><br>Payout|$500|10%|_Minimal impact on account balance_|
|Medium<br><br>Payout|$1,000|20%|_Plan ahead, live to trade another day_|
|Large<br><br>Payout|$1,750|25%|_Consider scaling back daily risk_|
|Extra Large Payout|$2,500|50%|_Must scale back daily risk in order to continue trading safely - Don’t blow up your account for requesting too much._|

**$10,000 Account Balance**

|   |   |   |   |
|---|---|---|---|
|Small<br><br>Payout|$1,000|10%|_Minimal impact on account balance_|
|Medium<br><br>Payout|$2,000|20%|_Plan ahead, live to trade another day_|
|Large<br><br>Payout|$2,500|25%|_Consider scaling back daily risk_|
|Extra Large Payout|$5,000|50%|_Must scale back daily risk in order to continue trading safely - Don’t blow up your account for requesting too much._|

**$15,000 Account Balance**

|   |   |   |   |
|---|---|---|---|
|Small<br><br>Payout|$1,500|10%|_Minimal impact on account balance_|
|Medium<br><br>Payout|$3,000|20%|_Plan ahead, live to trade another day_|
|Large<br><br>Payout|$3,750|25%|_Consider scaling back daily risk_|
|Extra Large Payout|$7,500*|50%|_Must scale back daily risk in order to continue trading safely - Don’t blow up your account for requesting too much._|

**$20,000 Account Balance**

|   |   |   |   |
|---|---|---|---|
|Small<br><br>Payout|$2,000|10%|_Minimal impact on account balance_|
|Medium Payout|$4,000|20%|_Plan ahead, live to trade another day_|
|Large<br><br>Payout|$5,000|25%|_Consider scaling back daily risk_|
|Extra Large Payout|$10,000*|50%|_Must scale back daily risk in order to continue trading safely - Don’t blow up your account for requesting too much._|

***Please note:** the example payout amounts above may not apply to all account types. Payout caps exist for the Express Funded Accounts, but not the Live Funded Accounts. You can review Topstep's payout policy [here](https://intercom.help/topstep-llc/en/articles/8284233-topstep-payout-policy).

# Funded Trader Tax Questions

Updated this week

- [2025 1099's](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_e4a6cb3abf)
    
- [What tax forms do I need to complete?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_07e678f2a7)
    
- [Will I be considered an employee of Topstep?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_326fac9fdf)
    
- [How should I report my earnings from Topstep?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_70cea3e028)
    
- [Can I open a Funded Account under a business or company?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_b15a1ed231)
    
- [What forms will I receive at the end of the year?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_34cc9bd0b9)
    
- [Payout Processing Fees & 1099-NEC Reporting](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_2606c6f6c0)
    
- [How should I report my earnings to a country besides the US?](https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions#h_4a1cc6ff6c)
    

## 2025 1099's​

## On January 31, 2026, Topstep sent 1099s via email to traders who are United States citizens and received over $600 in payouts in 2025. If you are not a United States citizen, or your total payouts in 2025 were under $600, you did not receive a 1099 or any tax documentation from Topstep. If you meet the criteria and have not received yours, please check your spam folder. If you have questions about your 2025 1099, please email [1099support@topstep.com](mailto:1099support@topstep.com).

## What tax forms do I need to complete?

The tax forms you need to complete depend on your location.

- If you have US citizenship, you must fill out a W9. This is true even if you do not currently live in the US. Additionally, if you are a resident alien of the US, you must fill out a W9 regardless of your citizenship.
    

- If you do not have US citizenship and are living outside of the US, you must fill out a W-8 BEN.
    

- If you are a US resident alien and have an Individual Taxpayer Identification Number (ITIN) instead of a Social Security Number (SSN), the W-9 is still the correct form for you. Enter your ITIN in the SSN field on the W-9. If the form does not accept your ITIN, please contact our Support Team. They can help troubleshoot the issue.
    

## Will I be considered an employee of Topstep?

No, you will not be considered an employee of Topstep. All traders are considered independent contractors.

## How should I report my earnings from Topstep?

- Funded traders should report earnings as regular income.
    

- Funded traders are only required to report the amount they have received as payouts. For example, if you earn $5,000 in your funded account but only request a $1,000 payout, you will have to report $1,000 worth of income.
    

## Can I open a Funded Account under a business or company?

No, you cannot open a Funded Account under a business or company. Traders can only set up a Funded Account in their own name (as an individual) using their legal first and last name.

- Even though traders cannot set up a Funded Account under a business, traders **are permitted to receive Payouts and file taxes under a US-based single-member LLC.**
    
- If you want to use a single-member LLC, Topstep will create your Express Funded Account or Live Funded Account using your personal information. You can then complete your tax documents for the account with your single-member LLC information.
    

If you want to use your eligible business to receive payouts and file taxes, you must **_use your personal information (legal first and last name, etc.)_** on the Funded Account Agreement

You can enter your business information on the bank information and tax forms. Topstep traders are not permitted to receive payouts or file taxes under a C-corp, S-corp, or multiple-member LLC.

## What tax forms will I receive at the end of the year?

The tax forms you receive at the end of the year will depend on your citizenship.

- **If you have US citizenship** and received over $600 worth of payouts in a calendar year, you will receive a 1099-NEC form the following year. The amount of funds you received will be recorded on the 1099-NEC form as nonemployee compensation.
    
- Topstep does not have to provide a 1099 form to anyone making less than $600 during a calendar year.
    
- **If you do not have US citizenship**, you will not receive a 1099 form from Topstep. The 1099-NEC is only applicable for United States tax reporting purposes and not for reporting in other countries.
    

Topstep is not obligated to provide any documents for reporting taxes to governments outside of the United States.

## Payout Processing Fees & 1099-NEC Reporting

This section explains how payout processing fees work and why your Form 1099-NEC may show a higher amount than the net payout you received.

  
​**Scenario Overview**

- You request a **$500 payout**.
    
- You select **ACH or Wire** as your payout method.
    
- A **$30 payout processing fee** applies to ACH/Wire payouts.
    
- You receive a **net payout of $470**.
    
- Your **Form 1099-NEC reports the gross amount of $500**, not $470.
    

This is expected and compliant with IRS reporting requirements.

  
​**Why Does My 1099-NEC Show $500 Instead of $470?**  
The IRS requires payers (the entity issuing the 1099-NEC) to report the **gross amount paid for services**, before any fees, commissions, or expenses are deducted.

In this case:

- **$500** = Gross payout amount (reported on your 1099-NEC)
    
- **$30** = ACH/Wire processing fee
    
- **$470** = Net amount you received
    

Even though you received $470, the IRS requires that the **full $500** be reported on your Form 1099-NEC.

  
​**How Fees Are Handled by Payout Method**

- **Wise**: No payout processing fee. You receive the full payout amount.
    
- **ACH / Wire**: A $30 processing fee is deducted from each payout processed through the new dashboard.
    

Your selected payout method does **not** change how income is reported on your 1099-NEC.

**How to Report This on Your Taxes**

  
If you are filing as self‑employed:

1. Report the **full $500** shown on your Form 1099-NEC as income.
    
2. Deduct the **$30 payout processing fee** as a business expense on **Schedule C (Form 1040)**.
    
3. This results in a **net taxable income of $470**.
    

You are only taxed on your **net profit**, not the processing fee.

# Common Questions

- **Did I get overreported to the IRS?**
    

No. Your income was reported correctly at the gross amount, as required by the IRS.

- **Can you issue a corrected 1099-NEC for $470?**
    

No. Since the $30 is a processing fee and not a reduction of income, the 1099-NEC must reflect the gross amount of $500.

- **Why doesn't Wise have this issue?**
    

Wise payouts do not have a processing fee, so the gross and net amounts are the same.

## How should I report my earnings to a country outside of the United States?

If you want to know how to report your earnings to a country outside of the United States, it's important to know that **Topstep cannot offer any guidance or advice for foreign tax reporting.**

- We advise traders to report any earnings per your country's local tax laws. We also recommend that traders consult a tax or legal professional if they have any specific questions regarding their country's tax standards.
    

# Important Disclaimer

This article is for informational purposes only and should not be considered tax advice. We recommend consulting a qualified tax professional if you have questions about your specific tax situation.

# TopstepX™

Updated this week

**[TopstepX Features](https://help.topstep.com/en/articles/14434175-topstepx#h_bb8377d003)**

**[TopstepX Order Management](https://help.topstep.com/en/articles/14434175-topstepx#h_fe9cb6ad59)**[](https://help.topstep.com/en/articles/14434175-topstepx#h_a3c384b323)

**[TopstepX Risk Settings](https://help.topstep.com/en/articles/14434175-topstepx#h_fc7e858f07)**[](https://help.topstep.com/en/articles/14434175-topstepx#h_a014f98a4f)

**[Troubleshooting](https://help.topstep.com/en/articles/14434175-topstepx#h_ed21f6b5d6)**

**[Mobile Devices](https://help.topstep.com/en/articles/14434175-topstepx#h_e42f9eebad)**

**[TopstepX YouTube Videos](https://help.topstep.com/en/articles/14434175-topstepx#h_2d08c30b5d)**

[TopstepX™](https://www.topstep.com/topstepx/) is a trading platform designed to support Traders with tools for execution, risk management, and performance tracking. With features like advanced order management, customizable risk settings, and detailed performance insights, it helps Traders stay disciplined and refine their strategies. TopstepX offers flexible functionality to support Traders at every stage of their journey.  
​

[Click here](https://topstepx.com/trade) to access TopstepX™. You will enter either your username or password, which were emailed to you when you made your first Trading Combine purchase. The password is specific to the platform and can be reset on this login page.

You can also launch TopstepX right from your dashboard!


Once you are logged into TopstepX™, you are ready to trade! Just be sure to select your account in the top left!

# **TopstepX Features**

#### TopstepX Features: Select each feature drop-down below to learn more!

### Account Nicknames

#### Account Nicknames

You can now assign nicknames to your accounts, making it easier to stay organized and avoid trading in the wrong account.

#### **How It Works**

Click the pencil/edit icon next to any account in the dropdown menu, enter your desired nickname, and click Save. Your nickname will appear in the dropdown going forward. To change or delete a nickname at any time, simply click the pencil/edit icon again.

**Why It's Useful**

Nicknames help you organize and personalize your accounts by strategy, risk tolerance, asset, or market condition, so you can quickly identify and switch between accounts without relying on account numbers.

**Good to Know**

- Works on all account types: Trading Combines, Express Funded, and Live Funded Accounts.
    
- Resetting a Trading Combine creates a new account number and clears the nickname.
    
- Nicknames are limited to 30 characters and support special characters and spaces.
    
- Nicknames are not visible to the Trader Support Team. When contacting support, always provide your original account number.
    

### Track Your Preferred Products

TopstepX does not currently offer a traditional watchlist feature. Instead, you can **favorite** your most frequently used products to quickly access them:

1. Open the **Order Ticket** or **DOM**.
    
2. Click the **Contract** dropdown.
    
3. Click the **star** ⭐ next to your preferred products.
    

All starred products will move to the **top of the product dropdown**, making it easier to find and access your most traded instruments.

### Extended and Regular Trading Hours Toggle

#### Extended and Regular Trading Hours Toggle

TopstepX lets you easily switch between Extended Trading Hours (ETH) and Regular Trading Hours (RTH) charts, giving you a more complete view of the market and greater flexibility in your analysis and strategy.

#### **ETH vs. RTH**

**Extended Trading Hours (ETH)** cover nearly 24 hours, including overnight sessions. With fewer active traders, liquidity is lower, and price movements tend to be more volatile and unpredictable.

**Regular Trading Hours (RTH)** see significantly higher participation, especially from institutional traders, resulting in better liquidity and more stable price action.

**Why It Matters**

Toggling between ETH and RTH helps you spot price gaps, identify key support and resistance levels, and tailor your strategy to current market conditions. Here are a few strategies where this feature is especially useful:

- **Gap Trading:** Spot price gaps that form between the previous day's close and the current day's open, typically during the ETH to RTH transition.
    
- **Breakout Trading:** RTH breakouts tend to be more reliable due to higher volume. Use the toggle to identify where and when key breakout levels form across both sessions.
    
- **Volume Profile** & **Supply/Demand Trading:** Toggling to RTH helps filter out low-volume noise, making it easier to identify institutional activity and high-probability setups.
    

### Exporting Trades

#### Exporting Trades

Exporting your trades is a powerful way to review performance, refine strategies, manage risk, and better understand your trading habits.

#### **How to Export Your Trades**

1. Click the **Orders** or **Trades** tab at the bottom of the page.
    
2. Click **"Export."**
    
3. Select your desired date range and click **"Export."**
    
4. A confirmation will appear at the bottom-left of your screen once complete.
    

From there, upload your file to Excel, Google Sheets, or any program you prefer.

### Hotkeys

#### Hotkeys

Hotkeys are keyboard shortcuts that let you execute trades and manage positions faster, with fewer errors and less manual input. They are fully customizable to match your trading style.

#### **How to Set Up Hotkeys**

1. Click the Settings gear and select **Hotkeys**.
    
2. Click **Set Hotkey** next to the action you want to assign.
    
3. Press the key(s) you'd like to use and click **Confirm**.
    
4. Once set, press the **H** button on the DOM or Orderbook to enable your hotkeys.
    

Hotkeys work across all your active accounts and can be reset or cleared at any time in Settings.

**Good to Know**

- Hotkeys are not set by default; you must configure your own.
    
- Avoid using keys already reserved by your system (e.g., CTRL+R reloads a webpage). The Windows and Command keys cannot be used.
    
- Hotkeys are desktop only and are not supported on mobile.
    
- If hotkeys stop responding, verify they are enabled in Settings or try restarting the platform. If the issue persists, contact Trader Support.
    
- Practice using hotkeys in a Practice Account before using them in an evaluation to avoid accidental trades.
    

### Performance Dashboard

#### Performance Dashboard

The Performance Dashboard gives you a real-time, comprehensive view of your trading activity, from high-level overviews to detailed breakdowns, helping you track, analyze, and refine your strategies.

Available on desktop only for Practice, Trading Combine, and Express Funded Accounts. Stats update as round-turn trades are completed. If you have multiple browser tabs open, refresh the performance page after each trade.

To access, click the **Performance Stats** tab on the left-hand side of your screen.

#### **What's Included**

_Performance Stats:_ Account Balance High/Current/Low, Best Day % of Total Profit, Avg. Winning & Losing Trade, Best & Worst Trade, Total Trades & Contracts Traded, Win Rate, Long vs. Short Trade %, and Weekly/Monthly P&L.

_Trade Log:_ A detailed breakdown of every closed trade, including Trade ID, Symbol, QTY, Entry/Exit Price & Order ID, Fees, P&L, and Order Type.

**_Additional Features_**_:_

- **Trader Journal:** Log your emotions, market observations, and notes on specific trades.
    
- **Calendar with Daily** P&L**:** View weekly and monthly performance at a glance.
    
- **Social Sharing:** Share your performance with others.
    

**A Few Things to Know**

- Data updates in real-time for most metrics; some update at the end of the day.
    
- Only closed trades are reflected in your stats; open orders are not included.
    
- The win/loss ratio is calculated by dividing the number of profitable trades by the number of losing trades.
    

---

#### **Journaling**

The Journaling Feature on the Performance Stats page is a great way to track your emotions, progress, market observations, and more.

Journaling is only available on days you have traded.

You can journal in two ways: by day (via the Calendar) or by specific trade (via the Trades section).

**Journaling by Day**

1. Click the Performance tab on the left-hand side of the platform.
    
2. Scroll to the Calendar and click the date you'd like to journal about.
    
3. Click "**Add Journal**," write your entry, and click "**Save Journal**."
    

---

**Journaling by Trade**

1. Click the Performance tab on the left-hand side of the platform.
    
2. Scroll past the Calendar to the Trades section and click the journal icon next to the trade you'd like to write about.
    
3. Write your entry and click "**Save Journal**."
    

### The Tilt™ Indicator

#### The Tilt™ Indicator

The Tilt is Topstep's proprietary, real-time sentiment indicator that shows the long (bullish) and short (bearish) positioning of all Funded Traders on TopstepX. It gives you a visual breakdown of buy and sell interest for specific products, helping you better understand market psychology and potential price direction.

#### **How It Works**

- Data refreshes every 10 seconds, tracking all Express Funded Account trades.
    
- Currently available for four instruments: E-Mini S&P 500 (ES), NASDAQ (NQ), Crude Oil (CL), and Gold (GC).
    

**How to Access The Tilt**

The Tilt is enabled by default and accessible from the bottom panel of your platform. If you don't see it:

- Click the "+" icon in the top-right corner of your layout and select The Tilt.
    
- If you're still having trouble, use the Reset Layout button to restore default settings.
    

Resetting your layout may remove any custom layouts you have saved.

**Best Practices**

- Use The Tilt alongside technical analysis and risk management — it is a complement to your strategy, not a replacement.
    
- Keep in mind it reflects Topstep funded Trader positioning only, not the broader market.
    
- Sentiment can shift quickly, so always consider current market context such as news and volatility.
    

### Trade Copier

#### Trade Copier

The Trade Copier allows you to copy trades from a Lead account to one or more Follower accounts, which is great for managing multiple accounts with a single strategy. The **Lead** account is where you place your trades. The **Follower** account(s) are where those trades are copied to.

#### **Before You Get Started**

- Orders on Follower accounts will only appear in the Order Log once filled.
    
- The Lead account must have the lowest Maximum Position Size among all accounts being used. For example, if you have a 50K, 100K, and 150K account, the Lead account should be the 50K, as it has the smallest Maximum Position Size.
    
- Trade copying is only available for Trading Combine and Express Funded Accounts. **Live Funded Accounts cannot use the Trade Copier.**
    
- While connected to a Leader account, you cannot trade directly on a Follower account. If the order buttons are greyed out, the account is still connected. To trade on it directly, remove it as a Follower account in Settings
    
- Filled orders on the Lead account are mirrored on Follower accounts; however, minor execution differences should be expected due to factors such as slippage, liquidity, market volatility, and the number of accounts being copied. This means that while the order itself is replicated, the exact execution (including fill price and timing) may vary slightly between accounts.
    
- Turning off the Trade Copier during an active trade will immediately flatten all Follower account(s).
    
- If the Lead account hits its Maximum Loss Limit, Daily Loss Limit, or is auto-liquidated, the Trade Copier will turn off and must be manually re-enabled.
    
- When a Payout request is submitted, Follower accounts are automatically unlinked. Always verify your copy trading settings at the start of each session.
    

Please read more about how copy trading can affect potential for hedging [here](https://intercom.help/topstep-llc/en/articles/13747047-understanding-hedging).

**Risk Settings for Follower Accounts**

Follower accounts can have a Personal Daily Loss Limit (PDLL) and/or Personal Daily Profit Target (PDPT) enabled. Trade Limits, Symbol Blocks, and Contract Limits are not available for Follower accounts.

**Setting Up the Trade Copier**

1. Log in to TopstepX and click Settings in the left sidebar.
    
2. Select the Copy Trading tab.
    
3. Choose your Lead account from the dropdown.
    
4. Under Followers, check the accounts you want to copy trade on.
    
5. Click Save Changes, then return to your workspace.
    

**Turning Off the Trade Copier**

1. Go to Settings → Copy Trading.
    
2. Click Clear, then Save Changes.
    

**Adding or Removing Follower Accounts**

1. Go to Settings → Copy Trading.
    
2. Check or uncheck accounts under Follow, then click Save Changes.
    

**Using the Trade Copier on Mobile**

1. Open TopstepX in your mobile browser.
    
2. Tap the 3 dots (bottom-right) → Trading → Copy Trading.
    
3. Select your Lead account, check your Follower accounts, and tap Save Changes.
    

### Trading Tones

#### **Trading Tones (Custom Audio Notifications)**

The new **Trading Tones** feature on TopstepX lets you personalize your trading experience by uploading custom audio alerts for key platform events.

You can now assign your own tones to notifications like order fills, risk limits, and more so you always know what’s happening without looking at the screen.

​**Where to Find Trading Tones**

1. Open **TopstepX**
    
2. Navigate to **Settings**
    
3. Click **Misc**
    
4. Scroll to the **Custom Sounds** section
    

Here, you’ll see a list of all supported notifications where you can assign custom audio.  
​

#### **Supported Notifications**

You can upload unique sounds for the following events:

- **Order Filled**
    
- **TP/SL (Take Profit / Stop Loss)** _(new)_
    
- **Order Rejected**
    
- **Market Open**
    
- **Market Closed**
    
- **Order Cancelled** _(new)_
    
- **Position Closed – In the Money** _(new)_
    
- **Position Closed – Out of the Money** _(new)_
    
- **PDLL (Personal Daily Loss Limit)** _(new)_
    
- **MLL (Max Loss Limit)** _(new)_
    
- **DLL (Daily Loss Limit)** _(new)_
    
- **PDPT (Profit Target)** _(new)_
    

**How to upload a Trading Tone**

1. Find the notification you want to customize
    
2. Click the **Upload** icon next to it
    
3. Select your custom audio file from your local computer
    
4. Click **Upload** to apply the sound
    

#### **Preview** & **Manage Sounds**

Once uploaded, you can:

- **Preview** your sound using the play button
    
- **Replace** it with a new file anytime
    
- **Delete** it to revert to default audio
    

#### **File Requirements**

Make sure your audio file meets the following:

- **Maximum size:** 3 MB
    
- **Supported formats:**
    
    - .mp3
        
    - .wav
        
    - .ogg
        
    - .m4a
        
    - .webm
        
    

**Important Notes**

- Custom audio uploads are specific to your account. Audio files you upload are not shared with or accessible by other Traders.
    
- Audio notifications configured on the desktop web will also apply to your mobile experience if audio notifications are enabled on your mobile device.
    
- Some notifications listed above are new additions to the platform. These new notifications do not include Hoag's audio pack and will only have a default sound available until you upload a custom file.
    

**Important:** TopstepX does not currently offer price alerts on charts. However, you can enable **sound alerts** to be notified when an order is placed, canceled, or filled.

# **TopstepX Order Management**

#### TopstepX Order Management: Select each feature drop-down below to learn more!

### Adding Auto Profit / Risk Brackets to your TopstepX Orders & Positions

#### Adding Auto Profit / Risk Brackets to your TopstepX Orders & Positions

TopstepX’s Position Brackets are designed to help Traders stay disciplined by automatically attaching predefined stop-loss and take-profit levels to each position. This helps keep risk controlled, profits planned, and emotions out of the decision-making process.

You can set brackets at the account level, allowing different accounts to support different strategies. This makes it easier to switch between products or sessions without needing to make quick adjustments in the moment.

#### **How to Set Up Position Brackets**

1. Click Settings from the left sidebar to access your risk/reward setup.
    
2. In the Positions module, locate the Risk and Profit fields.
    
3. Click the pencil icon to edit these values.
    
4. Enter your desired dollar amounts.
    
5. Be sure to click Save to apply your changes.
    

**Adjusting an Active Trade**

If you already have an open trade, you can adjust your risk and reward directly by dragging and dropping the P&L bar for that position.

### Auto-OCO Brackets

#### Auto-OCO Brackets

Auto-OCO (One Cancels Other) Brackets automatically attach a take-profit and stop-loss to each trade, helping you manage risk without manual order placement.

When you place an entry order, a take-profit and stop-loss are automatically created.

- When you place an entry order, a take-profit and stop-loss are automatically created.
    
- Each entry gets its own bracket (not averaged)
    
- If either the take-profit or stop-loss fills, the other is automatically canceled
    

#### **Important Notes**

- If you are using the DOM or Order component, OCO must also be enabled there
    
- You must be flat (no open positions/orders) to enable or switch bracket types
    
- Brackets are applied per entry, not across your entire position
    

**How to enable Auto-OCO Brackets**

- Go to **Settings → Risk Settings**
    
- Select **Switch to Auto-OCO Brackets**
    
- Configure your **take-profit and stop-loss values**
    
- Click **Save**
    

### Charting

#### Charting

TopstepX supports up to 8 charts open on a single screen, making it easy to monitor multiple products or timeframes at once. Each chart loads with /ES by default, but can be changed to any available product. To display different products across charts, leave them unlinked — unlinked charts operate independently and won't update when you change a symbol elsewhere. To keep charts in sync, use the Symbol Link feature to assign matching colors to the components you want connected.

**Important to Know:**

- TopstepX cannot be connected to external platforms like TradingView, and custom indicators are not currently available.
    
- Available chart timeframes are: 1 min, 2 min, 3 min, 5 min, 15 min, 30 min, 1 hour, 4 hours, 1 day, 1 week, and 1 month. The 10-minute timeframe is not currently available.
    

#### **Symbol** & **Component Linking**

Link components to a color so that updating a symbol in one component automatically updates all linked components, including your Chart and DOM. To link, click the link icon in any component header and select a color.

To link a component, click the link icon in the component header and select a color. To link a chart, click the "Add Chart Link" button while the chart is active and assign it a color. Components showing the "unlinked" icon are not connected to any color group.

**Chart Executions**

Chart Executions lets you display your trade entries and exits directly on your charts, giving you a clear visual record of your trading activity. When enabled, every entry and exit will be marked on your chart and stacked together, making it easy to:

- **Analyze trades** by identifying patterns and refining your strategies.
    
- **Review your decision-making** by visually comparing your entries and exits to price movements.
    
- **Recap and journal trades** by seeing exactly where you entered and exited the market.
    
- **Develop strategies** based on visual evidence of your past performance.
    

This feature is especially useful for frequent traders, as all entry and exit points remain visible even when multiple trades are made on a larger candle. Disabled by default.

To enable:

1. Click Settings → Charts & Data.
    
2. Toggle "Show Chart Executions" and click "Save."
    

**Chart Value Display**

Show your position values in dollars, ticks, percent, or points (dollars by default).

To change:

1. Click Settings → Charts & Data.
    
2. Select your preference from the "Chart Value Display Type" dropdown and click "Save."
    

**Topstep's Daily Levels Indicator**

Every day on TopstepTV, Senior Performance Coach and 35+ year trading veteran John "Hoag" Hoagland shares his key market levels. Now those levels are built directly into TopstepX as a charting indicator, giving you an extra layer of confluence for any trading strategy — at no additional cost, no plugins required, and suitable for all experience levels.

**Available for:** ES, NQ, CL, and GC.

**Levels Plotted**

|   |   |   |
|---|---|---|
|**Abbreviation**|**Level**|**Description**|
|LWH / LWL|Last Week's High / Low|Highest and lowest prices in last week's extended hours range|
|YH / YL|Yesterday's High / Low|Highest and lowest prices in yesterday's extended hours range|
|YVAH / YVAL|Yesterday's Value Area High / Low|Upper and lower bounds of where 70% of the previous day's volume occurred|
|YPOC|Yesterday's Volume Point of Control|Price level with the highest trading volume from the previous day|
|WKOH / WKOL|Weekly Kickoff High / Low|Key levels above/below market price used as potential resistance/support|
|Settlement|Settlement Price|Official closing price of a futures contract for the trading day|

On Mondays, all "Yesterday's" levels will display Friday's values. **Daily levels** update each trading day. **Weekly levels** update once per week.

**How to Access**

1. Click the Indicators tab on your chart.
    
2. Search "Topstep's Daily Levels" and select it from the dropdown.
    
3. Click the star icon to favorite it for easy access.
    
4. To customize colors or labels, click the Settings gear.
    

---

**Position Grid** & **Chart Sync**

You can now click any open position in the Positions Grid to instantly update your focused chart to that instrument, no manual symbol search needed.

Simply click on any position in the Positions Grid and your active chart will automatically update to display that instrument. This makes it faster and easier to analyze and manage open positions without interrupting your workflow.

- In a multi-chart layout, the sync targets whichever chart is currently in focus, keeping you in control of your layout.
    
- If your chart is linked to other components, everything updates together automatically when you select a position.
    

### Order Management Overview

#### **Types of Orders**

|   |   |
|---|---|
|**Order Type**|**Description**|
|**Market Order**|Filled immediately at the current market price|
|**Limit Order**|Filled at a specific price set by the trader|
|**Stop Market Order**|Remains pending until conditions are met; typically used to limit losses or enter a position after a confirmed directional move|
|**OCO (One Cancels the Other)**|Two orders that work together —when one is executed, the other is automatically canceled; great for managing risk and automating strategies|
|**Trailing Stop Order**|Places a stop order at a set price that trails the market in predetermined increments as price moves away from the stop|
|**Filled Order**|An order that has been executed in the market|
|**Open/Pending Order**|An order waiting to be filled in the market|
|**Risk (Stop)**|The amount (in USD) you're willing to risk on a position. When reached, the position closes and the loss is realized. Updates automatically as position size changes|
|**To Make (Take Profit)**|The amount (in USD) you want to make on a position. When reached, the position closes and profits are realized. Updates automatically as position size changes|

**Order Ticket**

The Order Ticket lets you quickly place and manage orders. From here you can select Buy or Sell, choose your order type (Market, Limit, Stop Market, Trailing Stop, or OCO), and access Cancel All, Flatten All, and Reverse Position.

**Time** & **Sales**

Time & Sales provides a live feed of all trading activity for your selected product. To filter trades by a minimum size, visit the System Settings area.

**DOM (Depth of Market)**

The DOM, also known as the ladder, displays market depth, volume profile, and price levels for one-click trading. It shows hundreds of price levels in each direction and allows you to automate entries and exits directly from the DOM.

- **Left-click** in the Bid or Ask column to place a Limit Order.
    
- **Right-click** in the Bid or Ask column to place a Stop Order.
    
- **Drag and drop** existing orders by hovering, clicking, and dragging them to a new level.
    

Once in a position, it will appear highlighted in blue on the DOM with your theoretical P&L displayed and updating automatically as your position size changes.

Note that TopstepX currently supports one window at a time, so the DOM cannot be moved to a secondary screen.

If you place orders from the DOM, you must also ensure OCO Brackets are enabled in the DOM. If OCO is turned off in the DOM, Auto-OCO Brackets will not be applied, even if enabled in Risk Settings.

**Trading Activity**

The bottom panel gives you a detailed view of your account and trading activity:

- **Accounts:** View all of your active accounts in one place.
    
- **Positions:** View or close open positions and edit your Risk (Stop) and To Make (Take Profit) in USD.
    
- **Orders:** View all completed and open orders for the current trading day and cancel any pending orders.
    
- **Trades:** View all completed round-trip positions.
    
- **Quotes:** View current market conditions for all available futures products.
    

**Order Confirmations**

To enable Order Confirmations on TopstepX:

1. Click **Settings** on the left side of the screen.
    
2. Click **Charts** & **Data**.
    
3. Under Order Settings, click **Show Confirmations**.
    
4. Click **Save**.
    

# **TopstepX Risk Settings**

#### TopstepX Risk Settings: Select each feature drop-down below to learn more!

### Contract Limits

#### Contract Limits

Contract Limits allow you to control your position size by setting a maximum number of contracts you can trade per symbol.

- Contract Limits set a maximum number of contracts you can trade at once (per symbol)
    
- Orders that exceed your limit are automatically rejected
    
- Limits are applied per account
    

#### **Important Notes**

- Contract Limits apply to order entry only- they do not close open positions
    
- Take Profit and Stop Loss bracket orders are ignored
    
- Limits are enforced separately for long and short positions
    

**How to set Contract Limits**

- Go to **Settings → Risk Settings**
    
- Select **Contract Limits**
    
- Enter a contract limit for your desired symbol(s)
    
- Click **Save**
    

### Daily Risk Lock

#### Daily Risk Lock

Daily Risk Lock allows you to lock your risk settings for the rest of the trading day.

#### **This includes:**

- Personal Daily Loss Limit
    
- Personal Daily Profit Target
    
- Trade Limits
    

**Once locked:**

- Settings cannot be changed until the next trading day
    
- Settings automatically unlock at 5:00 PM CT
    
- A timer will shot when the lock resets
    

Support cannot reverse a Daily Risk Lock once it has been applied

**How does it work?**

- Go to **Settings → Risk Settings**
    
- Set your:
    
    - **Personal Daily Limits**
        
    - **Trade Limits**
        
    
- Click **Save**
    
- Select **Lock Risk Settings for Day**
    
- **Confirm** to apply the lock
    

### Lockout

#### Lockout

Lockout allows you to manually restrict your trading for a set period of time. It applies only to the selected account and must be enabled separately for each account.

#### **You can:**

- Lock yourself out of specific trading sessions (New York, London, etc.)
    
- Set a custom duration (15 min, 1 hour, all day)
    

I**mportant Notes:**

- Once a lockout is applied, it cannot be canceled or adjusted
    
- Any open positions and working orders will be automatically closed
    
- Copy-traded positions will be exited
    

Support cannot reverse a lockout once it’s applied.

**All Day Lockout:**

- Locks your account for the full session
    
- If applied after session close, it remains active until 5 PM CT the following day
    

How to set a lockout

- Go to **Settings → Risk Settings**
    
- Select **Set Lockout**
    
- Choose one:
    
    - A session (New York, London, etc.)
        
    - A custom duration (15 min, 1 hour, all day)
        
    

### Personal Daily Profit Target/Daily Loss Limit

#### Personal Daily Profit Target/Daily Loss Limit

The Personal Daily Profit Target (PDPT) and Personal Daily Loss Limit (PDLL) are optional risk settings in TopstepX that allow you to define daily profit and loss thresholds.

When either threshold is reached, your account will respond based on the action you’ve selected.

#### **Key Points**:

- Based on net P&L (real-time)
    
- Designed to help with discipline and consistency
    

**Trailing Option for Personal Daily Loss Limit**:

- The PDLL can be configured as either **fixed** or **trailing**
    
- When **trailing is enabled**, your loss limit automatically adjusts upward as your account balance increases throughout the day
    
- This allows traders to **lock in profits while still maintaining a defined threshold**
    
- Traders can choose whether the trailing behavior is based on:
    
    - **Unrealized Gains** (updates in real-time with open trades)
        
    - **Realized Gains** (updates only after closing profitable trades)
        
    

**When the target is reached, one of the following will occur**:

|   |   |
|---|---|
|Follower Risk Setting|Behavior|
|**No PDLL/PDPT set**|Any liquidation or block on the Leader applies to the Follower|
|**PDLL/PDPT + Liquidate**|Follower liquidates and is removed from the copier when its limit is hit|
|**PDLL/PDPT + Liquidate** & **Block**|Follower liquidates and is blocked for the day; auto-resumes following the next trade day unless manually removed|

**How to Set Your PDPT:**

- Click **Settings → Risk Settings**
    
- Select **Risk Settings**
    
- Enter your desired Limits
    
- Choose your preferred **Action**
    
- Click **Save**
    

### Symbol Block

#### Symbol Block

Symbol Block allows you to restrict specific trading symbols, helping you stay focused on the products you trade best and avoid unnecessary risk.

You can select one or more symbols to block from trading. Once blocked, you will not be able to place trades on those symbols. Blocked Symbols remain restricted until you manually remove them.

#### **Important Notes**

- Symbol block does not close open positions
    
- Symbol block does not cancel working orders
    
- You must manually remove a symbol to trade it again
    
- You can combine Symbol Block with other risk settings (e.g., Trade Limits, Daily Risk Lock)
    

**How to Set Symbol Block**

- Go to **Settings → Risk Settings**
    
- Locate the **Symbol Block** section
    
- Select a symbol from the dropdown
    
- Click **Add Block**
    
- Click **Save**
    

**Blocked Symbols will appear in your Current Symbol Blocks list. To remove a symbol, click the “X” next to it and save.**

### Trade Clock

#### Trade Clock

The Trade Clock is a flexible risk management tool that pauses new trade entries without closing your open positions or canceling working orders. Unlike the Lockout feature, it keeps you in control of your active trades while preventing you from adding more risk.

#### **How to Use the Trade Clock**

1. Once you've entered a trade, open your Risk Settings and set the Trade Clock.
    
2. Choose a preset timer or set a custom duration.
    
3. Click "Enable Trade Clock." A countdown timer will appear near your P&L at the top of the screen.
    

You can still manage open trades, adjust stop losses, and profit targets while the Trade Clock is active. You can also use "Flatten All &Cancel All" to close everything if needed.

**Trade Clock vs. Lockout**

|   |   |   |
|---|---|---|
||Trade Clock|Lockout|
|Closes open positions|No|Yes|
|Cancels working orders|No|Yes|
|Prevents new entries|Yes|Yes|
|Manage existing trades|Yes|No|

### Trade Limits

#### Trade Limits

Trade Limits allow you to set a maximum number of trades you can take per day and/or week.

**How Trade Limits Work**

- You can set a maximum number of trades (daily, weekly, or both)
    
- Each entry and exit counts as a trade
    
- Once the limit is reached:
    
    - You cannot place new trades
        
    - Any working orders are canceled
        
    
- You can still manage open positions (close or adjusts stops/limits)
    

**Important Notes**

- Trade limits **do NOT automatically close open positions**
    
- You are still responsible for managing any open trades
    
- Once your final trade is completed, you cannot place additional trades until the limit resets
    
- A countdown timer will display showing when trading becomes available again Trade limits do not apply to follower accounts when using the trade copier
    

**How to set Trade Limits**

- Go to **Settings → Risk Settings**
    
- Locate **Trade Limits**
    
- Enter:
    
    - Maximum trades per day
        
    - Maximum trades per week
        
    
- Click **Save**
    

### Why Was My Account Liquidated If My Final Balance Was Above the Risk Limit?

#### Why Was My Account Liquidated If My Final Balance Was Above the Risk Limit?

Your Loss Limits (Maximum Loss Limit, Daily Loss Limit, Personal Daily Profit Target) are monitored in real time using your Net P&L, which includes both realized and unrealized profits and losses. For example, if your account balance touches or falls below the Maximum Loss Limit at any point during the trading day, your account is considered to have breached the rule and will be liquidated.

##   
**What this means**

In fast-moving markets, your account may breach Limit based on unrealized losses before your positions are liquidated. When liquidation occurs:

- Positions are closed using market orders
    
- Market conditions may change during execution
    
- Slippage may occur while positions are being flattened
    

Because of this, your final realized P&L after liquidation may appear above the Limit, even though your unrealized P&L temporarily breached the limit first, triggering the violation.

##   
**Maximum Loss Limit Example**

- Maximum Loss Limit: $48,000
    
- Account Balance: $50,000
    
- Open Trade Moves Against You:
    
    - Unrealized P&L drops account balance to **$47,750**
        
    - MLL is breached → liquidation triggered
        
    
- During liquidation, price moves favorably
    
- Final Realized Balance: **$48,050**
    

Even though your final realized balance is above the limit, the account still violated the Maximum Loss Limit because your unrealized P&L dropped below the threshold first.

While the example above covers the Maximum Loss Limit, the same logic applies to the Daily Loss Limit, Personal Daily Loss Limit, and Personal Daily Profit Target as well.

## **Best Practice**

To avoid unexpected violations, consider:

- Using stop losses before approaching your Maximum Loss Limit
    
- Monitoring unrealized P&L, not just closed trades
    
- Leaving a buffer above your Maximum Loss Limit during volatile markets
    
- Refraining from trading during high-impact news events
    

These Risk Limits are designed to simulate real-world risk management and ensure consistent trading discipline across all accounts.

# **Troubleshooting**

#### Troubleshooting

If you’re experiencing latency or slow performance:

- Lower your Data Speed (Slow or Medium Recommended)
    
- Remove indicators and add them back one at a time
    
- Reduce the number of active indicators
    
- If you’re on mobile, try using another device such as a laptop or desktop
    
- Try another browser or incognito mode
    
- Clear your Cache and Cookies
    

TopstepX uses real-time exchange data with no artificial delay. On slower machines or Wi-Fi connections, this may impact performance.

---

### **Inverted Charts**

#### Inverted Charts

If your chart appears upside down, the **Invert Scale** setting is likely enabled.

- **Right-click on the price axis** on the right side of the chart
    
- Look for "**Invert Scale**"
    
- If it is checked, uncheck the option
    
- The chart should return to its normal orientation
    

### How to Flatten Your Trades

#### How to Flatten Your Trades

If you want to quickly exit all positions and cancel all working orders, use Flatten All.

- This will **close all positions and cancel all working orders** on the selected account
    
- It does **not** affect other accounts
    

#### **Flatten Your Trades**

1. Locate the **Flatten All** button (available on both the Order Ticket and DOM)
    
2. Click **Flatten All**
    
3. Click **Confirm**
    

---

**Discord**

If you're unable to flatten directly on the platform, you can submit a request through out **#get-flat channel in [Discord](https://discord.gg/8qPyEuEhNS)**.

**Include:**

- Account number
    
- Platform (TopstepX)
    
- Brief reason for the request
    

Our team will review and process the request as quickly as possible.

💡 **Orders, stops, or take profits not showing on your chart?** Check chart linking first. Click the link icon on your chart and confirm it's connected to the account you're actively trading. This is the most common reason orders don't appear visually even when they're executing correctly. Performance troubleshooting (data speed, cache) is a separate issue.

### **Mobile Devices**

TopstepX is mobile-friendly and can be accessed through your phone’s web browser, allowing you to manage trades and monitor the market on the go. Most desktop features are available on mobile, providing a consistent and flexible trading experience.

For the best experience, use a smartphone, and tablets may perform better in desktop mode. Please note there is currently no mobile app.

If the mobile version is not loading correctly, ensure that “Desktop Mode” is disabled in your browser settings.

Because mobile performance depends on your device, Wi-Fi, and data provider, we’re unable to troubleshoot mobile-specific issues that may be related to connectivity.

### **TopstepX YouTube Videos**

TopstepX offers a video library on YouTube with a variety of videos to help you get comfortable with the Platform.

These videos are designed to provide quick, easy-to-follow guidance so you can find the information you need and learn at your own pace. Whether you’re just getting started or diving deeper into specific features, the library is a great place to find the information you’re looking for.

You can access these videos anytime on [YouTube](https://www.youtube.com/@TopstepOfficial/videos).

#   Daily Loss Limit in the Trading Combine and Express Funded Account

This article details how the Daily Loss Limit works in TopstepX™, including Personal and Trailing Daily Loss Limit options for Trading Combines and Express Funded Accounts.

Updated in the last hour

---

## **What is a Daily Loss Limit?**

The Daily Loss Limit (DLL) should be viewed as a safety net. It's a risk feature that is optional in Trading Combine or Express Funded Account, but will _automatically_ be applied to all Live Funded Accounts. To learn more about how the Daily Loss Limit works in the Live Funded Account, click [here](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters#:~:text=for%20trading.-,Daily%20Loss%20Limit,-Live%20Funded%20Accounts).  
​  
If broken, it does not count as a rule violation. If the Net P&L should hit or exceed the Daily Loss Limit during the trading day (5:00 PM CT-3:10 PM CT), the account will be auto-liquidated for the remainder of the trading session. This means any open trading positions will be flattened, any pending orders will be canceled, and your account will be prevented from placing any new trades until the start of the next trading day (5:00 PM CT).

**Remember, this is not considered a rule violation, but rather a temporary break from trading for the remainder of the trading session.**

For example, a $150K Trading Combine may have a Daily Loss Limit of $3,000. Therefore, if at any point during the trading day the Net P&L reaches or exceeds -$3,000, the Daily Loss Limit will trigger the account's auto-liquidation. The account will still be eligible for funding and can resume trading in the next session at 5:00 PM CST.

## **Why is the Daily Loss Limit important?**

- Adhering to a loss limit instills discipline and proper risk management
    
- At a certain point, you need to call a bad day a bad day (we all have them)
    
- It allows you to live to trade another day; the markets will be there tomorrow
    
- Losses can be emotional, and emotions can impact decision-making.
    

## **What happens if I exceed the Daily Loss Limit?**

If you exceed a Daily Loss Limit once it's set, the account will be auto-liquidated for the remainder of the trading day, and any order attempts will be rejected. You can begin trading as soon as the next trading day begins at 5 PM CT.

---

## **Set Your Daily Loss Limit at Purchase:** New!

As of April 14, 2026, you now have the option to add a Daily Loss Limit at checkout when purchasing a Trading Combine or activating an Express Funded Account.

#### **The Daily Loss Limit parameters are:**

- $50K Account: $1,000
    
- $100K Account: $2,000
    
- $150K Account: $3,000
    

## **⚠️ Important:**

- Daily Loss Limit is **fixed** (no changes later)
    
- Applies to your **Express Funded Account** after you pass
    

**Coach T Tip:** The traders who last manage risk first. Adding a **Daily Loss Limit** helps you:

- Mirror Live Funded Account rules from day one
    
- Stop losses before they reach your Maximum Loss Limit
    
- Remove emotion when a session turns against you
    
- Build the consistency that stacks solid days over time
    

Always trade for tomorrow.

#### **What happens if you do not set it at purchase**

After purchasing, you can still add a Daily Loss Limit manually through Risk Settings. Unlike Daily Loss Limits set at purchase, manual limits can be adjusted or removed at any time — making it easier to rationalize bad habits in the moment.

---

## **Additional Daily Loss Limit Options**

In the Trading Combine or Express Funded Account, if you do not select to add a permanent Daily Loss Limit at checkout, you may add a Personal Daily Loss Limit to your account (and turn it off) from the Risk Settings page of TopstepX. Read below for details.

## **TopstepX™ Personal Daily Loss Limit**

## **How to set your Personal Daily Loss Limit**

1. To set your Personal Daily Loss Limit, click the Settings gear and then click "Risk Settings".
    
    
    
2. This is where you can set the dollar amount of your Personal Loss Limit, and the action you want to take if it’s hit.
    
    
    
3. You have three options for how your account will respond if the PDLL is hit:
    

- Do Nothing: Continue trading as usual.
    
- Liquidate: Immediate liquidation of your account.
    
- Liquidate and Block: Temporarily deactivate your account for the remainder of the trading day.
    



4. Make sure to click "Lock Out Risk Settings For Day" to save your changes!



## **Helpful Tips**

- By default, "Do Nothing" is selected if you don't choose Liquidate or Liquidate and Block from the drop-down menu.
    

- Once an action is chosen, such as Liquidate or Liquidate and Block, it will be the default setting going forward. This means, in order to change how your Personal Daily Loss Limit works, you'll need to update it in your Settings.
    

- If you choose the Liquidate action for your Personal Daily Loss Limit and then hit or exceed that number, in order to continue trading, you will need to increase your PDLL by the amount liquidated, or change your action to Do Nothing.  
    ​
    
- For example, if you set your loss limit to $200, and are liquidated at $209 because the market was volatile and moving quickly, you must increase your PDLL to at least $210 in order to begin trading again.
    

- The Personal Daily Loss Limit is calculated on the net profit and loss, and it is updated in real-time.
    

## **TopstepX™ Trailing Personal Daily Loss Limit**

## How does it work?

Traders have the ability to set their Trailing Personal Daily Loss Limit to be based on realized profits**,** not just unrealized. When enabling trailing in your TopstepX™ settings, you can now choose to trail from either Unrealized Gains or Realized Gains. This update offers greater flexibility and customization in managing your risk.

## How Does This Benefit Traders?

- **Protect Profits:** By trailing the highest balance of the day, the feature allows traders to lock in gains while staying committed to a loss limit.
    
- **Dynamic Loss Limit:** The loss limit adjusts as your balance grows, allowing traders to capitalize on good trading days without increasing their risk.
    
- **Flexibility:** Choose between trailing based on unrealized (open trades) or realized (closed trades) profits to match your trading style.
    

## Trailing Losses

If you set a $500 Trailing Personal Daily Loss Limit with a starting balance of $50,000 and immediately start losing money, your liquidation action will trigger if your balance drops to $49,500.

## Trailing Profits

**Unrealized Gains:** If your open trade profits increase your balance to $51,200, your new liquidation threshold moves up to $50,700, automatically locking in gains as your profits increase.

**Realized Gains:** If you close a trade that brings your balance to $51,200, your new liquidation threshold moves up to $50,700 upon closing the trade.

If liquidation occurs at $50,700, the system resets the action to "Do Nothing." **You must manually re-enable the Trailing Personal Daily Loss Limit if this occurs.**

## Examples  

### _Unrealized Trailing Example_

1. **Starting Balance:** $50,000
    
2. **Trailing Personal Daily Loss Limit Set To:** $500
    
3. **Open Trade Profit:** $1,200 (unrealized)
    
4. **Trade Closed**: Profit of $1,000 (realized)
    
5. **Balance Reflects:** $51,200
    
6. **Loss Limit Adjusts To:** $50,700
    

_If your balance drops to $50,700, your selected liquidation action will trigger._ _The limit adjusts dynamically as your unrealized profit increases, helping to protect gains even before trades are closed._

---

### _Realized Trailing Example_

1. **Starting Balance:** $50,000
    
2. **Trailing Personal Daily Loss Limit Set To:** $500
    
3. **Open Trade Profit:** $1,200 (unrealized)
    
4. **Trade Closed:** Profit of $1,000 (realized)
    
5. **Balance Updates To:** $51,000
    
6. **Loss Limit Adjusts To:** $50,500
    

_In this example, the loss limit remains at $49,500 until the trade is closed and the $1,000 profit is realized. Once realized, the limit adjusts to $50,500, reflecting the updated balance._

## How to Set Your Trailing Personal Daily Loss Limit

1. **Access Your Risk Settings:**
    
    - Click the Settings gear.
        
    - Select "Risk Settings."
        
        
        
    
2. **Configure Your Trailing Personal Daily Loss Limit:**
    
    - Set the dollar amount of your loss limit.
        
        
        
    - Choose a loss limit action: Do Nothing, Liquidate, or Liquidate & Block.
        
        - **Do Nothing:** No action is taken when the limit is hit.
            
        - **Liquidate:** Closes open positions and orders.
            
        - **Liquidate & Block:** Closes trades and blocks the account for the rest of the day.
            
        
        
        
    - Check the box to Enable Trailing. Note: You must select "Enable Trailing" for the Trailing PDLL Type to display.
        
        
        
    - Select the trailing method: Unrealized Gains or Realized Gains.
        
        - **Unrealized Gains:** The loss limit adjusts in real-time as your floating profit increases.
            
        - **Realized Gains:** The loss limit stays static until you close a profitable trade. Once you do, it updates.
            
        
        
        
    
3. **Save your changes:**
    
    - Click "Lock Out Risk Settings For Day**"** to save your changes.
        
        
        
    - Once you've saved your changes, you'll see that you can no longer make changes to your Risk Settings. The timer lets you know when the lockout will end.
        
        
        
    

## Trailing Daily Loss Limit FAQs  

**What is the Trailing Personal Daily Loss Limit?**

- The Trailing Personal Daily Loss Limit (Trailing PDLL) is a dynamic loss limit that moves up as your balance grows throughout the day. It helps lock in profits while maintaining risk control.
    

**How is the Trailing Personal Daily Loss Limit different from the Fixed Personal Daily Loss Limit?**

- A Fixed Personal Daily Loss Limit stays at the same loss limit throughout the day, while a Trailing Personal Daily Loss Limit moves up as your balance increases, allowing you to protect gains without increasing risk.
    

**Can my Trailing Personal Daily Loss Limit go down?**

- No, the Trailing Personal Daily Loss Limit only moves up when your balance increases and does not trail downward if your balance declines.
    

**Does the Trailing Personal Daily Loss Limit apply to both realized and unrealized gains?**

- Yes, it adjusts based on your highest balance of the day, whether from realized or unrealized profits.
    

**What happens if my balance hits the Trailing Personal Daily Loss Limit?**

- If your balance reaches the Trailing Personal Daily Loss Limit, the system will follow your requested action: Do Nothing, Liquidate, Liquidate, and Block. As long as you don’t choose to block yourself the rest of the day, the system resets the action to "Do Nothing." You must manually reactivate the feature the next time you want to use it.
    

**Can I set up my Personal Daily Loss Limit while in a trade?**

- Yes, the limit will be based on your account balance at the time you save your Trailing Personal Daily Loss Limit settings.
    

**How does “Realized Trailing” work?**

- When Realized Trailing is enabled, your loss limit stays fixed until you close a profitable trade. Once a profit is realized, your loss limit begins to trail behind it. This gives you more control over when the limit starts adjusting.
    

**What’s the difference between realized and unrealized trailing?**

- Unrealized trailing adjusts your loss limit as your open/floating profit grows. Realized trailing only adjusts after a profitable trade is closed.
    

**Can I switch between realized and unrealized trailing during the day?**

- Yes. You can change your trailing setting at any time, unless you choose to lock them out for the session using the Daily Risk Lock feature.
    

---

### **Can you remove my Personal Daily Loss Limit for me?**

No, we cannot remove the Personal Daily Loss Limit for you. Once a trader sets their own Personal Daily Loss Limit through the platform, it cannot be removed mid-session. Traders will need to wait until the next trading session to make any changes to their Personal Daily Loss Limit.

# TopstepX™ API Access

Updated over 3 weeks ago

[What can I do with the API access?](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_b1c9753c32)

[Who is this for?](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_0e3f568f3c)

[Where do I access it?](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_667d24eda5)

[Frequently Asked Questions](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_7ad07632bb)

[Help with TopstepX API access](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_ff3cec675a)

[VPNs, VPS, Remote Servers](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_1b6d568000)

[Important disclaimers for API users](https://help.topstep.com/en/articles/11187768-topstepx-api-access#h_f4014485f8)

TopstepX™ API Access is a powerful new feature designed for advanced traders and developers. It gives you the ability to build, automate, and manage your own trading strategies and tools using TopstepX’s market data and order routing capabilities.

## **What can I do with the API access?**

With API access, you can:

- Build and run your own automated strategies
    
- Connect third-party tools and platforms
    
- Create custom risk management rules
    
- Pull live and historical market data into your custom setup
    
- Execute trades directly through your TopstepX account
    

## **Who is this for?**

API Access is best suited for traders and developers who:

- Have experience coding in languages like Python, Java, or .NET
    
- Want to automate trading logic or connect external tools
    
- Are comfortable working with REST and WebSocket APIs
    

## **Getting Started with API Access**

1. From inside your TopstepX platform, click on the Settings icon⚙️
    
2. Then click the API tab from the top bar
    
3. Then click “Link” under ProjectX Linking  
    ​
    
    
    

This will take you to the [dashboard.projectx.com](https://dashboard.projectx.com/) landing page, where you can verify that the correct email will be used to create your API Access account.



4. Next, click Log in/Register



5. Then select “Don’t have an account?”



6. Create your username and password, and select “Create Account.”



7. This will bring you to your ProjectX API dashboard.



8. On the sidebar, select “Subscriptions,” and you’ll see the option to select “ProjectX API Access.”



9. Once you click that option, you’ll be able to enter your credit card info and promo code (if applicable) to unlock API Access.



10. On the left side of the screen you will see the outline of a person. Linked accounts will show once these steps have been completed.



11. To finish and generate your API Key from your TopstepX Platform, click the settings wheel, then click the API tab on the top bar of the screen.

- Click "Add API Key" to generate a new API Key.
    

## Where do I Find my API Key?

- Login to your TopstepX Platform.
    
- Select the Settings Icon wheel.
    
- Click the API Tab from the top bar.
    
- You will generate an API key inside your ProjectX settings. Use this key to authenticate your requests through OAuth.
    
    - To authenticate your requests, you must use the API key generated within your TopstepX platform settings. This key must be used in conjunction with your TopstepX username.  
        ​
        
        
        
        ​
        
    

---

### **Frequently Asked Questions**

**What can I do with API access?**

- Traders can build and run trading bots, connect scripts or automation from third-party platforms, create custom dashboards and tools, set up trade alerts and monitoring systems, copy trades across accounts, and automate order execution based on their strategies.
    

**What programming languages can I use?**

- The REST API is compatible with most modern languages, including Python, Java, .NET, JavaScript, and more. Anything that can call a RESTful API or use WebSocket connections will work.
    

**How do I get started?**

- You can subscribe through the ProjectX Login Page. Once subscribed, you’ll receive access to developer docs, authentication instructions, and integration guides.
    

**Is there a sandbox environment for testing?**

- No, there is currently no sandbox environment available.
    

#### Does this include access to third-party charting or visualization APIs?

- No. This API does not include access to proprietary charting or visualization tools from external platforms.
    

**What’s included with the subscription?**

- Your API subscription includes your API token, access to REST and WebSocket APIs, real-time market data, integration tools, developer documentation, dashboard management tools, and access to ProjectX's help resources and support routing.
    

**Is real-time market data included?**

- Yes, the subscription includes real-time market data via WebSocket streams.
    

**Can I access historical market data?**

- Yes, historical data is available through the API.
    

**Can I use my subscription across multiple accounts?**

- Yes. If you have multiple TopstepX (white-label) accounts, a single subscription will apply to all accounts linked via your ProjectX Dashboard profile.
    

**How do I authenticate?**

- You’ll generate an API key inside your ProjectX settings. Use this key to authenticate your requests through OAuth.
    

**Do I need to know how to code?**

- If you're building your own tools, some coding knowledge is required. However, you don’t need to code if you’re using third-party tools built by others—just plug in your credentials.
    

**Is this a free feature?**

- No. API access is a paid monthly subscription. Pricing is TBD and will include access to the API and real-time market data.
    

**Who do I contact for support?**

- For basic access and onboarding, contact the Topstep support team. If needed, support will be escalated to ProjectX for payment issues, technical integration, and troubleshooting.
    

**How much does it cost?**

- API Access is $29/month. But Topstep Traders have access to a code for 50% off the duration of the subscription.
    

**What is the code and what are the details?**

- Use code **_topstep_** when purchasing your API Access subscription. This code is for 50% off the monthly price, every month, for the duration of the subscription. This will make your month cost $14.50/month. There is no end date for the code.
    

---

### **Need help?**

**Topstep does not provide technical support for coding, API implementation, integration, or troubleshooting**. For help with those issues, please refer to:

- The **ProjectX Developer Docs**
    
- The **#api-trading** channel in the [Topstep Discord](https://discord.com/invite/topstep) (to share ideas or hear from other traders)
    
- Or contact **ProjectX directly** here: [dashboard@projectx.com](mailto:dashboard@projectx.com)
    

For any **billing or subscription questions**, please contact **ProjectX Support**, as the API is billed and managed separately from your Topstep subscription.



---

## VPNs, VPS, Remote Servers

The TopstepX API unlocks advanced automation and integration for your trading. All activity must be performed from your own device, without using VPS, VPNs, or remote access tools, and must strictly follow Topstep’s [Terms of Use](https://www.topstep.com/terms-of-use/). As a reminder:

- The TopstepX API lets you automate trading and connect third-party tools directly from your own device with no need for outside servers.
    
- All trading activity must originate from your personal device. The use of VPS, VPNs, or remote servers is strictly prohibited by Topstep’s Terms of Use.
    
- Running automation on a VPS or similar service can result in account suspension or removal from the program.
    

---

## Important disclaimers for API users

- Orders made using third-party or custom-built API tools are not eligible for review, adjustment, or reversal by Topstep. All orders executed via the API are considered final.
    
- Topstep is not responsible for any functionality, accuracy, or performance of tools, algos, or systems built using API Access. This includes order execution, data access, latency, errors, or unintended trading behavior.
    
- Topstep does not provide technical support or troubleshooting for custom or third-party tools. All development, maintenance, and risk associated with API use is the sole responsibility of the user.
    
- Use of the API Access and any connected tools is entirely at your own risk. Please ensure your systems are tested, stable, and compliant with Topstep's [Terms of Use](https://www.topstep.com/terms-of-use/).
    
- Please read more about how API access can affect the potential for hedging [here](https://intercom.help/topstep-llc/en/articles/13747047-understanding-hedging).

# Locating Order IDs for Trade Review and Troubleshooting

Updated over a week ago

**Important:** If you experience any issues while trading, please stop trading immediately and [contact the Trader Support Team](https://help.topstep.com/en/articles/8284118-how-do-i-contact-the-support-team). If you continue trading after the issue occurs, we may not be able to review or approve exception requests in most cases. Providing accurate Order IDs when reporting issues ensures a thorough and efficient investigation by the Trader Support Team. These IDs allow the team to pinpoint specific transactions and identify discrepancies more effectively. Additionally, documenting issues with screen recordings and timestamps can provide further clarity and expedite the resolution process. Including your internet connection status and a full view of the platform interface can also be helpful.

When experiencing issues with your trading platform, providing the specific Order IDs for **each affected trade** can significantly speed up the troubleshooting process. By providing this information at the end of your conversation with Windy, you'll help us resolve your issue more efficiently and get you back to trading as quickly as possible. When submitting Order IDs, ensure that you also provide other supporting details such as the affected account numbers, the date and time of the trades, and any observed issues like platform lags or discrepancies. Including screenshots or video recordings can provide additional context for faster resolutions. Recording the issue in real-time using tools like Loom or similar screen recorders can capture critical details such as account numbers, timestamps, and platform interface views, which are invaluable for troubleshooting.

### **TopstepX**

1. Navigate to the account where the trade issues took place by clicking the drop-down of available accounts.
    
    
    
2. Then, navigate to the _Orders_ Component. You will find the “Orders” tab with the relevant information. Click the square on the right-hand side if you want to expand the area. Please note: it’s important that you provide **Order IDs** and _not_ **Trade IDs**.
    
    
    
3. Take a screenshot of the affected orders by using the PrtSc key (On a Mac, press Shift-Command-5). If you can’t provide a screenshot, please list Order IDs from the Orders tab.
    



If your order is no longer listed under the Orders tab (this may happen if the issue occurred more than a few days ago), you can [export your orders](https://intercom.help/topstep-llc/en/articles/9424086-exporting-trades-on-topstepx) to a CSV and locate them that way. To do this, click the **Export** button on the bottom right side of the module, and select the day the order was placed. Download the CSV to your computer and locate the order(s) in question from column A. **Please note: it’s important to share the specific Order ID and not the entire CSV file.**



If your account is closed, you can click the Show Closed Accounts option on your Topstep Dashboard under the Accounts tab to retrieve Order IDs.

# Risk Adjustments: High Risk/High Volatility

Learn why Topstep may temporarily adjust position limits during periods of extreme market volatility and what that means for your trading.

Updated yesterday

## **Overview**

At Topstep, our mission is to help you become a better Trader with healthier habits. Part of that commitment includes protecting your account during periods of extreme market volatility. When certain products experience unusually high volatility, we may temporarily adjust position limits to help you stay in the game long-term.

## **Why We Adjust Position Limits**

Markets occasionally experience periods of extreme volatility characterized by:

- Expanding price limits
    
- Velocity Logic halts
    
- Historic price ranges
    
- Rapid price movement
    

During these conditions, even experienced Traders face an increased risk of significant losses. By temporarily adjusting position limits, we're creating guardrails that help protect your accounts during unpredictable market conditions. **This is about protection, not punishment.** Our goal is to help you maintain your trading career by preventing catastrophic losses during chaotic market periods.

## **How Position Limits Are Adjusted**

When a product is deemed high-risk due to volatility, we may implement one or both of the following adjustments:

- **Micro Contract Limits**
    
- **Mini Contract Restrictions**
    
    - Trading on mini-sized contracts or larger may be temporarily halted for affected products
        
    

---

### **Current Restrictions**

Restrictions below are organized by account size: 50K/100K/150K

|   |   |   |
|---|---|---|
||**Trading Combine, Express Funded Account,**<br><br>**Pro Account**|**Live Funded Account**|
|**Energies Restriction**|RBOB Gasoline (RB) = 3/6/9<br><br>Heating Oil (HO) = 3/6/9<br><br>Crude Oil (CL) = 3/6/9<br><br>Micro Crude Oil (MCL) = 30/60/90<br><br>E-Mini Crude Oil (QM) = 3/6/9|RBOB Gasoline (RB) = 3/6/9<br><br>Heating Oil (HO) = 3/6/9<br><br>Crude Oil (CL) = 3/6/9<br><br>Micro Crude Oil (MCL) = 3/6/9<br><br>E-Mini Crude Oil (QM) = 3/6/9|
|**Metals Restriction**|Gold (GC) = 3/6/9<br><br>Micro Gold (MGC) = 30/60/90<br><br>Silver (SI) = 0<br><br>Micro Silver (SIL) = 2/4/6<br><br>Copper (HG) = 0<br><br>Micro Copper (MHG) = 2/4/6<br><br>Platinum (PL) = 0|Gold (GC) = 3/6/9<br><br>Micro Gold (MGC) = 5/10/15<br><br>Silver (SI) = 0<br><br>Micro Silver (SIL) = 2/4/6<br><br>Copper (HG) = 0<br><br>Micro Copper (MHG) = 2/4/6<br><br>Platinum (PL) = 0|

**Please note:** For Express Funded Accounts, position limits for restricted products have a ceiling of the contracts listed above (CL = 3/6/9, for example). However, a trader's actual limit may be lower depending on their current account balance, as the Scaling Plan applies independently. Learn more [here](https://intercom.help/topstep-llc/en/articles/8284223-what-is-the-scaling-plan).

### Example of the Scaling Plan for restricted symbols on the 3/6/9 plan

  
​**Symbols this applies to:**

- Crude Oil (CL)
    
- E-Mini Crude Oil (QM)
    
- Micro Crude Oil (MCL)
    
- Heating Oil (HO)
    
- RBOB Gasoline (RB)
    

**Metals**

- Gold (GC)
    
- Micro Gold (MGC)
    

**150K XFA**

- $0 balance = 1 contract
    
- $1,500 balance = 2 contracts
    
- $2,000 balance = 3 contracts
    
- $3,000 balance = 6 contracts
    
- $4,500 balance = 9 contracts
    

**100K XFA**

- $0 balance = 1 contract
    
- $1,500 balance = 2 contracts
    
- $2,000 balance = 3 contracts
    
- $3,000 balance = 6 contracts
    

**50K XFA**

- $0 balance = 1 contract
    
- $1,500 balance = 1 contract
    
- $2,000 balance = 3 contracts
    

---

## **When Do These Restrictions Apply?**

Position limit adjustments are:

- **Temporary**: Restrictions remain in place only while volatility levels are elevated
    
- **Product-specific**: Only products experiencing extreme volatility are affected
    
- **Actively monitored**: Our Risk Team continuously evaluates market conditions to determine when normal limits can be reinstated
    

## **What You Can Still Do**

- **Continue trading** with adjusted position sizes in affected products
    
- **Trade other products** with standard position limits
    
- **Focus on risk management** and strategic opportunities
    
- **Use this time** to refine your trading plan and review your strategy
    

## **Understanding Market Volatility**

Historic volatility means historic losses can happen faster than normal. When markets move unpredictably:

- Slippage increases
    
- Risk management becomes more challenging
    
- Even well-planned trades can move against you quickly
    

These temporary adjustments give you the opportunity to participate in volatile markets while managing your risk appropriately.

## **How You'll Be Notified**

When position limits are adjusted, you'll receive notification through:

- Email communication
    
- Dashboard banners
    
- Social media updates (@AskTopstep on X)
    

We'll also notify you when restrictions are lifted and normal position limits are reinstated.

## **Have Questions?**

Our Trader Support Team is here to help. If you have questions about current position limits or how these adjustments affect your trading, please [contact support](https://www.topstep.com/contact-support/).


# Quantower Connection Instructions

September 18, 2025

Quantower is now supported on the [New Topstep Dashboard](https://help.topstep.com/en/articles/10513413-new-topstep-dashboard) and connects using your TopstepX credentials. While Quantower doesn’t appear as a platform option in the Dashboard, you can still connect by selecting TopstepX as your platform. This connects your account to [ProjectX](https://www.projectx.com/) data, which powers the Quantower connection.

Using TopstepX with Quantower gives you access to 10:1 Micro to Mini contract conversions and a direct data feed from the CME for faster, cleaner market data. Quantower via TopstepX is currently available for the Trading Combine and Express Funded Account only.

- [Installation and Connection Instructions (Quantower/TopstepX)](https://help.topstep.com/en/articles/8284179-quantower-connection-instructions#h_9a021e4ded)
    
- [Getting Started Tips](https://help.topstep.com/en/articles/8284179-quantower-connection-instructions#getting-started)
    
- [What is Included in Quantower?](https://help.topstep.com/en/articles/8284179-quantower-connection-instructions#h_3ec8a32a4b)
    
- [Quantower Platform Support](https://help.topstep.com/en/articles/8284179-quantower-connection-instructions#platform-support)
    

## Installation and Connection Instructions (Quantower/TopstepX)

**Important Tips Before Getting Started**

- If you haven’t signed into the TopstepX Dashboard before launching Quantower, you may see a “Login Blocked” error. Be sure to first log into TopstepX first and sign any required platform and data agreements. After that, you’ll be able to connect to Quantower.
    

- You don’t need API access to ProjectX to connect TopstepX with Quantower. Simply log in using your TopstepX credentials to establish the connection.
    

- During installation, you may receive a pop-up to install .Net Framework. Please allow access to this installation in order for your platform to install properly. .Net Framework installations should be available in your Windows Updates or by conducting a web search for the specific .Net Framework the platform is requesting to be installed. If your computer is up to date, your platform should install without this pop-up message.
    

### If you're downloading Quantower for the first time:

1. After downloading Quantower, click “Extract” when the prompt appears. The platform will launch automatically with DX Feed selected by default – leave that as-is.
    
    
    
2. Click the “Connections” button at the top of the platform
    
    
    
    
    
3. Disconnect from DX Feed
    
4. Select “ProjectX” from the list of available connections
    
5. In the Server dropdown, choose “TopstepX”
    
6. Enter your TopstepX credentials to log in
    



### If you already have Quantower installed:

1. Open Quantower and click the “Connections” button
    
    
    
    
    
2. Disconnect from any active connection (such as DX Feed)
    
    
    
3. Select “ProjectX” from the list of available connections
    
4. In the Server dropdown, choose “TopstepX”
    
5. Enter your TopstepX credentials to log in
    



## Getting Started Tips

- How to place orders on the platform using Trading Panels. [Click here to view](https://help.quantower.com/quantower/trading-panels).
    
- How to monitor and flatten positions using Portfolio Panels. [Click here to view.](https://help.quantower.com/quantower/portfolio-panels)
    
- Frequently Asked Questions: General Errors. [Click here to view.](https://help.quantower.com/quantower/faq/general-errors)
    
- How to view order flow on the [DOM Surface Heatmap](https://www.quantower.com/dom-surface).
    
    - In order to make adjustments, click on Quick Settings and change the number under DOM levels count.
        
    - Order Entry and Imbalance / Sizes can be found in the top right corner of the DOM Surface module.
        
    - Depth of Market / Level 2 data is required to see DOM Levels.
        
    



## What is included in Quantower?

**Topstep accounts will be provided with the Premium Feature Bundle for free:**

- DOM Surface
    
- TPO Chart
    
- Volume Analysis Tools
    
- Charting (Maximum 2 indicators per chart)
    

_**Level 2 Data is needed to have full access to premium features._

**Topstep accounts do not provide the following:**

- Market Replay
    
- Strategy Manager
    
- Strategy Runner
    
- Trading Simulator
    

_**Additional features not listed may require a paid platform license. Additional platform features can be purchased [here](https://www.quantower.com/pricing)._

## Quantower Platform Support

[Quantower support can be contacted here](https://www.quantower.com/contact-us) through an online form. Additional information can be found through the [online guide.](https://help.quantower.com/quantower/)
