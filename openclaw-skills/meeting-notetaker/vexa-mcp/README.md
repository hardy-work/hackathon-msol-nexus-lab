# vexa-mcp

MCP server bridging [Vexa](https://vexa.ai)'s self-hosted meeting-bot REST API,
so an agent (OpenClaw / Claude Code) can send a bot into a Google Meet / Zoom
call, read the live transcript, and stop the bot.

## Setup

```bash
cd vexa-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Set the two env vars once you have Vexa deployed:

```bash
export VEXA_BASE_URL="http://<vexa-host>:18056"
export VEXA_API_KEY="vxa_..."
```

## Register with Claude Code / OpenClaw

Add to `.mcp.json` (or OpenClaw's MCP config):

```json
{
  "mcpServers": {
    "vexa-bridge": {
      "command": "<ABSOLUTE_PATH_TO_REPO>/openclaw-skills/meeting-notetaker/vexa-mcp/.venv/bin/python",
      "args": ["<ABSOLUTE_PATH_TO_REPO>/openclaw-skills/meeting-notetaker/vexa-mcp/server.py"],
      "env": {
        "VEXA_BASE_URL": "http://<vexa-host>:18056",
        "VEXA_API_KEY": "vxa_..."
      }
    }
  }
}
```

## Tools

- `join_meeting(meeting_url | platform + native_meeting_id, bot_name, language)` — sends the bot into a call
- `get_transcript(platform, native_meeting_id)` — polls the live/final transcript with speaker labels
- `bot_status()` — lists currently running bots
- `stop_meeting(platform, native_meeting_id)` — removes the bot from a call
- `list_meetings()` — lists past captured meetings

`join_meeting` parses `meeting_url` for Google Meet and Zoom links automatically.
For Teams, or if parsing fails, pass `platform` and `native_meeting_id` directly.

## Not yet wired up

- No webhook/callback from Vexa when a meeting ends — the calling skill
  needs to poll `get_transcript` or `bot_status` to detect completion.
- Summarization happens outside this server (the agent calling these tools
  is expected to summarize the transcript itself).
