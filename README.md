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
