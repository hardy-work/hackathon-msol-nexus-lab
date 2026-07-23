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
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
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
# Our own inbound auth, same dual scheme Vexa's reference service supports.
API_TOKEN = os.getenv("API_TOKEN", "").strip()

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
        "enable_language_identification": True,
    }
    if language:
        config["language_hints"] = [language]

    final_tokens: list[dict] = []
    finished = False

    async with websockets.connect(SONIOX_WS_URL, open_timeout=10) as ws:
        await ws.send(json.dumps(config))

        # Send the whole buffer in bounded chunks (kinder to the socket than one giant frame).
        chunk_size = 32000
        for i in range(0, len(audio_bytes), chunk_size):
            await ws.send(audio_bytes[i : i + chunk_size])
        await ws.send("")  # end-of-audio signal

        deadline = time.monotonic() + SONIOX_TIMEOUT_S
        while not finished:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Soniox response timed out before 'finished'; using tokens received so far")
                break
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("error_code"):
                raise HTTPException(status_code=502, detail=f"Soniox error {msg['error_code']}: {msg.get('error_message')}")
            for token in msg.get("tokens", []):
                if token.get("is_final"):
                    final_tokens.append(token)
            finished = bool(msg.get("finished"))

    return _tokens_to_whisper_response(final_tokens, language)


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


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
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
    try:
        result = await _transcribe_via_soniox(audio_bytes, language)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Soniox transcription failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Soniox transcription failed: {e}")

    logger.info(
        f"transcribed {len(audio_bytes)} bytes in {time.time() - start:.2f}s - "
        f"language={result['language']}, segments={len(result['segments'])}"
    )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
