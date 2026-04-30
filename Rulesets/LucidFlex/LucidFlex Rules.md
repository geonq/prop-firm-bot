# LucidFlex — Encoding Reference

> **Last updated:** 2026-04-30
> **Sources:** Original LucidFlex help-center paste (rule structure) + 2026-04-30 official Lucid help-center verification for evaluation/funded parameters, payouts, drawdown, scaling, approved products, permitted activities, and allowed trading times.
> **Status for Phase 1 encoding:** core rule mechanics are substantially complete for 50K encoding. Reviewer must still confirm dashboard-only commercial fields tagged `[VERIFY]`.

---

## Pricing

### Eval purchase price `[VERIFY]`

| Account | Eval Price |
|---------|-----------|
| 25K | $75 |
| 50K | **$175** |
| 100K | $345 |
| 150K | $345 |

> 100K and 150K both at $345 is suspicious — possible source typo. Reviewer to confirm against Lucid dashboard.

### Reset cost `[VERIFY]`

Approximately 30–40% of original eval price (third-party source).

| Account | Estimated Reset |
|---------|-----------------|
| 25K | ~$26 |
| 50K | **~$61** |
| 100K | ~$121 |
| 150K | ~$121 |

Actual price shown in Lucid dashboard at purchase time is authoritative.

### Activation fee

**None.** No fee to upgrade from LucidFlex Evaluation to LucidFlex Funded. Eval price + optional resets is the entire upfront cost path to a funded account.

---

## Approved Products

Official Lucid help-center source. NQ/MNQ are Phase 1 priority.

### Equity Index Futures

| Code | Name | Commission/side |
|------|------|-----------------|
| ES | E-mini S&P 500 | $1.75 |
| NQ | E-mini Nasdaq-100 | $1.75 |
| RTY | E-mini Russell 2000 | $1.75 |
| YM | E-mini Dow Jones | $1.75 |
| MES | Micro S&P 500 | $0.50 |
| MNQ | Micro Nasdaq-100 | $0.50 |
| M2K | Micro Russell 2000 | $0.50 |
| MYM | Micro Dow Jones | $0.50 |
| NKD | Nikkei 225/USD | $1.75 |

### Forex (all $2.40/side)
6A, 6B, 6C, 6E, 6J, 6S, 6N. **Micro forex contracts NOT permitted** at Lucid (despite CME availability).

### Energy
CL ($2.00), MCL ($0.50), QM ($2.00), NG ($2.00), QG ($1.30)

### Metals
GC ($2.30), MGC ($0.80), SI ($2.30), SIL ($1.60), PL ($2.30), HG ($2.30). **Palladium (PD) NOT in the approved list.**

### Agricultural (all $2.80/side)
ZS, ZC, ZW, ZL, ZM, LE, HE

### Explicitly excluded
Not present in the official approved-products list: Treasury futures (ZN, ZB, ZF, ZT, TN, UB), Bitcoin (BTC, MBT), VIX, soft commodities (cotton/cocoa/coffee/sugar), Palladium (PD), micro forex contracts.

### Project relevance
ES, NQ, MES, MNQ all permitted — Phase 4 Pine Script strategies on NQ have no product conflict.

---

## Tick values (CME standard, firm-agnostic)

| Contract | Tick size | Tick value | Point value |
|----------|-----------|------------|-------------|
| NQ | 0.25 | $5.00 | $20 |
| MNQ | 0.25 | $0.50 | $2 |
| ES | 0.25 | $12.50 | $50 |
| MES | 0.25 | $1.25 | $5 |

NQ + MNQ are Phase 1 priority.

---

## Open question — "velocity logic"

The News Trading section of the original paste mentions "velocity logic triggers" without defining the mechanism. Could affect slippage modeling in Phase 3. Reviewer to dig up Lucid's definition during Phase 1.

---

## Verification checklist for Phase 1 Reviewer pass

- [ ] Eval prices (50K = $175 specifically; check 100K/150K both at $345)
- [ ] Reset cost for 50K (~$61) — pull exact from Lucid dashboard
- [ ] "Velocity logic" definition

---

# 📄 Below: Original LucidFlex help-center paste (rule structure — verbatim)


# Simulated Account Fees

## One-Time Fee

LucidPro Evaluation and LucidDirect accounts are purchased by paying a one-time fee. There is no subscription and no automatic rebilling. Since there is no monthly billing cycle, you will need to purchase a reset if you wish to restart your evaluation account. Resets are not automatic or free.

