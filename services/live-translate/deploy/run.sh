#!/usr/bin/env bash
# launchd entrypoint for live-translate. Kept separate from the plist so secrets
# live in .env (gitignored) instead of in a committed plist. Loads .env, fixes
# up PATH (launchd gives a bare one), then runs the server under the venv.
set -euo pipefail

# cd to the app dir (parent of deploy/), regardless of where launchd invokes us.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# launchd hands processes a minimal PATH. Add the usual spots so `claude` (the
# subscription translation backend), node, etc. resolve. Include the newest
# installed nvm node bin if present.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
if [ -d "$HOME/.nvm/versions/node" ]; then
  latest_node="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1 || true)"
  [ -n "$latest_node" ] && export PATH="$latest_node:$PATH"
fi

# Load .env (KEY=VALUE lines) into the environment.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

exec .venv/bin/python server.py
