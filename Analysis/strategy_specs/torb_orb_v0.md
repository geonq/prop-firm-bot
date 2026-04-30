---
type: strategy spec
date: 2026-04-30
author: Codex
status: v0 baseline spec; not proprietary strategy source
related_shortlist: Analysis/2026-04-30_strategy_shortlist_nq_prop_firm.md
---

# TORB / ORB V0 Strategy Spec

## Purpose

This is the first backtestable baseline strategy for the prop-firm Monte Carlo engine. It is intentionally simple and mechanical. Its job is not to be the final trading system; its job is to produce a clean NQ/MNQ trade distribution that can be pushed through the account simulator.

The target path shape is:

- enough daily movement to reach eval targets before timeout
- controlled downside per trade
- limited trade count so costs and churn do not dominate
- R:R centered around the 1:1 to 2:1 zone suggested by the founding-thesis sanity check
- no dependence on discretionary bias

## Instrument And Session

Use NQ or MNQ continuous front contract data.

All strategy decisions use New York time.

| Field | Value |
|---|---|
| Primary session | CME equity index regular trading window aligned to US cash market |
| Opening anchor | 09:30:00 New York |
| Last allowed entry | 11:30:00 New York for v0 |
| Forced flat time | 15:45:00 New York |
| Overnight holding | false |
| Max completed trades per day | 1 for v0 |
| Direction | long and short |

No trade may use information from a bar before that bar has closed. If implementation uses bar-close signals, entries execute on the next bar.

## Required Input Columns

Minimum 1-minute bar input:

| Column | Meaning |
|---|---|
| `timestamp` | timezone-aware timestamp, convertible to New York time |
| `open` | bar open |
| `high` | bar high |
| `low` | bar low |
| `close` | bar close |
| `volume` | bar volume |
| `contract` | active contract identifier or continuous-contract label |

Derived fields:

| Field | Definition |
|---|---|
| `session_date` | New York date of the cash session |
| `minutes_from_open` | minutes since 09:30 New York |
| `prior_rth_close` | previous regular-session close |
| `overnight_return` | return from prior RTH close to 09:30 open |
| `range_width_points` | opening range high minus opening range low |
| `range_width_pctile` | rolling percentile of opening range width |
| `realized_vol_pctile` | rolling percentile of intraday realized volatility |

## Baseline Opening Range

For each `session_date`, define an opening range window starting at 09:30.

Parameter `opening_minutes` values:

- 1
- 3
- 5
- 10
- 15
- 30

For a given `opening_minutes`:

- `or_start = 09:30:00`
- `or_end = 09:30:00 + opening_minutes`
- `or_high = max(high)` for bars fully inside the window
- `or_low = min(low)` for bars fully inside the window
- `or_mid = (or_high + or_low) / 2`
- `or_width = or_high - or_low`

No entry is allowed before `or_end`.

## No-Trade Filters

Apply filters before looking for breakout entries.

Initial v0 filters:

| Filter | Rule | Purpose |
|---|---|---|
| Minimum range width | `or_width >= min_range_points` | avoid dead/noise opens |
| Maximum range width | `or_width <= max_range_points` | avoid stop sizes too large for prop drawdown |
| Range percentile | only trade selected `range_width_pctile` bucket | test whether mid-sized ranges are best |
| Volatility bucket | low, medium, high realized-vol bucket | separate timeout days from breach-risk days |
| Event filter | optional; off by default in v0 | later exclude CPI/FOMC/NFP opens |

Initial parameter grid:

| Parameter | Values |
|---|---|
| `min_range_points` | 10, 20, 30 |
| `max_range_points` | 80, 120, 160 |
| `range_width_pctile_bucket` | 20-80, 30-70, 40-80, unrestricted |
| `realized_vol_bucket` | low, medium, high, unrestricted |

Reject any parameter combination that leaves too few trades for validation. First-pass minimum: 150 trades across the sample, with at least 50 in the out-of-sample period.

## Entry Rules

### Breakout Entry

Long setup:

- no trade has completed for the day
- no-trade filters pass
- current time is after `or_end`
- current time is before or equal to `last_allowed_entry`
- price closes above `or_high + breakout_buffer_ticks * tick_size`

Short setup:

- no trade has completed for the day
- no-trade filters pass
- current time is after `or_end`
- current time is before or equal to `last_allowed_entry`
- price closes below `or_low - breakout_buffer_ticks * tick_size`

Execution assumption for v0:

- signal is detected on bar close
- entry fills at next bar open plus slippage

Parameter grid:

| Parameter | Values |
|---|---|
| `breakout_buffer_ticks` | 0, 1, 2, 4 |
| `last_allowed_entry` | 10:30, 11:30 |

If both long and short triggers occur on the same signal bar, skip the day. That usually means the implementation is using a malformed bar or a volatility event too large for v0.

## Stop Rules

Test stop modes independently. Do not combine them in v0.

| Stop Mode | Long Stop | Short Stop |
|---|---|---|
| opposite_range | `or_low - stop_buffer_ticks * tick_size` | `or_high + stop_buffer_ticks * tick_size` |
| midpoint | `or_mid` | `or_mid` |
| half_range | `entry_price - 0.5 * or_width` | `entry_price + 0.5 * or_width` |
| atr | `entry_price - atr_mult * atr_points` | `entry_price + atr_mult * atr_points` |