## No Activation Fees

There is no activation fee to upgrade a LucidPro Evaluation to a LucidPro Funded.

## Account Resets

If a trader fails an evaluation account, they may purchase a reset from the trader dashboard. A reset returns the account to its original starting conditions, including balance and risk parameters.
# Payout Methods

## Payout Providers

Lucid Trading currently supports the following payout methods for approved withdrawals:

### **Plaid**

- Instant bank transfers for U.S.-based traders
    
- To connect your bank account to Plaid for instant transfers:
    
- Go to your **dashboard** > **Payouts** > **Add Bank Account**
    

### **WorkMarket by ADP**

- Available for both U.S. and international traders
    
- Can withdraw via bank transfer or Paypal
    
- Funds can typically be received as early as the next business day
    

### **Crypto**

- Available for International Traders
    
    - Crypto Currency Payout Options
        
        - BTC
            
        - ETH
            
        - LTC
            
        - USDT
            
        - USDC

# LucidFlex Evaluation Account
## LucidFlex Evaluation Account Overview

The LucidFlex evaluation is a simulated account with a profit target that must be hit before traders are eligible to upgrade to a [LucidFlex funded account](https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account). See account sizes and details below.

|   |   |   |   |   |
|---|---|---|---|---|
|**Account Size**|**Profit Target**|**Max Loss Limit**|**Consistency %**|**Max Size**|
|[$25,000](https://lucidtrading.com/#plans)|$1,250|$1,000|50%|2 mini or 20 micros|
|[$50,000](https://lucidtrading.com/#plans)|$3,000|$2,000|50%|4 mini or 40 micros|
|[$100,000](https://lucidtrading.com/#plans)|$6,000|$3,000|50%|6 mini or 60 micros|
|[$150,000](https://lucidtrading.com/#plans)|$9,000|$4,500|50%|10 mini or 100 micros|

## LucidFlex Evaluation Account Benefits

- One-time fee, no monthly rebilling, take as long as you need to pass
    
- Real-time activation, upgrade to funded account within 5-30 minutes of hitting profit target
    
- No activation fees to upgrade to funded account
    
- There is no DLL on LucidFlex evaluation accounts
    
- The LucidFlex evaluation 50% consistency has cushion built in, so you can pass in two days

# LucidFlex Funded Account
## LucidFlex Funded Account Overview

See futures account sizes and details below:

|   |   |   |   |   |
|---|---|---|---|---|
|**Account Size**|**Max Loss Limit**|**DLL**|**Scaling Plan**|**Max Size**|
|[$25,000](https://lucidtrading.com/#plans)|$1,000|None|Yes|2 mini or 20 micros|
|[$50,000](https://lucidtrading.com/#plans)|$2,000|None|Yes|4 mini or 40 micros|
|[$100,000](https://lucidtrading.com/#plans)|$3,000|None|Yes|6 mini or 60 micros|
|[$150,000](https://lucidtrading.com/#plans)|$4,500|None|Yes|10 mini or 100 micros|

## LucidFlex Funded Account Benefits

- Objectives on our dashboard update in real-time within 5-30 minutes of your last closed trade
    
- There is no DLL on LucidFlex funded accounts
    
- There is no Consistency Percentage on LucidFlex funded accounts

# LucidFlex Payouts
## General Requirements

To be eligible for a payout from a LucidFlex account:

- You must not violate any Trading Rules, Terms & Conditions, or the LucidFlex Account Agreement.
    
- Payout requests are final once submitted, they cannot be edited or canceled.
    

## Profit Split Structure

- All [LucidFlex funded account](https://lucidtrading.com/#plans) payouts are split 90% to the trader and 10% to Lucid Trading.
    

## Payout Eligibility Criteria

There are two requirements must be met in LucidFlex to qualify for a payout.

## 1. Trading Days with Profit

Traders must earn at least the minimum required profit on 5 separate days during the payout cycle. The minimum profit on trading days reset and must be earned again after every approved payout.

|   |   |
|---|---|
|Account Size|Minimum Daily Profit|
|[$25,000](https://lucidtrading.com/#plans)|$100|
|[$50,000](https://lucidtrading.com/#plans)|$150|
|[$100,000](https://lucidtrading.com/#plans)|$200|
|[$150,000](https://lucidtrading.com/#plans)|$250|

## 2. Net Profit in Payout Cycle

Traders must have positive net profit (even just $1) during each payout cycle in order to request a payout. This objective simply ensures traders have made at least some amount of money between requests. As long as you meet the Trading Days with Profit requirement and have positive net profit for the payout cycle, you are eligible for payout.

## Payout Minimums and Maximums

- Minimum payout request: $500
    
- Maximum payout request: Futures traders may request 50% of their account balance up to a maximum dollar amount. The max dollar amount depends on account size and is laid out below:
    
- Number of requests per account: Traders may take up to 5 payouts from each LucidFlex account after which they will be moved live.
    

|   |   |
|---|---|
|Account Size|**Payout Maximum**|
|[$25,000](https://lucidtrading.com/#plans)|50% of Profit  <br>up to $1,000|
|[$50,000](https://lucidtrading.com/#plans)|50% of Profit  <br>up to $2,000|
|[$100,000](https://lucidtrading.com/#plans)|50% of Profit  <br>up to $2,500|
|[$150,000](https://lucidtrading.com/#plans)|50% of Profit  <br>up to $3,000|

There is no buffer balance that must be maintained in [LucidFlex funded accounts](https://lucidtrading.com/#plans).

Unlike our other prop firm funded accounts, the maximums here do not scale up with more payouts. The table above shows the payout maximums for all requests.

Important: If you take a trade before your payout is processed that drops your balance below the required amount, your request may be denied.

## Payout Timing and Processing

- There is no fixed payout window, you may request a payout any day after meeting all eligibility criteria.
    
- Once approved:
    
    - Funds will be deducted from your account within a few minutes.
        
    - Payouts will be disbursed to your payment method within 2 business days.
        
    

# LucidFlex Consistency Percentage
## Consistency

The Consistency Percentage tracks a traders ability to earn profits over multiple sessions. This demonstrates a that a trader has and can adhere to a risk management strategy.

## The Calculation

In LucidFlex evaluation accounts you must have Consistency Percentage of 50% or less to be eligible to upgrade to a LucidFlex funded account.

Use the following formula to determine if you are adhering to the Consistency Percentage:

**Largest Single Day Profit / Account Profit = Consistency Percentage**

## Example

You trade your $50k LucidFlex evaluation account and your Largest Single Day Profit was $750 when you reached the $3,000 profit target. Plug the values into the above formula.

**$750 / $3,000 = 25%**

Congratulations, you have maintained consistency under the LucidFlex evaluation 50% requirement. You may now upgrade to a LucidFlex funded account. However, if your largest day had exceeded 50% of your account profit, you would need to continue trading until your largest day is 50% or less.

## Consistency Cushion

There is a small cushion built into the LucidFlex consistency so that traders that are super eager to pass in two days can do so. However, taking your time to reach your profit target is the best approach.  
​  
Please see below for an example of how the cushion works.

|   |   |   |   |
|---|---|---|---|
|Account Size|Profit Target|50% Consistency|Cushion|
|25k Flex|$1,250|$625|$650.00|
|50k Flex|$3,000|$1,500|$1,560.00|
|100k Flex|$6,000|$3,000|$3,120.00|
|150k Flex|$9,000|$4,500|$4,680.00|

**Important:** This is merely an example table based on hitting exactly 50% of your profit target. The cushion is a percentage calculated on what your actual profit earned is for the day and will vary from trader to trader.

It is NOT a fixed dollar amount for all scenarios. The actual dollar amount is dependent on how much profit you earned on your biggest day.

# LucidFlex Scaling Plan
## LucidFlex Funded Account Scaling Plan

The scaling plan controls how much of your max size is available to trade based on the simulated profits in your account. As your simulated profits in the funded account increase and decrease, your max tradable contract size moves up and down based. There is no scaling plan in the evaluation phase.  
​  
The scaling plan updates at the end of each session, so your limits will not update in real-time throughout the day. Please see the table below for details:

|   |   |   |   |   |
|---|---|---|---|---|
|**Simulated Profits**|**$25,000**  <br>​**Contract Limits**|**$50,000**  <br>​**Contract Limits**|**$100,000**  <br>​**Contract Limits**|**$150,000**  <br>​**Contract Limits**|
|$0 - $999|1 mini or  <br>10 micros|2 minis or  <br>20 micros|3 minis or  <br>30 micros|4 minis or  <br>40 micros|
|$1,000 - $1,999|2 minis or  <br>20 micros|3 minis or  <br>30 micros|4 minis or  <br>40 micros|5 minis or  <br>50 micros|
|$2,000 - $2,999|-|4 minis or  <br>40 micros|5 minis or  <br>50 micros|6 minis or  <br>60 micros|
|$3,000 - $4,499|-|-|6 minis or  <br>60 micros|8 minis or  <br>80 micros|
|$4,500+|-|-|-|10 minis or  <br>100 micros|

## Circumventing the Scaling Plan

Some trader may be inclined to try and get around the scaling plan. Our back-end systems track and adjust balances for this. If we see repeated behavior attempting to get around the limits, we may review your account.

# LucidFlex Drawdown
## End of Day Drawdown

LucidFlex evaluation and funded accounts use an End-of-Day Drawdown (EOD Drawdown) system to calculate the Max Loss Limit (MLL).

- At the end of each trading session, the system calculates the account’s highest closing balance
    
- The MLL increases as your balance grows, up to a defined point
    
- Once your account exceeds the Initial Trail Balance, the MLL locks and no longer moves
    
- Once you request a payout from LucidFlex, your MLL automatically adjusts to the Locked MLL Balance
    

|   |   |   |   |
|---|---|---|---|
|**Account Size**|**MLL Amount**|**Initial Trail Balance**|**Locked MLL Balance**|
|$25,000|$1,000|$26,100|$25,100|
|$50,000|$2,000|$52,100|$50,100|
|$100,000|$3,000|$103,100|$100,100|
|$150,000|$4,500|$154,600|$150,100|

As with the other account types:

- The MLL rises with your closing balance until it reaches the trail
    
- Once the account exceeds the trail, the MLL locks at the initial balance plus $100
    
- If your account balance reached the MLL, your account will be breached.
# LucidFlex Live (Legacy)
## This is for accounts purchased/reset on 2/27/26 and prior.  
  
Getting Moved to Live

Traders are transitioned from LucidFlex funded accounts to live trading under one of the following conditions:

- After completing their sixth and final LucidFlex payout
    
- At the discretion of the Lucid risk team, before the sixth payout
    

## Transition to Live

When a trader is moved live from LucidFlex:

- Traders may have up to five live accounts
    
- Simulated profits from each LucidFlex account are used to calculate the live funding amount
    
- Each account size has a move-to-live cap, which limits how much simulated profit can be transferred
    

|   |   |
|---|---|
|Account Size|**Max Moved Live**  <br>​**(Per Account)**|
|$25,000|$4,000|
|$50,000|$8,000|
|$100,000|$12,000|
|$150,000|$16,000|

Any profits above the move-to-live cap will be forfeited during the transition to live.

## **Day-One Capital Allocation:**

- A portion of the move-to-live cap is deposited into the live account on Day 1
    
- The remaining capital is held in Escrow, which can be earned back by meeting performance benchmarks
    

|   |   |
|---|---|
|Account Size|**Max Deposited Day 1**  <br>(**Per Account)**|
|$25,000|$1,200|
|$50,000|$2,400|
|$100,000|$3,600|
|$150,000|$4,800|

**Example:**  
A trader moves five $50,000 LucidFlex accounts live with $10,000 in simulated profit per account.

- Max allowed per account = $8,000 → excess $2,000 is forfeited
    
- Total live capital: $40,000 ($8,000 × 5)
    
- Day 1 capital = $12,000 ($2,400 × 5)
    
- Remaining $28,000 is held in Escrow and may be unlocked
    

## Live Escrow

Escrow is the portion of your move-to-live capital not deposited on Day 1. It is released based on live performance.

**Escrow Release Criteria**

Before Escrow can begin releasing, you must meet two requirements:

- Complete 10 profitable trading days in your live account
    
- Earn $10,000 in live trading profits
    

Once both of these conditions are met, our risk team will review your performance.

**Escrow Release Structure**

- For every $10,000 in additional live profits earned, $5,000 in Escrow will be released
    
- Escrow is reviewed and calculated weekly, not daily
    
- This process continues until the full Escrow allocation has been released
    

**Important:** Traders who engage in reckless or high-risk behavior ("yolo" trading) will not be eligible for Escrow release.

## Accessing Escrow

|   |   |
|---|---|
|**Requirement**|**Rule**|
|Minimum Time to Withdraw|Must wait 60 days from account opening|
|Withdrawable Funds|Only released Escrow amounts may be withdrawn|
|Margin Use|Released funds may be used to meet margin requirements|
|Risk Monitoring|Significant drawdowns after release may trigger a risk review|

Escrow rewards are designed to incentivize consistent performance and reward discipline in the live environment. Our risk team monitors behavior to ensure traders are acting responsibly as they trade live capital.  
​
Legacy Flex Transition to Live

The below structure applies to traders currently mid onboarding and those that get move to live email on 1/31 or earlier. These traders may choose between the below legacy structure or the and above new structure.

- The simulated profits from your LucidFlex account are used to calculate your starting LucidLive balance.
    
- There is a $5,000 move to live cap for each LucidFlex account, regardless of account size.
    
- Any excess profits left over will be forfeit upon the move to live.
# New Live Structure
## Being Evaluated for Live

Lucid’s risk team continuously monitors trader performance to determine when a trader is ready to transition to live trading.  
​

Traders enter the live review pool when one or more of the following conditions are met:

- After receiving the final payout (Payout 5) on their plan
    
- After being paid out a significant amount of capital lifetime
    
- If they have exceptional performance in sim funded
    
- If they have previously been moved live
    

Payout 5 represents the maximum payout level, not a guaranteed minimum for live eligibility. All live transitions occur at the discretion of the Lucid risk team.

## Transition to Live

When a trader is moved live:

- Traders receive one live account per eligible funded account
    
- Each funded account must have received at least one payout to qualify
    

All live accounts begin with:

- $0 starting balance
    
- Daily payouts
    
- End-of-day drawdown
    
- No daily loss limit
    

|   |   |   |
|---|---|---|
|**Funded Account Size**|**Starting Live Drawdown**|**Max Live Contract Limit***|
|$25,000|$1,000|2 minis or 20 micros|
|$50,000|$2,000|4 minis or 40 micros|
|$100,000|$3,000|6 minis or 60 micros|
|$150,000|$4,500|10 minis or 100 micros|

*Certain extremely volatile contracts have reduced position sizing to ensure traders do not exceed the live drawdown.

## Locking the Live MLL

If a trader requests a live payout before getting over the live drawdown, the Max Loss Limit locks to $100.

## Live Bonus

The first time a trader is moved live under the new program, they may be eligible to earn a one-time bonus.

To earn the Live Bonus:

- Generate live profits equal to your starting live drawdown
    

When achieved:

- The Live Bonus is paid out
    

|   |   |   |
|---|---|---|
|**Funded Account Size**|**Live Target**|**Live Bonus**|
|$25,000|$1,100|$1,000|
|$50,000|$2,100|$2,000|
|$100,000|$3,100|$3,000|
|$150,000|$4,600|$4,500|

## Example

A trader is moved live with five $50,000 funded accounts:

- Each account starts with $0 balance and $2,000 drawdown
    
- The trader earns $2,100 in each account
    
- Lucid releases a $2,000 Live Bonus as a payout to the trader
    
- Trader received a $10,000 bonus payout
    

The bonus may be earned on all accounts moved live on the first trip under the new system. However, traders moved live 2 or more times will not be eligible for the bonus on subsequent sets of accounts. The bonus is not eligible for traders with LucidMaxx status.

## Cooldown

Traders who have been moved live may return to purchase a new evaluation after blowing a live account..

- Standard cooldown period: 2 weeks
    
- Traders who repeatedly blow live accounts due to reckless or “yolo” behavior may be subject to longer cooldowns at the discretion of the risk team
    

## LucidMaxx Status

Select traders may eventually earn LucidMaxx status.

LucidMaxx traders:

- May purchase the LucidMaxx evaluation
    
- Receive access to daily, uncapped payouts and instant live capital
    

Please refer to the LucidMaxx documentation for full details.

## Q&A

**Do all funded accounts move live at once?**  
Yes. All eligible funded accounts (with at least one payout) are moved when a trader transitions to live.

**What happens to remaining simulated accounts?**  
All simulated accounts are closed when a trader is moved live. If a funded account is not moved live because it has 0 payouts, the evaluation cost of that account will be refunded. If you are not comfortable with evaluations being closed, do not keep evaluations in reserve.

**If I am live, can someone in my household still trade sim?**  
No. If one household member is trading live, others may not trade simulated accounts.

**Can I hedge my live accounts?**  
Absolutely not. Hedging live accounts is strictly prohibited by both Lucid and the CME. Violations will result in a permanent ban.

# Trade with Integrity
## Our Philosophy

At Lucid Trading, integrity is the cornerstone of every trader’s journey. We believe that ethical trading practices are essential for building long-term success, both for the individual trader and for the firm as a whole. Our rules are intentionally designed to support traders who approach the markets with discipline, transparency, and professionalism.

Our focus is not on short-term wins, but on helping traders build sustainable, career-oriented success in the futures markets.

## A Partnership Based on Trust

Lucid Trading operates on a foundation of mutual benefit:

- We provide traders with access to capital, technology, and support
    
- Traders bring their strategies, discipline, and risk management to the platform
    

This balance only works when both sides act in good faith. Our expectation is that all traders operate with the same level of honesty and clarity that we bring to the relationship. Traders are rewarded not for exploiting technicalities, but for demonstrating real competence and consistency.

## What We Prohibit

To preserve a fair and competitive trading environment, Lucid Trading strictly prohibits the use of strategies that exploit platform mechanics or simulated market conditions.

The following are examples of prohibited behavior:

- Taking advantage of system errors or update delays
    
- Exploiting discrepancies in simulated prices
    
- Using tactics that do not reflect real-world trading conditions
    

These behaviors violate the spirit of the program and undermine the integrity of the trading ecosystem we are building. Our rules are clear: all traders are expected to uphold the same standards that define professional and sustainable trading.

## Commitment to Ethical Growth

By maintaining these ethical standards, we ensure that Lucid Trading remains a place where:

- Traders are evaluated on skill and discipline
    
- The platform evolves in alignment with professional industry standards
    
- Long-term partnerships are built on trust and performance
    

We’re here to fund real traders not opportunists. And we’re committed to creating a space where real traders can succeed.

# Restricted Countries

If you are a citizen or resident of any of the countries listed below, you are not eligible to use Lucid Trading services:  
​

Afghanistan  
Albania  
Algeria  
Angola  
Bahamas  
Barbados  
Belarus  
Bosnia & Herzegovina  
Bulgaria  
Burkina Faso  
Burma/Myanmar  
Botswana  
Burundi  
Cambodia  
Central African Republic Côte d’Ivoire  
Crimea  
Cuba  
Congo Republic (Brazzaville)  
Congo (Kinshasa)  
Donetsk  
Ecuador  
Ethiopia  
Ghana  
Guinea  
Haiti  
Iceland  
Indonesia  
Iran  
Iraq  
Jamaica  
Kenya  
Kherson  
Kosovo  
Laos  
Lebanon  
Liberia  
Libya  
Lithuania  
Luhansk  
Mali  
Mauritius  
Mongolia  
Montenegro  
Morocco  
Mozambique  
Namibia  
Nicaragua  
Nigeria  
North Korea  
North Macedonia  
Pakistan  
Panama  
Papua  
New Guinea  
Philippines  
Russia  
Senegal  
Serbia  
Sevastopol  
Slovenia  
Somalia  
South Africa  
South Sudan  
Sri Lanka  
Sudan  
Syria  
Tanzania  
Turkey  
Trinidad and Tobago  
Tunisia  
Uganda  
Ukraine  
Vietnam  
Venezuela  
Yemen  
Zimbabwe

# Inactivity Policy
## Active Status Policy

You are not required to trade daily or weekly, but accounts must remain active to avoid being flagged. We must remove dormant accounts to ensure system performance and data integrity.

  
Accounts that have not been traded in 30 calendar days will be deemed abandoned and will be permanently deleted from our systems.

## Breached Status Policy

If an evaluation is breached (has hit Max Loss Limit), it is still eligible for a reset. However, breached accounts are cleared on a schedule to keep the platform streamlined. Accounts are marked breached when the Max Loss Limit is exceeded. Traders can confirm the breached status using the dashboard, which provides details on which limits or rules were violated.

- All breached accounts will be automatically deleted after 30 days if not reset.
    
- Traders can manually purchase a reset at any time before that 30-day period expires.
    
    - Traders can also manually remove breached accounts through the dashboard at any time prior to automatic deletion.
    

# Steps for Manual Account Removal

1. **Access your dashboard:** Log in to your Lucid Trading account and navigate to the dashboard.
    
2. **Locate the "Remove Account" option:** The option is under the account management section. Refresh the page if it does not appear.
    
3. **Acknowledge the deletion warning:** Confirm the irreversible action by checking the required acknowledgment box.
    
4. **Finalize the removal:** Follow the prompts to complete the account deletion process. Ensure this step aligns with your trading strategy. The manual process ensures a trader-controlled approach to managing breached accounts.
# Prohibited: Microscalping

## What Is It?

Microscalping refers to a trading tactic where a trader attempts to capture very small price movements using very large size within extremely short time frames, often just a few seconds. The goal is typically to exploit how simulated fills work rather than to execute a sustainable trading strategy.

This is not the same as genuine scalping, which involves short-term trades without attempting to manipulate platform behavior. Genuine scalping is permitted as long as it reflects realistic market activity and order execution.

## What Happens If I Microscalp?

Lucid Trading uses automated systems to detect Microscalping patterns. You will be flagged if:

- **More than 50% of your profits are generated from trades held for 5 seconds or less**
    

Enforcement Process:

1. If your account is flagged, Lucid will initiate a manual review to verify whether the behavior violates company policies
    
2. If bad faith activity is confirmed, you may receive a written warning
    
3. If flagged behavior continues after a warning:
    
    - All profits from microscalping activity will be forfeited
        
    - You may be permanently restricted from using Lucid Trading services
        
    

Traders may request an appeal if they believe the flagged activity was incorrectly identified.

## Why Is It Prohibited?

Microscalping is not a valid or transferable strategy in the live market. Lucid Trading is committed to helping traders develop realistic, long-term strategies that are viable in professional trading environments.

Allowing Microscalping:

- Undermines the integrity of the evaluation process
    
- Makes it difficult to identify genuinely profitable traders
    
- Threatens the sustainability of the firm
    

Lucid Trading’s mission is to support traders building durable careers, not to facilitate system gaming.

# Prohibited: Hedging
## What Is It?

Hedging refers to the use of multiple accounts to take opposing positions on the same trade. This tactic artificially reduces risk by ensuring one account profits regardless of the market’s direction. It is a form of system manipulation, not genuine trading.

Example:  
A trader goes long on one NQ in one account and short NQ on another. No matter which way the market moves, one account gains while the other loses, manipulating the program structure to secure profits unfairly.

## Prohibited Forms of Hedging

Lucid Trading strictly prohibits all forms of hedging, including but not limited to:

- Hedging across multiple accounts held by the same user
    
- Hedging between different users' accounts
    
- Hedging between different firms or funded platforms
    
- Any other form of hedging designed to bypass risk management rules
    

## What Happens If I Hedge?

Lucid Trading has automated risk systems in place to detect hedging behavior. If your account is flagged:

1. You will receive an email notice & the associated accounts will be reset to prior days balance.
    
2. After repeated offenses all involved accounts will be breached and you may be permanently restricted from using Lucid Trading services.
    

## Why Is It Prohibited?

Lucid Trading is committed to funding skilled, consistent traders, not those exploiting structural loopholes. Hedging:

- Misrepresents a trader’s actual risk and skill
    
- Undermines the evaluation process
    
- Threatens the long-term sustainability of the firm
    

Allowing hedging would make it impossible to identify and reward legitimate trading performance.

## Common Questions

**Can I go long X contract and short X contract?**

- No, you cannot go long / short the same contract in the same or separate accounts. This is strictly prohibited.
    

**Can I go long X contract Mini and short X contract Micros?**

- You can go long / short the same contract but one is micros and one is minis in the same account.
    
- However, you cannot go long / short the same contract but one is minis or micros in separate accounts. This is strictly prohibited.
    

**Can I go long X contract and short Y contract?**

- You can go long / short different contracts in the same account.
    
- However, you cannot go long / short different contracts in separate accounts with correlated assets. This is strictly prohibited.
    
    - Example: You cannot go long ES in one account and short NQ in a separate account.
        
    - Correlated assets go for groupings in equities, metals, energies, etc.

# Prohibited: High Frequency Trading
## What Is It?

High-frequency trading (HFT) is a type of automated trading strategy that involves submitting and executing a high volume of trades within extremely short time frames, often measured in seconds or even milliseconds. These strategies are typically powered by algorithms and designed to exploit minute price inefficiencies at speed.

## What Happens If I Use HFT?

Lucid Trading employs automated risk detection systems to flag HFT activity. If your account is identified as using high-frequency trading methods:

1. First offense:
    
    - You will receive a written warning
        
    
2. Repeated offenses:
    
    - All profits generated from HFT activity will be removed
        
    - Accounts will be closed
        
    - You will be permanently restricted from using Lucid Trading services
        
    

You may file an appeal if you believe the activity was incorrectly flagged.

## Why Is It Prohibited?

HFT strategies can result in hundreds of orders being placed within minutes, generating an unusually high load on platform infrastructure.

Allowing HFT could:

- Degrade platform performance
    
- Create data instability
    
- Negatively impact the user experience for all traders
    

To maintain a reliable and equitable trading environment, HFT is strictly prohibited.

# Permitted Activities
## News Trading

- Allowed without restriction
    
- Traders may enter or exit positions around scheduled or unscheduled news events
    
- Important: News-driven markets are highly volatile and may involve slippage or velocity logic triggers- Sudden price movements during news events may result in slippage, influencing trade execution at unexpected prices or triggering unique order behaviors due to velocity logic mechanisms.
    
- Traders assume full responsibility for all outcomes when trading during news events- This responsibility emphasizes the necessity for careful planning and risk assessment, particularly during volatile conditions.
    

## Scaling Into Trades (DCA)

- Traders are free to scale into positions or use Dollar Cost Averaging (DCA)
    
- Lucid does not impose limits on entry methods- Scaling can serve as an effective risk management measure, allowing traders to adapt positions incrementally to varying market conditions.
    
    Note of caution:
    
- While scaling is permitted, martingaling, continuously adding to losing positions in hopes of recovery, is strongly discouraged
    
- Martingaling can quickly escalate risk and is not considered a sustainable long-term strategy
    

## Genuine Scalping

- Genuine scalping is allowed
    
- Short-term entries and exits that reflect realistic execution and market behavior are welcome
    
- Traders must ensure that their activity remains within Microscalping policy guidelines
    
- Scalping is considered valid as long as trades are taken in good faith and not intended to manipulate fill logic
    

## Automated Strategies

- Automated trading systems and trade copiers are permitted
    
- All automated activity must comply with Lucid Trading rules
    
- Traders are fully responsible for any software errors, malfunctions, or unintended outcomes
    

## Flipping

- Flipping is allowed
    
- Flipping refers to taking a quick in-and-out trade for the purpose of meeting minimum trading day requirements
    
- While we encourage meaningful trading activity, we do not restrict this practice
# Permitted Activities

## News Trading

- Allowed without restriction
    
- Traders may enter or exit positions around scheduled or unscheduled news events
    
- Important: News-driven markets are highly volatile and may involve slippage or velocity logic triggers- Sudden price movements during news events may result in slippage, influencing trade execution at unexpected prices or triggering unique order behaviors due to velocity logic mechanisms.
    
- Traders assume full responsibility for all outcomes when trading during news events- This responsibility emphasizes the necessity for careful planning and risk assessment, particularly during volatile conditions.
    

## Scaling Into Trades (DCA)

- Traders are free to scale into positions or use Dollar Cost Averaging (DCA)
    
- Lucid does not impose limits on entry methods- Scaling can serve as an effective risk management measure, allowing traders to adapt positions incrementally to varying market conditions.
    
    Note of caution:
    
- While scaling is permitted, martingaling, continuously adding to losing positions in hopes of recovery, is strongly discouraged
    
- Martingaling can quickly escalate risk and is not considered a sustainable long-term strategy
    

## Genuine Scalping

- Genuine scalping is allowed
    
- Short-term entries and exits that reflect realistic execution and market behavior are welcome
    
- Traders must ensure that their activity remains within Microscalping policy guidelines
    
- Scalping is considered valid as long as trades are taken in good faith and not intended to manipulate fill logic
    

## Automated Strategies

- Automated trading systems and trade copiers are permitted
    
- All automated activity must comply with Lucid Trading rules
    
- Traders are fully responsible for any software errors, malfunctions, or unintended outcomes
    

## Flipping

- Flipping is allowed
    
- Flipping refers to taking a quick in-and-out trade for the purpose of meeting minimum trading day requirements
    
- While we encourage meaningful trading activity, we do not restrict this practice

# Allowed Trading Times
## LucidPro, LucidFlex and LucidDirect Accounts

- All positions must be closed by 4:45 PM EST, Monday through Friday
    
- Any open positions will be automatically closed by Lucid Trading at 4:45 PM EST
    
- **Important: Holding a position past this time does not result in a failed account**
    

Market Reopen Times:

- Trading resumes at 6:00 PM EST, Sunday through Thursday
    
- On market holidays with altered closing times, all positions must be closed before the market closes, regardless of the usual 4:45 PM cutoff
    

## LucidLive Accounts

- Swing trading is allowed in LucidLive accounts
    
- Traders may hold positions past 4:45 PM EST and through the overnight maintenance window, provided they meet overnight margin maintenance requirements
    
- For added risk control, an auto-liquidate option can be enabled to automatically close positions before the maintenance window
    

Auto-liquidation settings and other risk configurations are handled during the LucidLive onboarding process.
