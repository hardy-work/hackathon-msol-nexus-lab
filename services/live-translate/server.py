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
# Dedicated loggers so `grep` can isolate each half of the interim-preview
# pipeline: what came in (raw interim text as it grows) vs. what happened to
# translating it (dispatched/broadcast/stale/failed).
logger_interim = logging.getLogger("live-translate.interim")
logger_interim_xlate = logging.getLogger("live-translate.interim.translate")

VEXA_BASE_URL = os.getenv("VEXA_BASE_URL", "http://localhost:18056")
VEXA_API_KEY = os.getenv("VEXA_API_KEY", "")
WEB_PUBLIC_URL = os.getenv("WEB_PUBLIC_URL", "").rstrip("/")
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "1.5"))
IDLE_SHUTDOWN_S = float(os.getenv("IDLE_SHUTDOWN_S", "300"))
DEFAULT_LANG = os.getenv("DEFAULT_TARGET_LANG", "vi")
# Preview-translate the live "đang nghe" interim line, not just committed
# segments. NOT debounced-until-stable — a completed sentence gets flushed to
# a real segment the instant soniox-bridge sees its closing punctuation (zero
# delay), so a stable-and-not-yet-final window essentially never exists during
# continuous speech; waiting for "stable" meant this almost never fired. Instead,
# translate whatever partial text is on screen at a fixed cadence (throttled by
# this interval, and only one in flight at a time) — same idea as live caption
# translation: the preview keeps catching up to a growing sentence rather than
# waiting for it to finish.
INTERIM_XLATE_MIN_INTERVAL_S = float(os.getenv("INTERIM_XLATE_MIN_INTERVAL_S", "1.2"))
# Don't bother translating a fragment this short — too little signal, and it's
# about to be superseded by more words anyway.
INTERIM_XLATE_MIN_CHARS = int(os.getenv("INTERIM_XLATE_MIN_CHARS", "8"))

_translator = build_translator()
# Pool of separate instances/sessions for interim previews. Confirmed-segment
# translation (via _translator) and interim previews used to share one
# persistent Claude session, which serializes ALL queries on one lock — under
# continuous speech, every interim preview queued up behind final-segment
# translations and was almost always stale by the time its turn came (observed
# 20+ second waits live). A single dedicated session removed contention with
# segment translation, but each translate() call is itself a multi-second LLM
# round-trip (observed 8-17s live even on a warm session), so ONE session can
# still only process one interim preview at a time — a slow call blocks every
# window behind it. A POOL lets several previews translate concurrently
# instead of queueing (each PersistentClaudeTranslator instance serializes
# internally on its own lock, so pooling — not just raising concurrency
# against one instance — is what actually parallelizes this).
INTERIM_TRANSLATOR_POOL_SIZE = int(os.getenv("INTERIM_TRANSLATOR_POOL_SIZE", "3"))
_interim_translator_pool: list = []          # filled in _lifespan (needs a running loop for warm())
_interim_pool_lock = asyncio.Lock()


async def _acquire_interim_translator():
    """Non-blocking: returns None immediately if every pool slot is busy,
    rather than waiting — a queued-up wait would defeat the point (better to
    skip this preview round and catch a fresher one next tick)."""
    async with _interim_pool_lock:
        if _interim_translator_pool:
            return _interim_translator_pool.pop()
    return None


