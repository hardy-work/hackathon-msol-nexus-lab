#!/usr/bin/env bash
# Build + (re)deploy live-translate as a launchd service on macOS.
# Idempotent — safe to re-run on every deploy. Run it on the gateway host:
#   bash openclaw-skills/meeting-notetaker/live-translate/deploy/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
LABEL="ai.openclaw.live-translate"
PLIST_SRC="deploy/ai.openclaw.live-translate.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

echo "==> live-translate deploy ($APP_DIR)"

# --- 1. Python venv (need >= 3.10 for claude-agent-sdk / the subscription path) ---
pick_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3.10; do
    command -v "$c" >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  if command -v python3 >/dev/null 2>&1 \
     && python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)'; then
    echo python3; return 0
  fi
  return 1
}
if ! PYBIN="$(pick_python)"; then
  echo "ERROR: need Python >= 3.10 (claude-agent-sdk, the default subscription backend)."
  echo "       Install one — e.g.  brew install python@3.12  — or set"
  echo "       TRANSLATE_BACKEND=api in .env and re-run. Found: $(python3 -V 2>&1 || echo none)"
  exit 1
fi
echo "==> python: $PYBIN ($("$PYBIN" -V 2>&1))"
[ -d .venv ] || "$PYBIN" -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

# --- 2. Frontend build (node/npm usually via nvm on this host) ---
if ! command -v npm >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"; nvm use default >/dev/null 2>&1 || true
fi
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm not found (nvm not sourced?)."; exit 1; }
echo "==> building frontend (npm $(npm -v))"
( cd web && { npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund; } )
( cd web && npm run build )

# --- 3. .env ---
if [ ! -f .env ]; then
  cp .env.example .env
  echo "!! created .env from .env.example — fill VEXA_BASE_URL / VEXA_API_KEY /"
  echo "   WEB_PUBLIC_URL, then re-run this script."
fi

# --- 4. launchd service ---
mkdir -p logs "$HOME/Library/LaunchAgents"
chmod +x deploy/run.sh
sed "s|__APP_DIR__|$APP_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
echo "==> installed $PLIST_DST"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true   # ignore "not loaded"
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"
echo "==> service $LABEL (re)started"

# --- 5. health check ---
PORT="$(sed -n 's/^PORT=//p' .env 2>/dev/null | head -1)"; PORT="${PORT:-8080}"
sleep 2
if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo "==> healthy at http://127.0.0.1:$PORT/healthz"
else
  echo "!! not answering on :$PORT yet — tail logs/live-translate.err.log"
fi

cat <<NOTE

--- One-time, to make the Slack link work (not automated: edits gateway config) ---
The Slack link comes from the vexa-bridge MCP server, whose env lives in
~/.openclaw-hackathon/openclaw.json (NOT this app's .env). Add to its "env":
    "WEB_PUBLIC_URL": "<public URL of this app>",
    "LIVE_TRANSLATE_LANG": "vi"
then restart the gateway so it re-spawns the MCP server with the new env:
    launchctl kickstart -k gui/$UID_NUM/ai.openclaw.hackathon
NOTE
