#!/usr/bin/env bash
# Build + (re)deploy live-translate as a launchd service on macOS.
# Idempotent — safe to re-run on every deploy. Run it on the gateway host:
#   bash <app_dir>/deploy/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
LABEL="ai.openclaw.live-translate"
PLIST_SRC="deploy/ai.openclaw.live-translate.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

echo "==> live-translate deploy ($APP_DIR)"

# Make `claude` / node reachable the same way run.sh does, so backend detection
# and the frontend build behave like the running service will.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
if [ -d "$HOME/.nvm/versions/node" ]; then
  _node="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1 || true)"
  [ -n "$_node" ] && export PATH="$_node:$PATH"
fi

# --- 1. Pick Python; note whether it's >= 3.10 (needed by claude-agent-sdk) ---
PYBIN=""; HAS_PY310=false
for c in python3.13 python3.12 python3.11 python3.10; do
  if command -v "$c" >/dev/null 2>&1; then PYBIN="$c"; HAS_PY310=true; break; fi
done
if [ -z "$PYBIN" ]; then
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: no python3 found."; exit 1; }
  PYBIN=python3
  python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' && HAS_PY310=true
fi
echo "==> python: $PYBIN ($("$PYBIN" -V 2>&1)); >=3.10: $HAS_PY310"

# --- 2. Decide translation backend (respect an existing .env choice) ---
existing_backend="$(sed -n 's/^TRANSLATE_BACKEND=//p' .env 2>/dev/null | head -1 || true)"
BACKEND="${existing_backend:-subscription}"
if [ "$BACKEND" = "subscription" ] && [ "$HAS_PY310" != true ]; then
  # claude-agent-sdk needs >=3.10; fall back to a backend that runs on 3.9.
  if command -v claude >/dev/null 2>&1; then
    BACKEND="cli"
    echo "!! Python < 3.10: subscription (SDK) unavailable -> using 'cli' backend"
    echo "   (spawns the logged-in \`claude\` CLI per call, ~6s; still subscription)."
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    BACKEND="api"
    echo "!! Python < 3.10: using 'api' backend (ANTHROPIC_API_KEY present)."
  else
    echo "ERROR: Python < 3.10 and no \`claude\` CLI / ANTHROPIC_API_KEY."
    echo "       Install Python >= 3.10, log in with Claude Code, or set an API key."
    exit 1
  fi
fi
echo "==> translation backend: $BACKEND"

# --- 3. venv + deps (base + backend extra) ---
[ -d .venv ] || "$PYBIN" -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
case "$BACKEND" in
  subscription) ./.venv/bin/pip install -q "claude-agent-sdk>=0.2" ;;
  api)          ./.venv/bin/pip install -q "anthropic>=0.40" ;;
  cli)          : ;;  # no python deps; uses the claude CLI
esac

# --- 4. Frontend build (node/npm via nvm) ---
if ! command -v npm >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"; nvm use default >/dev/null 2>&1 || true
fi
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm not found (nvm not sourced?)."; exit 1; }
echo "==> building frontend (npm $(npm -v))"
( cd web && { npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund; } )
( cd web && npm run build )

# --- 5. .env (create if missing, then pin the resolved backend) ---
[ -f .env ] || { cp .env.example .env; echo "!! created .env from .env.example — fill VEXA_* / WEB_PUBLIC_URL"; }
if grep -q '^TRANSLATE_BACKEND=' .env; then
  # portable in-place edit (BSD/GNU sed both need a backup suffix)
  sed -i.bak "s|^TRANSLATE_BACKEND=.*|TRANSLATE_BACKEND=$BACKEND|" .env && rm -f .env.bak
else
  printf '\nTRANSLATE_BACKEND=%s\n' "$BACKEND" >> .env
fi

# --- 6. launchd service ---
mkdir -p logs "$HOME/Library/LaunchAgents"
chmod +x deploy/run.sh
sed "s|__APP_DIR__|$APP_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
echo "==> installed $PLIST_DST"
# Unload first (so a changed plist is picked up), then WAIT until it's really
# gone — bootstrapping while a bootout is still settling throws
# "Bootstrap failed: 5: Input/output error".
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
for _ in $(seq 1 10); do
  launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || break
  sleep 0.5
done
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"
echo "==> service $LABEL (re)started"

# --- 7. health check (retry: startup + first warm-up can take a few seconds) ---
PORT="$(sed -n 's/^PORT=//p' .env 2>/dev/null | head -1)"; PORT="${PORT:-8080}"
ok=false
for _ in $(seq 1 15); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then ok=true; break; fi
  sleep 1
done
if $ok; then
  echo "==> healthy at http://127.0.0.1:$PORT/healthz"
else
  echo "!! not answering on :$PORT after 15s — tail logs/live-translate.err.log"
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
