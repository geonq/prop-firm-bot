"""Daily markdown report generator: LiveState/reports/YYYY-MM-DD.md.

Reads LiveState/trades.csv (append-only journal, src/live/runner.py) and
LiveState/events.jsonl (append-only event log) -- performs no I/O beyond
those two files plus writing the report itself. Contents (per Tasks/todo.md
"Phase 6B" spec):
  - today's signal/trade vs modeled expectation (from LiveOrderFilled
    events' recorded slippage_vs_model, and the trade row's own gross vs
    net figures)
  - realized slippage vs the 1-tick model (same slippage_vs_model figure,
    aggregated)
  - running trailing-40 shadow-R -- explicitly labeled "ops health metric
    -- failed validation as a hard gate; human judgment only" (see
    Analysis/2026-07-18_orb_verdict.md-adjacent Phase 6A-R findings: this
    project already falsified trailing-shadow-R as an admissible TRADING
    gate; it is retained here ONLY as a human-readable ops signal, never
    used to alter engine behavior)
  - cumulative live-vs-model reconciliation stats (mean/max abs entry
    slippage, trade count, win rate, mean R, all-time)
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from src.live.config import PARAMS_HASH


def _read_trades(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="") as f:
        return list(csv.DictReader(f))


def _read_events(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.exists():
        return []
    events = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _trailing_r(trades: list[dict], *, k: int = 40) -> float | None:
    recent = trades[-k:]
    if not recent:
        return None
    values = [float(t["r_multiple"]) for t in recent if t.get("r_multiple") not in (None, "")]
    if not values:
        return None
    return sum(values) / len(values)


def _slippage_events_for_date(events: list[dict], session_date: date) -> list[dict]:
    return [
        e
        for e in events
        if e.get("event") == "LiveOrderFilled"
        and e.get("role") == "entry"
        and "slippage_vs_model" in e
    ]


# Event types that represent a genuine, unresolved live-money risk and must
# be surfaced at the TOP of the report, not buried -- reviewer Fix 3
# (2026-07-19, CRITICAL) requires the daily report to make a naked-position/
# naked-order alarm "prominent." Kept as an explicit list (not "any event
# with Alarm in the name") so this stays a deliberate, reviewed set.
ALARM_EVENT_TYPES = ("NakedPositionAlarm", "NakedOrderAlarm")


def _alarm_events_for_date(events: list[dict], session_date: date) -> list[dict]:
    target = session_date.isoformat()
    return [
        e
        for e in events
        if e.get("event") in ALARM_EVENT_TYPES and (e.get("session_date") == target or e.get("session_date") is None)
    ]


def build_daily_report_markdown(*, session_date: date, state_dir: Path) -> str:
    trades = _read_trades(state_dir / "trades.csv")
    events = _read_events(state_dir / "events.jsonl")

    today_trades = [t for t in trades if t.get("session_date") == session_date.isoformat()]
    today_slippage_events = _slippage_events_for_date(events, session_date)
    alarms = _alarm_events_for_date(events, session_date)

    lines: list[str] = []
    lines.append(f"# Daily report — {session_date.isoformat()}")
    lines.append("")

    if alarms:
        lines.append("## :rotating_light: ALARM — unresolved live-money risk, act now")
        lines.append("")
        for e in alarms:
            event_name = e.get("event")
            message = e.get("message", "")
            lines.append(f"- **{event_name}**: {message}")
            for key in ("order_id", "contracts", "direction", "attempts", "last_error"):
                if key in e and e[key] is not None:
                    lines.append(f"  - {key}: {e[key]}")
        lines.append("")
        lines.append(
            "**Verify directly on the TopStepX platform before assuming anything about "
            "this account's real position/orders — do not trust only this report.**"
        )
        lines.append("")

    lines.append(f"params_hash: `{PARAMS_HASH}`")
    lines.append("")

    lines.append("## Today's signal/trade vs modeled expectation")
    if not today_trades:
        no_trade_events = [e for e in events if e.get("session_date") == session_date.isoformat() and e.get("event") in ("NoTradeToday", "TradeSkippedZeroContracts", "LiveFeedSkipDay")]
        if no_trade_events:
            for e in no_trade_events:
                lines.append(f"- {e.get('event')}: {e.get('reason', e)}")
        else:
            lines.append("- No trade recorded today.")
    else:
        for t in today_trades:
            lines.append(
                f"- {t['direction']} {t['contracts']}x, entry {t['entry_price']}, exit {t['exit_price']} "
                f"({t['exit_reason']}), gross R={float(t['r_multiple']):.3f}, net R={float(t.get('net_r', 'nan') or 'nan'):.3f}, "
                f"gross P&L=${float(t['pnl_usd']):.2f}, net P&L=${float(t.get('net_pnl_usd', 'nan') or 'nan'):.2f}"
            )
        if today_slippage_events:
            for e in today_slippage_events:
                lines.append(f"- entry slippage vs model: {e['slippage_vs_model']:+.3f} points (modeled entry {e.get('modeled_entry_price')})")
    lines.append("")

    lines.append("## Realized slippage vs 1-tick model")
    all_slippage = [
        e["slippage_vs_model"] for e in events if e.get("event") == "LiveOrderFilled" and e.get("role") == "entry" and "slippage_vs_model" in e
    ]
    if all_slippage:
        mean_slip = sum(all_slippage) / len(all_slippage)
        max_abs_slip = max(abs(s) for s in all_slippage)
        lines.append(f"- n={len(all_slippage)}, mean={mean_slip:+.4f} pts, max|slip|={max_abs_slip:.4f} pts")
        lines.append(f"  (modeled slippage assumption: 1 tick = {0.25} pts; positive = worse than modeled)")
    else:
        lines.append("- No live/paper fills recorded yet (replay-mode trades do not populate this).")
    lines.append("")

    lines.append("## Trailing-40 shadow-R (ops health metric)")
    lines.append(
        "**Labeled explicitly: this is an ops health signal, not a trading gate.** "
        "Phase 6A-R (Tasks/todo.md) found trailing shadow-ORB R does NOT pass the "
        "pre-registered worst-fold-positive admissibility test as a regime filter — "
        "it failed validation as a hard gate. It is shown here ONLY so a human "
        "glancing at this report can sanity-check recent performance; it must never "
        "be wired back into engine/sizing/gating logic."
    )
    trailing = _trailing_r(trades, k=40)
    if trailing is not None:
        lines.append(f"- trailing-40 mean gross R: {trailing:+.4f} (n={min(40, len(trades))} of {len(trades)} total trades)")
    else:
        lines.append("- Not enough trade history yet.")
    lines.append("")

    lines.append("## Cumulative live-vs-model reconciliation")
    if trades:
        n = len(trades)
        wins = sum(1 for t in trades if float(t["r_multiple"]) > 0)
        mean_r = sum(float(t["r_multiple"]) for t in trades) / n
        mean_net_r_vals = [float(t["net_r"]) for t in trades if t.get("net_r") not in (None, "", "nan")]
        mean_net_r = sum(mean_net_r_vals) / len(mean_net_r_vals) if mean_net_r_vals else float("nan")
        total_pnl = sum(float(t["pnl_usd"]) for t in trades)
        total_net_pnl_vals = [float(t["net_pnl_usd"]) for t in trades if t.get("net_pnl_usd") not in (None, "")]
        total_net_pnl = sum(total_net_pnl_vals) if total_net_pnl_vals else float("nan")
        lines.append(f"- all-time: n={n}, win_rate={wins / n:.4f}, mean_gross_R={mean_r:+.4f}, mean_net_R={mean_net_r:+.4f}")
        lines.append(f"- all-time P&L: gross=${total_pnl:.2f}, net=${total_net_pnl:.2f}")
    else:
        lines.append("- No trades recorded yet.")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_daily_report(*, session_date: date, state_dir: Path) -> Path:
    reports_dir = state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{session_date.isoformat()}.md"
    path.write_text(build_daily_report_markdown(session_date=session_date, state_dir=state_dir))
    return path
