# soniox-bridge

Drop-in replacement for Vexa's `deploy/transcription` unit. Implements the
same OpenAI-Whisper-compatible contract Vexa's bot expects
(`POST /v1/audio/transcriptions`, `GET /health`) but transcribes via
[Soniox](https://soniox.com)'s real-time WebSocket API instead of a local
faster-whisper model — no GPU, no local model weights, no CPU-bound model
loading (this is what crashed the OrbStack VM on `192.168.4.15` when we
tried self-hosting Whisper there).

## Why this exists

Vexa's bot sends each audio chunk (~15-20s WAV) to whatever
`TRANSCRIPTION_SERVICE_URL` is configured, as a synchronous multipart POST,
and expects a Whisper-`verbose_json`-shaped response back. Soniox has no
Whisper-compatible REST endpoint — its API is either async-job (create →
poll → fetch) or a real-time WebSocket stream. This bridge picks the
WebSocket path (per request, since we already have the whole chunk): open a
connection, stream the chunk in, collect finalized tokens, close, and
translate the result into the exact JSON shape Vexa's client parses.

## Setup

```bash
cp .env.example .env
# fill in SONIOX_API_KEY (from https://console.soniox.com) and a strong API_TOKEN
docker compose up -d --build
curl http://localhost:8083/health
```

## Point Vexa's main stack at it

In the main stack's `deploy/compose/.env`:

```
TRANSCRIPTION_SERVICE_URL=http://<this-host>:8083
TRANSCRIPTION_SERVICE_TOKEN=<same API_TOKEN as above>
TRANSCRIPTION_MODEL=
```

Then recreate the services that read it:

```bash
cd <vexa-repo>/deploy/compose
docker compose up -d meeting-api terminal
```

## Known limitations

- **One dominant language per chunk.** Like Whisper's own `verbose_json`,
  the response has a single top-level `language` field — even though this
  bridge asks Soniox to identify language per *token* (real code-switching
  support), Vexa's meeting-api only reads the call-level field, so a chunk
  that's genuinely half Japanese / half Vietnamese still gets stamped with
  whichever language had more tokens in that ~15-20s window. This is a
  limitation of Vexa's request/response contract, not of Soniox — fixing
  it fully would mean changing the contract, not just this bridge.
- **Segments are gap-split, not diarization-split.** Speaker labels are NOT
  set here — Vexa's `TranscriptionSegment` type has no speaker field, so
  Vexa attaches speaker identity through its own separate mechanism
  upstream of this call. Segment boundaries here are just silence-gap
  heuristics (>1.2s between tokens), meant to roughly match how Whisper's
  own VAD would have split the same audio.
- **Confidence mapping is approximate.** Soniox gives a 0–1 `confidence`
  per token; this bridge maps it to a Whisper-style `avg_logprob` via
  `ln(confidence)` so Vexa's own `isLowConfidenceSegment()` noise filter
  keeps working meaningfully, but it's an approximation, not the same
  metric Whisper produces.
- **No backpressure.** Vexa's own reference service returns 503 under load
  (bounded concurrency + queue). This bridge has none yet — under heavy
  concurrent meetings you may want to add a semaphore.