async def _release_interim_translator(t) -> None:
    async with _interim_pool_lock:
        _interim_translator_pool.append(t)

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
        # B-full: when the bot streams a continuous transcript straight to us
        # (via the bridge's /v1/stream relay), it becomes the authoritative source
        # for this room and the Vexa confirm-layer poller stops emitting segments
        # (it would duplicate / lag). Segments then arrive via ingest_final().
        self.bfull = False
        self._bfull_idx: dict[str, int] = {}   # seg_id -> stable idx
        self._bfull_next = 1_000_000           # idx space disjoint from Vexa's
        # Live preview translation of the current interim line (see ingest_interim).
        self._interim_text = ""
        self._interim_last_xlate_at = 0.0
        # lang -> (text it was translated for, translation). The most recent
        # successful interim preview per language — reused in ingest_final to
        # seed a segment's translation cell instantly instead of a blank "…"
        # while the authoritative translation (below) is still in flight.
        self._last_interim_xlate: dict[str, tuple[str, str]] = {}

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
        # B-full is live for this room -> the bot's continuous stream is the source
        # of truth; don't also emit Vexa's confirm-layer segments (they'd duplicate
        # and re-introduce the seam drops we bypassed). Still check for bot-gone.
        if self.bfull:
            if await self._bot_gone():
                self._ended = True
            return

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
                # Segment is already in the target language -> nothing to
                # translate; the frontend collapses these to a single column
                # instead of showing identical text twice.
                and not (self._segments[i].language and self._segments[i].language == lang)
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

    # -- B-full ingest (bot's continuous stream = authoritative source) ----- #

    def ingest_interim(self, text: str, speaker: Optional[str]) -> None:
        self._broadcast({"type": "interim", "text": text, "speaker": speaker or ""})
        self._interim_text = text
        loop = asyncio.get_event_loop()
        now = loop.time()
        gap = now - self._interim_last_xlate_at
        logger_interim.info("room %s: %r (speaker=%s)", self.key, text, speaker or "")
        if len(text.strip()) < INTERIM_XLATE_MIN_CHARS:
            return
        if gap < INTERIM_XLATE_MIN_INTERVAL_S:
            return
        self._interim_last_xlate_at = now
        asyncio.create_task(self._interim_translate(text))

    async def _interim_translate(self, text: str) -> None:
        translator = await _acquire_interim_translator()
        if translator is None:
            logger_interim_xlate.info(
                "room %s: pool busy (all %d slots in use), skipping (%d chars): %r",
                self.key, INTERIM_TRANSLATOR_POOL_SIZE, len(text), text,
            )
            return
        logger_interim_xlate.info("room %s: dispatched (%d chars): %r", self.key, len(text), text)
        try:
            for lang in self._active_langs():
                try:
                    translated = await translator.translate([text], lang)
                except Exception as e:  # noqa: BLE001 - a failed preview is not fatal
                    logger_interim_xlate.info("room %s: translate failed: %s", self.key, e)
                    continue
                # The translate call is slow enough (an LLM round-trip) that the
                # interim line has usually grown further by the time it returns —
                # requiring an EXACT match here meant almost every preview got
                # dropped as "stale" even though the sentence just kept extending
                # in the same direction. Accept it as long as the current interim
                # still starts with the text we translated (still the same,
                # still-growing sentence); only drop if it's genuinely gone
                # (finalized, cleared, or the sentence actually changed).
                if not self._interim_text.startswith(text):
                    logger_interim_xlate.info(
                        "room %s: stale, dropping (lang=%s) — translated %r but current interim is now %r",
                        self.key, lang, text, self._interim_text,
                    )
                    continue
                logger_interim_xlate.info(
                    "room %s: broadcast (lang=%s) %r -> %r", self.key, lang, text, translated[0],
                )
                self._broadcast(
                    {"type": "interim_translation", "lang": lang, "text": translated[0], "for_text": text},
                    only_lang=lang,
                )
                self._last_interim_xlate[lang] = (text, translated[0])
        finally:
            await _release_interim_translator(translator)

    def ingest_final(
        self, seg_id: str, speaker: str, language: str, text: str,
        start: Optional[float], end: Optional[float],
    ) -> None:
        """A finalized line from the bot's continuous stream. Treat it as a room
        segment (translate + broadcast), bypassing Vexa's confirm layer entirely."""
        self.bfull = True  # from now on the poller won't emit its own segments
        # This text just got committed as a real segment (which gets its own,
        # authoritative translation below). Clear it so an in-flight interim
        # preview's staleness check (in _interim_translate) drops its result
        # instead of showing next to text no longer on screen.
        self._interim_text = ""
        idx = self._bfull_idx.get(seg_id)
        if idx is None:
            idx = self._bfull_next
            self._bfull_next += 1
            self._bfull_idx[seg_id] = idx
        seg = Segment(idx=idx, speaker=speaker or "Speaker", language=(language or "").lower(),
                      text=text, start=start, end=end)
        self._seen[idx] = text
        self._segments[idx] = seg
        self._broadcast(self._segment_event(seg))
        # New/updated text -> drop stale translations so it re-translates.
        for cache in self._translations.values():
            cache.pop(idx, None)
        # Seed the segment's translation cell with the most recent interim
        # preview, if it covers this segment's text (same sentence, interim
        # just hadn't caught up to the very end of it yet) — the viewer sees a
        # translation immediately instead of "…". This is NOT written into
        # self._translations (that cache is what _schedule_missing checks to
        # decide what still needs translating), so the authoritative call
        # below still runs and its broadcast corrects/replaces this seed once
        # ready. Not reused across segments: whether used or not, it belonged
        # to interim text that's now gone.
        for lang, (for_text, translated_text) in self._last_interim_xlate.items():
            if text.startswith(for_text):
                logger_interim_xlate.info(
                    "room %s: seeded segment idx=%s (lang=%s) from interim preview %r -> %r",
                    self.key, idx, lang, for_text, translated_text,
                )
                self._broadcast(self._translation_event(idx, lang, translated_text), only_lang=lang)
        self._last_interim_xlate.clear()
        self._schedule_missing()

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

async def _build_and_warm_interim_translator() -> None:
    t = build_translator()
    await t.warm()
    async with _interim_pool_lock:
        _interim_translator_pool.append(t)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Pay the persistent-session connect cost now, in the background, so the
    # first real translation of a meeting isn't stalled waiting for it.
    asyncio.create_task(_translator.warm())
    for _ in range(INTERIM_TRANSLATOR_POOL_SIZE):
        asyncio.create_task(_build_and_warm_interim_translator())
    yield


