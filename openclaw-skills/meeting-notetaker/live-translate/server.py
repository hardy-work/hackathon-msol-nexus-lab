"""Live transcript + realtime translation web app.

Sits next to vexa-mcp / soniox-bridge and reuses the same Vexa instance. It
does NOT touch Vexa core — it only *reads* the growing transcript via the same
REST endpoint the meeting-notetaker skill already polls, translates newly
arrived segments once, and fans the result out to every browser watching the
room over Server-Sent Events.

Key design points:
  * One poller per room, shared across all viewers. N viewers != N Vexa polls
    and != N translation calls — translation happens once per (segment, target
    language) and is cached, so opening the shared link many times is cheap.
  * Original text is broadcast the instant it arrives; the translation is
    broadcast as a follow-up event once ready, so the UI never blocks on the
    translator.

Env:
  VEXA_BASE_URL, VEXA_API_KEY   - same as vexa-mcp
  WEB_PUBLIC_URL                - public base used when building shareable links
  POLL_INTERVAL_S               - transcript poll cadence (default 1.5)
  IDLE_SHUTDOWN_S               - stop a room's poller after this long with no
                                  viewers (default 300)
  TRANSLATE_BACKEND             - "subscription" (default) | "api"  (see translator.py)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from translator import build_translator, lang_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("live-translate")

VEXA_BASE_URL = os.getenv("VEXA_BASE_URL", "http://localhost:18056")
VEXA_API_KEY = os.getenv("VEXA_API_KEY", "")
WEB_PUBLIC_URL = os.getenv("WEB_PUBLIC_URL", "").rstrip("/")
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "1.5"))
IDLE_SHUTDOWN_S = float(os.getenv("IDLE_SHUTDOWN_S", "300"))
DEFAULT_LANG = os.getenv("DEFAULT_TARGET_LANG", "vi")

_translator = build_translator()

_vexa = httpx.AsyncClient(
    base_url=VEXA_BASE_URL,
    headers={"X-API-Key": VEXA_API_KEY},
    timeout=15.0,
)


# --------------------------------------------------------------------------- #
# Transcript parsing                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class Segment:
    idx: int
    speaker: str
    language: str
    text: str
    start: Optional[float]
    end: Optional[float]


def _parse_segments(payload: dict) -> list[Segment]:
    """Normalize Vexa's transcript response into ordered Segments.

    Vexa returns a dict with a "segments" list; each item carries text plus
    (optionally) speaker/language/start/end. We stay defensive about missing
    keys so an upstream shape tweak degrades gracefully instead of crashing.
    """
    raw = payload.get("segments") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return []
    out: list[Segment] = []
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append(
            Segment(
                idx=i,
                speaker=str(seg.get("speaker") or seg.get("speaker_name") or "Speaker"),
                language=str(seg.get("language") or seg.get("lang") or "").lower(),
                text=text,
                start=seg.get("start") if isinstance(seg.get("start"), (int, float)) else seg.get("start_time"),
                end=seg.get("end") if isinstance(seg.get("end"), (int, float)) else seg.get("end_time"),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Room = one meeting, one shared poller, many viewers                          #
# --------------------------------------------------------------------------- #


@dataclass(eq=False)  # identity-based hash so instances can live in a set
class Subscriber:
    lang: str
    queue: "asyncio.Queue[dict]" = field(default_factory=lambda: asyncio.Queue(maxsize=1000))


class Room:
    def __init__(self, platform: str, native_id: str) -> None:
        self.platform = platform
        self.native_id = native_id
        self.key = f"{platform}/{native_id}"
        self.subscribers: set[Subscriber] = set()
        # idx -> source text last seen (to detect new/changed segments)
        self._seen: dict[int, str] = {}
        # lang -> idx -> translated text (translate-once cache)
        self._translations: dict[str, dict[int, str]] = {}
        # lang -> {idx} currently being translated, so overlapping polls don't
        # double-dispatch the same segment to the model.
        self._pending: dict[str, set[int]] = {}
        # last known original snapshot, so a fresh viewer gets the backlog
        self._segments: dict[int, Segment] = {}
        self._task: Optional[asyncio.Task] = None
        # keep strong refs to in-flight translation tasks (else they get GC'd)
        self._xlate_tasks: set[asyncio.Task] = set()
        self._ended = False
        self._empty_polls = 0

    # -- viewer lifecycle --------------------------------------------------- #

    def add_subscriber(self, lang: str) -> Subscriber:
        sub = Subscriber(lang=lang)
        self.subscribers.add(sub)
        if self._task is None or self._task.done():
            # Reset any stale "ended" state from a previous cycle so a room that
            # is being re-viewed (e.g. same meeting id, or after a lull) polls
            # fresh and only re-ends if the bot is genuinely gone.
            self._ended = False
            self._empty_polls = 0
            self._task = asyncio.create_task(self._poll_loop())
        # A viewer may pick a language nothing has been translated into yet (or
        # join after capture) — backfill immediately instead of waiting for the
        # next spoken segment, which might never come.
        if self._segments:
            self._schedule_missing({lang})
        return sub

    def remove_subscriber(self, sub: Subscriber) -> None:
        self.subscribers.discard(sub)

    def backlog_for(self, lang: str) -> list[dict]:
        """Everything already captured, so a newly opened tab isn't blank."""
        events: list[dict] = []
        for idx in sorted(self._segments):
            seg = self._segments[idx]
            events.append(self._segment_event(seg))
            translated = self._translations.get(lang, {}).get(idx)
            if translated is not None:
                events.append(self._translation_event(idx, lang, translated))
        return events

    # -- event shapes ------------------------------------------------------- #

    @staticmethod
    def _segment_event(seg: Segment) -> dict:
        return {
            "type": "segment",
            "idx": seg.idx,
            "speaker": seg.speaker,
            "lang": seg.language,
            "text": seg.text,
            "start": seg.start,
            "end": seg.end,
        }

    @staticmethod
    def _translation_event(idx: int, lang: str, text: str) -> dict:
        return {"type": "translation", "idx": idx, "lang": lang, "text": text}

    def _broadcast(self, event: dict, only_lang: Optional[str] = None) -> None:
        for sub in list(self.subscribers):
            if only_lang is not None and sub.lang != only_lang:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("subscriber queue full on %s; dropping event", self.key)

    def _active_langs(self) -> set[str]:
        return {sub.lang for sub in self.subscribers}

    # -- the shared poll loop ---------------------------------------------- #

    async def _poll_loop(self) -> None:
        logger.info("room %s: poller started", self.key)
        idle_since: Optional[float] = None
        loop = asyncio.get_event_loop()
        try:
            while True:
                if not self.subscribers:
                    idle_since = idle_since or loop.time()
                    if loop.time() - idle_since > IDLE_SHUTDOWN_S:
                        logger.info("room %s: idle, stopping poller", self.key)
                        return
                else:
                    idle_since = None

                try:
                    await self._poll_once()
                except Exception as e:  # noqa: BLE001 - keep the room alive
                    logger.error("room %s: poll error: %s", self.key, e)

                if self._ended:
                    self._broadcast({"type": "end"})
                    logger.info("room %s: meeting ended", self.key)
                    return

                await asyncio.sleep(POLL_INTERVAL_S)
        finally:
            logger.info("room %s: poller exited", self.key)

    async def _poll_once(self) -> None:
        resp = await _vexa.get(f"/transcripts/{self.platform}/{self.native_id}")
        resp.raise_for_status()
        segments = _parse_segments(resp.json() if resp.content else {})

        new_or_changed: list[Segment] = []
        for seg in segments:
            if self._seen.get(seg.idx) != seg.text:
                self._seen[seg.idx] = seg.text
                self._segments[seg.idx] = seg
                new_or_changed.append(seg)
                self._broadcast(self._segment_event(seg))
                # Text changed (e.g. ASR finalized it) -> drop stale translations
                # in every language so it gets re-translated below.
                for cache in self._translations.values():
                    cache.pop(seg.idx, None)

        self._empty_polls = 0 if new_or_changed else self._empty_polls + 1

        # Translate any (segment, active-language) pair not yet done. This covers
        # new segments, re-translations of finalized text, AND languages a late
        # viewer just requested. Runs in the background so polling never stalls.
        self._schedule_missing()

        # End ONLY when the bot has actually left the meeting. (We used to also
        # end after a long silent stretch, but soniox transcription is bursty and
        # quiet meetings are normal, so that caused rooms to end mid-meeting and
        # stop pushing updates until a manual reload.)
        if await self._bot_gone():
            self._ended = True

    def _schedule_missing(self, langs: Optional[set[str]] = None) -> None:
        """For each target language, dispatch a background task translating any
        captured segment not yet translated (and not already in-flight) into it.
        Idempotent and cheap when nothing is missing, so it's safe to call every
        poll. This is what backfills late viewers and newly requested languages."""
        for lang in (langs or self._active_langs()):
            cache = self._translations.setdefault(lang, {})
            pending = self._pending.setdefault(lang, set())
            todo = [
                self._segments[i]
                for i in sorted(self._segments)
                if i not in cache and i not in pending
            ]
            if not todo:
                continue
            for s in todo:
                pending.add(s.idx)
            task = asyncio.create_task(self._run_translation(lang, todo))
            self._xlate_tasks.add(task)
            task.add_done_callback(self._xlate_tasks.discard)

    async def _run_translation(self, lang: str, segs: list[Segment]) -> None:
        cache = self._translations.setdefault(lang, {})
        pending = self._pending.setdefault(lang, set())
        try:
            translated = await _translator.translate([s.text for s in segs], lang)
            for seg, txt in zip(segs, translated):
                cache[seg.idx] = txt
                self._broadcast(self._translation_event(seg.idx, lang, txt), only_lang=lang)
        finally:
            for seg in segs:
                pending.discard(seg.idx)

    async def _bot_gone(self) -> bool:
        try:
            resp = await _vexa.get("/bots/status")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return False  # don't end on a transient status hiccup
        # Vexa's /bots/status returns {"running_bots": [...], "running": [...],
        # "count": N} — NOT a "bots" key. Read the right list.
        if isinstance(data, dict):
            bots = data.get("running_bots") or data.get("running") or data.get("bots") or []
        elif isinstance(data, list):
            bots = data
        else:
            return False
        if not isinstance(bots, list):
            return False
        for bot in bots:
            if not isinstance(bot, dict):
                continue
            if str(bot.get("native_meeting_id")) == self.native_id and str(bot.get("platform")) == self.platform:
                # Still listed as running (joining / awaiting_admission / active /
                # etc.) -> the bot is alive, the meeting is NOT over.
                return False
        # Absent from the running list -> genuinely gone. Only treat as ended if
        # we've actually captured content (don't end before it's admitted).
        return bool(self._segments)


