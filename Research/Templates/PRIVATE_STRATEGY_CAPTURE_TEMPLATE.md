# Private Strategy Capture Template

Use this template inside a local-only strategy folder such as:

`Research/StrategyCapture/<private_model_name>/`

Do not commit filled strategy notes, screenshots, model rules, entry logic, or target/invalidation details.

## Folder Layout

```text
Research/StrategyCapture/<private_model_name>/
  screenshots/
    good_trades/
    no_trades/
    skip_examples/
    failed_trades/
  processed/
    example_notes.md
  specs/
    <private_model_name>_spec.md
  simulation/
```

## Example Notes Template

```markdown
### Example ID

- Type: good trade / no-trade / skip / failed trade
- Symbol:
- Date/time:
- Timeframes shown:
- Market context:
- Clean vs choppy decision:
- Draw on liquidity:
- Setup sequence:
- Entry trigger:
- Stop:
- Target:
- Expected R:
- Invalidation before entry:
- Management notes:
- What this example teaches:
```

## Agent Rules

- Keep raw screenshots and filled notes local-only.
- Summarize only non-sensitive progress in `Coordination/HANDOFF.md`.
- If a strategy detail is needed in a public/tracked doc, describe only the abstraction, not the rule values or entry recipe.