app = FastAPI(title="Live Translate", version="1.0.0", lifespan=_lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "vexa": VEXA_BASE_URL, "backend": os.getenv("TRANSLATE_BACKEND", "subscription")}


# --------------------------------------------------------------------------- #
# Interim ingest (B1): soniox-bridge pushes its RAW transcript here, bypassing #
# Vexa's confirm layer, for a low-latency "live" line. Feature is opt-in — the #
# bridge only pushes when its LIVE_INGEST_URL env is set, so unsetting that     #
# reverts to the confirmed-only behavior with no code changes.                 #
# --------------------------------------------------------------------------- #

INGEST_TOKEN = os.getenv("INGEST_TOKEN", "").strip()
_active_cache: dict = {"room": None, "at": 0.0}


async def _current_active_room() -> Optional[tuple[str, str]]:
    """Return (platform, native_id) if EXACTLY one bot is running (so we can
    route an id-less ingest to it), else None. Cached ~2s so frequent ingests
    don't hammer Vexa."""
    loop = asyncio.get_event_loop()
    now = loop.time()
    if now - _active_cache["at"] < 2.0:
        return _active_cache["room"]
    room = _active_cache["room"]
    try:
        resp = await _vexa.get("/bots/status")
        resp.raise_for_status()
        data = resp.json()
        bots = data.get("running_bots") or data.get("running") or []
        running = [b for b in bots if isinstance(b, dict)]
        room = (
            (str(running[0].get("platform")), str(running[0].get("native_meeting_id")))
            if len(running) == 1
            else None
        )
    except Exception:  # noqa: BLE001 - keep last known on a transient hiccup
        pass
    _active_cache["room"] = room
    _active_cache["at"] = now
    return room


@app.post("/api/ingest")
async def ingest(payload: dict, request: Request) -> dict:
    """Ingest a transcript line pushed by soniox-bridge.

    Two shapes are accepted:
      * B-full stream relay (preferred): a structured line addressed to a specific
        room by {platform, native_meeting_id}, with kind="interim" | "final". A
        "final" becomes an authoritative room segment (translated); "interim" is a
        fast live line. This is the bot's continuous per-speaker stream, which
        never drops words at turn seams.
      * B1 legacy: a bare {text} with no room -> routed to the single active
        meeting as an interim line (kept for backward compatibility).
    """
    if INGEST_TOKEN and request.headers.get("X-Ingest-Token") != INGEST_TOKEN:
        return {"ok": False, "error": "unauthorized"}

    text = (payload.get("text") or "").strip()
    platform = payload.get("platform")
    native_id = payload.get("native_meeting_id")
    kind = payload.get("kind")

    # Structured (B-full) path: addressed to an explicit room.
    if platform and native_id and kind:
        room = get_room(str(platform), str(native_id))
        if kind == "final":
            if not text:
                return {"ok": True, "skipped": "empty"}
            room.ingest_final(
                seg_id=str(payload.get("seg_id") or f"x:{len(room._segments)}"),
                speaker=str(payload.get("speaker") or "Speaker"),
                language=str(payload.get("lang") or ""),
                text=text,
                start=payload.get("start"),
                end=payload.get("end"),
            )
        else:  # interim
            if text:
                room.ingest_interim(text, payload.get("speaker"))
        return {"ok": True, "room": room.key}

    # Legacy B1 path: bare interim text -> single active meeting.
    if not text:
        return {"ok": True, "skipped": "empty"}
    target = await _current_active_room()
    if not target:
        return {"ok": True, "skipped": "no-single-active-meeting"}
    p, n = target
    get_room(p, n)._broadcast({"type": "interim", "text": text})
    return {"ok": True, "room": f"{p}/{n}"}


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


@app.get("/api/rooms/{platform}/{native_id}/transcript")
async def room_transcript(platform: str, native_id: str) -> JSONResponse:
    """Full assembled transcript for a room, for meeting-notetaker's get_transcript
    to read instead of hitting Vexa directly. When `bfull` is true the segments
    came from the bot's continuous per-speaker Soniox stream (no turn-seam loss);
    otherwise they're whatever this room's Vexa-confirm-layer poller has seen so
    far. Doesn't create a room / trigger any polling — a plain lookup so calling
    this for a meeting live-translate never saw just returns empty segments."""
    room = _rooms.get(f"{platform}/{native_id}")
    if room is None:
        return JSONResponse({"segments": [], "bfull": False})
    segments = [
        {
            "speaker": seg.speaker,
            "language": seg.language,
            "text": seg.text,
            "start": seg.start,
            "end": seg.end,
        }
        for _, seg in sorted(room._segments.items())
    ]
    return JSONResponse({"segments": segments, "bfull": room.bfull})


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
