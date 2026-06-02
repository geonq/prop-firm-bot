---
type: validation checklist
date: 2026-05-06
status: operator review guide
scope: checks for Claude + Codex Phase 3.5/Phase 4 work
---

# Agent Work Validation Checklist

Use this file to check whether the recent Claude + Codex work is actually
correct before trusting the conclusions or committing anything.

## 1. See Exactly What Changed

Run:

```bash
git status --short --untracked-files=all
git diff --stat
git diff --cached --stat
git diff
git diff --cached
```

What to check:

- Staged files are not automatically "approved"; they still need review.
- `Analysis/output/`, `TVExports/`, and `PineScripts/` should stay ignored.
- Coordination files should stay terse, especially `Coordination/HANDOFF.md`
  at <= 60 lines.

## 2. Run The Full Test Suite

Run:

```bash
.venv/bin/python -m pytest
```

Expected after the latest Codex work:

```text
156 passed
```

If this fails, stop. Do not trust the analysis outputs until the failing test
is understood.

## 3. Reproduce Or Spot-Check Phase 3.5 Outputs

Important files:

- `Analysis/2026-05-06_target_cell_catalog.md`
- `Analysis/2026-05-06_reset_vault_decision_sheet.md`
- `Analysis/scripts/target_cell_catalog.py`
- `Analysis/scripts/reset_vault_decision_sheet.py`
- `Analysis/output/target_cell_catalog/cells.csv`
- `Analysis/output/target_cell_catalog/manifest.json`
- `Analysis/output/reset_vault_decision_sheet/decision_sheet.csv`
- `Analysis/output/reset_vault_decision_sheet/manifest.json`

Run:

```bash
cat Analysis/output/target_cell_catalog/manifest.json
cat Analysis/output/reset_vault_decision_sheet/manifest.json
```

Check:

- Target catalog manifest says `mode=full`.
- Target catalog row count is `5940`.
- Reset/vault manifest row count is `77`.
- The markdown writeups cite the same row counts, sim counts, and headline
  recommendation as the generated CSV/manifest files.

Optional full rerun:

```bash
.venv/bin/python Analysis/scripts/target_cell_catalog.py --full
.venv/bin/python Analysis/scripts/reset_vault_decision_sheet.py
```

The catalog full rerun is slow. Only do this when you want a full reproducible
check, not for every normal session.

## 4. Review The Load-Bearing Rule Logic

These files are the highest-risk correctness surface:

- `src/rules/topstep.py`
- `src/pipeline/topstep_account.py`
- `src/pipeline/topstep_pipeline.py`
- `src/pipeline/topstep_replay.py`
- `src/rules/lucidflex.py`
- `src/pipeline/lucidflex_account.py`
- `src/pipeline/lucidflex_pipeline.py`
- `src/pipeline/lucidflex_replay.py`
- `src/pipeline/monte_carlo.py`
- `src/sizing/dynamic.py`

Manual checks:

- Trade P&L is applied before breach checks.
- Intraday MLL breaches happen immediately.
- End-of-day drawdown updates happen only at day close.
- Consistency rules use the correct daily P&L history.
- Eval/subscription fees are charged once per attempt/account.
- TopStep Back2Funded is only available before first payout.
- TopStep payout caps in simulations are labeled as simulation stops, not firm
  rules.
- No future trade/day information is used to decide current state.

## 5. Run Focused Tests For Each Risk Area

Rules:

```bash
.venv/bin/python -m pytest tests/test_rulesets.py
```

TopStep:

```bash
.venv/bin/python -m pytest \
  tests/test_topstep_account_state.py \
  tests/test_topstep_pipeline.py \
  tests/test_topstep_replay.py
```

LucidFlex:

```bash
.venv/bin/python -m pytest \
  tests/test_lucidflex_account_state.py \
  tests/test_lucidflex_pipeline.py \
  tests/test_lucidflex_replay.py
```

Monte Carlo / optimizer / catalog:

```bash
.venv/bin/python -m pytest \
  tests/test_monte_carlo.py \
  tests/test_optimizer.py \
  tests/test_target_cell_catalog.py \
  tests/test_reset_economics.py
```

TradingView replay:

```bash
.venv/bin/python -m pytest \
  tests/test_tv_trade_loader.py \
  tests/test_tv_lucidflex_replay_probe.py \
  tests/test_tv_topstep_replay_probe.py
```

## 6. Check The Phase 4 TradingView Path

Current Phase 4 candidate:

- Spec: `Analysis/strategy_specs/nq_robust_trend_v0.md`
- Local Pine draft: `PineScripts/nq_robust_trend_v0.pine` ignored by Git
- Replay probe: `Analysis/scripts/tv_topstep_replay_probe.py`

First, confirm the private Pine file is ignored:

```bash
git check-ignore -v PineScripts/nq_robust_trend_v0.pine
```

Then, after exporting a TradingView Strategy Tester XLSX into `TVExports/`,
run:

```bash
.venv/bin/python Analysis/scripts/tv_topstep_replay_probe.py \
  --xlsx TVExports/<export>.xlsx \
  --risk-amount <risk-if-export-has-no-R-column>
```

The export only passes the Phase 4 gate if the probe prints:

- `profile4=True`
- WR in `[0.40, 0.50]`
- R in `[1.7, 2.3]`
- frequency in `2-4` trades per replay weekday
- lag-10 outcome autocorr `<= 0.3`
- TopStep terminal result is not Combine breach/timeout

Also run:

```bash
.venv/bin/python Analysis/scripts/tv_topstep_replay_probe.py \
  --xlsx TVExports/<export>.xlsx \
  --risk-amount <risk-if-export-has-no-R-column> \
  --uncapped
```

This checks whether TopStep Standard vs Consistency might flip on a longer
funded horizon.

## 7. Check No Secrets Or Private Artifacts Are In The Commit

Run:

```bash
git diff --cached --name-only
git ls-files | rg '(\.env|TVExports|PineScripts|Analysis/output|strategy_params|secret|token|credentials)'
```

Expected:

- No `.env` files.
- No TradingView exports.
- No Pine strategy source.
- No generated `Analysis/output/` CSVs/manifests.
- No credentials, tokens, or account parameters.

## 8. Ask A Fresh Agent For A Strict Review

Use this prompt in a fresh Codex/Claude session:

```text
Review this repo's uncommitted changes for rule-encoding errors,
lookahead/state-ordering bugs, Monte Carlo aggregation mistakes, and
misleading analysis claims. Do not edit files. Findings first, with
file/line references. Focus on correctness, not style.
```

The reviewer should answer with bugs and risks first. If it only summarizes
the work, it did not do the review you need.

## 9. Decision Rule

Do not trust the Phase 3.5 recommendation or Phase 4 candidate until all of
these are true:

- Full test suite passes.
- Manifests match the markdown claims.
- Rule logic has been manually reviewed against the source rule docs.
- Ignored/private artifacts are not staged.
- A fresh review finds no high-severity correctness issue.
- TradingView export replay lands inside Profile 4 before any EV optimization.
