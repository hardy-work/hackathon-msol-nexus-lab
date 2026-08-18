"""
Soniox-backed transcription service, drop-in replacement for Vexa's
deploy/transcription unit. Implements the same OpenAI-Whisper-compatible
contract Vexa's bot expects (POST /v1/audio/transcriptions, GET /health),
but transcribes via Soniox's real-time WebSocket API instead of a local
faster-whisper model.

Contract mirrored from vexa/core/meetings/services/transcription/src/transcription/main.py
and vexa/core/meetings/modules/whisper/src/transcription-client.ts.
"""

import asyncio
import io
import json
import logging
import math
import os
import time
import wave
from datetime import datetime, timezone
from typing import Optional

import websockets
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("soniox-bridge")

SONIOX_API_KEY = os.getenv("SONIOX_API_KEY", "").strip()
SONIOX_WS_URL = os.getenv("SONIOX_WS_URL", "wss://stt-rt.soniox.com/transcribe-websocket")
SONIOX_MODEL = os.getenv("SONIOX_MODEL", "stt-rt-v5")
# How long to wait for Soniox to finish a single chunk before giving up.
# Vexa's own client aborts its HTTP request after 30s, so we must return well before that.
SONIOX_TIMEOUT_S = float(os.getenv("SONIOX_TIMEOUT_S", "22"))

# --- Async/batch lane (long windows) --------------------------------------
# The realtime WS can't finalize a very long clip inside Vexa's 30s HTTP abort, so a
# continuous-speech window loses its tail. Soniox's async/batch *file* API transcribes
# the whole clip in a few seconds regardless of length, so it never loses the tail.
# It's a touch slower for SHORT clips (upload+create+poll overhead), so we only route
# windows LARGER than a threshold to it; short windows stay on the low-latency realtime WS.
SONIOX_API_BASE = os.getenv("SONIOX_API_BASE", "https://api.soniox.com").rstrip("/")
SONIOX_ASYNC_MODEL = os.getenv("SONIOX_ASYNC_MODEL", "stt-async-v5")
# Windows bigger than this (bytes of 16k mono s16le WAV ≈ 32000 B/s) go async.
# Default ~25s — comfortably past where realtime starts risking the 30s abort.
# 0 -> everything async; a huge value -> nothing async (pure realtime, i.e. revert).
SONIOX_ASYNC_OVER_BYTES = int(os.getenv("SONIOX_ASYNC_OVER_BYTES", "800000"))
# Hard cap on the whole async round-trip; MUST stay under Vexa's 30s abort.
SONIOX_ASYNC_TIMEOUT_S = float(os.getenv("SONIOX_ASYNC_TIMEOUT_S", "25"))
SONIOX_ASYNC_POLL_MS = int(os.getenv("SONIOX_ASYNC_POLL_MS", "400"))

# --- B-full live streaming relay (WS /v1/stream) --------------------------
# The bot streams raw PCM here over a WebSocket; we keep ONE persistent Soniox
# realtime stream per speaker channel (never windowed, never confirmed) and push
# interim/final lines straight to the live-translate app. This bypasses Vexa's
# segmentation/confirm entirely for the live view, so nothing is dropped at turn
# seams. Reuses LIVE_INGEST_URL / LIVE_INGEST_TOKEN (same as the B1 push).
LIVE_STREAM_MODEL = os.getenv("LIVE_STREAM_MODEL", "stt-rt-v5")
# Split on a gap between two final tokens this large (only at a word boundary).
STREAM_SEG_GAP_MS = int(os.getenv("STREAM_SEG_GAP_MS", "900"))
# Wall-clock idle before the ticker force-closes the open segment. Must be well
# above Soniox's commit latency (~1-1.5s) or the ticker cuts mid-word during a
# normal stream; a real speaker pause is longer than this.
STREAM_IDLE_FLUSH_MS = int(os.getenv("STREAM_IDLE_FLUSH_MS", "2500"))
# Debounce for pushing the evolving interim line.
STREAM_INTERIM_MS = int(os.getenv("STREAM_INTERIM_MS", "350"))
# Force-close a very long run-on segment so translation units stay reasonable.
STREAM_SEG_MAX_CHARS = int(os.getenv("STREAM_SEG_MAX_CHARS", "220"))
# Don't split off a segment shorter than this on a gap/punctuation — merge it into
# the next instead (avoids tiny junk fragments like "ad." from a mid-word gap).
STREAM_SEG_MIN_CHARS = int(os.getenv("STREAM_SEG_MIN_CHARS", "14"))
# A per-channel Soniox realtime connection lives for the whole meeting. A
# transient Soniox-side error (e.g. "408 Request timeout") must not kill
# transcription for that speaker for the rest of the meeting — reconnect
# instead. Backoff between attempts, and a cap so a truly dead Soniox
# doesn't spin the channel forever.
STREAM_RECONNECT_BACKOFF_S = float(os.getenv("STREAM_RECONNECT_BACKOFF_S", "1.0"))
STREAM_MAX_RECONNECTS = int(os.getenv("STREAM_MAX_RECONNECTS", "20"))
# Soniox's real-time API can translate alongside transcription in the same
# stream at no extra cost (a "translation" block in the connect config) —
# tokens come back tagged translation_status="original"/"translation", already
# interleaved, typically tens of ms behind each other (measured locally: an
# LLM-based translate() round-trip was 8-17s; this is ~0.03s). Empty/unset ->
# translation off entirely (unchanged behavior, live-translate's Claude-based
# translation is the sole path — this is the default until confirmed live).
TRANSLATE_TARGET_LANG = os.getenv("TRANSLATE_TARGET_LANG", "").strip()
# Our own inbound auth, same dual scheme Vexa's reference service supports.
API_TOKEN = os.getenv("API_TOKEN", "").strip()
# B1 low-latency interim push (opt-in). When set, each transcript is forwarded to
# the live-translate app for a fast "interim" line. Unset -> reverts to normal.
LIVE_INGEST_URL = os.getenv("LIVE_INGEST_URL", "").strip().rstrip("/")
LIVE_INGEST_TOKEN = os.getenv("LIVE_INGEST_TOKEN", "").strip()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_token(request: Request, api_key: Optional[str] = Depends(api_key_header)) -> bool:
    if not API_TOKEN:
        return True
    if api_key and api_key == API_TOKEN:
        return True
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header.removeprefix("Bearer ").strip() == API_TOKEN:
        return True
    raise HTTPException(status_code=401, detail="Invalid or missing API token")


