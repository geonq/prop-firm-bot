# Strategy Capture

This area is for translating Georg's discretionary model into a mechanical strategy before deeper paper/ICT/order-flow research.

The immediate priority is `georg_model_v1/`.

## Why This Comes First

Georg's own model produced attractive simulator geometry when represented as roughly 10% WR / 10R / $200 fixed risk. The likely edge is not a generic ICT entry. It is the selection layer:

- clean vs choppy price action
- obvious draw on liquidity
- session/regime suitability
- no-trade discipline
- target availability for high-R exits

The next research step is to capture that discretion, simulate an approximation, and only then use papers/ICT/order-flow research to improve weak parts.

## Folder Rules

- `screenshots/` is ignored by Git. Put raw chart screenshots there.
- `processed/` is tracked. Agents should summarize screenshots into compact notes.
- `specs/` is tracked. Candidate specs go here before implementation.
- `simulation/` is tracked unless it contains large generated outputs.

Skip examples are load-bearing. Do not only collect winners.
