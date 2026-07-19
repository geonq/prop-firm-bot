#!/bin/bash
# Installs com.geonq.orbbot.plist into ~/Library/LaunchAgents/, substituting
# the real repo path for the __REPO_ROOT__ placeholder in the template.
# Idempotent: re-running unloads any existing agent with this label first.
#
# See RUNBOOK_LIVE.md step 5 for when to run this (AFTER a passing
# --preflight, BEFORE the paper-parallel validation period begins).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/launchd/com.geonq.orbbot.plist"
LABEL="com.geonq.orbbot"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [ ! -f "$TEMPLATE" ]; then
    echo "install_launchd.sh: template not found at $TEMPLATE" >&2
    exit 1
fi

if [ ! -x "$REPO_ROOT/scripts/launchd/run_orbbot.sh" ]; then
    echo "install_launchd.sh: $REPO_ROOT/scripts/launchd/run_orbbot.sh is not executable -- chmod +x it first" >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

# Unload any prior installation of this agent (safe no-op if none exists).
launchctl unload "$DEST" 2>/dev/null || true

sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$TEMPLATE" > "$DEST"

launchctl load "$DEST"

echo "Installed and loaded: $DEST"
echo ""
echo "Verify with:"
echo "  launchctl list | grep $LABEL"
echo ""
echo "This agent fires weekdays at 14:20 and 15:20 local Mac time (covers"
echo "CET/CEST vs ET DST drift) and self-gates on the session calendar --"
echo "it will run 'python3 -m src.live.runner --mode paper --auto' by default"
echo "(edit ORBBOT_MODE in scripts/launchd/run_orbbot.sh, or export it in"
echo ".env, to switch to 'live' -- see RUNBOOK_LIVE.md step 7)."
echo ""
echo "To uninstall: launchctl unload \"$DEST\" && rm \"$DEST\""
