# LucidFlex 50K Rules — Compact Encoding Reference

Status: compressed 2026-05-05 for agent token discipline. The original
help-center paste was removed after reviewer pass because the encoded values
now live in `src/rules/lucidflex.py` and are audited in
`Rulesets/PHASE1_RULESET_AUDIT.md`.

## Source Status

- Core mechanics: official LucidFlex help-center verification, 2026-04-30.
- Commercial economics: Georg dashboard verification, 2026-05-01.
- Use this file as a compact source map; use `src/rules/lucidflex.py` as the
  executable truth.

## 50K Evaluation

- Starting balance: `$50,000`
- Profit target: `$3,000`
- Maximum loss limit: `$2,000`
- MLL starts at `$48,000`
- EOD trailing drawdown; MLL never moves down
- Trail trigger balance: `$52,100`
- Locked MLL: `$50,100` (`start + $100`)
- Eval consistency: largest winning day / account profit must be `<= 50%`
- Eval contract cap: `4` minis or `40` micros
- No activation fee from eval to funded

## LucidFlex 50K Economics

- Base eval fee: `$140`
- Realistic coupon-adjusted eval fee: `$98`
- Reset cost: `$95`
- Vault-cycle first-five-account discounts may be `40-50%`; model realized
  current-cycle price instead of assuming `$98`.

## Funded / Payout Mechanics

- Profit split: `90/10`
- Payout request minimum: `$500`
- 50K payout max: `50% of simulated profit`, capped at `$2,000`
- Payout cycle requires `5` trading days with at least `$150` profit each
- Maximum simulated payouts before move-to-live: `5`
- Funded scaling by simulated profit:
  - `$0-$999`: `2` minis / `20` micros
  - `$1,000-$1,999`: `3` minis / `30` micros
  - `$2,000+`: `4` minis / `40` micros

## Trading Hours / Products

- Must be flat by `4:45 PM` New York time Monday-Friday.
- Reopens `6:00 PM` New York time Sunday-Thursday.
- Weekend holding prohibited.
- Phase-1 priority products are allowed: `NQ`, `MNQ`, `ES`, `MES`.
- Relevant NQ/MNQ values: tick size `0.25`; NQ tick `$5`, point `$20`; MNQ
  tick `$0.50`, point `$2`.

## Deferred / Watch Items

- News/velocity logic exists in source prose but is not yet modeled.
- Product list should be rechecked before trading anything outside NQ/MNQ.
