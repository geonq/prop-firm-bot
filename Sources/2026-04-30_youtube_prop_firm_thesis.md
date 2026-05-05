---
type: source summary
role: founding thesis
medium: YouTube transcript
ingested: 2026-04-30
compressed: 2026-05-05
status: marketing claims summarized; do not treat numbers as facts
---

# Founding Thesis — Compact Summary

The original auto-transcript was removed for token discipline after its
load-bearing claims were distilled into `PROJECT_CONTEXT.md` and tested in
`Analysis/2026-04-30_founding_thesis_validation.md`.

## Core Claim To Keep

Prop-firm accounts behave like path-dependent structured products:

- downside is capped at fees/resets/activation costs
- simulated account losses are not real dollar losses
- payouts are real cashflows if the funded phase survives long enough
- therefore the objective is full-pipeline net EV, not raw strategy Sharpe or
  trader-intuitive R:R

This framing remains valid and is the reason the simulator exists.

## Transcript Claims Rejected Or Downgraded

- Claimed high-WR / low-R:R zero-EV strategies monotonically improve pass odds.
  Our TopStep sanity check found an inverted-U: too-low R:R times out; too-high
  R:R gets hurt by drawdown and consistency.
- Claimed `(20% WR, 4:1 RR)` zero-EV TopStep pass rate around `37%`. Our model
  gives roughly `10-30%` depending on sizing and consistency enforcement.
- Claimed high expected funded payouts around `$9K`, about `$300` to obtain an
  active funded account, and net EV around `$8.6K`. Treat as marketing context,
  not calibration truth.
- Claimed ORB-like strategy work as easy proof. Georg rejects ORB/TORB as a
  candidate strategy; it remains only a falsification baseline.

## Calibration Source Of Truth

Use `Analysis/2026-04-30_founding_thesis_validation.md` and
`PROJECT_CONTEXT.md` for current calibration targets.

URL and creator name were intentionally not recorded.
