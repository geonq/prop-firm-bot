"""Phase 6B: live/paper session runner, preflight, and --auto self-gating.

Kept as a SEPARATE module from src/live/runner.py (rather than folded into
`run_replay`) so the already-tested replay-mode code path (407 tests as of
Phase 6A) is never touched by this phase's additions -- this module imports
from runner.py (TradeJournal, RunnerState, _flatten_and_record, etc.) and
adds session-scoped live/paper logic on top.

Emits the SAME event/journal shape as run_replay's per-bar loop wherever
possible (TradeOpened/TradeClosed/DailyLossCapHit/etc via TradeJournal), so
the daily report and any downstream analysis of LiveState/events.jsonl does
not need to know which mode produced a given day's entries.

KNOWN MODEL GAP (--mode live only, documented rather than silently left):
the engine (src/live/engine.py) computes its OWN internal stop_price/
target_price/risk_points from its MODELED entry fill at TradeOpened time,
and never learns the REAL fill price LiveBroker reports back (there is no
mechanism, by design, for a broker to feed information back into the
engine's decision state -- the engine only ever emits intents, per its own
module docstring). Consequences, both bounded and non-critical:
  - The exchange-resident STOP order LiveBroker places is anchored to the
    engine's stop_price, which is an absolute OR-extreme level (or_opposite
    stop mode) independent of the entry fill -- this is unaffected by the
    gap and stays correct regardless of real slippage.
  - The exchange-resident TARGET order is placed at the engine's
    target_price, which WAS computed from the modeled entry (entry +
    target_r * modeled_risk) -- if the real fill is worse than modeled,
    the real risk:reward to that resting target is slightly off from
    exactly 4R, though the order itself is still a legitimate, intentional
    price level (not a bug, a small drift from the theoretical target).
  - The engine's own time_stop check (mfe_r < 1.0 by time_stop_minutes)
    uses the MODELED entry as its reference point for favorable-excursion
    calculations, not the real fill -- a small, bounded blind spot on
    exactly how the +1R time-stop-exemption threshold is measured when
    real slippage is nonzero. This does not affect stop/target correctness
    (those are separate, exchange-resident, real orders) and is reported
    on in the daily report's slippage section so it is visible, not hidden.
Fixing this properly would require either feeding the real fill back into
the engine (a decision-logic change explicitly out of scope for Phase 6B --
see Tasks/todo.md "no changes to src/backtest, src/optimizer, src/pipeline,
src/rules, or live engine decision logic") or re-deriving a parallel
real-fill-relative state machine, which is a larger redesign left for a
future phase if the paper-parallel reconciliation data shows this gap
actually matters in practice.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from src.backtest.sessions import ET
from src.live.broker import FilledTrade, PaperBroker
from src.live.config import (
    DEFAULT_DAILY_LOSS_CAP_USD,
    DEFAULT_MAX_CONTRACTS,
    FROZEN_PARAMS,
    MNQ,
    RISK_PER_TRADE_USD,
    compute_full_config_hash,
    compute_params_hash,
    verify_params_hash,
)
from src.live.engine import ORBLiveEngine
from src.live.env import MissingCredentialsError, load_projectx_credentials
from src.live.feed import Bar, LiveBarFeed, LiveFeedSkipDay
from src.live.live_broker import LiveBroker, LiveBrokerError
from src.live.projectx import ProjectXClient, ProjectXError, RequestsTransport
from src.live.runner import (
    DEFAULT_STATE_DIR,
    RunnerState,
    TradeJournal,
    _event_payload,
    _flatten_and_record,
    _print_summary,
)
from src.live.sizing import contracts_for

AUTO_START_WAIT_ET = ET  # re-exported for clarity at call sites

# EoD/error-path flatten retry policy (reviewer Fix 3, 2026-07-19,
# CRITICAL): same shape as LiveBroker's own CANCEL_RETRY_ATTEMPTS /
# CANCEL_RETRY_BACKOFF_SECONDS (src/live/live_broker.py) -- ~5 attempts
# over ~30s, using an injected sleep so tests never wait in real time.
FLATTEN_RETRY_ATTEMPTS = 5
FLATTEN_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 15.0)


class SessionErrored(RuntimeError):
    """Raised by run_live_or_paper_session when the session's own exception
    handler could not confirm the account was left flat (see its
    docstring) -- a distinct type from whatever the ORIGINAL exception was,
    so callers can always tell "the session broke AND we don't know if a
    position is still open" apart from "the session broke but we
    successfully flattened first."
    """

    def __init__(self, original: BaseException, *, flattened: bool) -> None:
        self.original = original
        self.flattened = flattened
        state = "flattened successfully" if flattened else "FLATTEN FAILED -- position may still be open"
        super().__init__(f"session errored ({type(original).__name__}: {original}); {state}")


class CooperativeStopRequested(RuntimeError):
    """Internal control-flow signal raised when the operator requests stop."""


def _build_client() -> ProjectXClient:
    creds = load_projectx_credentials()
    return ProjectXClient(RequestsTransport(), username=creds.username, api_key=creds.api_key)


def _resolve_account(client: ProjectXClient, *, account_name_hint: str | None = None):
    accounts = client.search_accounts(only_active=True)
    tradable = [a for a in accounts if a.can_trade]
    if not tradable:
        raise RuntimeError("no tradable active accounts returned by Account/search")
    if account_name_hint is not None:
        matches = [a for a in tradable if a.name == account_name_hint]
        if not matches:
            names = ", ".join(a.name for a in tradable)
            raise RuntimeError(f"account_name_hint={account_name_hint!r} not found among tradable accounts: {names}")
        return matches[0]
    if len(tradable) > 1:
        names = ", ".join(f"{a.id} ({a.name})" for a in tradable)
        raise RuntimeError(
            f"{len(tradable)} tradable accounts found ({names}) -- pass --account-name to disambiguate, "
            "do not guess which one to trade"
        )
    return tradable[0]


def _default_feed_factory(
    client: ProjectXClient,
    contract_id: str,
    session_date: date,
    journal: TradeJournal,
    on_wait_tick: Callable[[], None] = lambda: None,
) -> LiveBarFeed:
    return LiveBarFeed(
        retrieve_bars=lambda cid, **kw: client.retrieve_bars(cid, **kw),
        contract_id=contract_id,
        session_date=session_date,
        on_late_bar=lambda msg: journal.record_event("LiveFeedLateBar", {"message": msg}),
        on_wait_tick=on_wait_tick,
    )


def run_live_or_paper_session(
    *,
    mode: str,
    session_date: date,
    state_dir: Path = DEFAULT_STATE_DIR,
    risk_per_trade_usd: float = RISK_PER_TRADE_USD,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    daily_loss_cap_usd: float = DEFAULT_DAILY_LOSS_CAP_USD,
    account_name_hint: str | None = None,
    client_factory: Callable[[], ProjectXClient] = _build_client,
    feed_factory: Callable[[ProjectXClient, str, date, TradeJournal, Callable[[], None]], LiveBarFeed] = _default_feed_factory,
    sleep: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> list[FilledTrade]:
    """Runs ONE real trading session (today) via LiveBarFeed + PaperBroker or LiveBroker.

    `mode` is "paper" (LiveBarFeed + PaperBroker -- the paper-parallel
    instrument the go-live gate requires) or "live" (LiveBarFeed +
    LiveBroker -- real orders). Both modes use the REAL live feed; only the
    broker differs, so paper-mode is the true reconciliation instrument
    (identical feed timing/latency to live, simulated fills instead of
    real ones).

    `client_factory`/`feed_factory` default to real construction
    (`_build_client`: real credentials + real HTTP transport;
    `_default_feed_factory`: a real `LiveBarFeed` polling the real API) and
    exist ONLY so tests can inject a fake-transport client and a feed with
    a controllable clock (see tests/test_live_session.py) -- production
    call sites never pass either. `sleep` is injected the same way, ONLY
    for the error-path flatten retry backoff (see the exception handler
    below) so tests never wait in real time.

    Raises `SessionErrored` (never a bare/opaque exception) if the
    per-bar loop or session-end raises for any reason OTHER than
    `LiveFeedSkipDay` (which is not an error -- see that branch) --
    `SessionErrored.flattened` tells the caller whether the retry-with-
    backoff flatten attempted in the handler below actually succeeded.
    """
    if mode not in ("paper", "live"):
        raise ValueError(f"mode must be 'paper' or 'live', got {mode!r}")

    verify_params_hash()

    client = client_factory()
    client.login()
    account = _resolve_account(client, account_name_hint=account_name_hint)
    contract = client.resolve_front_contract(MNQ.symbol, live=(mode == "live"))

    journal = TradeJournal(state_dir)
    runner_state = RunnerState(state_dir / "state.json")
    engine = ORBLiveEngine.from_params(FROZEN_PARAMS)

    was_restored = runner_state.session_date == session_date and runner_state.trade_taken
    runner_state.roll_to_session(session_date)

    if mode == "paper":
        broker = PaperBroker(point_value=MNQ.point_value)
        if was_restored and runner_state.position is not None:
            # PaperBroker has no real exchange to reconcile against -- restore its
            # in-memory position from the persisted snapshot, same as run_replay does.
            pos = runner_state.position
            engine.restore_session(
                session_date=session_date, trade_taken=True, direction=pos.direction, entry_ts=pd.Timestamp(pos.entry_ts),
                entry_price=pos.entry_price, stop_price=pos.stop_price, target_price=pos.target_price,
                risk_points=pos.risk_points,
            )
            broker.place_bracket(
                session_date=pos.session_date, direction=pos.direction, entry_price=pos.entry_price,
                stop_price=pos.stop_price, target_price=pos.target_price, contracts=pos.contracts, entry_ts=pos.entry_ts,
            )
        elif was_restored:
            engine.restore_session(session_date=session_date, trade_taken=True, direction=None)
    else:
        broker = LiveBroker(
            client=client,
            account_id=account.id,
            contract_id=contract.id,
            point_value=MNQ.point_value,
            on_event=journal.record_event,
        )
        # ALWAYS reconcile against the real exchange on startup, regardless of
        # what local state.json believes -- the exchange is the source of
        # truth for whether a real position exists (state.json could be
        # missing/stale/corrupted after a crash, but a real position placed
        # before the crash does not care about that). This is what makes
        # restart recovery idempotent in --mode live: a second process
        # start can NEVER double-enter, because it always asks the exchange
        # first, never trusts only its own prior belief.
        adopted = broker.reconcile()
        if adopted is not None:
            journal.record_event(
                "SessionStartReconciled",
                {"direction": adopted.direction, "contracts": adopted.contracts, "entry_price": adopted.entry_price, "entry_ts": adopted.entry_ts},
            )
            try:
                adopted_entry_ts = pd.Timestamp(adopted.entry_ts)
            except (ValueError, TypeError):
                # The exchange did not provide a usable creationTimestamp for
                # the adopted position (see LiveBroker.reconcile()'s
                # "unknown-reconciled" fallback) -- fall back to "now" so
                # restore_session can still compute A time-stop deadline
                # rather than crashing. This is conservative in the same
                # direction as the mfe_r reset documented in
                # ORBLiveEngine.restore_session: treating the position as
                # having JUST entered means the time-stop deadline is LATER
                # than the true one would have been, so it can only make
                # the time-stop fire LATER than a fully-informed restore
                # would -- never earlier, never suppressing a stop/target
                # (those remain the real exchange-resident orders,
                # unaffected by this). Journaled explicitly so this
                # fallback is visible, not silent.
                adopted_entry_ts = pd.Timestamp.now(tz="UTC")
                journal.record_event(
                    "ReconcileEntryTsFallback",
                    {"reason": "exchange did not provide a parseable creationTimestamp", "raw_value": str(adopted.entry_ts)},
                )
            engine.restore_session(
                session_date=session_date, trade_taken=True, direction=adopted.direction, entry_ts=adopted_entry_ts,
                entry_price=adopted.entry_price, stop_price=adopted.stop_price, target_price=adopted.target_price,
                risk_points=adopted.risk_points,
            )
            # Sync local state to match the exchange's own truth (not the
            # other way around) -- if state.json disagreed (e.g. thought we
            # were flat, or had stale/wrong details), the exchange wins.
            runner_state.trade_taken = True
            runner_state.position = adopted
            runner_state.save()
        elif was_restored:
            # No real position exists, but local state.json says today's
            # trade was already taken (e.g. it closed normally before a
            # later crash, or was skipped for 0 contracts) -- honor that,
            # no re-entry today.
            engine.restore_session(session_date=session_date, trade_taken=True, direction=None)

    filled_trades: list[FilledTrade] = []
    halted = False
    last_bar: Bar | None = None
    last_known_price: float | None = None

    def _handle_oco_fill(oco_result: str, *, exit_ts, exit_price: float) -> None:
        # Shared by both the once-per-bar poll below AND the ~10s
        # between-bar poll (reviewer Fix 6, 2026-07-19, OPS -- see
        # on_wait_tick below) so a real stop/target fill is recorded the
        # same way regardless of which poll noticed it first.
        nonlocal halted
        trade = broker.close_position(exit_ts=exit_ts, exit_price=exit_price, exit_reason=oco_result)
        filled_trades.append(trade)
        journal.record_trade(trade)
        runner_state.realized_pnl_usd += trade.pnl_usd
        runner_state.position = None
        runner_state.save()
        engine.restore_session(session_date=session_date, trade_taken=True, direction=None)

    # Reviewer Fix 6 (2026-07-19, OPS): while a position is open, poll OCO
    # status roughly every 10s WHILE WAITING for the next bar too, not only
    # once per bar (once/minute) -- a real stop/target fill can happen at
    # any moment, and 60s of exposure to a fill the runner doesn't yet know
    # about (still showing a resting sibling order, still computing
    # unrealized pnl off a stale model) is an avoidable gap. `on_wait_tick`
    # fires roughly once per second (see LiveBarFeed._wait_until); this
    # counts ticks rather than depending on any particular feed clock, and
    # only does real work (an API call) every ~10th tick, and only in
    # --mode live, and only while a position is actually open -- flat
    # sessions and paper mode pay nothing extra. Uses `datetime.now(ET)`
    # (not the feed's `now`, which the factory has already closed over by
    # the time this closure exists) for `exit_ts` since there is no bar to
    # anchor to between polls; `exit_price` falls back to the last bar's
    # close (`close_position` resolves the REAL fill price itself from
    # Trade/search when available -- see live_broker.py -- this is only
    # the fallback if that lookup fails).
    OCO_WAIT_TICK_POLL_EVERY = 10
    wait_tick_count = 0

    def _on_wait_tick() -> None:
        nonlocal wait_tick_count
        if stop_requested():
            raise CooperativeStopRequested("operator requested cooperative stop")
        if mode != "live" or halted or not isinstance(broker, LiveBroker) or broker.position is None:
            return
        wait_tick_count += 1
        if wait_tick_count % OCO_WAIT_TICK_POLL_EVERY != 0:
            return
        oco_result = broker.poll_oco()
        if oco_result is not None:
            _handle_oco_fill(
                oco_result, exit_ts=datetime.now(ET), exit_price=(last_known_price or broker.position.entry_price)
            )

    feed = feed_factory(client, contract.id, session_date, journal, _on_wait_tick)

    try:
        for bar in feed:
            last_bar = bar
            last_known_price = bar.close
            if stop_requested():
                raise CooperativeStopRequested("operator requested cooperative stop")

            if not halted and broker.position is not None:
                mtm_pnl = runner_state.realized_pnl_usd + broker.unrealized_pnl_usd(bar.close)
                if mtm_pnl <= -abs(daily_loss_cap_usd):
                    halted = True
                    _flatten_and_record(
                        broker=broker, journal=journal, runner_state=runner_state, filled_trades=filled_trades,
                        exit_ts=bar.ts, exit_price=bar.close, exit_reason="daily_loss_cap",
                    )
                    journal.record_event(
                        "DailyLossCapHit",
                        {"session_date": str(session_date), "mark_to_market_pnl_usd": mtm_pnl, "cap_usd": daily_loss_cap_usd},
                    )
                    engine.restore_session(session_date=session_date, trade_taken=True, direction=None)

            # Live-broker OCO polling: the exchange may have filled the stop
            # or target BETWEEN bars (real fills aren't bar-synchronous) --
            # check before feeding this bar to the engine's own modeled
            # stop/target logic, so we never double-report an exit the
            # exchange already executed.
            if mode == "live" and not halted and isinstance(broker, LiveBroker) and broker.position is not None:
                oco_result = broker.poll_oco()
                if oco_result is not None:
                    _handle_oco_fill(oco_result, exit_ts=bar.ts, exit_price=bar.close)

            events = engine.on_bar(bar) if not halted else []
            for ev in events:
                ev_type = type(ev).__name__
                journal.record_event(ev_type, _event_payload(ev))

                if ev_type == "TradeOpened":
                    if halted or runner_state.trade_taken:
                        continue
                    contracts = contracts_for(
                        ev.risk_points, risk_per_trade_usd=risk_per_trade_usd, point_value=MNQ.point_value,
                        max_contracts=max_contracts,
                    )
                    if contracts == 0:
                        runner_state.trade_taken = True
                        runner_state.save()
                        journal.record_event(
                            "TradeSkippedZeroContracts", {"session_date": str(session_date), "stop_points": ev.risk_points}
                        )
                        continue
                    snapshot = broker.place_bracket(
                        session_date=ev.session_date, direction=ev.direction, entry_price=ev.entry_price,
                        stop_price=ev.stop_price, target_price=ev.target_price, contracts=contracts, entry_ts=ev.entry_ts,
                        target_r=FROZEN_PARAMS.target_r,
                    )
                    # LiveBroker returns exchange-confirmed fill/target values;
                    # make those the engine's source of truth for exits and MFE.
                    engine.restore_session(
                        session_date=snapshot.session_date,
                        trade_taken=True,
                        direction=snapshot.direction,
                        entry_ts=pd.Timestamp(snapshot.entry_ts),
                        entry_price=snapshot.entry_price,
                        stop_price=snapshot.stop_price,
                        target_price=snapshot.target_price,
                        risk_points=snapshot.risk_points,
                    )
                    runner_state.trade_taken = True
                    runner_state.position = snapshot
                    runner_state.save()

                elif ev_type == "TradeClosed":
                    if broker.position is None:
                        continue  # already closed via OCO poll above, or was skipped (0 contracts)
                    trade = broker.close_position(exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason)
                    filled_trades.append(trade)
                    journal.record_trade(trade)
                    runner_state.realized_pnl_usd += trade.pnl_usd
                    runner_state.position = None
                    runner_state.save()

            if not halted and runner_state.realized_pnl_usd <= -abs(daily_loss_cap_usd):
                halted = True
                journal.record_event(
                    "DailyLossCapHit",
                    {"session_date": str(session_date), "realized_pnl_usd": runner_state.realized_pnl_usd, "cap_usd": daily_loss_cap_usd},
                )

        if last_bar is not None:
            end_events = engine.on_session_end(last_bar)
            for ev in end_events:
                journal.record_event("TradeClosed", _event_payload(ev))
                if broker.position is not None:
                    trade = broker.close_position(exit_ts=ev.exit_ts, exit_price=ev.exit_price, exit_reason=ev.exit_reason)
                    filled_trades.append(trade)
                    journal.record_trade(trade)
                    runner_state.realized_pnl_usd += trade.pnl_usd
                    runner_state.position = None
                    runner_state.save()

    except CooperativeStopRequested:
        if broker.position is not None:
            exit_ts = last_bar.ts if last_bar is not None else datetime.now(ET)
            exit_price = last_bar.close if last_bar is not None else broker.position.entry_price
            last_error = ""
            for attempt in range(FLATTEN_RETRY_ATTEMPTS):
                try:
                    _flatten_and_record(
                        broker=broker, journal=journal, runner_state=runner_state, filled_trades=filled_trades,
                        exit_ts=exit_ts, exit_price=exit_price, exit_reason="cooperative_stop",
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - safety retry boundary
                    last_error = f"{type(exc).__name__}: {exc}"
                    journal.record_event(
                        "CooperativeStopFlattenRetryFailed",
                        {"attempt": attempt + 1, "max_attempts": FLATTEN_RETRY_ATTEMPTS, "error": last_error},
                    )
                    if attempt < FLATTEN_RETRY_ATTEMPTS - 1:
                        sleep(FLATTEN_RETRY_BACKOFF_SECONDS[attempt])
            if broker.position is not None:
                journal.record_event(
                    "NakedPositionAlarm",
                    {"message": "cooperative stop could not confirm flatten; verify TopstepX immediately", "last_error": last_error},
                )
                raise SessionErrored(CooperativeStopRequested("flatten failed"), flattened=False)
        journal.record_event("CooperativeStopAcknowledged", {"session_date": str(session_date), "flattened": True})
        return filled_trades
    except LiveFeedSkipDay as exc:
        journal.record_event("LiveFeedSkipDay", {"session_date": str(exc.session_date), "reason": exc.reason})
        return filled_trades
    except Exception as original_exc:
        # Reviewer Fix 3 (2026-07-19, CRITICAL): journal FlattenOnError FIRST,
        # unconditionally, before attempting anything else -- the original bug
        # was that a re-raising close_position() call inside this handler
        # prevented FlattenOnError from EVER being written, leaving a naked
        # overnight position with no journal record and no daily report. The
        # journal call below is the FIRST thing this handler does, full stop,
        # so it is guaranteed to exist regardless of what happens next.
        journal.record_event("FlattenOnError", {"traceback": traceback.format_exc()})

        flattened = True
        if broker.position is not None and last_bar is not None:
            flattened = False
            last_flatten_error = ""
            for attempt in range(FLATTEN_RETRY_ATTEMPTS):
                try:
                    _flatten_and_record(
                        broker=broker, journal=journal, runner_state=runner_state, filled_trades=filled_trades,
                        exit_ts=last_bar.ts, exit_price=last_bar.close, exit_reason="flatten_on_error",
                    )
                    flattened = True
                    break
                except Exception as flatten_exc:  # noqa: BLE001 -- must catch anything so the retry loop and the guaranteed alarm below always run
                    last_flatten_error = f"{type(flatten_exc).__name__}: {flatten_exc}"
                    journal.record_event(
                        "FlattenOnErrorRetryFailed",
                        {"attempt": attempt + 1, "max_attempts": FLATTEN_RETRY_ATTEMPTS, "error": last_flatten_error},
                    )
                    if attempt < FLATTEN_RETRY_ATTEMPTS - 1:
                        sleep(FLATTEN_RETRY_BACKOFF_SECONDS[attempt])

            if not flattened:
                # Guaranteed regardless of how many close attempts failed --
                # this is the record a human/the daily report relies on to
                # know real money may still be exposed.
                journal.record_event(
                    "NakedPositionAlarm",
                    {
                        "session_date": str(session_date),
                        "contracts": broker.position.contracts if broker.position is not None else None,
                        "direction": broker.position.direction if broker.position is not None else None,
                        "attempts": FLATTEN_RETRY_ATTEMPTS,
                        "last_error": last_flatten_error,
                        "message": "every flatten attempt failed after an unhandled session exception -- "
                        "position may still be open; verify directly on the TopStepX platform immediately",
                    },
                )

        raise SessionErrored(original_exc, flattened=flattened) from original_exc

    return filled_trades


# ---------------------------------------------------------------------------
# --preflight
# ---------------------------------------------------------------------------


@dataclass
class PreflightResult:
    ok: bool
    checks: list[tuple[str, bool, str]]  # (check_name, passed, detail)


def run_preflight(
    *, account_name_hint: str | None = None, client_factory: Callable[[], ProjectXClient] = _build_client
) -> PreflightResult:
    """Validates .env creds, auth, account lookup, contract resolution, one
    bars fetch, both params hashes, local clock vs ET -- per Tasks/todo.md
    "Phase 6B" `--preflight` spec. Never places an order or touches a position.
    """
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, fn):
        try:
            detail = fn()
            checks.append((name, True, str(detail) if detail is not None else "ok"))
            return detail
        except Exception as exc:  # noqa: BLE001 -- preflight must report every failure, not crash on the first
            checks.append((name, False, f"{type(exc).__name__}: {exc}"))
            return None

    check("params_hash (holdout-provenance)", compute_params_hash)
    check("params_hash (full-config)", compute_full_config_hash)
    try:
        verify_params_hash()
        checks.append(("verify_params_hash()", True, "both guards pass"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("verify_params_hash()", False, str(exc)))

    creds = check(".env credentials present", lambda: load_projectx_credentials().username)
    if creds is None:
        return PreflightResult(ok=False, checks=checks)

    def _login():
        client = client_factory()
        client.login()
        return client

    client = check("auth (loginKey)", _login)
    if client is None:
        return PreflightResult(ok=False, checks=checks)

    account = check("account lookup", lambda: _resolve_account(client, account_name_hint=account_name_hint))
    contract = check("contract resolution (MNQ front month)", lambda: client.resolve_front_contract(MNQ.symbol))

    if contract is not None:
        check(
            "bars fetch (smoke)",
            lambda: len(
                client.retrieve_bars(
                    contract.id,
                    start_time=(datetime.now(ZoneInfo("UTC")) - timedelta(minutes=10)).isoformat(),
                    end_time=datetime.now(ZoneInfo("UTC")).isoformat(),
                    limit=10,
                )
            ),
        )

        def bar_timestamp_convention_check():
            # Reviewer Fix 5 (2026-07-19, MEDIUM): retrieveBars' bar-
            # timestamp convention (does `t` label the OPEN or the CLOSE of
            # the bar's interval?) is UNVERIFIED against the real API -- see
            # src/live/projectx.py module docstring. Getting this wrong
            # silently shifts every bar (OR window, entry, time-stop
            # deadline) by one bar-width with no error raised anywhere.
            # This fetches the last ~3 one-minute bars and prints each
            # bar's `ts` next to the CURRENT wall-clock minute so a human
            # can eyeball the convention before any real order is ever
            # placed -- this is a manual confirmation step, not an
            # automated pass/fail (a "recent-looking" timestamp is
            # consistent with EITHER labeling convention; only a human
            # comparing this printout against what they know the market
            # was doing at that exact minute can actually tell).
            now_et = datetime.now(ET)
            end = now_et
            start = end - timedelta(minutes=10)
            bars = client.retrieve_bars(
                contract.id, start_time=start.isoformat(), end_time=end.isoformat(), unit=2, unit_number=1, limit=3,
            )
            if not bars:
                return "no bars returned (market likely closed) -- re-run during RTH to check labeling"
            # client.retrieve_bars returns the RAW src.live.projectx.Bar (field
            # `t`, the API's own ISO string, NOT the ET-localized/converted
            # src.live.feed.Bar) -- printed verbatim, unconverted, since the
            # whole point of this check is to see exactly what the API sent.
            lines = [f"current wall clock (ET): {now_et.isoformat()}"]
            for bar in bars[-3:]:
                lines.append(f"  bar t={bar.t} o={bar.o} h={bar.h} l={bar.l} c={bar.c}")
            lines.append(
                "MANUAL CHECK REQUIRED: this project assumes bar `ts` labels the OPEN of its "
                "1-minute interval (matching src/backtest/src/pipeline convention elsewhere). "
                "Compare the last bar's ts against the current wall clock: an open-labeled bar's "
                "ts should be ~1-2 minutes BEHIND the wall clock (the just-completed minute's "
                "start); a close-labeled bar's ts would be ~1 minute closer to the wall clock "
                "than that. If the bars look close-labeled instead of open-labeled: STOP, do NOT "
                "go live -- report this back before running --mode live, since every OR-window/"
                "entry/time-stop timestamp in the engine would be off by one bar-width."
            )
            return "\n" + "\n".join(lines)

        check("bar timestamp convention (manual confirmation required)", bar_timestamp_convention_check)

    def clock_check():
        local_now_et = datetime.now(ET)
        return f"local clock (ET): {local_now_et.isoformat()}"

    check("local clock vs ET", clock_check)

    ok = all(passed for _, passed, _ in checks)
    return PreflightResult(ok=ok, checks=checks)


def print_preflight(result: PreflightResult) -> None:
    for name, passed, detail in result.checks:
        mark = "OK" if passed else "FAIL"
        print(f"[{mark}] {name}: {detail}")
    print()
    print("PREFLIGHT PASSED" if result.ok else "PREFLIGHT FAILED")


# ---------------------------------------------------------------------------
# --auto self-gating
# ---------------------------------------------------------------------------

LOCK_FILENAME = "orbbot.lock"


class ProcessLockHeld(RuntimeError):
    """Raised when another process already holds the exclusive orbbot lock."""


class ProcessLock:
    """Exclusive, non-blocking, process-lifetime advisory lock on
    LiveState/orbbot.lock (reviewer Fix 1, 2026-07-19, CRITICAL -- launchd's
    two StartCalendarInterval entries (14:20 and 15:20 local) can both land
    inside the 09:25-11:40 ET trading window on a normal week (e.g.
    08:20/09:20 ET), and `should_run_today`'s weekday/already-traded check
    alone does NOT prevent a second process from starting while the first
    is still pre-entry (trade_taken is only set once TradeOpened actually
    fires, which can be minutes after the process starts) -- both processes
    would then independently decide "should run today" and BOTH place a
    real entry, doubling the position with no lock anywhere to stop it.

    `acquire()` uses the native non-blocking file-lock primitive --
    ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows -- so a second
    process gets an immediate failure rather than queuing behind the
    first (queuing would just delay the double-entry, not prevent it, since
    the second process would then proceed once the first exits). The lock
    is held for the ENTIRE process lifetime (acquired once at the start of
    `run_auto`, released only on process exit via the context manager) --
    not just around the entry decision -- because the risk isn't limited to
    the entry: two processes both polling/managing exits for what they each
    believe is "their" position would be equally unsafe.

    The implementation is deliberately limited to local personal-device
    execution. It supports both macOS/Linux and the Windows Hermes PC; it is
    not a distributed lock and must not be treated as one.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def acquire(self) -> bool:
        """Returns True if the lock was acquired, False if already held elsewhere.

        Never raises on contention -- contention is the EXPECTED case for
        the launchd double-fire scenario this exists to guard against, not
        an error condition. Only raises for a genuine filesystem problem
        (permissions, missing parent dir, etc.).
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+")
        try:
            if os.name == "nt":
                # Windows locks byte ranges rather than whole files. Ensure
                # byte zero exists, then lock exactly that byte without
                # waiting. ``a+`` is intentional: it also creates the lock
                # file atomically when it does not yet exist.
                import msvcrt

                fh.seek(0, 2)
                if fh.tell() == 0:
                    fh.write("\0")
                    fh.flush()
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={__import__('os').getpid()} acquired_at={datetime.now(ET).isoformat()}\n")
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None

    def __enter__(self) -> "ProcessLock":
        if not self.acquire():
            raise ProcessLockHeld(f"{self.path} is already held by another process")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def should_run_today(today: date, *, state_dir: Path = DEFAULT_STATE_DIR) -> tuple[bool, str]:
    """Weekday + already-traded self-gate. Returns (should_run, reason).

    Deliberately does NOT try to detect exchange holidays from a static
    calendar (no reliable source of that without live bars -- see module
    docstring): a holiday naturally produces no OR-window bars and is
    caught safely downstream by LiveBarFeed's own LiveFeedSkipDay, which
    --auto treats as "nothing to do today" the same as any other skip.
    """
    if today.weekday() >= 5:
        return False, f"{today} is a weekend (weekday={today.weekday()})"
    state_path = state_dir / "state.json"
    if state_path.exists():
        raw = json.loads(state_path.read_text())
        if raw.get("session_date") == today.isoformat() and raw.get("trade_taken"):
            return False, f"{today} already traded (state.json trade_taken=True)"
    return True, "ok"


def run_auto(
    *,
    mode: str,
    state_dir: Path = DEFAULT_STATE_DIR,
    risk_per_trade_usd: float = RISK_PER_TRADE_USD,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    daily_loss_cap_usd: float = DEFAULT_DAILY_LOSS_CAP_USD,
    account_name_hint: str | None = None,
    now_fn=lambda: datetime.now(ET),
    sleep_fn=None,
    client_factory: Callable[[], ProjectXClient] = _build_client,
    feed_factory: Callable[[ProjectXClient, str, date, TradeJournal, Callable[[], None]], LiveBarFeed] = _default_feed_factory,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """--auto: acquire the exclusive process lock, self-gate on session
    calendar, wait until 09:25 ET, run the session, flatten by EoD (handled
    inside run_live_or_paper_session), write the daily report, exit.
    Returns a process exit code.

    Lock acquisition (reviewer Fix 1, 2026-07-19) happens FIRST, before the
    should_run_today gate -- a second process (e.g. launchd's 15:20 fire
    landing while the 14:20 fire's session is still running) must never
    even reach the trading-calendar check while another process holds the
    lock, since should_run_today's own state.json check is not sufficient
    on its own to prevent a double-entry (see ProcessLock's docstring for
    the exact race). On contention, journals a LockHeldExit event via a
    throwaway TradeJournal (this run_auto call never gets far enough to
    construct the real per-session one) and exits 0 -- silently, not an
    error, since a launchd double-fire is expected/harmless BY DESIGN once
    the lock exists (that is now the actual mechanism providing the
    harmlessness scripts/launchd/com.geonq.orbbot.plist and
    RUNBOOK_LIVE.md describe -- see their updated comments).
    """
    import time as _time

    from src.live.runner import TradeJournal as _TradeJournal

    sleep_fn = sleep_fn or _time.sleep
    today = now_fn().date()

    lock = ProcessLock(state_dir / LOCK_FILENAME)
    if not lock.acquire():
        journal = _TradeJournal(state_dir)
        journal.record_event(
            "LockHeldExit",
            {"session_date": str(today), "reason": f"{lock.path} already held by another process"},
        )
        print(f"--auto: {lock.path} already held by another process -- exiting (this is expected on a launchd double-fire)")
        return 0

    try:
        return _run_auto_locked(
            mode=mode, state_dir=state_dir, risk_per_trade_usd=risk_per_trade_usd, max_contracts=max_contracts,
            daily_loss_cap_usd=daily_loss_cap_usd, account_name_hint=account_name_hint, now_fn=now_fn,
            sleep_fn=sleep_fn, client_factory=client_factory, feed_factory=feed_factory, today=today,
            stop_requested=stop_requested,
        )
    finally:
        lock.release()


def _run_auto_locked(
    *,
    mode: str,
    state_dir: Path,
    risk_per_trade_usd: float,
    max_contracts: int,
    daily_loss_cap_usd: float,
    account_name_hint: str | None,
    now_fn,
    sleep_fn,
    client_factory: Callable[[], ProjectXClient],
    feed_factory: Callable[[ProjectXClient, str, date, TradeJournal, Callable[[], None]], LiveBarFeed] = _default_feed_factory,
    today: date,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """The original run_auto body, now running under the exclusive lock (see run_auto)."""
    should_run, reason = should_run_today(today, state_dir=state_dir)
    if not should_run:
        print(f"--auto: skipping today ({reason})")
        return 0

    wait_until = datetime.combine(today, datetime.min.time(), tzinfo=ET).replace(hour=9, minute=25)
    # Defensive iteration cap: at a MINIMUM 1s per sleep call, this covers
    # >27 hours of waiting -- far more than could ever legitimately be
    # needed (launchd starts this at 14:20/15:20 local, at most a few hours
    # before 09:25 ET) -- guards against a frozen/non-advancing clock
    # (real or injected via now_fn in tests) spinning forever rather than
    # ever reaching the session.
    max_wait_iterations = 100_000
    for _ in range(max_wait_iterations):
        if stop_requested():
            print("--auto: cooperative stop acknowledged while waiting")
            return 0
        if now_fn() >= wait_until:
            break
        remaining = (wait_until - now_fn()).total_seconds()
        sleep_fn(max(min(remaining, 30.0), 1.0))
    else:
        print(
            f"--auto: gave up waiting for 09:25 ET after {max_wait_iterations} poll iterations "
            f"(now={now_fn()!r}, target={wait_until!r}) -- clock may be stuck; aborting",
            file=sys.stderr,
        )
        return 1

    from src.live.report import write_daily_report

    # Reviewer Fix 3 (2026-07-19, CRITICAL): the daily report must be written
    # regardless of whether the session raised -- a SessionErrored (which
    # run_live_or_paper_session's own handler already journaled
    # FlattenOnError/NakedPositionAlarm for) is exactly the case where a
    # human most needs the report to exist, since it surfaces the alarm
    # prominently (see src/live/report.py). This is a try/finally, not a
    # try/except, specifically so "write the report" is guaranteed to run
    # even for exception types not in the narrower except clause below
    # (e.g. a bug in run_live_or_paper_session itself raising something
    # unexpected) -- report-writing must not silently depend on the
    # exception being one this function anticipated.
    exit_code = 0
    try:
        trades = run_live_or_paper_session(
            mode=mode, session_date=today, state_dir=state_dir, risk_per_trade_usd=risk_per_trade_usd,
            max_contracts=max_contracts, daily_loss_cap_usd=daily_loss_cap_usd, account_name_hint=account_name_hint,
            client_factory=client_factory, feed_factory=feed_factory, sleep=sleep_fn,
            stop_requested=stop_requested,
        )
        _print_summary(trades)
    except SessionErrored as exc:
        print(f"--auto: session errored: {exc}", file=sys.stderr)
        exit_code = 1
    except (MissingCredentialsError, ProjectXError, LiveBrokerError) as exc:
        print(f"--auto: session aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        report_path = write_daily_report(session_date=today, state_dir=state_dir)
        print(f"wrote {report_path}")

    return exit_code