Initial parameter grid:

| Parameter | Values |
|---|---|
| `stop_mode` | opposite_range, midpoint, half_range, atr |
| `stop_buffer_ticks` | 0, 2 |
| `atr_lookback` | 14, 20 |
| `atr_mult` | 0.75, 1.0, 1.25 |

Discard trades where stop distance is zero or below the minimum tick value.

## Target And Exit Rules

Target:

- long target: `entry_price + rr * stop_distance`
- short target: `entry_price - rr * stop_distance`

Parameter grid:

| Parameter | Values |
|---|---|
| `rr` | 0.75, 1.0, 1.25, 1.5, 2.0 |

Time exits:

| Parameter | Values |
|---|---|
| `time_exit` | 10:30, 11:30, 12:00, 15:45 |

Exit priority for a bar where stop and target are both touched:

1. Conservative v0 assumption: stop fills first.
2. Record a `same_bar_stop_target=true` flag for later sensitivity testing.

Forced flat:

- all open trades exit at `forced_flat_time`
- v0 uses next available bar open or close consistently; implementation must record which fill policy was used

## Costs And Slippage

Every backtest must report gross and net results.

Initial assumptions:

| Item | NQ | MNQ |
|---|---:|---:|
| Tick size | 0.25 points | 0.25 points |
| Point value | $20 | $2 |
| Tick value | $5 | $0.50 |
| Slippage first pass | 1 tick per side | 1 tick per side |
| Commission | parameterized | parameterized |

Use MNQ-equivalent sizing in the simulator even if the source backtest is NQ. The first question is path geometry; contract sizing comes after.

## Conditional State Features

These features must be exported with every trade even if v0 does not filter on them yet:

| Feature | Definition |
|---|---|
| `prior_rth_return` | prior regular-session close-to-close return |
| `overnight_return` | prior RTH close to current RTH open |
| `gap_bucket` | opening gap percentile bucket |
| `weekday` | Monday through Friday |
| `realized_vol_bucket` | rolling realized-volatility percentile bucket |
| `or_width_bucket` | opening-range width percentile bucket |
| `first_30m_return` | 09:30 to 10:00 return |
| `first_60m_return` | 09:30 to 10:30 return |

These fields support the next phase: conditional momentum/reversal selection.

## Output Trade Schema

Every completed trade export must include:

| Column | Meaning |
|---|---|
| `strategy_id` | parameter-set identifier |
| `session_date` | New York session date |
| `symbol` | NQ/MNQ/continuous symbol |
| `direction` | long or short |
| `entry_time` | timestamp |
| `entry_price` | fill price |
| `exit_time` | timestamp |
| `exit_price` | fill price |
| `exit_reason` | target, stop, time_exit, forced_flat |
| `qty` | contracts in source backtest |
| `gross_pnl_points` | points before costs |
| `gross_pnl_usd` | dollars before costs |
| `net_pnl_usd` | dollars after costs |
| `risk_points` | entry to stop distance |
| `r_multiple` | net or gross R multiple; must specify |
| `or_minutes` | opening range window |
| `or_width_points` | range width |
| `rr` | configured target multiple |
| `stop_mode` | configured stop mode |
| `same_bar_stop_target` | boolean |
| `features_json` | serialized conditional features if flat columns are inconvenient |

## Raw Backtest Acceptance Gates

Before running the prop-firm simulator, a parameter set must pass basic sanity gates:

- no lookahead bias
- at least 150 trades total
- at least 50 out-of-sample trades
- average loss is close to planned stop after costs
- same-bar stop/target ambiguity is reported
- results are shown gross and net of costs
- no single trade contributes more than 20% of total gross profit

These gates are not final profitability requirements. They prevent bad data from entering the prop-firm simulator.

## Prop-Firm Simulator Acceptance Gates

A parameter set is worth deeper work only if it improves account-level behavior versus the zero-EV baseline:

- higher net EV after eval fee
- higher pass probability without unacceptable consistency violations
- lower or equal timeout probability versus high-WR grinder profiles
- breach probability acceptable under multiple Monte Carlo seeds
- funded-phase payout expectation is not destroyed by the eval-optimized sizing

Track results separately for LucidFlex and TopStep because consistency and drawdown mechanics differ.

## First Implementation Order

1. Implement the raw ORB/TORB trade generator with only `opening_minutes`, `breakout_buffer_ticks`, `stop_mode`, `rr`, and `time_exit`.
2. Validate fills visually on a small set of hand-picked days.
3. Export trade schema.
4. Run gross/net raw stats.
5. Add range-width and realized-volatility filters.
6. Feed trade sequences into the prop-firm simulator.
7. Only then add conditional momentum/reversal state.

## Explicit Non-Goals For V0

- no machine learning
- no discretionary ICT/bias inputs
- no news prediction
- no multi-account allocation
- no live execution assumptions
- no optimizer-picked "best cell" without walk-forward validation

## Open Questions

- Which data source will provide reliable 1-minute NQ/MNQ history?
- Will the first implementation be TradingView Pine, Python, or both?
- What commission/slippage assumptions should be used for NQ and MNQ?
- Should macro-event filters be introduced in v0 or reserved for v1?
- What out-of-sample split should be standard: chronological 70/30, yearly walk-forward, or regime-based split?