app = FastAPI(
    title="Soniox Transcription Bridge",
    description="OpenAI Whisper API compatible transcription service, backed by Soniox real-time STT",
    version="1.0.0",
)


def _wav_duration_seconds(audio_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _confidence_to_avg_logprob(confidences: list[float]) -> float:
    """Map Soniox's 0-1 confidence to a Whisper-style avg_logprob so Vexa's
    own isLowConfidenceSegment() filter (which reads avg_logprob/no_speech_prob/
    compression_ratio) behaves meaningfully instead of always passing or always failing."""
    if not confidences:
        return -0.1
    clamped = [max(c, 1e-6) for c in confidences]
    return sum(math.log(c) for c in clamped) / len(clamped)


async def _transcribe_via_soniox(audio_bytes: bytes, language: Optional[str]) -> dict:
    """Stream one WAV buffer through Soniox's real-time WebSocket API and
    return the accumulated final tokens, grouped into segments by gaps."""
    config: dict = {
        "api_key": SONIOX_API_KEY,
        "model": SONIOX_MODEL,
        "audio_format": "auto",
    }
    if language:
        # Language is known -> pin it and skip language identification. LID adds
        # per-request processing latency; when Vexa already tells us the meeting
        # language, it's pure overhead (and hurts accuracy on short chunks).
        config["language_hints"] = [language]
    else:
        config["enable_language_identification"] = True

    final_tokens: list[dict] = []
    finished = False

    t0 = time.monotonic()
    # Disable per-message compression: chunks are small and the deflate
    # negotiation/CPU only adds handshake latency here.
    async with websockets.connect(SONIOX_WS_URL, open_timeout=10, compression=None) as ws:
        t_conn = time.monotonic()
        await ws.send(json.dumps(config))

        # Send the whole buffer in bounded chunks (kinder to the socket than one giant frame).
        chunk_size = 32000
        for i in range(0, len(audio_bytes), chunk_size):
            await ws.send(audio_bytes[i : i + chunk_size])
        await ws.send("")  # end-of-audio signal
        t_sent = time.monotonic()

        deadline = time.monotonic() + SONIOX_TIMEOUT_S
        while not finished:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Soniox timed out before 'finished'; returning %d partial tokens", len(final_tokens))
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                # CRITICAL: on timeout, return whatever was finalized so far
                # instead of crashing/returning empty. A long window (continuous
                # speech) used to lose ALL its text here.
                logger.warning("Soniox recv timed out; returning %d partial tokens", len(final_tokens))
                break
            msg = json.loads(raw)
            if msg.get("error_code"):
                raise HTTPException(status_code=502, detail=f"Soniox error {msg['error_code']}: {msg.get('error_message')}")
            for token in msg.get("tokens", []):
                if token.get("is_final"):
                    final_tokens.append(token)
            finished = bool(msg.get("finished"))

    t_done = time.monotonic()
    logger.info(
        "soniox timing: connect=%.2fs send=%.2fs finalize=%.2fs total=%.2fs (lid=%s)",
        t_conn - t0, t_sent - t_conn, t_done - t_sent, t_done - t0, not bool(language),
    )
    return _tokens_to_whisper_response(final_tokens, language)


async def _transcribe_via_soniox_async(audio_bytes: bytes, language: Optional[str]) -> dict:
    """Transcribe one WAV buffer through Soniox's async/batch FILE API (upload → create →
    poll → fetch → cleanup). Batch finalizes a bounded clip in a few seconds regardless of
    length, so a long continuous-speech window can't blow past Vexa's 30s HTTP abort and
    lose its tail — the failure mode the realtime WS has on long monologues.

    Returns the SAME whisper-shaped dict as the realtime path (all async tokens are final,
    and carry text/start_ms/end_ms/confidence/language just like the realtime ones)."""
    import httpx

    headers = {"Authorization": f"Bearer {SONIOX_API_KEY}"}
    create_body: dict = {"model": SONIOX_ASYNC_MODEL}
    if language:
        # Known language -> pin it, skip LID (same rationale as the realtime path).
        create_body["language_hints"] = [language]
    else:
        create_body["enable_language_identification"] = True

    t0 = time.monotonic()
    deadline = t0 + SONIOX_ASYNC_TIMEOUT_S
    file_id: Optional[str] = None
    tx_id: Optional[str] = None
    t_up = t0
    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            # 1) upload the WAV
            up = await http.post(
                f"{SONIOX_API_BASE}/v1/files",
                headers=headers,
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            )
            up.raise_for_status()
            file_id = up.json()["id"]
            t_up = time.monotonic()

            # 2) create the transcription job
            create_body["file_id"] = file_id
            cr = await http.post(
                f"{SONIOX_API_BASE}/v1/transcriptions", headers=headers, json=create_body
            )
            cr.raise_for_status()
            tx_id = cr.json()["id"]

            # 3) poll to completion, bounded by the deadline (stay < Vexa's 30s abort)
            body: dict = {}
            status = "queued"
            while status not in ("completed", "error"):
                if time.monotonic() >= deadline:
                    logger.warning(
                        "Soniox async timed out in status=%s after %.1fs (bytes=%d)",
                        status, time.monotonic() - t0, len(audio_bytes),
                    )
                    return _tokens_to_whisper_response([], language)
                await asyncio.sleep(SONIOX_ASYNC_POLL_MS / 1000.0)
                st = await http.get(f"{SONIOX_API_BASE}/v1/transcriptions/{tx_id}", headers=headers)
                st.raise_for_status()
                body = st.json()
                status = body.get("status", "")
            if status == "error":
                raise HTTPException(
                    status_code=502, detail=f"Soniox async error: {body.get('error_message')}"
                )

            # 4) fetch the transcript tokens
            tr = await http.get(
                f"{SONIOX_API_BASE}/v1/transcriptions/{tx_id}/transcript", headers=headers
            )
            tr.raise_for_status()
            tokens = tr.json().get("tokens", [])
        finally:
            # 5) best-effort cleanup so files/jobs don't accrue on the Soniox account
            for url in (
                f"{SONIOX_API_BASE}/v1/transcriptions/{tx_id}" if tx_id else None,
                f"{SONIOX_API_BASE}/v1/files/{file_id}" if file_id else None,
            ):
                if url:
                    try:
                        await http.delete(url, headers=headers)
                    except Exception:  # noqa: BLE001
                        pass

    t_done = time.monotonic()
    logger.info(
        "soniox async: bytes=%d total=%.2fs (upload=%.2fs) tokens=%d (lid=%s)",
        len(audio_bytes), t_done - t0, t_up - t0, len(tokens), not bool(language),
    )
    return _tokens_to_whisper_response(tokens, language)


def _tokens_to_whisper_response(tokens: list[dict], language_hint: Optional[str]) -> dict:
    if not tokens:
        return {"text": "", "language": language_hint or "unknown", "language_probability": 0.0, "duration": 0.0, "segments": []}

    # Split into segments on gaps > 1.2s between consecutive tokens (mirrors Whisper's
    # own VAD-driven segmentation closely enough for Vexa's downstream consumer, which
    # only reads the merged `text` plus start/end for timeline placement).
    GAP_THRESHOLD_MS = 1200
    segments: list[list[dict]] = [[tokens[0]]]
    for tok in tokens[1:]:
        prev_end = segments[-1][-1].get("end_ms") or 0
        if (tok.get("start_ms") or 0) - prev_end > GAP_THRESHOLD_MS:
            segments.append([tok])
        else:
            segments[-1].append(tok)

    lang_counts: dict[str, int] = {}
    seg_dicts = []
    for seg_tokens in segments:
        text = "".join(t.get("text", "") for t in seg_tokens).strip()
        if not text:
            continue
        start_s = (seg_tokens[0].get("start_ms") or 0) / 1000.0
        end_s = (seg_tokens[-1].get("end_ms") or 0) / 1000.0
        confidences = [t["confidence"] for t in seg_tokens if isinstance(t.get("confidence"), (int, float))]
        words = [
            {
                "word": t.get("text", ""),
                "start": (t.get("start_ms") or 0) / 1000.0,
                "end": (t.get("end_ms") or 0) / 1000.0,
                "probability": t.get("confidence", 1.0),
            }
            for t in seg_tokens
        ]
        seg_dicts.append(
            {
                "start": start_s,
                "end": end_s,
                "text": text,
                "avg_logprob": _confidence_to_avg_logprob(confidences),
                "no_speech_prob": 0.0,
                "compression_ratio": 1.0,
                "words": words,
            }
        )
        for t in seg_tokens:
            lang = t.get("language")
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

    full_text = " ".join(s["text"] for s in seg_dicts).strip()
    duration = seg_dicts[-1]["end"] if seg_dicts else 0.0
    dominant_language = max(lang_counts, key=lang_counts.get) if lang_counts else (language_hint or "unknown")

    return {
        "text": full_text,
        "language": dominant_language,
        "language_probability": 0.0,
        "duration": duration,
        "segments": seg_dicts,
    }


@app.get("/health")
async def health_check():
    status = "healthy" if SONIOX_API_KEY else "unhealthy"
    body = {
        "status": status,
        "backend": "soniox-realtime",
        "model": SONIOX_MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(content=body, status_code=200 if SONIOX_API_KEY else 503)


@app.get("/")
async def root():
    return {
        "service": "Soniox Transcription Bridge",
        "backend": "soniox-realtime",
        "model": SONIOX_MODEL,
        "endpoints": {"transcribe": "/v1/audio/transcriptions", "health": "/health"},
    }


def _push_interim(text: str, language: Optional[str]) -> None:
    """Fire-and-forget: forward the raw transcript to the live-translate app so
    it can show a low-latency 'interim' line, skipping Vexa's confirm layer.
    Opt-in via LIVE_INGEST_URL; failures are swallowed so this never affects the
    transcription response. Sync + stdlib urllib (no extra dep); Starlette runs
    this in a threadpool as a background task, so it won't block the event loop."""
    if not LIVE_INGEST_URL or not text.strip():
        return
    try:
        import json as _json
        import urllib.request

        body = _json.dumps({"text": text, "language": language or ""}).encode("utf-8")
        req = urllib.request.Request(
            f"{LIVE_INGEST_URL}/api/ingest", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        if LIVE_INGEST_TOKEN:
            req.add_header("X-Ingest-Token", LIVE_INGEST_TOKEN)
        urllib.request.urlopen(req, timeout=4.0).close()
    except Exception as e:  # noqa: BLE001
        logger.debug("interim push failed (ignored): %s", e)


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form(...),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: str = Form("verbose_json"),
    timestamp_granularities: str = Form("segment"),
    max_speech_duration_s: Optional[str] = Form(None),
    min_silence_duration_ms: Optional[str] = Form(None),
    task: str = Form("transcribe"),
    _: bool = Depends(verify_api_token),
):
    if not SONIOX_API_KEY:
        raise HTTPException(status_code=500, detail="SONIOX_API_KEY not configured")

    audio_bytes = await file.read()
    start = time.time()
    # Long windows -> async/batch (can't lose the tail); short windows -> realtime (lower latency).
    use_async = len(audio_bytes) > SONIOX_ASYNC_OVER_BYTES
    lane = "async" if use_async else "realtime"
    try:
        if use_async:
            result = await _transcribe_via_soniox_async(audio_bytes, language)
        else:
            result = await _transcribe_via_soniox(audio_bytes, language)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Soniox transcription failed ({lane}): {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Soniox transcription failed: {e}")

    logger.info(
        f"transcribed {len(audio_bytes)} bytes via {lane} in {time.time() - start:.2f}s - "
        f"language={result['language']}, segments={len(result['segments'])}"
    )
    # After the response is sent to Vexa, forward the raw text to live-translate
    # for the low-latency interim line (no-op unless LIVE_INGEST_URL is set).
    if LIVE_INGEST_URL and result.get("text"):
        background_tasks.add_task(_push_interim, result["text"], language)
    return result


# --------------------------------------------------------------------------- #
# B-full live streaming relay: bot --WS(PCM)--> here --> persistent Soniox     #
# stream --> POST interim/final to live-translate. One Soniox stream per        #
# speaker channel; never windowed, never confirmed, so long monologues keep     #
# every word (no turn-seam drops).                                              #
# --------------------------------------------------------------------------- #

_ingest_http = None  # lazy shared httpx client for ingest POSTs


async def _post_ingest(payload: dict) -> None:
    """POST a structured interim/final line to live-translate. Best-effort:
    failures are swallowed so the relay never breaks on a transient hiccup."""
    global _ingest_http
    if not LIVE_INGEST_URL:
        return
    try:
        import httpx

        if _ingest_http is None:
            _ingest_http = httpx.AsyncClient(timeout=4.0)
        headers = {}
        if LIVE_INGEST_TOKEN:
            headers["X-Ingest-Token"] = LIVE_INGEST_TOKEN
        await _ingest_http.post(f"{LIVE_INGEST_URL}/api/ingest", json=payload, headers=headers)
    except Exception as e:  # noqa: BLE001
        logger.debug("stream ingest post failed (ignored): %s", e)


class _ChannelStream:
    """One persistent Soniox realtime stream for a single speaker channel."""

    def __init__(self, platform: str, native_id: str, channel: int, language: Optional[str], target_lang: Optional[str] = None):
        self.platform = platform
        self.native_id = native_id
        self.channel = channel
        self.language = language or None
        # If set, Soniox translates alongside transcription in the SAME realtime
        # stream (a "translation" block in the connect config) — the response
        # then interleaves tokens tagged translation_status="original" (the usual
        # transcript) and "translation" (the translated text), no separate call.
        self.target_lang = target_lang or None
        self.speaker = "Speaker"
        self._pcm_q: "asyncio.Queue[Optional[bytes]]" = asyncio.Queue(maxsize=2000)
        self._ws = None
        self._tasks: list[asyncio.Task] = []
        self._open: list[dict] = []   # final ORIGINAL tokens of the currently-open segment
        self._interim_tail = ""       # non-final ORIGINAL tokens (live, changing)
        self._open_translated: list[dict] = []   # final TRANSLATION tokens, paired 1:1 with _open's segment
        self._interim_tail_translated = ""       # non-final TRANSLATION tokens (live, changing)
        # A trailing "." right after a digit is ambiguous — could be a real
        # sentence end, or a decimal/thousands separator ("4.000" in Vietnamese
        # number formatting) that's about to continue with more digits. Defer
        # the punct-close decision one token: resolved in the next append once
        # we can see whether that next token starts a new word (real sentence
        # end) or continues the number (false alarm, don't close).
        self._pending_dot_close = False
        self._pending_dot_close_translated = False
        self._seq = 0
        self._seq_translated = 0
        self._last_token_at = time.monotonic()
        self._last_interim_push = 0.0
        self._closed = False
        self._flush_lock = asyncio.Lock()
        self._flush_translated_lock = asyncio.Lock()
        self._run_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        # _run owns the Soniox websocket's whole lifecycle, including
        # reconnecting it on transient errors — see _run() below.
        await self._connect()
        self._run_task = asyncio.create_task(self._run())
        self._tasks = [
            asyncio.create_task(self._writer()),
            self._run_task,
            asyncio.create_task(self._ticker()),
        ]

    async def _connect(self) -> None:
        self._ws = await websockets.connect(SONIOX_WS_URL, open_timeout=10, compression=None)
        cfg: dict = {
            "api_key": SONIOX_API_KEY,
            "model": LIVE_STREAM_MODEL,
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
        }
        if self.language:
            cfg["language_hints"] = [self.language]
        else:
            cfg["enable_language_identification"] = True
        if self.target_lang:
            cfg["translation"] = {"type": "one_way", "target_language": self.target_lang}
        await self._ws.send(json.dumps(cfg))

    def feed(self, pcm: bytes) -> None:
        try:
            self._pcm_q.put_nowait(pcm)
        except asyncio.QueueFull:
            pass  # drop under backpressure rather than stall the relay

    async def _writer(self) -> None:
        # Never exit on a transient send failure — that would silently and
        # permanently stop audio from reaching Soniox even after _run()
        # reconnects. Drop the one chunk that failed and keep going; a brief
        # gap during reconnect is fine, a dead channel for the rest of the
        # meeting is not.
        while True:
            pcm = await self._pcm_q.get()
            if pcm is None:  # sentinel -> end of audio
                try:
                    if self._ws is not None:
                        await self._ws.send("")
                except Exception:  # noqa: BLE001
                    pass
                return
            try:
                if self._ws is not None:
                    await self._ws.send(pcm)
            except Exception:  # noqa: BLE001
                pass

    async def _reader_loop(self) -> None:
        """Consume one Soniox connection until it errors, finishes, or
        breaks. Raises/returns on any of those — the caller (_run) decides
        whether to reconnect."""
        while True:
            raw = await self._ws.recv()
            msg = json.loads(raw)
            if msg.get("error_code"):
                logger.warning(
                    "stream ch%d soniox error: %s %s",
                    self.channel, msg.get("error_code"), msg.get("error_message"),
                )
                return
            changed = False
            tail = ""
            tail_translated = ""
            for tok in msg.get("tokens", []):
                # Untagged (translation not configured) counts as "original".
                # Translation tokens close their own segments independently
                # (_append_translated_final) — see _flush_translated for why
                # this can't just piggyback on the original's flush timing.
                if tok.get("translation_status") == "translation":
                    if tok.get("is_final"):
                        await self._append_translated_final(tok)
                    else:
                        tail_translated += tok.get("text", "")
                elif tok.get("is_final"):
                    await self._append_final(tok)
                    changed = True
                else:
                    tail += tok.get("text", "")
            self._interim_tail = tail
            self._interim_tail_translated = tail_translated
            self._last_token_at = time.monotonic()
            await self._maybe_push_interim(force=changed)
            if msg.get("finished"):
                return

    async def _run(self) -> None:
        """Owns the Soniox connection for this channel's whole lifetime.
        A transient Soniox-side error (e.g. "408 Request timeout") used to
        kill transcription for this speaker for the rest of the meeting —
        the socket died but nothing ever reconnected it, while feed() kept
        queueing real audio that then went nowhere. Reconnect instead."""
        reconnects = 0
        while True:
            try:
                await self._reader_loop()
            except Exception as e:  # noqa: BLE001
                logger.debug("stream ch%d reader ended: %s", self.channel, e)
            # Commit whatever was open on this connection. Mark it as a seam
            # (not a final end) unless we're actually shutting down, so a
            # mid-sentence cut here reads as "connection seam", matching the
            # gap/idle flush reasons already used elsewhere in this file.
            flush_reason = "end" if self._closed else "reconnect"
            await self._flush(reason=flush_reason)
            await self._flush_translated(reason=flush_reason)
            if self._closed:
                return
            reconnects += 1
            if reconnects > STREAM_MAX_RECONNECTS:
                logger.error(
                    "stream ch%d giving up after %d reconnects to soniox",
                    self.channel, reconnects,
                )
                return
            logger.info("stream ch%d reconnecting to soniox (attempt %d)", self.channel, reconnects)
            self._ws = None  # _writer drops frames while this is None instead of erroring
            await asyncio.sleep(STREAM_RECONNECT_BACKOFF_S)
            try:
                await self._connect()
            except Exception as e:  # noqa: BLE001
                logger.warning("stream ch%d reconnect failed: %s", self.channel, e)
                self._ws = None
                # loop back around: _reader_loop() will raise immediately on
                # self._ws.recv() against None and we'll retry with backoff

    async def _append_final(self, tok: dict) -> None:
        # New segment if there's a real gap since the last final token: close the
        # open one FIRST (before appending) so the gap becomes the seam — but only
        # if it's already a worthwhile length, else let this token extend it (avoids
        # tiny mid-word fragments when Soniox reports a spurious gap).
        #
        # SKIPPED when translation is on: the translated stream has no
        # start_ms/end_ms to split on (Soniox doesn't timestamp translation
        # tokens), so it only ever closes on punctuation/maxlen. If the
        # original ALSO split on gaps, it produced systematically MORE, finer
        # segments than translation did — live-tested and confirmed wrong:
        # a lone "artificial intelligence." original segment (split off by a
        # gap900) ended up paired via FIFO with the translation of a
        # DIFFERENT, unrelated sentence three segments later, because the
        # translated stream had merged everything between two periods into
        # one chunk. Restricting both sides to punctuation/maxlen keeps their
        # segment COUNTS aligned so the FIFO pairing in live-translate stays
        # correct — the idle-timeout ticker flush is disabled too, for the
        # same reason (see _ticker).
        # Only split at a WORD boundary — Soniox prefixes a new word with a
        # leading space, so a token without one continues the current word;
        # splitting there would cut a word in half ("re" | "ad").
        at_word_boundary = (tok.get("text") or "").startswith((" ", "\n"))
        # Resolve a punct-close deferred by the PREVIOUS token (see below):
        # if this token doesn't start a new word, it's a continuation (e.g.
        # "4." was a thousands separator and this token is "000"), so the
        # earlier "." wasn't a real sentence end — skip the close.
        if self._pending_dot_close:
            self._pending_dot_close = False
            if at_word_boundary:
                await self._flush(reason="punct")
        if self._open and not self.target_lang:
            gap = (tok.get("start_ms") or 0) - (self._open[-1].get("end_ms") or 0)
            if gap > STREAM_SEG_GAP_MS and at_word_boundary and len(self._open_text()) >= STREAM_SEG_MIN_CHARS:
                await self._flush(reason=f"gap{gap}")
        self._open.append(tok)
        text = self._open_text()
        # Close on sentence punctuation (once long enough) or when it grows too long.
        if text and text[-1] in ".?!。！？" and len(text) >= STREAM_SEG_MIN_CHARS:
            if text[-1] == "." and len(text) >= 2 and text[-2].isdigit():
                # Ambiguous: "4." could be a decimal/thousands separator about
                # to continue ("4.000") rather than a real sentence end.
                # Defer — resolved by the next token above.
                self._pending_dot_close = True
            else:
                await self._flush(reason="punct")
        elif not self.target_lang and len(text) > STREAM_SEG_MAX_CHARS:
            # Same reasoning as the gap/idle skip above: maxlen is a raw
            # character-count threshold, and translated text is a different
            # length than the original (different language) — the two
            # streams hit it at different points, producing an extra
            # unpaired segment on one side. Live-tested: an English segment
            # closed at maxlen while its Vietnamese translation was still
            # short of maxlen, then closed AGAIN moments later on its own
            # punctuation — 1 original vs 2 translated for the same speech,
            # desyncing the FIFO pairing from there on. With translation on,
            # punctuation/channel-close are the only closers on both sides.
            await self._flush(reason="maxlen")

    def _open_text(self) -> str:
        return "".join(t.get("text", "") for t in self._open).strip()

    def _open_translated_text(self) -> str:
        return "".join(t.get("text", "") for t in self._open_translated).strip()

    async def _ticker(self) -> None:
        # Close the open segment once speech pauses (so the last sentence before a
        # silence is committed instead of lingering as interim).
        #
        # SKIPPED when translation is on, same reasoning as the gap-based split
        # in _append_final: an idle-triggered cut on the original with no
        # matching cut on the translated stream (which only closes on
        # punctuation) would reintroduce the same segment-count mismatch that
        # broke FIFO pairing. With translation on, original closes ONLY on
        # punctuation/maxlen/channel-close — interim still shows a mid-pause
        # sentence live in the meantime, just the CONFIRMED list catches up a
        # bit slower than without translation.
        try:
            while not self._closed:
                await asyncio.sleep(0.3)
                # Don't idle-flush while a partial (non-final) word is still forming
                # — that's Soniox mid-word, and flushing there would cut it ("re"|"ad").
                if (
                    self._open
                    and not self.target_lang
                    and not self._interim_tail.strip()
                    and (time.monotonic() - self._last_token_at) * 1000 > STREAM_IDLE_FLUSH_MS
                ):
                    await self._flush(reason="idle")
        except Exception:  # noqa: BLE001
            pass

    async def _maybe_push_interim(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_interim_push) * 1000 < STREAM_INTERIM_MS:
            return
        self._last_interim_push = now
        line = (self._open_text() + " " + self._interim_tail).strip()
        if not line:
            return
        payload = {
            "platform": self.platform, "native_meeting_id": self.native_id,
            "kind": "interim", "text": line, "speaker": self.speaker,
        }
        if self.target_lang:
            translated_line = (self._open_translated_text() + " " + self._interim_tail_translated).strip()
            if translated_line:
                payload["translated_text"] = translated_line
                payload["translated_lang"] = self.target_lang
        await _post_ingest(payload)

    async def _flush(self, final: bool = False, reason: str = "end") -> None:
        # On an abnormal cutoff (reason "reconnect" — a mid-stream Soniox
        # error — or "end" — the channel is closing), Soniox may not have
        # had time to mark trailing tokens is_final before the connection
        # died, so they never made it into self._open. We already showed
        # that text live as the interim "đang nghe" line, though — recover
        # it here as best-effort rather than silently losing text the viewer
        # already saw (this is exactly how "Can you give me some examples?"
        # was getting flushed as just "Can y": the rest was still sitting in
        # _interim_tail when the reconnect-triggered flush fired). Not done
        # for normal punct/gap/idle/maxlen flushes — there the tail is
        # usually just a word still being formed, and grabbing it early would
        # duplicate/cut it instead of letting it finalize properly next.
        recovered_tail = ""
        if reason in ("reconnect", "end"):
            recovered_tail = self._interim_tail.strip()
            self._interim_tail = ""
        async with self._flush_lock:
            if not self._open and not recovered_tail:
                return
            toks, self._open = self._open, []
        text = "".join(t.get("text", "") for t in toks).strip()
        if recovered_tail:
            text = f"{text} {recovered_tail}".strip()
        if not text:
            return
        seg_id = f"{self.channel}:{self._seq}"
        self._seq += 1
        logger.info("stream ch%d FLUSH seg=%s reason=%s len=%d: ...%s", self.channel, seg_id, reason, len(text), text[-24:])
        # toks can be empty here (recovered_tail-only flush: nothing was ever
        # finalized before the cutoff) — fall back to 0 rather than indexing
        # into an empty list.
        start = (toks[0].get("start_ms") or 0) / 1000.0 if toks else 0.0
        end = (toks[-1].get("end_ms") or 0) / 1000.0 if toks else start
        langs = [t.get("language") for t in toks if t.get("language")]
        lang = max(set(langs), key=langs.count) if langs else (self.language or "")
        await _post_ingest({
            "platform": self.platform, "native_meeting_id": self.native_id,
            "kind": "final", "seg_id": seg_id, "text": text, "speaker": self.speaker,
            "lang": lang, "start": start, "end": end,
        })

    async def _flush_translated(self, reason: str = "end") -> None:
        """Independent segmentation for the TRANSLATED stream — deliberately
        NOT paired inline with the original's own flush. Measured live: at the
        instant an original segment hits its punctuation boundary, its
        translation is usually still arriving (translation tokens stream
        "chunk by chunk" behind the original per Soniox's docs) — draining
        _open_translated synchronously there attached segment N's translation
        to segment N+1 instead. Let translation close on ITS OWN punctuation
        (no gap-based splitting: translated tokens carry no start_ms/end_ms
        per Soniox's docs) and ship it as its own kind="final_translation"
        event; live-translate pairs these back to original segments in
        arrival ORDER per channel (a FIFO queue), which is safe because
        Soniox streams both in speaking order."""
        recovered_tail = ""
        if reason in ("reconnect", "end"):
            recovered_tail = self._interim_tail_translated.strip()
            self._interim_tail_translated = ""
        async with self._flush_translated_lock:
            if not self._open_translated and not recovered_tail:
                return
            toks, self._open_translated = self._open_translated, []
        text = "".join(t.get("text", "") for t in toks).strip()
        if recovered_tail:
            text = f"{text} {recovered_tail}".strip()
        if not text:
            return
        seg_id = f"{self.channel}:t{self._seq_translated}"
        self._seq_translated += 1
        logger.info(
            "stream ch%d FLUSH_TRANSLATED seg=%s reason=%s len=%d: ...%s",
            self.channel, seg_id, reason, len(text), text[-24:],
        )
        await _post_ingest({
            "platform": self.platform, "native_meeting_id": self.native_id,
            "kind": "final_translation", "seg_id": seg_id, "text": text,
            "speaker": self.speaker, "lang": self.target_lang,
        })

    async def _append_translated_final(self, tok: dict) -> None:
        # Mirrors _append_final's punctuation closing, minus the gap-based
        # split (translated tokens have no start_ms/end_ms to compute a gap
        # from). maxlen is ALSO skipped here when translation is on — see the
        # comment in _append_final for why an independent char-count
        # threshold desyncs the two streams' segment counts.
        # Same digit-period ambiguity as _append_final (e.g. Vietnamese
        # "4.000") — defer the close decision to the next token.
        at_word_boundary = (tok.get("text") or "").startswith((" ", "\n"))
        if self._pending_dot_close_translated:
            self._pending_dot_close_translated = False
            if at_word_boundary:
                await self._flush_translated(reason="punct")
        self._open_translated.append(tok)
        text = self._open_translated_text()
        if text and text[-1] in ".?!。！？" and len(text) >= STREAM_SEG_MIN_CHARS:
            if text[-1] == "." and len(text) >= 2 and text[-2].isdigit():
                self._pending_dot_close_translated = True
            else:
                await self._flush_translated(reason="punct")
        elif not self.target_lang and len(text) > STREAM_SEG_MAX_CHARS:
            await self._flush_translated(reason="maxlen")

    async def close(self) -> None:
        self._closed = True
        try:
            self._pcm_q.put_nowait(None)  # signal writer to send "" (end-of-audio) to Soniox
        except Exception:  # noqa: BLE001
            pass
        # Soniox commits the FINAL tokens only after it sees end-of-audio, in a
        # trailing burst. WAIT for _run to drain that burst (it flushes the
        # remaining segment once self._closed is seen) before tearing anything
        # down — cancelling early here was dropping the tail of every stream.
        if self._run_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._run_task), timeout=10)
            except Exception:  # noqa: BLE001
                pass
        for t in self._tasks:
            t.cancel()
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:  # noqa: BLE001
            pass


@app.websocket("/v1/stream")
async def stream_relay(ws: WebSocket) -> None:
    """Bot -> bridge PCM relay. Query: platform, meeting, lang, target_lang, token.
    Binary frames = [1-byte channel][s16le PCM]. Text frames = JSON control
    ({"type":"speaker","channel":N,"name":"..."})."""
    if API_TOKEN and ws.query_params.get("token") != API_TOKEN:
        await ws.close(code=1008)
        return
    if not SONIOX_API_KEY:
        await ws.close(code=1011)
        return
    platform = ws.query_params.get("platform", "google_meet")
    native_id = ws.query_params.get("meeting", "")
    language = (ws.query_params.get("lang") or "").strip() or None
    # target_lang enables Soniox's native real-time translation (a "translation"
    # block added to each channel's connect config) — the bot doesn't send this
    # today, so it falls back to TRANSLATE_TARGET_LANG; explicit query param
    # wins if a caller ever does pass one. Empty/unset -> translation off,
    # unchanged behavior (live-translate's own Claude-based path still runs).
    target_lang = (ws.query_params.get("target_lang") or TRANSLATE_TARGET_LANG or "").strip() or None
    await ws.accept()
    logger.info(
        "stream relay open: %s/%s (lang=%s, target_lang=%s)",
        platform, native_id, language or "auto", target_lang or "none",
    )
    channels: dict[int, _ChannelStream] = {}
    pending_speaker: dict[int, str] = {}  # speaker set before the channel's first audio

    async def get_channel(ch: int) -> _ChannelStream:
        cs = channels.get(ch)
        if cs is None:
            cs = _ChannelStream(platform, native_id, ch, language, target_lang)
            if ch in pending_speaker:
                cs.speaker = pending_speaker[ch]
            channels[ch] = cs
            await cs.start()
        return cs

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data is not None and len(data) >= 1:
                ch = data[0]
                cs = await get_channel(ch)
                cs.feed(bytes(data[1:]))
                continue
            txt = msg.get("text")
            if txt:
                try:
                    ctrl = json.loads(txt)
                    if ctrl.get("type") == "speaker" and ctrl.get("name"):
                        ch = int(ctrl.get("channel", 0))
                        name = str(ctrl["name"])
                        pending_speaker[ch] = name
                        cs = channels.get(ch)
                        if cs is not None:
                            cs.speaker = name
                except Exception:  # noqa: BLE001
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("stream relay error: %s", e)
    finally:
        for cs in channels.values():
            await cs.close()
        logger.info("stream relay closed: %s/%s", platform, native_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
