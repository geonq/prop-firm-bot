# Trading Controller Goal Tracker — 2026-07-20

Source plan: local Hermes execution plan (not committed).

Safety boundary: live trading remains locked. No real order, account mutation, or unsupported lifecycle claim is authorized.

## Execution checklist

- [x] Inspect project, live runner, ProjectX boundary, controller topology, coordination decisions, and source plan.
- [x] Implement atomic desired-state/runtime stores and command CLI with default-paper and explicit-live gates.
- [x] Add cooperative stop checkpoints, flatten retries, broker-flat distinction, and runner verification.
- [x] Implement periodic account discovery snapshots, confirmed transitions, and a durable transition-deduplicating Telegram outbox.
- [x] Add fail-closed one-account pilot policy; new accounts are monitor-only and auto-enrollment is disabled.
- [x] Integrate operator-only `/starttrading`, `/stoptrading`, `/tradingstatus`, visible menu entries, and daily dashboard into `geonqcontrollerbot`.
- [x] Install and exercise the per-user five-minute `ORBTradingSupervisorWatchdog` Scheduled Task.
- [x] Add local operational dashboard and runbook with exact credential/activation placement.
- [x] Refresh official ProjectX account/trade evidence and Topstep rule-source links; preserve unsupported lifecycle limitations.
- [x] Classify the long-history strategy audit input gate and record a machine-readable blocked artifact rather than fabricate results.
- [x] Run a research-only 70/30 study on independent 60-day Yahoo MNQ five-minute data; record that no tested literature-anchored candidate established credible OOS improvement.
- [x] Audit exact live timing and identify the completed-bar/retroactive-09:35-open fill discrepancy.
- [x] Correct completed-bar entry timing under TDD; recalculate the 4R target from the actual broker fill and synchronize engine state to exchange-confirmed values.
- [x] Run a multi-year NQ/MNQ-cost proxy study over 818 complete RTH sessions with a locked 572/246 chronological split and four-fold IS stability gate.
- [x] Strengthen the overfitting audit with CSCV/PBO, White-style block bootstrap, independent Hansen SPA, Deflated Sharpe sensitivities, a 75-config parameter neighborhood, execution-reference sensitivity, cost stress, and block-bootstrap drawdown risk.
- [x] Run compile, canonical trading suite, focused trading/control/monitor/reporting suite, focused controller suite, real fail-closed start, dashboard render, and Scheduled Task exercise.
- [x] Update the local trading HANDOFF/DECISIONS with exact behavior, evidence, and blockers.
- [x] Verify controller integration and trading watchdog recovery without enabling trading.

## Verified evidence

- Trading canonical suite after timing correction, overfitting strengthening, and pre-commit review fixes: `553 passed, 21 skipped`.
- New trading/control/monitor/reporting focused suite: `16 passed`.
- Controller integration/dashboard focused suite: `5 passed`.
- `compileall`: passed.
- Actual paper start without credentials: exit `2`, named missing `PROJECTX_USERNAME` and `PROJECTX_API_KEY`, desired state remained `stopped`, no runner/supervisor.
- Windows recovery task: `Ready`, manually invoked, `Last Result: 0`.
- Dashboard: `stopped`, `unconfigured`, recovery `Ready`, broker reconciliation unavailable, zero discovered accounts/trades.
- Controller command/dashboard integration passed; the Windows watchdog was `Ready` with result `0`; trading control remained stopped with no supervisor or runner.

- Short-sample 70/30 result: 48 Yahoo MNQ five-minute RTH sessions, 33 IS/15 untouched OOS; deployed opening drive +6.571R IS and -3.877R OOS; no tested candidate had a positive conservative IS score or positive OOS total. Full report: `Analysis/2026-07-20_mnq_parameter_deep_dive.md`.
- Live timing correction: the final 09:34 bar now completes the OR and emits the entry near 09:35; live targets use the actual market fill and engine state is resynchronized. Focused live/session/feed verification passed, and the full suite passed. Real credential-backed paper reconciliation is still required before sessions count.
- Multi-year result after executable OR-close correction: public third-party Databento-described `NQ.c.0` five-minute data produced 818 complete sessions, 572 IS/246 untouched OOS. The IS-selected relative-volume true ORB earned +53.583R IS but lost -3.237R OOS and underperformed the deployed opening drive by -0.113R/session (95% CI -0.299 to +0.059). The deployed rule earned +24.591R OOS. No replacement is authorized.
- Formal overfitting battery: CSCV/PBO 42.9% (40.0%-52.8% block sensitivity); White-style p=0.2066 and incumbent family-wise p=0.5315; independent Hansen SPA consistent p=0.0630-0.1008; DSR probability 77.5% at heuristic N_eff 1.79, 17.9% at 85 nominal trials, and 11.6% at 234 historical-trial sensitivity; 57/75 neighbors positive overall but only 17/75 positive in at least three year buckets. The strategy is not confirmed robust and retains substantial overfitting/regime risk.

## Evidenced external blockers

These require operator-provided private inputs or elapsed real-world evidence and keep live mode locked:

- ProjectX/Topstep credentials and API subscription.
- Authenticated account inventory, broker reconciliation, and final exact account selector.
- Vendor-direct multi-year one-minute history or `DATABENTO_API_KEY`; the completed multi-year public five-minute proxy has no vendor receipt or roll metadata and does not replace one-minute validation.
- Private Pine source and Strategy Tester export for exact TradingView/Python parity.
- Credential-backed paper reconciliation of corrected entry timing and actual fills.
- At least ten accepted paper sessions and personal report review.
- Complete rule-version/account-history evidence before possible passed/breached/payout labels can become confirmed.
- Explicit approval of exact live strategy/config/account/risk hashes via the local activation artifact.

## Current task

The timing correction and multi-year proxy evaluation are complete. No replacement survived untouched OOS. Review fixed the account-polling contract/path and rejected unsafe mode switching while a supervisor is active. Credential-independent implementation is complete; live remains locked pending the external evidence above.
