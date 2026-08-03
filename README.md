# hackathon-msol-nexus-lab

A collection of OpenClaw skills. Each skill lives in its own folder under
[`openclaw-skills/`](openclaw-skills/), self-contained with whatever MCP
servers / backend services it depends on.

## Skills

- [`openclaw-skills/meeting-notetaker/`](openclaw-skills/meeting-notetaker/) —
  joins a Google Meet/Zoom call via a bot ([Vexa](https://vexa.ai),
  self-hosted), transcribes it (via [Soniox](https://soniox.com)'s real-time
  API), filters ASR noise/hallucination, and produces a structured meeting
  summary with action items. Contains:
  - `SKILL.md` — instructions the agent follows to run the whole flow.
  - `vexa-mcp/` — MCP server bridging Vexa's bot REST API.
  - `notes/` — generated meeting summaries.

  Depends on two standalone backend servers under [`services/`](services/):
  `soniox-bridge` (transcription) and `live-translate` (the shared live
  transcript + translation web view). They deploy independently of this skill
  — see [Services](#services) below.

- [`openclaw-skills/jira-task-editor/`](openclaw-skills/jira-task-editor/) —
  creates and updates Jira tasks in project NEX via natural language
  (Vietnamese/English) for the MOR PM, always previewing changes and
  requiring confirmation before writing to Jira. Contains:
  - `SKILL.md` — instructions the agent follows to create/update tasks.

  Needs a `.env` in this folder with `JIRA_EMAIL`, `JIRA_API_TOKEN`,
  `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_BOARD_ID` (see
  `.env.example` in the same folder).

- [`openclaw-skills/jira-daily-report/`](openclaw-skills/jira-daily-report/) —
  end-of-day report roll-up for the PM: who logged work today on the active
  sprint, who didn't, who logged but forgot to update status on an
  already-late issue, and a reschedule proposal for that member's other
  sprint issues (assumes 100% effort, one task at a time). Read-only — never
  writes to Jira; hand-off to `jira-task-editor` for any actual update.
  Contains:
  - `SKILL.md` — instructions the agent follows to build the report.

  Needs a `.env` in this folder with the same `JIRA_*` vars as
  `jira-task-editor` plus optional `DAILY_WORK_HOURS` (defaults to 8) — see
  `.env.example`.

- [`openclaw-skills/gg-sheet/`](openclaw-skills/gg-sheet/) — adds, edits, and
  deletes tasks in a project's Google Sheet schedule (tab/gid tracked in
  `config.json`, not hardcoded to one project) for the MOR PM, always
  previewing changes and requiring confirmation before writing. Calls the
  Google Sheets API v4 directly (Service Account for writes, API key for
  reads). Read-only for progress reporting — see `gg-sheet-daily-report`
  below. Contains:
  - `SKILL.md` — instructions the agent follows for add/edit/delete/reschedule.
  - `config.json` — per-project sheet/tab config (gitignored; see
    `config.example.json`).
  - `scripts/get-token.sh` — mints a Service Account access token for writes.

  Needs a `.env` in this folder with `GOOGLE_SHEETS_API_KEY` and
  `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` (see `.env.example`), plus a Service
  Account JSON key file shared as Editor on the target sheet.

- [`openclaw-skills/gg-sheet-daily-report/`](openclaw-skills/gg-sheet-daily-report/) —
  end-of-day report roll-up for the PM, mirroring `jira-daily-report` but for
  the Google Sheet schedule managed by `gg-sheet`: which assignees updated
  progress today vs. didn't, which today's tasks are out of effort but still
  show an unchanged status, and a reschedule proposal (scanning the whole
  tab) for assignees with overrun tasks. Read-only — never writes to the
  sheet; hand off to `gg-sheet` (Action 2b: Re-schedule) for any actual
  update. Shares `config.json` with `gg-sheet` rather than duplicating it.
  Contains:
  - `SKILL.md` — instructions the agent follows to build the report.

  Needs a `.env` in this folder with `GOOGLE_SHEETS_API_KEY` only (read-only,
  no Service Account needed) — see `.env.example`.

- [`openclaw-skills/project-knowledge/`](openclaw-skills/project-knowledge/) —
  read-only Nexus project knowledge skill. It answers questions from the
  committed Nexus Plan corpus with DuckDB/facts, wiki citations, confidence and
  explicit `not_in_kb`/`confident_no` semantics. It never writes Jira, Sheets or
  Slack. The corpus is self-contained; `derived/` indexes are rebuilt locally.
- [`openclaw-skills/slack-evidence-sheet/`](openclaw-skills/slack-evidence-sheet/) —
  turns one Slack evidence-collection thread into a brand-new Google Sheet: one
  row per person, with their email, the time they posted, and their attached
  screenshots uploaded to a Google Drive folder. Columns/title come from
  `config.json` so the next round only needs a config edit. Always previews the
  roster and asks for confirmation before creating anything on Drive. Contains:
  - `SKILL.md` — instructions the agent follows for the whole flow.
  - `scripts/oauth-setup.js` — one-time browser consent to mint a refresh token.
  - `scripts/get-token.sh` — refresh token → access token (same interface as
    `gg-sheet`'s script).
  - `scripts/slack-fetch.js` — reads the thread, resolves emails, downloads files.
  - `scripts/build-sheet.js` — uploads to Drive, builds and formats the sheet.

  Unlike `gg-sheet`, this one authenticates as an **OAuth user, not a Service
  Account** — Service Accounts have no Drive storage quota, so they cannot
  *create* files at all (`storageQuotaExceeded`), only edit existing ones. The
  rule of thumb for this repo: **edit an existing file → Service Account; create
  a new file → OAuth.** See the skill's README for the full reasoning.

  Needs a `.env` in this folder with `SLACK_BOT_TOKEN`,
  `GOOGLE_OAUTH_CLIENT_FILE`, `GOOGLE_OAUTH_TOKEN_FILE` (see `.env.example`),
  plus a `config.json` copied from `config.example.json`.

Assumes a Vexa instance is already running and reachable (see the machine at
`192.168.4.15:18056` on the LAN, or your own self-hosted instance — see
[Vexa's README](https://github.com/Vexa-ai/vexa) to deploy one).

## Services

Standalone backend servers under [`services/`](services/) — not OpenClaw
skills themselves, but persistent servers a skill depends on. Each deploys and
runs independently of the skill-sync flow (its own build/run steps, own
lifecycle), see its own README:

- [`services/soniox-bridge/`](services/soniox-bridge/) — transcription backend
  Vexa calls into, used by `meeting-notetaker`.
- [`services/live-translate/`](services/live-translate/) — realtime meeting
  transcript + translation web app, used by `meeting-notetaker`.

## Setup on a new machine

1. Clone this repo.
2. Set up the MCP server:
   ```bash
   cd openclaw-skills/meeting-notetaker/vexa-mcp
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in VEXA_API_KEY (VEXA_BASE_URL is already correct if you're on the same LAN)
   ```
3. Register the MCP server for Claude Code:
   ```bash
   cd ../../..
   cp .mcp.json.example .mcp.json
   # edit .mcp.json: replace <ABSOLUTE_PATH_TO_REPO> with this repo's real
   # absolute path, and <YOUR_VEXA_API_KEY> with the same key from step 2
   ```
4. Restart Claude Code so it picks up `.mcp.json` — the `vexa-bridge` tools
   (`join_meeting`, `get_transcript`, `bot_status`, `stop_meeting`,
   `list_meetings`) should now be available.
5. (Optional, to use as an actual OpenClaw skill rather than through Claude
   Code directly) copy the skill into your OpenClaw workspace, or symlink it
   so `git pull` here keeps it in sync:
   ```bash
   mkdir -p ~/.openclaw/workspace/skills
   ln -s "$(pwd)/openclaw-skills/meeting-notetaker" ~/.openclaw/workspace/skills/meeting-notetaker
   ```
6. Deploy the transcription backend — see
   [`services/soniox-bridge/README.md`](services/soniox-bridge/README.md).

### Project Knowledge skill

For the offline Nexus Q&A demo, install its pinned Python dependencies and run
the skill-local demo:

```bash
cd openclaw-skills/project-knowledge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 bash demo/run_demo.sh
```

The normal entrypoint is `scripts/run.py`. It is deterministic and does not
need network or Claude credentials. With `--llm`, unresolved queries use a
cheap Haiku router first and send selected wiki context to Sonnet; Gate 3b
review remains opt-in.

The query boundary is fail-closed. Inject a trusted identity and roles from the
host runtime (SSO/Slack mapping), for example:

```bash
PROJECT_KNOWLEDGE_ACTOR=local-demo \
PROJECT_KNOWLEDGE_ROLES=project_member \
python3 scripts/run.py --project nexus --query "ĐôNT làm vai trò gì?"
```

Coverage receipts do not grant themselves authority. Production also injects
`PROJECT_KNOWLEDGE_COVERAGE_GRANTS` and `PROJECT_KNOWLEDGE_APPROVAL_IDS` from an
approval service; the offline test runner supplies demo-only values.

The pipeline also builds a task relationship graph and records corpus
version/freshness metadata. Query JSON reports `fresh`, `stale`, or `unknown`
so a changed workbook cannot silently look like a current answer. Run
`scripts/run_all.sh` after replacing the workbook.

Document identity and supersession live in `documents.yml`. New document versions
are ingested in an isolated `ingest/<doc>@vN` worktree using
`scripts/ingest_flow.py`; the flow creates a raw diff/impact plan and never merges
automatically.

The stage-by-stage mapping and remaining data boundaries are documented in
[`openclaw-skills/project-knowledge/FLOW_STATUS.md`](openclaw-skills/project-knowledge/FLOW_STATUS.md).

`demo/run_slack_demo.sh` exercises the Slack-shaped adapter locally without a
token. A minimal signed HTTP boundary is available at
`adapters/slack/slack_http.py`; set `SLACK_SIGNING_SECRET` and run it on
`/slack/events`. `SLACK_BOT_TOKEN` is optional and is used only to post the
formatted Block Kit response. The Project Knowledge skill remains read-only.
Set `PROJECT_KNOWLEDGE_SLACK_ROLE_MAP` to a trusted JSON user-to-roles mapping. The
gateway acknowledges Slack before retrieval, posts asynchronously, and keeps
bounded conversation context per channel/thread.

Production Slack delivery uses a durable idempotent queue with retry/dead-letter;
see `adapters/slack/.env.example`. Mount `PROJECT_KNOWLEDGE_STATE_DIR` on persistent
storage because it owns jobs, query cache, conversation retention and privacy-safe
telemetry. `/health` reports aggregate queue/runtime status.

The Slack process uses a long-lived runtime, so DuckDB, graph and BGE-M3 stay warm.
Run `scripts/benchmark.py` for p50/p95 latency. `scripts/eval_onboarding.py` and
`scripts/eval_production.py` cover onboarding, authorization, context, cache and
concurrent request boundaries.

To expose it to an OpenClaw workspace, link the skill directory and restart the
gateway:

```bash
mkdir -p ~/.openclaw/workspace/skills
ln -s "$(pwd)" ~/.openclaw/workspace/skills/project-knowledge
```

`.env` and `.mcp.json` are gitignored (they hold API keys) — always copy
from the `.example` files rather than committing real ones.

## Known limitations

See the "Known limitation" section in
[`SKILL.md`](openclaw-skills/meeting-notetaker/SKILL.md) (multilingual
meetings, single-language-per-chunk) and in
[`soniox-bridge/README.md`](services/soniox-bridge/README.md)
(no per-request diarization, approximate confidence mapping).

## Adding a new skill

Create a new folder under `openclaw-skills/<skill-name>/` with its own
`SKILL.md` and any supporting MCP servers/services it needs, following the
same self-contained pattern as `meeting-notetaker/`.
