# TopStep 50K No Activation Fee — Compact Encoding Reference

Status: compressed 2026-05-05 for agent token discipline. The original long
help-center paste was removed after reviewer pass because encoded values now
live in `src/rules/topstep.py` and audit state lives in
`Rulesets/PHASE1_RULESET_AUDIT.md`.

## Source Status

- Core mechanics: official TopStep help-center verification, 2026-04-30.
- Pricing reflects post-2026-04-28 No Activation Fee path.
- XFA 50K scaling tiers verified 2026-05-05 against Topstep public rules table.

## 50K Trading Combine

- Starting balance: `$50,000`
- Profit target: `$3,000`
- Maximum loss limit: `$2,000`
- MLL starts at `$48,000`
- EOD trailing MLL; never moves down
- MLL locks at original starting balance `$50,000`
- Intraday breach below MLL is account failure
- Best day / total profit must be `<= 50%`
- Contract cap: `5` minis or `50` micros
- Daily loss limit: `$1,000`, optional/session-lock only, not account failure

## No Activation Fee Economics

- Monthly subscription: `$95`
- Manual reset: `$109`
- Activation fee: `$0`
- Back2Funded: `$599`, max `2` times before first payout only

## XFA / Funded Account

- Displayed starting balance: `$0`
- MLL starts at `-$2,000`
- EOD trailing MLL locks at `$0`
- After each payout, MLL is set to `$0`
- Optional DLL behavior remains session-only
- XFA breach permanently closes account unless Back2Funded is available

## Payout Paths

Standard path:
- Minimum request: `$125`
- Request cap: `50% of balance`, max `$2,000`
- Requires `5` winning days of at least `$150`

Consistency path:
- Minimum request: `$125`
- Request cap: `50% of balance`, max `$3,000`
- Requires `3` trading days
- Largest day must be `<= 40%` of cycle profit

Both paths:
- Profit split: `90/10`
- Payout path is chosen at activation and locked per account

## Trading Hours / Products

- Must flatten before `3:10 PM` Chicago time Monday-Friday.
- Reopens `5:00 PM` Chicago time weekdays / Sunday.
- No swing trading in Combine or XFA.
- Phase-1 priority products are allowed: `NQ`, `MNQ`, `ES`, `MES`.

## XFA 50K Scaling

- `$0-$1,500` profit: `2` lots
- `$1,500+` profit: `3` lots
- `$2,000+` profit: `5` lots
- TopstepX micro conversion: `1` mini = `10` micros.
- Scaling updates after the daily Trade Report, not intraday.

## Reviewer-Gated / Deferred

- News embargo and CME price-limit proximity rules are documented but not yet
  encoded; deferred as second-order risk.
