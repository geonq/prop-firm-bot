# Prop Firm Bot

Monte Carlo engine that models prop firm accounts as structured products and finds the strategy parameters that maximize net expected value across the full pipeline (eval fee → eval phase → funded phase → payouts → breach).

**Current phase:** Phase 4 — TradingView Pine backtest validation against the parametric model.

## What this is

Prop firm accounts have a defined payoff structure: fixed eval cost, rules that determine pass/fail, and a payout schedule on the funded side. This project treats that structure as a financial instrument and searches for strategy parameters (win rate, R:R, frequency, sizing) that produce the best risk-adjusted EV given the specific ruleset.

The engine runs 10k+ Monte Carlo simulations of the full account lifecycle per parameter set. Validation uses real TradingView backtests exported as XLSX, replayed through the same account state machines.

## Scope

- **Rulesets:** LucidFlex 50K, TopStep 50K No-Fee
- **Strategy under development:** Model A — NQ M15 key-open OTE entries with MTF confluence scoring
- **Sizing:** fixed and dynamic (phase-aware)
- **Output:** MC mean EV, pass rate, breach-after-pass, sizing recommendation

## Folder guide

```
Prop Firm Bot/
├── src/
│   ├── rules/           # encoded LucidFlex / TopStep ruleset logic
│   ├── pipeline/        # account state machines, replay, Monte Carlo
│   ├── sizing/          # fixed / dynamic sizing functions
│   ├── strategies/      # synthetic trade generators + replay adapter
│   ├── optimizer/       # parameter grid search + reset economics
│   └── data/            # TradingView XLSX loader, trade audit, replay loader
├── Analysis/
│   ├── scripts/         # replay probes, MC runners, Model A analysis, TV automation
│   └── strategy_specs/  # retired baseline specs for reference
├── Rulesets/            # official prop firm rule summaries
├── Research/
│   ├── ConfluenceResearch/  # ICT / order-flow feature library, paper leads
│   └── StrategyCapture/     # private model capture (ignored)
├── Dashboard/           # Streamlit MC dashboard
├── Tasks/               # local plan files (ignored)
├── PineScripts/         # ignored: local Pine strategy files
└── TVExports/           # ignored: local XLSX/CSV backtest exports
```

## Key modules

| Module | What it does |
|--------|-------------|
| `src/rules/topstep.py` | TopStep 50K ruleset: Combine, XFA payout, DLL, Back2Funded |
| `src/rules/lucidflex.py` | LucidFlex 50K ruleset: eval phases, funded payout, vault |
| `src/pipeline/monte_carlo.py` | Shared MC aggregation with EV and CI |
| `src/pipeline/replay_monte_carlo.py` | Block-bootstrap MC on TV export trade sequences |
| `src/pipeline/topstep_replay.py` | Deterministic TopStep replay from TV exports |
| `src/pipeline/lucidflex_replay.py` | Deterministic LucidFlex replay |
| `src/pipeline/strategy_registry.py` | Indexes all TV exports with cached MC results |
| `src/data/tv_trade_loader.py` | Loads TradingView Strategy Tester XLSX into replay days |
| `src/data/tv_trade_audit.py` | Validates and normalises TV export column formats |
| `src/optimizer/search.py` | Adaptive sizing grid search across parameter space |
| `Analysis/scripts/run_tradingview_backtest.py` | CDP automation: load Pine → export CSV → validate → registry |
| `Analysis/scripts/tv_topstep_replay_probe.py` | CLI: sweep risk amounts on a TV export through TopStep MC |
| `Analysis/scripts/tv_topstep_replay_mc.py` | Block-bootstrap MC runner for TV exports |

## Model A analysis scripts

Probes built during Phase 4 validation of the NQ key-open OTE strategy:

| Script | Purpose |
|--------|---------|
| `model_a_parent_trades.py` | Reconstitute partial fills into parent trades |
| `model_a_postpatch_compare.py` | Verify Pine execution bug fixes across TF exports |
| `model_a_open_hour_diagnosis.py` | Diagnose blow-throughs by bar/hour |
| `model_a_be_multitp_compare.py` | BE vs baseline and multi-TP comparison |
| `model_a_mfe_distribution.py` | MFE/MAE distributions by trade bucket |
| `model_a_entry_filter_probe.py` | Entry-time feature ablation |
| `model_a_notrade_filter_impact.py` | No-trade rule impact (CPI/NFP days etc.) |
| `model_a_mtf_notrade_filter_impact.py` | Same with MTF confluence score breakdown |
| `model_a_highvol_block_proxy.py` | High-vol bar block impact proxy |
| `model_a_losscap_multitp_probe.py` | Loss-cap and multi-TP parameter sweep |

## Running

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/
```

TV automation (requires TradingView open with `--remote-debugging-port=9222`):
```bash
python Analysis/scripts/run_tradingview_backtest.py --help
```

## Phase status

| Phase | Status |
|-------|--------|
| 1 — Ruleset encoding | Done |
| 2 — Account state machines + single pipeline | Done |
| 3 — Parametric MC + dynamic sizing | Done |
| 4 — TV Pine backtests + validation | Active |
| 5 — Optimizer + Streamlit dashboard | Pending |
| 6 — Live execution bot | Pending |
