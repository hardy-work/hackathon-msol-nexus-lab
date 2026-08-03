# Slack adapter

This adapter translates Slack Events API or slash-command payloads into the
provider-neutral Project Knowledge JSON contract. It is deliberately transport
agnostic: local tests use JSON over stdin, while a future Slack HTTP gateway can
verify the request and pass the same payload to `slack_bridge.py`.

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
`thread_ts`, and `ts` for context/audit. A production HTTP gateway must verify
Slack's signing secret and reject stale timestamps before invoking the bridge;
`parse_event.py` includes the HMAC helper for that boundary.

For a minimal local gateway, run:

```bash
python3 adapters/slack/slack_http.py
```

It listens on `/slack/events`, validates `SLACK_SIGNING_SECRET`, and returns
the formatted response directly. If `SLACK_BOT_TOKEN` is configured, it posts
the Block Kit response asynchronously with `chat.postMessage`; no credentials
are stored in the skill.

## Response rules

- Keep `status`, `confidence`, `citations`, `reason`, `tier`, and optional
  `route` telemetry in `metadata`.
- Render citations as Slack context bullets; do not hide provenance.
- Render `suggested_actions` as approval buttons only. The bridge never calls
  Jira, Excel, mail, or another write API.
- Reply in the originating thread when `thread_ts` exists; otherwise use the
  event timestamp for a threaded reply.
- Keep the source answer unchanged for numeric values and status semantics.

## Future transport

The team can wrap this bridge with Bolt, a small HTTP server, or serverless
functions. That transport should only handle Slack verification, retries and
posting; parsing, retrieval and formatting remain in this adapter.
