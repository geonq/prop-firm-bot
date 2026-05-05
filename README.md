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
├── Sources/                   # compact source summaries and provenance notes
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

- `Analysis/2026-04-30_strategy_shortlist_nq_prop_firm.md` — compact retired shortlist; superseded by engine-targeted strategy research.
- `Analysis/strategy_specs/torb_orb_v0.md` — retired ORB/TORB baseline note; not a candidate strategy.
- `Analysis/2026-04-30_lucidflex_eval_probe_orb_proxy.md` — first synthetic ORB-like distribution probe against LucidFlex 50K evaluation rules.
- `Analysis/2026-04-30_lucidflex_full_pipeline_probe_orb_proxy.md` — first synthetic ORB-like distribution probe through LucidFlex eval and funded payouts.
- `Analysis/2026-04-30_lucidflex_phase_sizing_probe.md` — first synthetic phase-aware sizing probe using different eval/funded risk.
- `Analysis/2026-04-30_lucidflex_phase_risk_grid.md` — first synthetic grid search over LucidFlex eval risk and funded risk.

The ORB/TORB work is a falsification baseline, not an endorsed profitable strategy. Current evidence says low-risk ORB-like profiles timeout and higher-risk profiles breach often.

Current next step: define the first real candidate strategy from the engine's target trade profile, then backtest/export/replay it. The project is not trying to find generic live-market EV first; market research only needs a distribution that can extract value from the prop-firm payoff structure.

## Current state machines

- `src/pipeline/lucidflex_account.py` — canonical LucidFlex 50K account state machine for eval, funded payouts, breach, and eval reset.
- `src/pipeline/lucidflex_pipeline.py` — synthetic LucidFlex eval-to-funded pipeline for parametric Monte Carlo probes.
- `src/pipeline/lucidflex_replay.py` — deterministic LucidFlex replay path for dated trade R-multiple days, including no-trade days.
- `src/data/replay_loader.py` — CSV loader for replay-day inputs using `session_date,r_multiple`.
- `src/data/tv_trade_loader.py` — TradingView Strategy Tester XLSX loader that emits dated replay days from R or profit/P&L columns.
- `Analysis/scripts/tv_lucidflex_replay_probe.py` — CLI replay probe for sweeping LucidFlex eval/funded risk on one TV export.
- `src/pipeline/topstep_account.py` — canonical TopStep 50K No Activation Fee account state machine for Combine, XFA Standard/Consistency payout paths, optional DLL lock, Combine reset, and Back2Funded.
- `src/pipeline/topstep_pipeline.py` — synthetic TopStep Combine-to-XFA pipeline for cross-firm parametric probes, including optional Back2Funded retries.
- `src/pipeline/monte_carlo.py` — shared LucidFlex/TopStep Monte Carlo aggregation with EV and proportion confidence intervals.
- `src/strategies/parametric.py` — i.i.d., phase-aware, state-aware, autocorrelated, and regime-switching synthetic trade generators.
- `src/optimizer/search.py` — adaptive sizing grid search for LucidFlex or TopStep.
- `src/optimizer/reset_economics.py` — reset-vs-fresh cost comparisons for LucidFlex and TopStep.
