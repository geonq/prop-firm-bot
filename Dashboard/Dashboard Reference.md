# Dashboard Reference

Date: 2026-04-30
Scope: public QuantPad pages only, plus local Claude notes already committed in this repo. This file is for visual and product-reference inspiration for our private Prop Firm Bot dashboard. Do not copy QuantPad branding, proprietary workflows, private app screens, source code, prompts, market data access, or exact UI composition.

## Legal Boundary

QuantPad's public legal pages are unusually explicit: its Terms claim ownership over UI/UX, workflows, feature structure, prompts, orchestration logic, internal tools, market data pipelines, datasets, and branding, and prohibit using the service to reproduce or build a substantially similar competing workflow or dashboard. Its Acceptable Use Policy also prohibits scraping, crawling, bulk-downloads, access-control bypass, and reverse engineering.

Practical rule for this project: use broad product-design lessons from the public homepage only. Build our dashboard around our own data model, our own copy, our own layout decisions, and our own visual identity. Do not attempt to mirror QuantPad's exact screen, logo, wording, private routes, or interaction flow.

Sources: https://quantpad.ai/terms, https://quantpad.ai/license, https://quantpad.ai/acceptable-use.

## Public Product Facts

QuantPad positions itself as "The Quantitative Edge for Serious Traders" and sells an all-in-one workflow: discover statistical edges, build strategies with AI, validate with institutional-grade math, and deploy with confidence.

The public homepage exposes four major product ideas:

1. A project workspace where an AI agent creates files, edits code, searches the web, and executes tasks inside a split workspace.
2. Trade-log analysis where the user uploads a trade log and the agent writes analysis code, runs it, produces charts, and suggests next steps.
3. Production DSL coding with domain skills, curated retrieval, iterative lint/fix, and support for PineScript, NinjaScript, PowerLanguage, and EasyLanguage.
4. Prop-firm Monte Carlo simulation against real prop firm rules, including pass probability, drawdown paths, time-to-target, and payout outcomes from reshuffled trade sequences.

The public simulator preview specifically shows `Topstep 50K Combine`, `Challenge` and `Funded` modes, payout probability, mean payout, days to first payout, mean net EV, 5th/95th percentile net EV, challenge equity paths, an `All paths (1000)` filter, a day slider, and distribution stats such as p5, median, p95, and percent losing.

Sources: https://quantpad.ai/.

## Local Claude Findings About QuantPad

Claude added `Sources/2026-04-30_youtube_prop_firm_thesis.md`, identified the transcript as QuantPad marketing material, and then replaced the transcript-derived calibration claims with simulation-derived targets in `Analysis/2026-04-30_founding_thesis_validation.md`.

The useful conclusion from Claude's work is that QuantPad is not independent academic validation of the thesis. It is a commercial product using the same prop-firm Monte Carlo concept. The transcript is still useful as inspiration and a source of hypotheses, but its numerical claims should be treated as marketing claims until our engine reproduces or rejects them.

One cleanup suggestion: `PROJECT_CONTEXT.md` still contains a paragraph saying the high-WR/lower-RR monotonic claim is "robust mathematics," while the later calibration section says Claude's simulation rejects monotonic behavior. That contradiction should be removed before Phase 3 starts.

## Visual Structure Observed

QuantPad's public UI is a dark-first, workbench-style application shell rather than a marketing-heavy SaaS landing page. The page uses a fixed 64px top navigation with a left-aligned brand mark, centered nav items with small Lucide icons, and a compact sign-in action on the right. The hero is centered and typography-led, then immediately gives way to a large product preview.

The product preview is the most relevant visual reference. It is a framed, multi-pane workspace with a thin border, restrained shadow, and minimal chrome. The desktop layout uses a narrow file tree on the left, a code/editor pane in the middle, and an AI/chat or analytics pane on the right. The chat pane is roughly half the preview width. This creates the feeling of an actual tool, not a static report.

For analytics, QuantPad uses compact metric tiles above chart surfaces. The prop-firm preview has a segmented control for `Challenge` versus `Funded`, a metric grid, a large equity-path chart, a path filter dropdown, a range slider, and a secondary distribution chart. Labels are short. Numeric values are prominent but not oversized. Percentiles and annotations sit close to the chart rather than in explanatory prose.

## Visual Tokens To Borrow Broadly

Use Inter or a similar neutral sans font for all UI text. Use a system monospace for code, logs, parameter names, and run IDs.

