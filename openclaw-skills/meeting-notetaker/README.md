# meeting-notetaker (OpenClaw skill)

Everything this skill needs lives in this one folder:

- [`vexa-mcp/`](vexa-mcp/) — MCP server bridging Vexa's bot API (`join_meeting`,
  `get_transcript`, `bot_status`, `stop_meeting`, `list_meetings`). Register
  this first (see its README) so those tools exist in your OpenClaw workspace.
- `notes/` — generated meeting summaries.

This skill also depends on the standalone backend server
[`soniox-bridge`](../../services/soniox-bridge/) (transcription; replaces
self-hosted Whisper — see its README for why and how to deploy) and
[`live-translate`](../../services/live-translate/) (the shared live transcript
+ translation web view). Both live under [`services/`](../../services/) and
deploy independently of this skill. **`live-translate` is required, not
optional** — `get_transcript` reads exclusively from its assembled transcript
(sourced from the B-full continuous Soniox stream via `vexa-bot-patch/`).
Vexa's own `/transcripts` endpoint is never called; Vexa is only used for bot
orchestration now (`join_meeting`/`bot_status`/`stop_meeting`/`list_meetings`),
since its confirm layer used to drop text at ~30s turn seams.

## Install

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -r meeting-notetaker ~/.openclaw/workspace/skills/
```

`VEXA_BASE_URL` and `VEXA_API_KEY` must be set wherever the `vexa-bridge` MCP
server runs (its own env, not OpenClaw's) — the `requires.env` gate in this
skill's frontmatter just keeps it hidden until those are configured.

`notes/` is where generated meeting summaries land, named
`<date>-<native_meeting_id>.md`.
