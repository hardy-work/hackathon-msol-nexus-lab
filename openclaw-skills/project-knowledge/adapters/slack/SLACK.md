# Slack adapter

This adapter translates Slack Events API or slash-command payloads into the
provider-neutral Project Knowledge JSON contract. Local tests use JSON over
stdin; `slack_http.py` is the signed Events API HTTP boundary.

## Local usage

```bash
python3 adapters/slack/slack_bridge.py \
  < adapters/slack/fixtures/app_mention.json
```

The output is a Slack-compatible response payload containing `blocks`, a
thread target when available, and machine-readable metadata under `metadata`.
By default the bridge is deterministic/offline. Set
`PROJECT_KNOWLEDGE_LLM=1` to enable the Haiku router and Sonnet fallback for
open questions; if the model runtime is unavailable it safely falls back to
the deterministic path.

## Supported inputs

- Events API `event_callback` with `event.type=app_mention` or `message`;
- slash command payloads with `command`, `user_id`, `channel_id`, and `text`;
- URL verification payloads (the challenge is echoed without querying the KB).

The parser strips `<@BOT_ID>` mentions and keeps `channel_id`, `user_id`,
`thread_ts`, and `ts` for context/audit. The gateway verifies Slack's signing
secret, rejects stale timestamps, and maps `user_id` to trusted roles using
`PROJECT_KNOWLEDGE_SLACK_ROLE_MAP`.

For a minimal local gateway, run:

```bash
python3 adapters/slack/slack_http.py
```

It listens on `/slack/events` and validates `SLACK_SIGNING_SECRET`. With
`SLACK_BOT_TOKEN`, it acknowledges the event before retrieval/model work, then
posts Block Kit asynchronously with `chat.postMessage`. Conversation context is
stored per channel/thread in ignored `derived/`; no credentials are stored in
the skill.

## Response rules

- Keep `status`, `confidence`, `citations`, `reason`, `tier`, and optional
  `route` telemetry in `metadata`.
- Render citations as Slack context bullets; do not hide provenance.
- Render `suggested_actions` as approval buttons only. The bridge never calls
  Jira, Excel, mail, or another write API.
- Reply in the originating thread when `thread_ts` exists; otherwise use the
  event timestamp for a threaded reply.
- Keep the source answer unchanged for numeric values and status semantics.

For a larger deployment, Bolt/serverless may replace only the HTTP transport;
parsing, authorization, retrieval and formatting contracts remain unchanged.
