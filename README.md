# Prop Firm Bot

Monte Carlo engine for prop-firm account economics.

**Current phase:** Parked. This was a foundational project, not a failed one. It built the rule engine and, more importantly, exposed the real limitation: the hard part was never getting Claude/Codex to produce more code, it was having a mechanical edge that Georg understood deeply enough to express, validate, and maintain himself.

Georg is now moving into a more in-depth path: studying the market mechanics and quantitative foundations more seriously, then likely rebuilding the next version from scratch with his own code instead of relying on agents for the core implementation.

## Parked State

The core engine stays: model prop-firm accounts as structured products, then evaluate whether a trade distribution survives eval, funded, payout, and breach rules.

What this project clarified:

- Prop-firm accounts can be modeled as structured products with exact state machines.
- The engine, rulesets, replay, sizing, and Monte Carlo layers are useful reusable foundations.
- The weak point was strategy definition: discretionary SMT, daily bias, clean/choppy reads, liquidity draws, and no-trade selection were not objective enough to automate honestly.
- Agent-generated code can accelerate scaffolding, but it cannot replace Georg's own market understanding or ownership of the implementation.
- The next serious attempt should start from direct understanding, smaller scope, and code Georg can reason about line by line.

The strategy path is parked:

- Georg's discretionary Model A / SMT / OTE / CISD automation attempt is parked.
- Prior paper-mining and public Pine strategy attempts are parked.
- TradingView/Pine export tooling is parked.
- Rithmic/Quantower order-flow/L2 research is parked as a future path, not active repo work.

Archived tracked work lives on the GitHub branch `archived`. Private raw artifacts remain local-only under ignored archive folders.

Return condition: resume this project only when there is one mechanical entry rule with a live sample of at least 30 trades that plausibly fits the target prop-firm geometry: 40-50% win rate, reward/risk at least 2.0, and roughly 2-4 trades per day.

## Scope

- **Rulesets:** LucidFlex 50K, TopStep 50K No-Fee
- **Engine:** eval → funded → payouts → breach simulation
- **Sizing:** fixed, buffer-aware, adaptive
- **Research status:** parked until a mechanical signal is ready for replay
- **Out of active scope:** discretionary SMT automation, published-concept Pine strategies, TradingView export automation, active L2/order-flow buildout

## Folder Guide

```text
Prop Firm Bot/
├── src/
│   ├── rules/           # encoded LucidFlex / TopStep ruleset logic
│   ├── pipeline/        # account state machines, replay, Monte Carlo
│   ├── sizing/          # fixed / dynamic sizing functions
│   ├── strategies/      # synthetic trade generators + replay adapter
│   ├── optimizer/       # parameter grid search + reset economics
│   └── data/            # generic replay data loading
├── Research/
│   └── OrderFlowL2/     # parked future Rithmic/Quantower data-capture plan
├── Rulesets/            # official prop firm rule summaries
├── Dashboard/           # Streamlit MC dashboard
└── Archived/            # ignored local archive payloads; GitHub branch: archived
```

## Key Modules

| Module | What it does |
|--------|-------------|
| `src/rules/topstep.py` | TopStep 50K ruleset: Combine, XFA payout, DLL, Back2Funded |
| `src/rules/lucidflex.py` | LucidFlex 50K ruleset: eval phases, funded payout, vault |
| `src/pipeline/monte_carlo.py` | Shared MC aggregation with EV and CI |
| `src/pipeline/replay_monte_carlo.py` | Block-bootstrap MC on historical trade sequences |
| `src/pipeline/topstep_replay.py` | Deterministic TopStep replay from dated R-multiple days |
| `src/pipeline/lucidflex_replay.py` | Deterministic LucidFlex replay |
| `src/data/replay_loader.py` | Loads generic dated R-multiple CSVs |
| `src/optimizer/search.py` | Adaptive sizing grid search across parameter space |

## Running

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/
```

## Phase Status

| Phase | Status |
|-------|--------|
| 1 — Ruleset encoding | Done |
| 2 — Account state machines + single pipeline | Done |
| 3 — Parametric MC + dynamic sizing | Done |
| 4 — Strategy research | Parked |
| 5 — Optimizer + dashboard refinement | Parked |
| 6 — Live execution bot | Parked |
