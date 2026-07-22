"""CLI runner: wires BarFeed -> ORBLiveEngine -> Broker, journals trades, persists daily state.

Usage:
    python3 -m src.live.runner --mode replay --start 2025-07-01 --end 2026-07-15
    python3 -m src.live.runner --preflight
    python3 -m src.live.runner --mode paper --auto
    python3 -m src.live.runner --mode live --auto

`--mode paper`/`--mode live` (Phase 6B, src/live/live_runner.py) run ONE
real trading session (today) against the real ProjectX/TopstepX API via
`src.live.feed.LiveBarFeed`: `paper` uses `PaperBroker` (simulated fills on
real live prices -- the paper-parallel reconciliation instrument),
`live` uses `LiveBroker` (real orders). `--preflight` validates creds,
auth, account/contract lookup, a bars smoke-fetch, both params hashes, and
local clock vs ET WITHOUT placing any order. `--auto` self-gates on the
session calendar (skips weekends/already-traded), waits until 09:25 ET,
runs the session, writes a daily report (src/live/report.py), and exits --
see RUNBOOK_LIVE.md for the full operator sequence and scripts/launchd/ for
unattended scheduling.

State/journal files (all under LiveState/, gitignored):
- `LiveState/trades.csv`         — one row per closed trade (append-only journal)
- `LiveState/events.jsonl`       — one JSON object per engine event (append-only)
- `LiveState/state.json`         — current day's trade-taken flag + open-position
                                    snapshot, so a restart mid-session cannot
                                    double-enter or lose track of an open position

Kill-switch guards, all checked at startup / per-bar:
- params-hash tamper check (`src.live.config.verify_params_hash`) — refuses
  to start on any drift from the holdout-recorded FROZEN_PARAMS (BOTH the
  holdout-provenance hash and the full-config hash, see src/live/config.py).
- daily loss cap (`--daily-loss-cap`, default $600), checked TWO ways
  (reviewer Fix 3, 2026-07-18):
  1. Per-bar MARK-TO-MARKET check, run BEFORE the bar is handed to the
     engine: realized P&L so far today + unrealized P&L on any still-open
     position at that bar's CLOSE. This is the guard that actually matters
     for gap risk — the engine's own stop-hit fill always reports the
     MODELED stop price (mirrors src.backtest.orb._walk_to_exit's
     deliberate gap-through-optimism convention), so a bar that gaps far
     past the stop would otherwise get closed "at the stop" by the engine
     before a post-hoc realized check ever saw the real damage. On breach:
     flattens at that bar's close, halts new entries for the rest of the
     session, and tells the engine (via `ORBLiveEngine.restore_session`)
     the session is done.
  2. A realized-only backstop AFTER the engine's own on_bar() processing,
     for the case where a trade closed via normal stop/target/time_stop/eod
     logic on this same bar and that realized loss alone breaches the cap.
  Invariant (see `tests/test_live_daily_loss_cap.py`): a NORMAL (non-gap)
  at-stop loss at the default $400 risk budget must NEVER trip the $600
  cap — the cap exists for gap/tail risk, not ordinary losing trades.
- flatten-on-unhandled-exception: any exception escaping the per-bar loop
  triggers a best-effort flatten of an open position before re-raising.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from src.live.broker import FilledTrade, PaperBroker, PositionSnapshot
from src.live.config import (
    DEFAULT_DAILY_LOSS_CAP_USD,
    DEFAULT_MAX_CONTRACTS,
    FROZEN_PARAMS,
    MNQ,
    MNQ_COMMISSION_USD_PER_SIDE,
    PARAMS_HASH,
    RISK_PER_TRADE_USD,
    verify_params_hash,
)
from src.live.engine import ORBLiveEngine
from src.live.feed import Bar, ReplayFeed
from src.live.sizing import contracts_for

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2015-01-01_2026-07-16.parquet"
DEFAULT_STATE_DIR = ROOT / "LiveState"

# gross columns unchanged (pnl_usd/r_multiple = PaperBroker's fills, no
# commission -- this is what makes parity exact, see src/live/broker.py).
# net_pnl_usd/net_r are ADDITIVE (reviewer commission adjudication,
# 2026-07-18): gross P&L minus a modeled MNQ_COMMISSION_USD_PER_SIDE per
# contract per side, computed here in the journal layer only -- PaperBroker
# and FilledTrade themselves are untouched.
TRADE_CSV_FIELDS = [
    "session_date",
    "direction",
    "entry_ts",
    "entry_price",
    "exit_ts",
    "exit_price",
    "exit_reason",
    "contracts",
    "risk_points",
    "r_multiple",
    "pnl_usd",
    "net_pnl_usd",
    "net_r",
    "params_hash",
]


def _net_economics(trade: FilledTrade) -> tuple[float, float]:
    """(net_pnl_usd, net_r): gross fills minus a modeled commission, additive
    to (never replacing) the gross pnl_usd/r_multiple columns. Commission is
    `MNQ_COMMISSION_USD_PER_SIDE` per contract per side (2 sides per round
    trip), charged on the ACTUAL sized contract count (`trade.contracts`) --
    see src/live/config.py::MNQ_COMMISSION_USD_PER_SIDE for why this is not
    the backtest's NQ-scaled commission constant.
    """
    commission_usd = 2 * MNQ_COMMISSION_USD_PER_SIDE * trade.contracts
    net_pnl_usd = trade.pnl_usd - commission_usd
    risk_usd = trade.risk_points * trade.point_value * trade.contracts
    net_r = net_pnl_usd / risk_usd if risk_usd > 0 else float("nan")
    return net_pnl_usd, net_r


class RunnerState:
    """Loads/saves LiveState/state.json: today's trade-taken flag + open-position snapshot.

    Restart safety: if the runner is killed and restarted mid-session, the
    reloaded state must refuse a second entry for a date that already has
    `trade_taken=True`, and must restore any open-position snapshot so the
    engine/broker can be made consistent again (see `runner.py`'s startup
    reconciliation in `run_replay`/`_run_session`).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.session_date: date | None = None
        self.trade_taken: bool = False
        self.realized_pnl_usd: float = 0.0
        self.position: PositionSnapshot | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text())
        if raw.get("session_date"):
            self.session_date = date.fromisoformat(raw["session_date"])
        self.trade_taken = bool(raw.get("trade_taken", False))
        self.realized_pnl_usd = float(raw.get("realized_pnl_usd", 0.0))
        pos = raw.get("position")
        self.position = PositionSnapshot.from_dict(pos) if pos else None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "trade_taken": self.trade_taken,
            "realized_pnl_usd": self.realized_pnl_usd,
            "position": self.position.to_dict() if self.position else None,
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def roll_to_session(self, session_date: date) -> None:
        """Reset the trade-taken flag/realized P&L when a NEW session_date begins.

        A restart within the SAME session_date must NOT reset trade_taken —
        that's the whole point of the restart-recovery guarantee.
        """
        if self.session_date != session_date:
            self.session_date = session_date
            self.trade_taken = False
            self.realized_pnl_usd = 0.0
            self.position = None
            self.save()


