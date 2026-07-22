# meeting-notetaker (OpenClaw skill)

Depends on the `vexa-bridge` MCP server in [../../vexa-mcp](../../vexa-mcp) —
register that first (see its README) so the `join_meeting` / `get_transcript`
/ `bot_status` / `stop_meeting` tools exist in your OpenClaw workspace.

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
