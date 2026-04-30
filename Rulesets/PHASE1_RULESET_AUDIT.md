# Phase 1 Ruleset Audit — 2026-04-30

This audit compares the local `Rulesets/` documents against the requirements in `Tasks/todo.md`.

## Current Directory State

- `Rulesets/LucidFlex/LucidFlex Rules.md` exists and contains an encoding reference plus verbatim source paste.
- `Rulesets/TopStep/TopStep NoFee.md` exists and contains an encoding reference plus verbatim source paste.
- No Python rule modules exist yet: `src/rules/lucidflex.py` and `src/rules/topstep.py` still need to be written.
- No ruleset tests exist yet: `tests/test_rulesets.py` still needs to be written.

## Task Guideline Match

The rulesets are good enough to start Phase 1 encoding for the 50K LucidFlex and 50K TopStep No Activation Fee paths, but they are not fully signed off.

They do match the task guideline on core encoding coverage:

- evaluation/funded account phases are documented
- profit targets, MLL, consistency, payout mechanics, max size, trading hours, and permitted products are present
- NQ/MNQ are confirmed permitted in both firms

They do not fully match the task guideline on evidence hygiene:

- filenames are not date-stamped, although the files contain `Last updated: 2026-04-30`
- some commercial/dashboard values remain `[VERIFY]`
- TopStep scaling-plan graph numbers still need dashboard/image confirmation before encoding hard numeric thresholds

## LucidFlex 50K Encoding Matrix

| Field | Value | Status |
|-------|-------|--------|
| Eval starting balance | $50,000 | official source present |
| Eval profit target | $3,000 | official source present |
| Eval MLL amount | $2,000 | official source present |
| Eval drawdown method | End-of-day trailing drawdown | official source present |
| Initial trail balance | $52,100 | official source present |
| Locked MLL balance | $50,100 | official source present |
| Eval DLL | None | official source present |
| Eval consistency | 50%; largest day / account profit <= 50% | official source present |
| Consistency cushion at exact target | $1,560 largest day on $3,000 target | official source present |
| Funded DLL | None | official source present |
| Funded consistency | None | official source present |
| Funded scaling | 50K: 2 minis at $0-$999, 3 at $1,000-$1,999, 4 at $2,000+ | official source present |
| Max size | 4 minis or 40 micros | official source present |
| Payout profit split | 90/10 | official source present |
| Payout eligibility | 5 days with at least $150 profit, plus positive net profit in cycle | official source present |
| Payout min/max | min $500; max 50% of profit up to $2,000 | official source present |
| Max payout count | 5 simulated payouts, then moved live | official source present |
| Activation fee | none | official source present |
| Eval price | $175 | needs dashboard/commercial verification |
| Reset cost | approximately $61 | needs dashboard/commercial verification |
| Trading hours | flat by 4:45 PM EST Mon-Fri; reopen 6:00 PM EST Sun-Thu | official source present |
| News trading | allowed without restriction; velocity/slippage risk remains | official source present |
| HFT/microscalping | prohibited/flagged | official source present |

## TopStep 50K No Activation Fee Encoding Matrix

| Field | Value | Status |
|-------|-------|--------|
| Trading Combine starting balance | $50,000 | official source present |
| Trading Combine MLL | $2,000 | official source present |
| Trading Combine MLL method | Highest end-of-day balance trailing, monitored real-time, locks at starting balance | official source present |
| Trading Combine max size | 5 minis or 50 micros | official source present |
| Trading Combine consistency | best day below 50% of total profits | official source present |
| XFA displayed starting balance | $0 | official source present |
| XFA MLL | starts at -$2,000, trails to $0 and locks | official source present |
| MLL after first payout | set to $0 | official source present |
| DLL | optional in Trading Combine/XFA; automatic in Live; 50K amount $1,000 if used | official source present |
| DLL breach behavior | auto-liquidates/blocks only for session; not a rule violation | official source present |
| No Activation Fee subscription | $95/mo for new 50K purchases after April 28, 2026 | official source present |
| No Activation Fee reset | $109 | official source present |
| Activation fee | $0 on No Activation Fee path | official source present |
| Back2Funded | $599; max 2 reactivations before first payout | official source present |
| XFA Standard payout | 5 winning days of $150+, positive profit after prior payout except first; 50% balance capped at $2,000 for 50K | official source present |
| XFA Consistency payout | 3 trading days, largest day <= 40% total net profit; 50% balance capped at $3,000 for 50K | official source present |
| Profit split | 90/10 | official source present |
| Payout minimum | $125 | official source present |
| Trading hours | flat by 3:10 PM CT Mon-Fri; reopen 5:00 PM CT; Sunday overnight exception into Monday | official source present |
| XFA scaling plan | applies to XFA only, updates after trade report/end-of-day | official source present |
| XFA scaling numeric thresholds | graph-based; local summary has third-party values | needs dashboard/image verification before encoding |
| News/prohibited conduct | source text present but not yet compressed into encoding rules | needs reviewer compression |

## Optimized Encoding Order

1. Encode LucidFlex first. It has fewer unresolved dashboard-only values and no DLL.
2. Encode TopStep Trading Combine and XFA MLL/payout/DLL mechanics next.
3. Treat TopStep XFA scaling thresholds as a separate reviewer-gated table before allowing `max_contracts()` to use them in funded simulations.
4. Write threshold tests before any Monte Carlo code.

## Reviewer Gates Before Phase 1 Sign-off

- Confirm LucidFlex 50K eval price and reset cost from dashboard/commercial page.
- Confirm TopStep XFA scaling numeric thresholds from dashboard or graph image.
- Compress TopStep prohibited conduct/news restrictions into explicit simulator assumptions.
- Decide whether the repo should rename raw rule files to date-stamped names or keep the current stable filenames plus this dated audit.