_rooms: dict[str, Room] = {}


def get_room(platform: str, native_id: str) -> Room:
    key = f"{platform}/{native_id}"
    room = _rooms.get(key)
    if room is None:
        room = Room(platform, native_id)
        _rooms[key] = room
    return room


# --------------------------------------------------------------------------- #
# HTTP app                                                                     #
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Pay the persistent-session connect cost now, in the background, so the
    # first real translation of a meeting isn't stalled waiting for it.
    asyncio.create_task(_translator.warm())
    yield


app = FastAPI(title="Live Translate", version="1.0.0", lifespan=_lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "vexa": VEXA_BASE_URL, "backend": os.getenv("TRANSLATE_BACKEND", "subscription")}


@app.get("/api/rooms/{platform}/{native_id}")
async def room_info(platform: str, native_id: str) -> JSONResponse:
    """Lightweight metadata for a room, incl. whether the bot is still live."""
    room = get_room(platform, native_id)
    bot_active = not await room._bot_gone() if room._segments else True
    link = f"{WEB_PUBLIC_URL}/meet/{platform}/{native_id}" if WEB_PUBLIC_URL else None
    return JSONResponse(
        {
            "platform": platform,
            "native_meeting_id": native_id,
            "segments": len(room._segments),
            "bot_active": bot_active,
            "ended": room._ended,
            "share_link": link,
        }
    )


@app.get("/api/rooms/{platform}/{native_id}/stream")
async def stream(platform: str, native_id: str, request: Request, lang: str = DEFAULT_LANG) -> StreamingResponse:
    room = get_room(platform, native_id)
    sub = room.add_subscriber(lang)

    async def event_source() -> AsyncIterator[bytes]:
        # 1) hello + any backlog so a late joiner sees the conversation so far.
        yield _sse({"type": "hello", "lang": lang, "lang_name": lang_name(lang)})
        for event in room.backlog_for(lang):
            yield _sse(event)
        # 2) live events until the client disconnects.
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"  # comment frame keeps the connection warm
        finally:
            room.remove_subscriber(sub)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _sse(data: dict) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


# --------------------------------------------------------------------------- #
# Serve the built React app (SPA) — mounted last so /api/* wins.              #
# --------------------------------------------------------------------------- #

_DIST = Path(__file__).parent / "web" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        # Any non-API path serves index.html; React Router handles /meet/...
        return FileResponse(_DIST / "index.html")
else:
    logger.warning("web/dist not found — run `npm run build` in web/ to serve the UI")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), log_level="info")
