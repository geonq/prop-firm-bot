# Phase 1 Ruleset Audit

Reviewer-pass log for `src/rules/lucidflex.py` and `src/rules/topstep.py` against the source docs in `Rulesets/`. Encoded values + source citations live in the rule modules themselves — this file does not reproduce them.

## Reviewer Pass — 2026-04-30 (Claude Code)

Line-by-line cross-check against `Rulesets/LucidFlex/LucidFlex Rules.md` and `Rulesets/TopStep/TopStep NoFee.md`.

**Fixed:**
- `src/rules/lucidflex.py:eval_consistency_limit` 0.52 → 0.50. The 0.52 was the help-center cushion *example* ($1,560 / $3,000); source doc states the threshold strictly as "50% or less" and describes the cushion as a soft, trader-dependent buffer ("calculated on what your actual profit earned is for the day and will vary from trader to trader") — not a fixed numeric limit.

**Confirmed correct against source:**
- LucidFlex 50K: starting $50,000, profit target $3,000, MLL $2,000, EOD trail to $52,100, lock at $50,100 (start + $100), 4 mini / 40 micro caps, 90/10 split, payout $500–$2,000 (50% of profit), 5×$150 day requirement, 5 simulated payouts max.
- LucidFlex funded scaling: 2/3/4 minis at $0–$999 / $1,000–$1,999 / $2,000+.
- TopStep 50K NoFee: Combine $50K start, MLL $2,000 trailing then locked at $50,000 (no buffer); XFA $0 displayed start, MLL trails -$2,000 → $0; 5 mini Combine cap; $1,000 optional DLL (session-only, not a violation); $95/mo subscription, $109 reset, $0 activation; Back2Funded $599 max 2 pre-first-payout.
- TopStep payouts: min $125; Standard cap $2,000 / Consistency cap $3,000; 5×$150 days (Standard) or 3 days with largest ≤40% (Consistency); 90/10 split; MLL set to $0 after each payout.
- TopStep XFA 50K scaling, verified 2026-05-05 from Topstep public rules table: $0–$1,500 → 2 lots; $1,500+ → 3 lots; $2,000+ → 5 lots; updates after daily Trade Report, not intraday; TopstepX micros use 10:1 mini equivalent.

**Later corrected:**
- LucidFlex eval/reset economics updated from Georg dashboard verification on 2026-05-01.
- Time-of-day helpers and deployment compliance helpers added in later passes.

**Test coverage:** `tests/test_rulesets.py` pins all four Phase 1 exit-criteria categories (breach at exact threshold, consistency violation, payout eligibility math, `max_contracts` per phase) for both firms. Boundary tests are deliberately tight (1500/3000 passes, 1501/3000 fails) so any future encoding drift surfaces immediately. Full suite: 75 passing.

## Deployment Pass — 2026-05-06 (Codex)

Fresh public-source check for previously deferred deployment risks.

**Encoded:**
- TopStep price-limit proximity helper: no participation within 2% of current CME product/session price limit.
- LucidFlex microscalping helper: flags when >50% of positive profits come from trades held ≤5 seconds.
- LucidFlex HFT helper: configurable order-rate hard stop because public text is qualitative, not numeric.
- TradingView audit parser pairs entry/exit rows to expose hold seconds and P&L.

**Not encoded as hard EV rules:**
- News trading: current checked public sources did not show a blanket TopStep/LucidFlex news embargo.
- Price-limit percentages: caller must supply current CME limits because they vary and update.

**Test coverage:** deployment helpers covered in `tests/test_rulesets.py` and `tests/test_tv_trade_audit.py`.
