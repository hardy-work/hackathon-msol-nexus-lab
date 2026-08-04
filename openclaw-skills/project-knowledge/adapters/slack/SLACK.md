# Slack adapter

This adapter translates Slack Events API or slash-command payloads into the
provider-neutral Project Knowledge JSON contract. Local tests use JSON over
stdin; `slack_http.py` is the signed Events API HTTP boundary.

## Local usage

The stdin bridge is a fixture/demo transport and still needs a trusted local
identity because the Project Knowledge skill is internal by default:

```bash
export PROJECT_KNOWLEDGE_ACTOR=local-slack-demo
export PROJECT_KNOWLEDGE_ROLES=project_member
export PROJECT_KNOWLEDGE_DEMO_MODE=1
```

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

## Slack app checklist

Before connecting a real workspace:

1. Build and verify the corpus from the same commit that will run the gateway:
   `python3 scripts/versioning.py check --summary` must report `fresh`.
2. Create a Slack app, enable Event Subscriptions, and set a public HTTPS
   Request URL ending in `/slack/events`. Slack's URL verification challenge
   is handled by the gateway.
3. Subscribe to `app_mention` (and add a Slash Command such as `/nexus` only
   if that interaction is needed). Install/reinstall the app after changing
   scopes, then invite the bot to the target channel.
4. Configure `SLACK_SIGNING_SECRET` and `SLACK_BOT_TOKEN` out of band. The
   bot needs `app_mentions:read` and `chat:write`; Slash Commands also need the
   command feature enabled in the Slack app.
5. Fill `PROJECT_KNOWLEDGE_SLACK_ROLE_MAP` with real Slack `U...` user IDs and
   only roles declared in `access.yml`. A missing user mapping is deliberately
   `forbidden`; do not set `PROJECT_KNOWLEDGE_DEMO_MODE=1` in production.
6. Keep `PROJECT_KNOWLEDGE_STATE_DIR` on persistent storage. It contains the
   durable queue, bounded conversation context, cache and privacy-safe
   telemetry. Do not commit `.env` or state files.

The HTTP boundary rejects payloads larger than `SLACK_MAX_BODY_BYTES` before
reading or verifying them; the default is 1 MiB, far above normal Slack event
payloads. Keep the reverse proxy's request limit at least as strict as this
value.

For a demo on one host, load `adapters/slack/.env` from a secret manager or
process environment, then run:

```bash
python3 scripts/versioning.py check --summary
python3 adapters/slack/slack_http.py
curl -fsS http://127.0.0.1:8787/health
```

Keep `SLACK_BOT_TOKEN` configured for Events API/app mentions: the gateway
queues and acknowledges queries before retrieval, then posts the answer with
`chat.postMessage`. Without the token, synchronous responses are useful for a
local HTTP test or slash-command response but app-mention answers cannot be
posted back to the channel. Put TLS/public exposure in a reverse proxy or
tunnel; do not expose the stdlib HTTP server directly to the Internet.

For a minimal local gateway, run:

```bash
python3 adapters/slack/slack_http.py
```

It listens on `/slack/events` and validates `SLACK_SIGNING_SECRET`. With
`SLACK_BOT_TOKEN`, it acknowledges the event before retrieval/model work, then
posts Block Kit asynchronously with `chat.postMessage`. Conversation context is
stored per channel/thread in persistent `.runtime/`; no credentials are stored in
the skill.

Slack events are inserted into an idempotent SQLite queue before ACK. The unique
`event_id` prevents duplicate replies, failures use exponential retry, and jobs
move to `dead` after `SLACK_JOB_MAX_ATTEMPTS`. The formatted answer is persisted
before posting, so a post retry does not rerun retrieval/model generation.

The embedded worker is enabled by default. For a separate worker process:

```bash
SLACK_EMBEDDED_WORKER=0 python3 adapters/slack/slack_http.py
python3 adapters/slack/slack_worker.py
python3 adapters/slack/slack_worker.py --stats
python3 adapters/slack/slack_worker.py --show 42
python3 adapters/slack/slack_worker.py --requeue 42
```

Mount `PROJECT_KNOWLEDGE_STATE_DIR` on a persistent volume. `/health` exposes
queue counts and one-hour aggregate telemetry without raw questions or actor IDs.

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
