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

    def __init__(self, platform: str, native_id: str, channel: int, language: Optional[str]):
        self.platform = platform
        self.native_id = native_id
        self.channel = channel
        self.language = language or None
        self.speaker = "Speaker"
        self._pcm_q: "asyncio.Queue[Optional[bytes]]" = asyncio.Queue(maxsize=2000)
        self._ws = None
        self._tasks: list[asyncio.Task] = []
        self._open: list[dict] = []   # final tokens of the currently-open segment
        self._interim_tail = ""       # non-final tokens (live, changing)
        self._seq = 0
        self._last_token_at = time.monotonic()
        self._last_interim_push = 0.0
        self._closed = False
        self._flush_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
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
        await self._ws.send(json.dumps(cfg))
        self._reader_task = asyncio.create_task(self._reader())
        self._tasks = [
            asyncio.create_task(self._writer()),
            self._reader_task,
            asyncio.create_task(self._ticker()),
        ]

    def feed(self, pcm: bytes) -> None:
        try:
            self._pcm_q.put_nowait(pcm)
        except asyncio.QueueFull:
            pass  # drop under backpressure rather than stall the relay

    async def _writer(self) -> None:
        try:
            while True:
                pcm = await self._pcm_q.get()
                if pcm is None:  # sentinel -> end of audio
                    await self._ws.send("")
                    return
                await self._ws.send(pcm)
        except Exception:  # noqa: BLE001
            pass

    async def _reader(self) -> None:
        try:
            while True:
                raw = await self._ws.recv()
                msg = json.loads(raw)
                if msg.get("error_code"):
                    logger.warning("stream soniox error: %s %s", msg.get("error_code"), msg.get("error_message"))
                    break
                changed = False
                tail = ""
                for tok in msg.get("tokens", []):
                    if tok.get("is_final"):
                        await self._append_final(tok)
                        changed = True
                    else:
                        tail += tok.get("text", "")
                self._interim_tail = tail
                self._last_token_at = time.monotonic()
                await self._maybe_push_interim(force=changed)
                if msg.get("finished"):
                    break
        except Exception as e:  # noqa: BLE001
            logger.debug("stream reader ended: %s", e)
        finally:
            await self._flush(final=True)

    async def _append_final(self, tok: dict) -> None:
        # New segment if there's a real gap since the last final token: close the
        # open one FIRST (before appending) so the gap becomes the seam — but only
        # if it's already a worthwhile length, else let this token extend it (avoids
        # tiny mid-word fragments when Soniox reports a spurious gap).
        if self._open:
            gap = (tok.get("start_ms") or 0) - (self._open[-1].get("end_ms") or 0)
            # Only split at a WORD boundary — Soniox prefixes a new word with a
            # leading space, so a token without one continues the current word;
            # splitting there would cut a word in half ("re" | "ad").
            at_word_boundary = (tok.get("text") or "").startswith((" ", "\n"))
            if gap > STREAM_SEG_GAP_MS and at_word_boundary and len(self._open_text()) >= STREAM_SEG_MIN_CHARS:
                await self._flush(reason=f"gap{gap}")
        self._open.append(tok)
        text = self._open_text()
        # Close on sentence punctuation (once long enough) or when it grows too long.
        if text and text[-1] in ".?!。！？" and len(text) >= STREAM_SEG_MIN_CHARS:
            await self._flush(reason="punct")
        elif len(text) > STREAM_SEG_MAX_CHARS:
            await self._flush(reason="maxlen")

    def _open_text(self) -> str:
        return "".join(t.get("text", "") for t in self._open).strip()

    async def _ticker(self) -> None:
        # Close the open segment once speech pauses (so the last sentence before a
        # silence is committed instead of lingering as interim).
        try:
            while not self._closed:
                await asyncio.sleep(0.3)
                # Don't idle-flush while a partial (non-final) word is still forming
                # — that's Soniox mid-word, and flushing there would cut it ("re"|"ad").
                if (
                    self._open
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
        if line:
            await _post_ingest({
                "platform": self.platform, "native_meeting_id": self.native_id,
                "kind": "interim", "text": line, "speaker": self.speaker,
            })

    async def _flush(self, final: bool = False, reason: str = "end") -> None:
        async with self._flush_lock:
            if not self._open:
                return
            toks, self._open = self._open, []
        text = "".join(t.get("text", "") for t in toks).strip()
        if not text:
            return
        seg_id = f"{self.channel}:{self._seq}"
        self._seq += 1
        logger.info("stream ch%d FLUSH seg=%s reason=%s len=%d: ...%s", self.channel, seg_id, reason, len(text), text[-24:])
        start = (toks[0].get("start_ms") or 0) / 1000.0
        end = (toks[-1].get("end_ms") or 0) / 1000.0
        langs = [t.get("language") for t in toks if t.get("language")]
        lang = max(set(langs), key=langs.count) if langs else (self.language or "")
        await _post_ingest({
            "platform": self.platform, "native_meeting_id": self.native_id,
            "kind": "final", "seg_id": seg_id, "text": text, "speaker": self.speaker,
            "lang": lang, "start": start, "end": end,
        })

    async def close(self) -> None:
        self._closed = True
        try:
            self._pcm_q.put_nowait(None)  # signal writer to send "" (end-of-audio) to Soniox
        except Exception:  # noqa: BLE001
            pass
        # Soniox commits the FINAL tokens only after it sees end-of-audio, in a
        # trailing burst. WAIT for the reader to drain that burst (it flushes the
        # remaining segment(s) in its finally) before tearing anything down —
        # cancelling early here was dropping the tail of every stream.
        if self._reader_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._reader_task), timeout=10)
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
    """Bot -> bridge PCM relay. Query: platform, meeting, lang, token.
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
    await ws.accept()
    logger.info("stream relay open: %s/%s (lang=%s)", platform, native_id, language or "auto")
    channels: dict[int, _ChannelStream] = {}
    pending_speaker: dict[int, str] = {}  # speaker set before the channel's first audio

    async def get_channel(ch: int) -> _ChannelStream:
        cs = channels.get(ch)
        if cs is None:
            cs = _ChannelStream(platform, native_id, ch, language)
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
