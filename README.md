# Prop Firm Bot

Monte Carlo engine that models prop firm accounts as structured products and finds the strategy parameters that maximize net expected value across the full pipeline (eval fee → eval phase → funded phase → payouts → breach).

## Read first

- `PROJECT_CONTEXT.md` — why every architectural decision was made
- `AGENTS.md` — shared rules for Codex, Claude Code, and future agents
- `Coordination/HANDOFF.md` — current state, next action, and active constraints
- `Coordination/CHANGELOG.md` — shared agent changelog
- `Coordination/DECISIONS.md` — settled decisions

Local-only files such as `Tasks/todo.md`, `CLAUDE.md`, and `REFERENCE.md` may exist on Georg's machine, but they are intentionally ignored and are not required for GitHub collaboration.

## Scope

- Rulesets: LucidFlex 50K + TopStep 50K (v1)
- Strategies: parametric synthetic (for optimization) + TradingView Pine backtests on NQ (for validation)
- Output: optimal sizing function for the chosen strategy/ruleset combination

Phases 1–5 build the engine. Phase 6 (separate) builds a bot that executes the engine's recommendation. The bot does not start until the engine produces a clear answer.

## Project layout

```
Prop Firm Bot/
├── Rulesets/                  # rule documents pulled from official sources
│   ├── LucidFlex/
│   └── TopStep/
├── Sources/                   # verbatim primary-source documents (e.g. founding-thesis transcript)
├── Analysis/                  # research notes, sanity checks, literature reviews
│   ├── scripts/               # standalone research/probe scripts
│   └── strategy_specs/        # implementation contracts for candidate strategies
├── Coordination/              # tracked Codex/Claude handoff + changelog
├── Notebooks/                 # .ipynb validation + exploration
├── Tasks/                     # local-only todo.md, ignored
├── Dashboard/                 # streamlit app
├── PineScripts/               # TradingView Pine source
├── TVExports/                 # XLSX strategy tester exports (gitignored)
├── src/
│   ├── rules/                 # encoded LucidFlex / TopStep rule modules
│   ├── strategies/            # parametric trade generators
│   ├── sizing/                # dynamic sizing functions
│   ├── pipeline/              # account state machine, simulator, monte carlo
│   ├── optimizer/             # parameter search
│   └── data/                  # TV export loader
└── tests/
```

## Current research artifacts

- `Analysis/2026-04-30_strategy_shortlist_nq_prop_firm.md` — ranked NQ/MNQ strategy candidates for the prop-firm payoff model.
- `Analysis/strategy_specs/torb_orb_v0.md` — exact v0 timely opening range breakout baseline spec.
- `Analysis/2026-04-30_lucidflex_eval_probe_orb_proxy.md` — first synthetic ORB-like distribution probe against LucidFlex 50K evaluation rules.

The ORB/TORB work is a falsification baseline, not an endorsed profitable strategy. Current evidence says low-risk ORB-like profiles timeout and higher-risk profiles breach often.
