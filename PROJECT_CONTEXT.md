# PROJECT_CONTEXT.md — Prop Firm Monte Carlo Engine

> **For Claude Code:** Read this before touching any code. This file captures the reasoning behind every architectural decision. If you find yourself wanting to question a decision below, the answer is probably here.
>
> **For Georg:** This is the bridge file between the Claude.ai planning conversation and your Claude Code build sessions. Update it when major decisions change.
>
> **Created:** 2026-04-29
> **Companion files:** `Tasks/todo.md` (build plan), `CLAUDE.md` (workflow rules, symlinked), `REFERENCE.md` (technical patterns, symlinked)

---

## What This Project Is

A Monte Carlo engine that models prop firm accounts as **structured products** and finds the strategy parameters (win rate, R:R, frequency, sizing function) that maximize **net expected value across the full account pipeline**: eval fee → eval phase → funded phase → payouts → breach.

**Concretely:**
- Inputs: prop firm ruleset (LucidFlex, TopStep), strategy distribution (parametric or backtested), sizing function
- Pipeline simulator: walks an account through every state transition (trade → P&L → rule check → phase change → payout → breach)
- Monte Carlo: 10,000+ runs of the pipeline to get statistical estimates
- Optimizer: searches the parameter space for the strategy/sizing combination that maximizes net EV
- Output: "given these constraints, the optimal strategy looks like X, with expected net profit of Y over Z months"

**Then, separately**, a bot is built to execute whatever strategy the engine recommends. The bot is a Phase 6 future project, not part of this build.

---

## What This Project Is NOT

- **NOT automating Georg's discretionary trading system.** This was the first instinct and it's wrong. Georg's system uses ICT concepts (sequential SMT, CISD, M15 rejection blocks, key opens) filtered through a daily bias forecast. The bias forecast is the largest single source of edge and is not automatable. Stripping it out and automating only the rules layer would lose money.

- **NOT a "good trader's strategy" optimizer.** A good trader optimizes for win rate, R:R, capital preservation, identity. Prop firm extraction optimizes for *probability of passing eval × expected payouts before breach − eval fees*. These goals diverge sharply. The engine will likely recommend strategies that look reckless to a discretionary trader (high frequency, smaller R:R, aggressive sizing on fresh evals) because the math says so.

- **NOT building from a trading idea up.** Building from the math down. Strategy is the output, not the input.

---

## The Core Insight

Prop firm accounts have a **convex payoff structure**:
- Downside: limited to the eval fee (~$100–175)
- Upside: uncapped, in payout cycles of $1,500–6,000+

This means a strategy doesn't need positive raw EV to be net-EV-positive at a prop firm. The right risk geometry can extract value from any strategy with the right distributional properties. The eval fee is functionally a **premium paid for a structured product** with known terms (the ruleset).

**Implication:** the optimization target is not "what's the best trading strategy" — it's "what trade distribution and sizing function maximizes value extraction from this specific structured product."

---

## Why These Specific Decisions Were Made

### Why prop firms instead of prediction markets

Georg considered building a Polymarket/Kalshi bot first. Rejected because:
- €50 starting capital makes longshot bias and convergence trading produce €5–15/month best case
- Cross-platform arbitrage requires sub-second latency from co-located servers; not accessible to retail
- Realistic monthly extraction: €0–20, with 90% probability of net loss after fees
- Prop firms with €100 eval fee can yield $800–2,500/month once funded

**Math says prop firms. Capital efficiency is roughly 50–100× better.**

### Why LucidFlex + TopStep specifically

- **LucidFlex:** No daily loss limit, no funded consistency rule, end-of-day drawdown only. This is the rare prop firm whose rules don't actively kill bots. Payout cycles every 3 days on Pro tier. News trading and scalping allowed. Genuinely bot-friendly.
- **TopStep:** Industry standard, large user base, well-documented rules. Different rule structure (trailing drawdown mechanics differ from Lucid). Including it makes the engine generalizable rather than Lucid-specific.
- **Excluded for v1:** Apex, FTMO, MyFundedFutures — different rule structures, can be added later as ruleset modules.

### Why parametric + backtested strategy modeling (not one or the other)

- **Parametric only** = fast optimization, but trade independence assumption is unrealistic. Real strategies cluster wins and losses in ways that interact badly with consistency rules and drawdown limits.
- **Backtested only** = realistic, but only optimizes within the strategies actually coded. Can't sweep the full parameter space cheaply.
- **Both** = parametric layer for cheap exploration of the prop firm math itself ("any strategy with these properties has X% chance of net profit"), backtested layer for validation ("does this real strategy actually produce a distribution close to what the parametric model assumed?").

This mirrors how serious quant teams structure validation: cheap synthetic exploration, expensive real-data confirmation. Maps directly onto the Writer/Reviewer pattern from CLAUDE.md.

### Why dynamic sizing functions

Georg's instruction was "whatever the math says." Translated:
- The optimizer doesn't assume sizing is fixed
- Sizing is a function `size(remaining_buffer, days_in_cycle, current_pnl, payout_count) → contracts`
- Optimizer searches over the parameters of this function
- May collapse to fixed sizing if optimal; may go fully dynamic; the engine doesn't bias toward either

