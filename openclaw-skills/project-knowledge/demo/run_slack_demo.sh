#!/usr/bin/env bash
# Local Slack-shaped demo; no Slack token or network required.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
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
