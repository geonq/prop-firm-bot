# Georg Model V1 Capture

Use this folder tomorrow to capture Georg's discretionary strategy before deeper external research.

## What Georg Should Add

Put screenshots into:

- `screenshots/good_trades/`
- `screenshots/no_trades/`
- `screenshots/skip_examples/`
- `screenshots/failed_trades/`

The screenshot folders are ignored by Git.

For each example, add a short note in `processed/example_notes.md` or tell the agent verbally:

- market/date/time/symbol/timeframe
- why price action was clean or choppy
- draw on liquidity
- entry trigger
- stop location
- target and why high R was available
- invalidation before entry
- reason to skip, if skipped

## Agent Task

1. Convert examples into a mechanical rule draft.
2. Identify which decisions are still discretionary.
3. Separate selection filters from entry triggers.
4. Write `specs/georg_model_v1_spec.md`.
5. Only then simulate a rough version.

## Target Geometry

Initial simulator target from Georg:

- WR about 10%
- Average R about 10
- Fixed risk about $200

Do not assume these are achieved by the mechanical version. They are the distribution to approximate and test.
