#!/bin/bash
# Install the fire monitor as a macOS LaunchAgent (starts on login, restarts if it crashes).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3)"
PLIST_SRC="$PROJECT_DIR/launchd/com.sdfire.agent.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/com.sdfire.agent.plist"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "Create .env first: cp .env.example .env && edit TEAMS_WEBHOOK_URL"
  exit 1
fi

sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__PYTHON__|$PYTHON|g" "$PLIST_SRC" > "$PLIST_DST"

launchctl bootout "gui/$(id -u)/com.sdfire.agent" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.sdfire.agent"
launchctl kickstart -k "gui/$(id -u)/com.sdfire.agent"

echo "Installed. Agent logs: $PROJECT_DIR/agent.log"
echo "Stop:  launchctl bootout gui/$(id -u)/com.sdfire.agent"
echo "Start: launchctl bootstrap gui/$(id -u) $PLIST_DST && launchctl kickstart -k gui/$(id -u)/com.sdfire.agent"
