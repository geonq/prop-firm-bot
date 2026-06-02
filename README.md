# Prop Firm Bot

Monte Carlo engine for prop-firm account economics plus a new order-flow/L2 research track.

**Current phase:** Phase 4 pivot — Rithmic/Quantower order-flow data capture and measurable L2 feature research.

## Current Direction

The core engine stays: model prop-firm accounts as structured products, then evaluate whether a trade distribution survives eval, funded, payout, and breach rules.

The old strategy path is parked:

- Georg's discretionary Model A / SMT / OTE / CISD automation attempt is parked.
- Prior paper-mining and public Pine strategy attempts are parked.
- TradingView/Pine export tooling is parked.

The active strategy-research path is now objective order-flow/L2 data:

- NQ and ES market depth
- tape/trade prints
- queue imbalance
- order-flow imbalance
- absorption and depth replenishment
- ES/NQ confirmation
- prop-firm replay of any resulting signal distribution

Archived tracked work lives on the GitHub branch `archived`. Private raw artifacts remain local-only under ignored archive folders.

## Scope

- **Rulesets:** LucidFlex 50K, TopStep 50K No-Fee
- **Engine:** eval → funded → payouts → breach simulation
- **Sizing:** fixed, buffer-aware, adaptive
- **Research focus:** Rithmic/Quantower L2 data capture and feature validation
- **Out of active scope:** discretionary SMT automation, published-concept Pine strategies, TradingView export automation

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
│   └── OrderFlowL2/     # active Rithmic/Quantower data-capture plan
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
| 4 — Strategy research | Pivoted to order-flow/L2 |
| 5 — Optimizer + dashboard refinement | Pending |
| 6 — Live execution bot | Pending |