Dark theme should be the default for our dashboard:

| Role | Reference Value |
|---|---|
| Page background | `#000000` |
| Secondary surface | `#0a0a0a` |
| Tertiary surface | `#141414` |
| Primary text | `#fafafa` |
| Secondary text | `#a3a3a3` |
| Tertiary text | `#737373` |
| Primary border | `#262626` |
| Secondary border | `#404040` |
| Hover surface | `#1e1e1e` |
| Accent | indigo around `#6366f1` |
| Positive EV / success | emerald around `#34d399` |
| Loss / breach | rose/red, muted until critical |

Light theme can exist but is secondary. QuantPad's light palette uses cool gray-blue surfaces rather than pure white: page background around `#e9eef6`, secondary surface around `#d8e0ec`, tertiary around `#c6d0e2`, dark slate primary text, and muted slate borders.

Keep radii restrained in our implementation. QuantPad uses larger preview radii in the landing page, but our working dashboard should use 6-8px for panels, controls, and metric tiles so it stays operational and dense.

## Recommended Prop Firm Bot Dashboard Layout

The first screen should be the actual simulator dashboard, not a landing page.

Top bar:

- Left: `Prop Firm Bot` plus current project/run name.
- Center: tabs for `Overview`, `Rulesets`, `Monte Carlo`, `Sizing`, `Backtests`, `Payouts`, and `Runs`.
- Right: run status, last simulation time, settings icon, theme toggle.

Left sidebar:

- Ruleset selector: `TopStep 50K`, `LucidFlex 50K`.
- Phase selector: `Eval`, `Funded`, `Full Pipeline`.
- Strategy selector: synthetic profile or imported backtest.
- Scenario controls: account path, fee model, consistency mode, DLL on/off, max days, trades/day.

Main overview:

- Segmented control for `Challenge`, `Funded`, and `Pipeline`.
- Metric grid: pass probability, breach probability, timeout probability, mean net EV, p5/p50/p95 EV, expected days to pass, expected days to payout, average fees burned, max drawdown buffer at terminal.
- Primary chart: Monte Carlo equity paths with filter menu for all, passed, breached, timed out, payout-positive, payout-negative.
- Secondary chart: terminal EV distribution with p5/p50/p95 markers.
- Tertiary panel: path inspector for a selected run with day-by-day balance, MLL, DLL, target, consistency state, and payout events.

Ruleset view:

- Use compact tables for encoded rules.
- Show current account state against every active rule with simple pass/warn/breach badges.
- Keep source links visible, because rule encoding is the highest-risk part of the project.

Sizing view:

- Show sizing function inputs and output curve.
- Plot remaining drawdown buffer versus selected contract size.
- Include side-by-side eval/funded sizing because Claude's work reinforces that phase-specific sizing is likely necessary.

Runs view:

- Use a file-tree-like left list for simulation runs.
- Main pane shows run config as JSON/YAML and result summary.
- Right pane shows notes, warnings, and next actions.

## Component Notes

Use segmented controls for mode switching, not text links. Use icon buttons for actions like rerun, export, copy config, compare, and inspect. Use dropdown menus for path filters and ruleset selection. Use sliders only for numeric exploration where immediate visual feedback matters, such as selected trading day or risk multiplier.

Metric cards should be dense and stable: fixed min-height, uppercase 10-11px label, 16-20px tabular numeric value, small Lucide icon, and color only when semantically meaningful. Avoid huge marketing numbers.

Charts should sit in unframed or lightly framed panels. Grid lines should be subtle. Use annotations sparingly: MLL, target, payout, breach, and selected day are enough.

Tables should be compact and scannable. Prefer sticky headers, monospace numeric columns, and explicit status cells over paragraphs of explanation.

## Product Conclusion

QuantPad validates that the marketable product shape is not just "run Monte Carlo." The appealing workflow is: upload or define a strategy, bind it to real prop-firm rules, run many paths, inspect risk geometry, and iterate with an agent-like workspace around the results.

For our personal dashboard, the best thing to borrow is the clean workbench feeling: dark neutral shell, minimal chrome, split panes, compact metrics, clear mode toggles, and charts that explain the barrier problem without tutorial text. The thing to avoid is copying QuantPad's proprietary workflow or treating its public claims as evidence. Our dashboard should look like an internal quant cockpit for our own engine, not like a QuantPad clone.