### Why TradingView Premium for Phase 4 instead of Python backtesting

Georg already has TradingView Premium. Re-building backtesting infrastructure in Python when:
- TV's strategy tester gives Deep Backtesting up to 2M bars (more than enough)
- Pine Script is ~50 lines per strategy (much faster than Python framework)
- TV provides visual debugging on every trade (replay on chart, no Python framework matches this)
- The Monte Carlo engine only consumes trade sequences, not raw OHLCV — so we don't need price data in Python at all

...would be re-inventing infrastructure for no reason. **Use what's already paid for.**

### Why no bot in this project

The bot is Phase 6, deliberately separated. Building a bot before knowing what strategy to deploy is the classic mistake — six weeks of plumbing for a strategy that turns out to be unprofitable. The engine tells us *what to build*; the bot *builds it*. Sequence matters.

---

## What Georg Actually Wants (Stated Explicitly)

Quoting Georg from the planning conversation:

> "i don't care that it goes against trading instincts. my feelings don't print profit, facts and systems do. and if the bot chooses to use 3:1rr, so be it (i have 1:10rr). also i don't want to code MY system, i want to build a prop firm system. that is way less difficult and it won't tell me 'my system' is off, because the system is built to not be off (the system i will give the bot)."

This is the project's mission statement. If Claude Code's instinct is to suggest "but what about your existing system?" or "shouldn't we add discretionary judgment here?" — the answer is no. Strategy is whatever the math outputs. Georg has explicitly committed to deploying it regardless of how it feels.

---

## What "Done" Looks Like

End state of this project (Phases 1–5):

1. A Python package that takes `(ruleset, strategy_distribution, sizing_function)` as input and returns net EV with confidence intervals
2. A Streamlit dashboard exposing the parameter space — Georg can slide win rate / R:R / frequency and see net EV update live for both LucidFlex and TopStep
3. At least one TradingView Pine Script strategy backtested, exported, and validated through the engine
4. An optimizer that recommends specific sizing function parameters for the chosen strategy/ruleset combination
5. Documented assumptions, caveats, known limitations (slippage modeling, trade independence, regime stability)

**Then and only then** does Phase 6 begin: building a bot that executes the optimizer's recommended strategy.

---

## Key Risks and Watch-outs

- **Rule encoding errors:** The whole engine is worthless if rules are wrong by even one decimal. Phase 1 manual validation is non-negotiable. Use Writer/Reviewer pattern. Both LucidFlex and TopStep rules must be pulled from official sources, not from training-data memory — both firms update terms periodically.
- **Lookahead bias in state updates:** The simulator updates account state after each trade. Easy to accidentally let a future trade's information leak into a current rule check. `shift(1)` discipline applies to simulator code, not just backtests.
- **Off-by-one on consistency rule:** Lucid's 50% consistency rule has specific math. Test exhaustively.
- **TopStep rules drift:** TopStep updates its rules periodically. Search current rules before encoding, do not trust training-data memory.
- **TradingView strategy tester quirks:** Pine Script's default fill assumptions can be optimistic. Configure realistic slippage and commissions in the strategy. Validate that TV's reported P&L per trade matches what would actually fill in live markets.
- **Optimizer overfitting:** With enough parameters, the optimizer can find a "winning" strategy that's just fitting noise in the historical data. Cross-validate by holding out a time period.
- **Monte Carlo seed sensitivity:** Always run with multiple seeds. If results swing wildly between seeds, increase N or revisit the model.

---

## What This Project Builds On

- **Existing momentum backtest** (QQQ, see Obsidian notes): the Monte Carlo validator from that project is the foundation for this engine. We're extending the same pattern, not building from scratch.
- **Streamlit dashboard pattern** (from momentum backtest dashboard): reuse layout, caching, two-call `update_layout` pattern for Plotly.
- **CLAUDE.md workflow rules:** Plan mode for architecture decisions, Writer/Reviewer for load-bearing files, `ultrathink` for breach detection logic and Monte Carlo aggregation, `/btw` for side questions.

---

## Decisions Still Open

These are tracked in `Tasks/todo.md` open questions but flagged here so Claude Code knows they're unresolved, not assumed:

1. TopStep's exact current ruleset — must be searched fresh, not assumed from memory
2. LucidFlex's exact current ruleset — same standard; do not trust memory even though Lucid is the "preferred" firm in this project
3. Whether to model slippage as a strategy parameter or as a fixed assumption
4. Whether multiple concurrent accounts should be modeled (probably v2 scope)
5. Reset economics — when does paying for a reset beat starting fresh

---

## How to Use This File in Claude Code

1. At session start: `read PROJECT_CONTEXT.md, CLAUDE.md, REFERENCE.md, and Tasks/todo.md`
2. Before any architectural decision: check this file first for prior reasoning
3. After completing a phase: update the "Decisions Still Open" section if anything was resolved
4. If a major decision changes mid-build: append to a new "Decision Changelog" section at the bottom, with date and reasoning

This file is the single source of truth for *why*. The `Tasks/todo.md` is the source of truth for *what*. Together they should make any session resumable without re-litigating settled questions.
