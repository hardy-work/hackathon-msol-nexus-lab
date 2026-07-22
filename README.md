# Meeting Notetaker (Vexa + OpenClaw skill)

Joins a Google Meet/Zoom call via a bot ([Vexa](https://vexa.ai), self-hosted),
transcribes it, filters ASR noise/hallucination, and produces a structured
meeting summary with action items.

## Structure

- [`vexa-mcp/`](vexa-mcp/) — MCP server bridging Vexa's REST API (`join_meeting`,
  `get_transcript`, `bot_status`, `stop_meeting`, `list_meetings`).
- [`openclaw-skills/meeting-notetaker/`](openclaw-skills/meeting-notetaker/) —
  the `SKILL.md` instructing an agent how to run the whole flow, plus
  generated meeting notes under `notes/`.

Assumes a Vexa instance is already running and reachable (see the machine at
`192.168.4.15:18056` on the LAN, or your own self-hosted instance — see
[Vexa's README](https://github.com/Vexa-ai/vexa) to deploy one).

## Setup on a new machine

1. Clone this repo.
2. Set up the MCP server:
   ```bash
   cd vexa-mcp
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in VEXA_API_KEY (VEXA_BASE_URL is already correct if you're on the same LAN)
   ```
3. Register the MCP server for Claude Code:
   ```bash
   cd ..
   cp .mcp.json.example .mcp.json
   # edit .mcp.json: replace <ABSOLUTE_PATH_TO_REPO> with this repo's real
   # absolute path, and <YOUR_VEXA_API_KEY> with the same key from step 2
   ```
4. Restart Claude Code so it picks up `.mcp.json` — the `vexa-bridge` tools
   (`join_meeting`, `get_transcript`, `bot_status`, `stop_meeting`,
   `list_meetings`) should now be available.
5. (Optional, to use as an actual OpenClaw skill rather than through Claude
   Code directly) copy the skill into your OpenClaw workspace:
   ```bash
   mkdir -p ~/.openclaw/workspace/skills
   cp -r openclaw-skills/meeting-notetaker ~/.openclaw/workspace/skills/
   ```

`.env` and `.mcp.json` are gitignored (they hold the API key) — always copy
from the `.example` files rather than committing real ones.

## Known limitation

Transcript accuracy is bounded by the underlying STT (currently a free
hosted Whisper token) — expect mistranscribed jargon/numbers on technical,
mixed Vietnamese/English meetings. See the "Known limitation" section in
[`SKILL.md`](openclaw-skills/meeting-notetaker/SKILL.md) for details and
the fix path (self-hosted GPU Whisper).
