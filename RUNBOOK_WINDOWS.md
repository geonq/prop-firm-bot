# Windows runbook

Use this on the PC that will run the bot. The Python live runner itself is
cross-platform; only the Mac `launchd` wrapper is platform-specific.

## 1. Install and verify

```powershell
git clone https://github.com/geonq/prop-firm-bot.git
cd prop-firm-bot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

Copy no private data or credentials into Git. Add `.env` locally:

```text
PROJECTX_USERNAME=...
PROJECTX_API_KEY=...
```

Topstep's `--preflight` must pass before paper or live mode:

```powershell
python -m src.live.runner --preflight
```

It places no order. Manually confirm the returned bar timestamps are
open-labelled before proceeding; see `RUNBOOK_LIVE.md`.

## 2. Paper runner and scheduling

Run a monitored paper session first:

```powershell
.\scripts\windows\run_orbbot.ps1 -Mode paper
```

Install the default paper task only after that succeeds:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\windows\install_orbbot_task.ps1 -Mode paper
```

The task runs at 14:20 and 15:20 on weekdays in Germany-local time; the
runner's process lock makes the second trigger exit safely. Keep it in paper
mode for at least ten completed trading sessions over two weeks. Switch to
live only through the explicit gate in `RUNBOOK_LIVE.md`.

## 3. Fleet EV report

The report requires the private Databento parquet (not committed):
`DataLocal/nq_ohlcv_1m_2015-01-01_2026-07-16.parquet`. Obtain it with your
own Databento key using the tracked fetch script, then run:

```powershell
python .\Analysis\scripts\fleet_ev.py
```

It writes ignored JSON under `Analysis/output/`. It replays the frozen
`8afbe6259cab2dd2` ORB distribution and does not tune parameters or unlock a
holdout.

## 4. Tradeify and MyFundedFutures

Do not point the TopstepX adapter at Tradovate credentials: it is a ProjectX
client only. A Tradovate execution adapter needs the actual API contract and
account credentials on the PC, followed by a separate paper/reconciliation
pass. No endpoint is guessed in this repository.

Tradeify permits personal non-HFT automation but requires the bot to be
exclusive to Tradeify; never run the same ORB bot there alongside Topstep,
Lucid, or MFFU. MFFU permits tailored automation and same-user account
copying, subject to its no-HFT/no-sim-fill-exploitation/T1-news rules.
