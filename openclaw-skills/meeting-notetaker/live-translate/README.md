# live-translate

Realtime meeting **transcript + translation** web app, layered on top of the
existing Vexa bridge. It reads the same growing transcript the
`meeting-notetaker` skill polls, translates each new segment once, and streams
the result to every browser watching the room over Server-Sent Events.

```
[Browser] ──SSE──► [FastAPI] ──poll──► Vexa REST   (source transcript)
 2 columns              │
 src | translated       └──► Claude (Haiku) translates each new segment once
```

## Why it can use a Claude **subscription**

Translation goes through a pluggable backend (`translator.py`):

| `TRANSLATE_BACKEND` | Auth | Cost | Latency |
|---|---|---|---|
| `subscription` (default) | `claude` CLI login (Pro/Max) | subscription quota, no token bill | higher |
| `api` | `ANTHROPIC_API_KEY` | per-token | lower |

The subscription path shells out to `claude -p`, so it uses whatever Claude
Code is logged in with. **Requirements for that path:** Claude Code installed
and logged in on this host, and `ANTHROPIC_API_KEY` **unset** for this process
(its presence flips the CLI to API billing).

Crucially, translation happens **once per (segment, target language)** and is
cached, then fanned out to all viewers. 2 or 50 people opening the shared link
costs the same number of Claude calls — subscription rate limits scale with the
meeting, not the audience.

## Run

Backend:

```bash
cd live-translate
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill VEXA_BASE_URL / VEXA_API_KEY / WEB_PUBLIC_URL
python server.py        # serves on :8080
```

Frontend:

```bash
cd web
npm install
npm run build           # backend serves web/dist automatically
# or, for hot-reload dev (proxies /api to :8080):
npm run dev
```

## Deploy on the gateway (macOS / launchd)

The gateway host is a Mac (services run under `launchd`, not systemd/docker).
`deploy/deploy.sh` builds and installs the app as a launchd user agent — run it
on that host:

```bash
bash openclaw-skills/meeting-notetaker/live-translate/deploy/deploy.sh
```

It picks a Python ≥ 3.10, creates the venv + installs deps, sources `nvm` and
builds the frontend, renders `deploy/ai.openclaw.live-translate.plist` into
`~/Library/LaunchAgents/`, then (re)starts the `ai.openclaw.live-translate`
service and health-checks it. Env/secrets come from `.env` (loaded by
`deploy/run.sh`), never from the committed plist. Logs: `logs/live-translate.*`.

Service controls:

```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.live-translate   # restart
launchctl bootout   gui/$(id -u)/ai.openclaw.live-translate      # stop/unload
```

**Slack link (one-time, manual — edits gateway config):** the link is produced
by the vexa-bridge MCP server, whose env lives in
`~/.openclaw-hackathon/openclaw.json`, *not* this app's `.env`. Add
`"WEB_PUBLIC_URL"` and `"LIVE_TRANSLATE_LANG"` to that server's `env`, then
`launchctl kickstart -k gui/$(id -u)/ai.openclaw.hackathon` to restart the
gateway. `deploy.sh` prints this reminder at the end.

Then open `http://<host>:8080/meet/<platform>/<native_meeting_id>?lang=vi`
— e.g. `/meet/google_meet/abc-defg-hij?lang=vi`. The room home page (`/`) also
accepts a raw Meet/Zoom link.

**The target language is fixed by the link** and is intentionally not
switchable inside the room — everyone watching a given link sees the same
translation. The language is chosen once, when the link is created (by the
Slack flow, or on the home page). This keeps one consistent shared output and
avoids per-viewer changes. A late viewer opening the same room with a
*different* `?lang=` still works: the server backfills that language on demand.

## How a room streams

- `GET /api/rooms/{platform}/{id}/stream?lang=vi` — SSE. Emits `hello`, then a
  backlog of everything captured so far, then live `segment` events (original
  text, shown instantly) followed by `translation` events (filled in when
  ready). Ends with an `end` event when the bot leaves or the room goes silent.
- `GET /api/rooms/{platform}/{id}` — room metadata + `share_link` (built from
  `WEB_PUBLIC_URL`).
- `GET /healthz`

## Slack auto-post (wired)

When the bot is asked to join from Slack, the room link is posted back into the
thread automatically:

1. Set `WEB_PUBLIC_URL` (and optionally `LIVE_TRANSLATE_LANG`, default `vi`) in
   the **vexa-mcp** server's env (`../vexa-mcp/.env`) and restart it.
2. `join_meeting` then returns a `share_link`
   (`{WEB_PUBLIC_URL}/meet/{platform}/{id}?lang={LIVE_TRANSLATE_LANG}`).
3. The `meeting-notetaker` skill posts that link into the Slack thread right
   after the bot joins (see `../SKILL.md`, step 3).

The link's target language is fixed and not switchable by viewers, matching the
in-room UI. Keep `LIVE_TRANSLATE_LANG` (vexa-mcp) and this app's
`DEFAULT_TARGET_LANG` consistent so a link with no `?lang=` still lands on the
same language.

The `/api/rooms/{platform}/{id}` endpoint also returns `share_link` if you need
it elsewhere.
