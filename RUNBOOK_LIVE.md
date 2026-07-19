# RUNBOOK_LIVE — Phase 6B operator sequence

Frozen config (params_hash `8afbe6259cab2dd2`, do not edit without a new
holdout sign-off): OR=5min first_candle entry, or_opposite stop, 4R target,
120min time stop, EoD flat, 1 trade/day, $400 risk/trade, MNQ, TopStep only.

Params NEVER self-tune. Live data is journaled as forward out-of-sample
evidence for an H2-2026 review, not fed back into the engine. "Learning"
here means: read the journal, decide by hand whether the config still
deserves capital. The bot never changes its own parameters.

## 1. Subscribe to TopstepX API access

1. Log into your TopStep account.
2. TopstepX Settings → API → link ProjectX.
3. Go to dashboard.projectx.com and complete the subscription there.
4. Use discount code `topstep` for 50% off, if still valid at signup time.
5. Confirm the subscription is active before proceeding — step 4 below
   will fail cleanly (not silently) if it isn't.

## 2. Create an API key

1. In the ProjectX dashboard, generate an API key for your TopStep account.
2. Note your TopStep username and the generated API key. You will need
   both — the ProjectX Gateway auth flow is `loginKey` (username + API
   key), not a username/password login.

## 3. Write `.env`

In the repo root (`Prop Firm Bot/.env` — gitignored, never commit it), add:

```
PROJECTX_USERNAME=your_topstep_username
PROJECTX_API_KEY=your_generated_api_key
```

If `.env` already exists (it does, for `DATABENTO_API_KEY`), just append
these two lines — do not overwrite the existing content.

Credentials are never written to `LiveState/events.jsonl` or any log file
by this codebase (`src/live/env.py::ProjectXCredentials.__repr__` redacts
the key even if something accidentally tries to print the object).

## 4. Run `--preflight`

```bash
cd "Prop Firm Bot"
source .venv/bin/activate
python3 -m src.live.runner --preflight
```

This checks, in order, and reports every failure (not just the first):
both params-hash tamper guards, `.env` credentials present, `loginKey`
auth, account lookup (fails loudly if more than one tradable account
exists — pass `--account-name` to disambiguate), MNQ front-contract
resolution, a bars smoke-fetch, a **bar timestamp convention check**, and
the local clock vs ET. It places **no orders** and touches **no position**.

Do not proceed past this step until `PREFLIGHT PASSED` prints. If contract
resolution reports more than one active MNQ-prefixed contract, stop and
resolve it by hand — the code deliberately refuses to guess which one is
the true front month (see `src/live/projectx.py::resolve_front_contract`).

