# Prop Firm Bot

Monte Carlo engine that models prop firm accounts as structured products and finds the strategy parameters that maximize net expected value across the full pipeline (eval fee → eval phase → funded phase → payouts → breach).

## Read first

- `PROJECT_CONTEXT.md` — why every architectural decision was made
- `Tasks/todo.md` — phased build plan with exit criteria
- `CLAUDE.md` (symlink to global) — workflow rules
- `REFERENCE.md` (symlink to global) — technical patterns

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
├── Notebooks/                 # .ipynb validation + exploration
├── Tasks/                     # todo.md
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
