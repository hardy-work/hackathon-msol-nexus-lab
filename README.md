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
  - `soniox-bridge/` — transcription backend Vexa calls into.
  - `notes/` — generated meeting summaries.

- [`openclaw-skills/jira-task/`](openclaw-skills/jira-task/) — creates and
  updates Jira tasks in project NEX via natural language (Vietnamese/English)
  for the MOR PM, always previewing changes and requiring confirmation before
  writing to Jira. Contains:
  - `SKILL.md` — instructions the agent follows to create/update tasks.

  Needs a `.env` in this folder with `JIRA_EMAIL`, `JIRA_API_TOKEN`,
  `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_BOARD_ID` (see
  `.env.example` in the same folder).

- [`openclaw-skills/risk-assessment/`](openclaw-skills/risk-assessment/) —
  reads project progress data (Google Sheet Sprint tabs or Jira, per-project
  config) daily or on demand, runs a deterministic rule engine to detect
  risks/issues, and drafts a narrative report for the PM. Writes only happen
  after the PM confirms in natural language — never straight from the daily
  scan. Contains:
  - `SKILL.md` — instructions the agent follows for the Scan/Apply flow.
  - `scripts/rule-engine.js` (+ `rule-engine.test.js`) — deterministic risk
    scoring/trend logic, run via `node --test scripts/`.

  Needs a `config.json` (see `config.example.json`) and a `.env` (see
  `.env.example`) in this folder — self-contained, independent from
  `gg-sheet`/`jira-task` even when reading the same project.

- [`openclaw-skills/daily-report/`](openclaw-skills/daily-report/) — reminds
  the team to report task status in Slack, collects reports, answers
  questions, and pushes reports to Google Sheets and/or Jira (reusing
  `jira-task`) after confirmation. Connects to Slack via OpenClaw's official
  Slack plugin (no custom bot code needed). Contains:
  - `SKILL.md` — instructions the agent follows for reminders, report
    collection, and pushing data.
  - `sheets-bridge/` — MCP server bridging the Google Sheets API via a
    service account.

  Needs a `.env` in this folder with `SLACK_REPORT_CHANNEL`,
  `REMINDER_TIME`, `REMINDER_TIMEZONE`, `REMINDER_WEEKDAYS_ONLY` (see
  `.env.example`), plus `sheets-bridge/.env` and the `jira-task/.env` vars
  above for the Jira-linked path. See
  [`openclaw-skills/daily-report/README.md`](openclaw-skills/daily-report/README.md)
  for full setup including the OpenClaw Slack plugin.

Assumes a Vexa instance is already running and reachable (see the machine at
`192.168.4.15:18056` on the LAN, or your own self-hosted instance — see
[Vexa's README](https://github.com/Vexa-ai/vexa) to deploy one).

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
   [`openclaw-skills/meeting-notetaker/soniox-bridge/README.md`](openclaw-skills/meeting-notetaker/soniox-bridge/README.md).

`.env` and `.mcp.json` are gitignored (they hold API keys) — always copy
from the `.example` files rather than committing real ones.

## Known limitations

See the "Known limitation" section in
[`SKILL.md`](openclaw-skills/meeting-notetaker/SKILL.md) (multilingual
meetings, single-language-per-chunk) and in
[`soniox-bridge/README.md`](openclaw-skills/meeting-notetaker/soniox-bridge/README.md)
(no per-request diarization, approximate confidence mapping).

## Adding a new skill

Create a new folder under `openclaw-skills/<skill-name>/` with its own
`SKILL.md` and any supporting MCP servers/services it needs, following the
same self-contained pattern as `meeting-notetaker/`.