**Bar timestamp convention (manual check, required before go-live):** the
preflight output includes a `[OK] bar timestamp convention (manual
confirmation required)` line printing the last ~3 one-minute bars' `t`
field next to the current wall clock. Whether `t` labels the OPEN or the
CLOSE of its 1-minute interval is UNVERIFIED against the real API — no
fetched doc page states it. This project assumes OPEN-labeling everywhere
(matching the backtest/replay convention). Read the printed bars: an
open-labeled bar's `t` should sit ~1-2 minutes BEHIND the current wall
clock (the just-completed minute's start). **If the bars instead look
close-labeled, STOP — do not proceed to `--mode live` or even
`--mode paper` — report this back first**, since every OR-window, entry,
and time-stop timestamp the engine computes would be silently off by one
bar-width.

### What cannot be verified without credentials

- The exact `Authorization` header format (see `src/live/projectx.py`
  module docstring, "AUTH HEADER").
- Whether `stopLossBracket`/`takeProfitBracket` create true exchange-side
  OCO orders, or whether this bot's own client-side OCO polling
  (`LiveBroker.poll_oco`) is what actually protects against a naked sibling
  order — the code assumes the latter (safer) and does its own polling
  regardless.
- retrieveBars' bar-timestamp (open vs close) labeling convention — see
  the preflight check described just above.
- `Position/closeContract`'s behavior when called against an
  already-flat contract for that symbol — `LiveBroker.close_position`
  checks `Position/searchOpen` first and skips the call entirely if
  already flat, specifically so this never needs to be relied upon.

## 5. Install the launchd schedule

```bash
chmod +x scripts/launchd/run_orbbot.sh scripts/launchd/install_launchd.sh
./scripts/launchd/install_launchd.sh
```

This installs `~/Library/LaunchAgents/com.geonq.orbbot.plist`, firing
weekdays at 14:20 and 15:20 local Mac time (covers the CET/CEST-vs-ET DST
drift). Self-gating (weekday / already-traded) alone does NOT make the
second fire safe — on a normal week both fires land before the trading
session even starts, and the second process would still pass that check.
What actually prevents a double-entry is an exclusive process lock
(`src/live/live_runner.py::ProcessLock`, held for the full process
lifetime): the second process fails to acquire it, journals a
`LockHeldExit` event, and exits immediately. Verify it loaded:

```bash
launchctl list | grep com.geonq.orbbot
```

The wrapper script defaults to `--mode paper` — this is intentional. Do
not change it to `live` until step 6 is satisfied.

Personal-device requirement: TopStep's terms prohibit running this on a
VPS or cloud host — the schedule above assumes your Mac is on and awake
(or at least wakeable) at the scheduled times; `caffeinate -i` inside
`run_orbbot.sh` keeps it from idle-sleeping once the job starts, but does
not wake a sleeping Mac to START the job (see `pmset schedule` if you need
scheduled wake — out of scope for this runbook).

## 6. Paper-parallel validation (minimum 2 weeks)

With the launchd schedule running `--mode paper --auto` every trading day:

**Daily, read `LiveState/reports/YYYY-MM-DD.md`:**
- Does today's signal/trade match what you'd expect from the frozen
  config (direction, entry roughly at the OR extreme, exit reason
  sane)?
- What is the reported entry slippage vs the 1-tick model? A single bad
  day is not a red flag; a persistent bias is.
- Sanity-check the trailing-40 shadow-R figure — it is explicitly labeled
  an ops health signal, not a gate (Phase 6A-R found it fails as an
  admissible trading filter). Use human judgment, not a threshold.

**Go-live gate (pre-registered, do not shortcut):** at least 2 full weeks
of paper-parallel running, with fills reconciling against the model within
a documented tolerance. Concretely, before considering switching to live:
- At least 10 trading days of paper sessions completed (not calendar
  days — weekends/holidays/no-trade doji days do not count toward this).
- Mean entry slippage vs the 1-tick model should be small and NOT
  systematically one-sided by more than a few ticks — if every single
  fill is worse than modeled by 2+ ticks, the 1-tick assumption in
  `src/live/config.py` (used for position sizing, not just reporting) is
  wrong and needs revisiting before real money is at risk.
- No unexplained `LiveFeedSkipDay` or `FlattenOnError` events in
  `LiveState/events.jsonl` that you cannot account for.
- You (geonq) have personally read every daily report from the run, not
  just spot-checked a few.

There is no automatic pass/fail here — this is a human go/no-go decision,
made explicitly, not inferred from a script's exit code.

## 7. Switching paper to live

Live trading is a manual, explicit change — never something a scheduled
job escalates to on its own.

1. Decide which TopStep Combine/funded account will trade (note its exact
   account name as shown by `Account/search` — run `--preflight` again if
   unsure, it prints the resolved account).
2. If more than one tradable account exists on your TopStep login, you
   MUST pass `--account-name "Exact Account Name"` explicitly (to both the
   manual CLI invocation and, if scheduling live via launchd, added to
   `run_orbbot.sh`'s `python3 -m src.live.runner` line) — the code refuses
   to guess.
3. Edit `scripts/launchd/run_orbbot.sh`, changing the default
   `MODE="${ORBBOT_MODE:-paper}"` line's default to `live`, OR simply add
   `ORBBOT_MODE=live` to `.env` (the wrapper sources `.env` before reading
   `ORBBOT_MODE`, so this is the less invasive edit and is the recommended
   way to flip it).
4. Run `--preflight` once more immediately before flipping the switch —
   confirm nothing has silently changed (contract roll, account access,
   etc.) since your last check.
5. The very first live session should be run manually in the foreground
   (`python3 -m src.live.runner --mode live` without `--auto`, during the
   09:25-11:40 ET window) so you can watch it, not unattended via launchd,
   at least once.

## 8. Daily monitoring routine (2 minutes)

TopStep's rules require ACTIVE monitoring — this bot is not a
"start it and forget it for the day" system, even though the actual
trading session is only about 2 hours (09:25-11:40 ET / roughly 15:25-17:40
CET or 14:25-16:40 CET depending on DST).

Each trading day:
1. Check `LiveState/reports/YYYY-MM-DD.md` was written (its absence means
   the scheduled run either didn't fire or crashed before reaching the
   report step — check `LiveState/launchd_stderr.log` and
   `LiveState/events.jsonl` for that date).
2. Skim the report's "today's signal/trade" section.
3. If in live mode: log into TopStepX/the platform directly and confirm
   the account's actual position/balance matches what the report claims.
   Do not trust the bot's own report as the sole source of truth for real
   money — cross-check against the broker platform itself.
4. Watch for anything in `LiveState/events.jsonl` tagged
   `DailyLossCapHit`, `LiveOrderCancelFailed`, or `FlattenOnError` — these
   are the kill-switch/error paths and always warrant a closer look even
   if the daily P&L looks fine.

## 9. Kill criteria

**Manual (you decide, no script enforces these):**
- Realized slippage vs the model is persistently and materially worse
  than the paper-parallel validation period showed.
- TopStep changes its API, fee schedule, or automation policy in a way
  that could affect this bot (re-run `--preflight` after any TopStepX
  platform update).
- You have a reason — trust your own judgment here; this is a frozen
  config being deployed for real money, not a research experiment where
  you should second-guess yourself into inaction.

**Automatic (the bot enforces these without asking):**
- Daily realized-loss cap: default `$600` (`DEFAULT_DAILY_LOSS_CAP_USD`,
  `--daily-loss-cap` to override) — mark-to-market checked every bar, not
  just after a close, specifically to catch gap-through-stop risk. Flattens
  and halts new entries for the rest of that session; does NOT halt future
  sessions.
- Unhandled exception mid-session: best-effort flatten before the
  exception propagates and the process exits (`FlattenOnError` event
  journaled either way).
- Params-hash mismatch at startup (`verify_params_hash()`): refuses to
  start at all if `FROZEN_PARAMS`, MNQ, or the risk budget were edited
  without re-recording the hash constants in `src/live/config.py`.
- `LiveFeedSkipDay` (OR window not confirmed by 09:35:30 ET, or the feed
  started outside its 09:25-11:40 ET polling window): no trade attempted
  that day. No-trade is always the safe failure mode.

To pull the plug entirely: `launchctl unload
~/Library/LaunchAgents/com.geonq.orbbot.plist` stops future scheduled
runs. If a position is open in live mode when you do this, it does NOT
flatten it — log into TopStepX directly and close it by hand, or run
`python3 -m src.live.runner --mode live` once more to let the bot's own
restart-recovery reconcile and manage the existing position through to
its exit.

## 10. What "learning" means here

This bot does not adapt. `FROZEN_PARAMS` in `src/live/config.py` is locked
behind two tamper-guard hashes (`PARAMS_HASH`, `FULL_CONFIG_HASH`) that the
runner checks and refuses to start on mismatch — there is no code path
anywhere in this package that writes back to that config from live
results.

What accumulates instead is the journal itself
(`LiveState/trades.csv`, `LiveState/events.jsonl`, daily reports): every
real fill is genuine forward out-of-sample evidence, distinct from and
independent of the backtest/holdout that justified deploying this config
in the first place. The plan (Tasks/todo.md "Phase 6A-R"/"Phase 6B") is to
accumulate this forward data through H2-2026 and then do an explicit,
human-reviewed comparison: does live performance track the modeled
expectation closely enough to keep running, scale up, or should the whole
approach be revisited? That review is a deliberate, scheduled human
decision — not a mechanism this bot performs on its own.
