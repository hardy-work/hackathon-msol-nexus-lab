#!/usr/bin/env bash
# Local Slack-shaped demo; no Slack token or network required.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# The stdin bridge is a local fixture runner, so give it an explicit demo
# identity. The real HTTP gateway maps Slack user IDs through the trusted role
# map and must not inherit this fallback.
export PROJECT_KNOWLEDGE_ACTOR="${PROJECT_KNOWLEDGE_ACTOR:-local-slack-demo}"
export PROJECT_KNOWLEDGE_ROLES="${PROJECT_KNOWLEDGE_ROLES:-project_member}"
export PROJECT_KNOWLEDGE_DEMO_MODE="${PROJECT_KNOWLEDGE_DEMO_MODE:-1}"
python3 adapters/slack/slack_selftest.py
python3 adapters/slack/slack_http_selftest.py
echo
echo "[slack-demo] app_mention response"
python3 adapters/slack/slack_bridge.py \
  < adapters/slack/fixtures/app_mention.json
echo
echo "[slack-demo] approval proposal response"
python3 adapters/slack/slack_bridge.py \
  < adapters/slack/fixtures/action_request.json
