#!/bin/bash
# Wrapper launched by launchd (see com.geonq.orbbot.plist). Activates the
# project venv, sources .env for PROJECTX_USERNAME/PROJECTX_API_KEY, and
# runs the runner's --auto mode under caffeinate so the Mac cannot sleep
# through the ~2-hour trading session (spec: Tasks/todo.md "Phase 6B" --
# "caffeinate so the Mac stays awake through the session").
#
# --auto self-gates on the session calendar (weekends/already-traded exit
# silently, return 0) -- this script is safe to be triggered by BOTH
# launchd StartCalendarInterval entries (14:20 and 15:20 local) every
# weekday without any date logic here; double-fires are harmless by design.
#
# Mode is fixed to "paper" here deliberately -- switching to live trading
# is a manual, explicit edit (see RUNBOOK_LIVE.md step 7 "switching
# paper->live"), never something a scheduled script silently escalates to.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "run_orbbot.sh: $REPO_ROOT/.env not found -- see RUNBOOK_LIVE.md step 3" >&2
    exit 1
fi

if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo "run_orbbot.sh: $REPO_ROOT/.venv not found -- create it first (python3 -m venv .venv && pip install -r requirements.txt)" >&2
    exit 1
fi

set -a
source "$REPO_ROOT/.env"
set +a

source "$REPO_ROOT/.venv/bin/activate"

MODE="${ORBBOT_MODE:-paper}"

mkdir -p "$REPO_ROOT/LiveState"
LOG_FILE="$REPO_ROOT/LiveState/launchd_$(date +%Y-%m-%d).log"

echo "=== run_orbbot.sh starting at $(date) mode=$MODE ===" >> "$LOG_FILE"

# caffeinate -i: prevent idle sleep for the duration of the child process
# (the runner itself exits on its own once the session/report is done, so
# this does not keep the Mac awake indefinitely).
caffeinate -i python3 -m src.live.runner --mode "$MODE" --auto >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "=== run_orbbot.sh finished at $(date) exit=$EXIT_CODE ===" >> "$LOG_FILE"
exit $EXIT_CODE