class TradeJournal:
    """Append-only CSV trade journal + JSONL event log under LiveState/."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = state_dir / "trades.csv"
        self.jsonl_path = state_dir / "events.jsonl"
        if not self.csv_path.exists():
            with self.csv_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=TRADE_CSV_FIELDS)
                writer.writeheader()

    def record_trade(self, trade: FilledTrade) -> None:
        net_pnl_usd, net_r = _net_economics(trade)
        row = {
            "session_date": trade.session_date.isoformat(),
            "direction": trade.direction,
            "entry_ts": str(trade.entry_ts),
            "entry_price": trade.entry_price,
            "exit_ts": str(trade.exit_ts),
            "exit_price": trade.exit_price,
            "exit_reason": trade.exit_reason,
            "contracts": trade.contracts,
            "risk_points": trade.risk_points,
            "r_multiple": trade.r_multiple,
            "pnl_usd": trade.pnl_usd,
            "net_pnl_usd": net_pnl_usd,
            "net_r": net_r,
            "params_hash": PARAMS_HASH,
        }
        with self.csv_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_CSV_FIELDS)
            writer.writerow(row)

    def record_event(self, event_type: str, payload: dict) -> None:
        record = {"event": event_type, **payload}
        with self.jsonl_path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")


def _event_payload(ev) -> dict:
    d = asdict(ev) if hasattr(ev, "__dataclass_fields__") else {"repr": repr(ev)}
    return {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in d.items()}


def _flatten_and_record(
    *,
    broker: PaperBroker,
    journal: TradeJournal,
    runner_state: RunnerState,
    filled_trades: list[FilledTrade],
    exit_ts,
    exit_price: float,
    exit_reason: str,
) -> FilledTrade | None:
    """Shared flatten-then-journal-then-persist path (used by the daily-loss
    kill switch and the flatten-on-error handler) so the bookkeeping for
    "close whatever is open, journal it, fold it into realized P&L, persist
    state" only exists in one place.
    """
    trade = broker.flatten(exit_ts=exit_ts, exit_price=exit_price, exit_reason=exit_reason)
    if trade is None:
        return None
    filled_trades.append(trade)
    journal.record_trade(trade)
    runner_state.realized_pnl_usd += trade.pnl_usd
    runner_state.position = None
    runner_state.save()
    return trade


def run_replay(
    *,
    start: str,
    end: str,
    parquet_path: Path = DEFAULT_PARQUET,
    state_dir: Path = DEFAULT_STATE_DIR,
    risk_per_trade_usd: float = RISK_PER_TRADE_USD,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    daily_loss_cap_usd: float = DEFAULT_DAILY_LOSS_CAP_USD,
) -> list[FilledTrade]:
    """Run the engine over a historical replay window. Returns the list of filled trades."""
    verify_params_hash()

    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)
    broker = PaperBroker(point_value=MNQ.point_value)
    journal = TradeJournal(state_dir)
    runner_state = RunnerState(state_dir / "state.json")

    feed = ReplayFeed(parquet_path, start=start, end=end)
    filled_trades: list[FilledTrade] = []

    for session in feed.sessions:
        was_restored = runner_state.session_date == session.session_date and runner_state.trade_taken
        runner_state.roll_to_session(session.session_date)

        if was_restored:
            # Restart mid-day (or mid-position): tell the engine not to re-decide
            # entry for a session that already has a trade recorded. If a
            # position was open at persist time, seed the broker with it too so
            # stop/target/time_stop management (and the eventual TradeClosed
            # journal entry) still happens for the resumed position.
            pos = runner_state.position
            engine.restore_session(
                session_date=session.session_date,
                trade_taken=True,
                direction=pos.direction if pos else None,
                entry_ts=pd.Timestamp(pos.entry_ts) if pos else None,
                entry_price=pos.entry_price if pos else None,
                stop_price=pos.stop_price if pos else None,
                target_price=pos.target_price if pos else None,
                risk_points=pos.risk_points if pos else None,
            )
            if pos is not None and broker.position is None:
                broker.place_bracket(
                    session_date=pos.session_date,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    stop_price=pos.stop_price,
                    target_price=pos.target_price,
                    contracts=pos.contracts,
                    entry_ts=pos.entry_ts,
                )

        halted = False
        last_bar: Bar | None = None
        try:
            for ts, row in session.bars.iterrows():
                bar = Bar(
                    ts=ts,
                    session_date=session.session_date,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                last_bar = bar

                # Per-bar mark-to-market daily-loss check (reviewer Fix 3, 2026-07-18)
                # -- runs BEFORE engine.on_bar(bar), not after. This ordering is
                # load-bearing: the engine's own stop-hit fill always reports the
                # MODELED stop price (fill_price(state.stop_price, ...)), mirroring
                # src.backtest.orb._walk_to_exit's deliberate "gap-through optimism"
                # convention -- so a bar whose low/high blows straight through the
                # stop by a huge margin still gets closed by the engine's own
                # TradeClosed event as if it filled AT the stop. If this check ran
                # AFTER engine.on_bar, the position would already be flat (closed at
                # the optimistic stop price) by the time this check looked, and the
                # real gap loss would never be seen. Marking to THIS bar's close
                # (per spec) while the position is still open (i.e. before the
                # engine has had a chance to close it this bar) is what lets the
                # kill switch see the real exposure instead of the modeled one.
                if not halted and broker.position is not None:
                    mtm_pnl = runner_state.realized_pnl_usd + broker.unrealized_pnl_usd(bar.close)
                    if mtm_pnl <= -abs(daily_loss_cap_usd):
                        halted = True
                        _flatten_and_record(
                            broker=broker,
                            journal=journal,
                            runner_state=runner_state,
                            filled_trades=filled_trades,
                            exit_ts=bar.ts,
                            exit_price=bar.close,
                            exit_reason="daily_loss_cap",
                        )
                        journal.record_event(
                            "DailyLossCapHit",
                            {
                                "session_date": str(session.session_date),
                                "mark_to_market_pnl_usd": mtm_pnl,
                                "cap_usd": daily_loss_cap_usd,
                                "flattened_at_bar_ts": str(bar.ts),
                                "flattened_at_close": bar.close,
                            },
                        )
                        # Tell the engine this session is done (no more entries, no
                        # dangling open-position state to manage) using its own
                        # tested restart-recovery mechanism -- restore_session with
                        # direction=None means "trade already taken, flat" (see
                        # src/live/engine.py). Without this, the engine would still
                        # think it has an open position and try to manage/exit a
                        # broker position that no longer exists.
                        engine.restore_session(session_date=session.session_date, trade_taken=True, direction=None)

                events = engine.on_bar(bar) if not halted else []
                for ev in events:
                    ev_type = type(ev).__name__
                    journal.record_event(ev_type, _event_payload(ev))

                    if ev_type == "TradeOpened":
                        if halted or runner_state.trade_taken:
                            continue  # guard: engine should not have opened, but belt+suspenders
                        stop_points = ev.risk_points
                        contracts = contracts_for(
                            stop_points,
                            risk_per_trade_usd=risk_per_trade_usd,
                            point_value=MNQ.point_value,
                            max_contracts=max_contracts,
                        )
                        if contracts == 0:
                            # Risk/contract exceeds budget: skip the trade entirely.
                            # The engine has already opened its internal position
                            # state; immediately flatten it broker-side as a 0-size
                            # no-op and mark the day used (matches "skip trade" spec).
                            runner_state.trade_taken = True
                            runner_state.save()
                            journal.record_event(
                                "TradeSkippedZeroContracts", {"session_date": str(session.session_date), "stop_points": stop_points}
                            )
                            continue
                        snapshot = broker.place_bracket(
                            session_date=ev.session_date,
                            direction=ev.direction,
                            entry_price=ev.entry_price,
                            stop_price=ev.stop_price,
                            target_price=ev.target_price,
                            contracts=contracts,
                            entry_ts=ev.entry_ts,
                        )
                        runner_state.trade_taken = True
                        runner_state.position = snapshot
                        runner_state.save()

                    elif ev_type == "TradeClosed":
                        if broker.position is None:
                            continue  # trade was skipped (0 contracts) -> nothing to close
                        trade = broker.close_position(
                            exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason
                        )
                        filled_trades.append(trade)
                        journal.record_trade(trade)
                        runner_state.realized_pnl_usd += trade.pnl_usd
                        runner_state.position = None
                        runner_state.save()

                # Realized-only backstop: catches the case where a trade closed via
                # NORMAL engine logic on THIS bar's on_bar() call (stop/target/
                # time_stop/eod, handled by the TradeClosed branch above) and that
                # realized loss alone already breaches the cap -- distinct from the
                # pre-on_bar mark-to-market check above, which only runs while a
                # position was still open BEFORE this bar was handed to the engine.
                # Under FROZEN_PARAMS' max-1-trade/day this mainly matters for a
                # same-bar entry+stop-out (a wide-enough single-bar move) whose
                # realized loss alone exceeds the cap; kept as an explicit, named
                # check rather than folded into the mark-to-market branch so both
                # code paths stay independently readable.
                if not halted and runner_state.realized_pnl_usd <= -abs(daily_loss_cap_usd):
                    halted = True
                    journal.record_event(
                        "DailyLossCapHit",
                        {
                            "session_date": str(session.session_date),
                            "realized_pnl_usd": runner_state.realized_pnl_usd,
                            "cap_usd": daily_loss_cap_usd,
                        },
                    )

            if last_bar is not None:
                end_events = engine.on_session_end(last_bar)
                for ev in end_events:
                    journal.record_event("TradeClosed", _event_payload(ev))
                    if broker.position is not None:
                        trade = broker.close_position(
                            exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason
                        )
                        filled_trades.append(trade)
                        journal.record_trade(trade)
                        runner_state.realized_pnl_usd += trade.pnl_usd
                        runner_state.position = None
                        runner_state.save()

        except Exception:
            # Flatten-on-unhandled-exception: best-effort close using the last seen
            # bar's close before propagating, so a crash never leaves a position
            # silently open with no journal record.
            if broker.position is not None and last_bar is not None:
                _flatten_and_record(
                    broker=broker,
                    journal=journal,
                    runner_state=runner_state,
                    filled_trades=filled_trades,
                    exit_ts=last_bar.ts,
                    exit_price=last_bar.close,
                    exit_reason="flatten_on_error",
                )
                journal.record_event("FlattenOnError", {"traceback": traceback.format_exc()})
            raise

    return filled_trades


def _print_summary(trades: list[FilledTrade]) -> None:
    n = len(trades)
    if n == 0:
        print("No trades.")
        return
    wins = sum(1 for t in trades if t.r_multiple > 0)
    mean_r = sum(t.r_multiple for t in trades) / n
    total_pnl = sum(t.pnl_usd for t in trades)
    print(f"trades={n}  win_rate={wins / n:.4f}  mean_r={mean_r:.6f}  total_pnl_usd={total_pnl:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["replay", "paper", "live"], required=False)
    parser.add_argument("--start", type=str, help="YYYY-MM-DD (replay mode)")
    parser.add_argument("--end", type=str, help="YYYY-MM-DD (replay mode)")
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--control-dir", type=Path, default=None, help="cooperative control-state directory")
    parser.add_argument("--risk", type=float, default=RISK_PER_TRADE_USD)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--daily-loss-cap", type=float, default=DEFAULT_DAILY_LOSS_CAP_USD)
    parser.add_argument("--account-name", type=str, default=None, help="disambiguate if >1 tradable account")
    parser.add_argument("--preflight", action="store_true", help="validate creds/auth/account/contract/clock, place no orders")
    parser.add_argument("--auto", action="store_true", help="self-gate on session calendar, wait, run, report, exit (requires --mode paper|live)")
    args = parser.parse_args(argv)

    if args.control_dir is not None:
        from src.ops.control import ControlStore

        control_store = ControlStore(args.control_dir)
        stop_requested = lambda: control_store.load()["requested_mode"] == "stopped"
    else:
        stop_requested = lambda: False

    if args.preflight:
        from src.live.live_runner import print_preflight, run_preflight

        result = run_preflight(account_name_hint=args.account_name)
        print_preflight(result)
        return 0 if result.ok else 1

    if args.auto:
        if args.mode not in ("paper", "live"):
            parser.error("--auto requires --mode paper or --mode live")
        from src.live.live_runner import run_auto

        return run_auto(
            mode=args.mode,
            state_dir=args.state_dir,
            risk_per_trade_usd=args.risk,
            max_contracts=args.max_contracts,
            daily_loss_cap_usd=args.daily_loss_cap,
            account_name_hint=args.account_name,
            stop_requested=stop_requested,
        )

    if args.mode in ("paper", "live"):
        from datetime import date as _date

        from src.live.live_runner import run_live_or_paper_session

        trades = run_live_or_paper_session(
            mode=args.mode,
            session_date=_date.today(),
            state_dir=args.state_dir,
            risk_per_trade_usd=args.risk,
            max_contracts=args.max_contracts,
            daily_loss_cap_usd=args.daily_loss_cap,
            account_name_hint=args.account_name,
            stop_requested=stop_requested,
        )
        _print_summary(trades)
        return 0

    if args.mode != "replay":
        parser.error("--mode is required (replay|paper|live) unless --preflight is given")

    if not args.start or not args.end:
        parser.error("--mode replay requires --start and --end")

    trades = run_replay(
        start=args.start,
        end=args.end,
        parquet_path=args.parquet,
        state_dir=args.state_dir,
        risk_per_trade_usd=args.risk,
        max_contracts=args.max_contracts,
        daily_loss_cap_usd=args.daily_loss_cap,
    )
    _print_summary(trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
