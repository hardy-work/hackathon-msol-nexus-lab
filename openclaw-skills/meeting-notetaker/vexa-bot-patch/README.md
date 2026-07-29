# B-full: bot streaming-lane patch (vexa-bot)

These two files patch the **vendored Vexa bot** (not part of this repo — it lives on
the gateway at `~/Desktop/Hackathon/vexa/core/meetings/services/bot/src/`). They add
an additive tap that streams the bot's continuous 16 kHz capture PCM to the
soniox-bridge `/v1/stream` relay, which keeps one persistent Soniox stream per
speaker and pushes a seam-loss-free transcript to live-translate — bypassing Vexa's
segmentation/confirm layer for the live view.

## Files
- `live-stream-lane.ts` — NEW file → `.../bot/src/live-stream-lane.ts`
- `pipeline.ts` — MODIFIED → `.../bot/src/pipeline.ts` (imports + threads the lane
  into `createBotPipeline` / gmeet + mixed `feedAudio`; disposes on stop).

The lane derives everything from the invocation (bridge URL + token + meeting id +
language) — no new bot env. It only reads the frames `feedAudio` already gets and
swallows all errors, so it can never disturb Vexa's real transcript.

## Build (overlay — no base image needed)
The gateway lacks the `vexa/meet-join-env:dev` build base, so we overlay-rebuild on
top of the existing image and just recompile the bot package:

```
# on gateway, build context = a dir with these 2 .ts files + this Dockerfile:
FROM vexaai/vexa-bot:v012-preBfull
COPY pipeline.ts live-stream-lane.ts /app/core/meetings/services/bot/src/
RUN cd /app/core/meetings/services/bot && /app/node_modules/.bin/tsc -p tsconfig.json
# docker build --platform linux/amd64 -t vexaai/vexa-bot:v012 .
```

## Revert
`docker tag vexaai/vexa-bot:v012-preBfull vexaai/vexa-bot:v012` (then next bot join
uses the original). The bridge/live-translate B-full code is inert without a bot
streaming to `/v1/stream`, so no other revert is needed.
