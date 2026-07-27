"""Pluggable translation backends for the live-translate web app.

Two backends, selected by env TRANSLATE_BACKEND:

  * "subscription" (default) — shells out to the `claude` CLI in print mode.
    This uses whatever auth Claude Code is logged in with, so a Claude
    Pro/Max **subscription** powers the translation with no per-token API
    bill. Requirement: run `claude` (Claude Code) logged in on this host and
    do NOT set ANTHROPIC_API_KEY (its presence would flip the CLI to API
    billing).

  * "api" — calls the Anthropic Messages API directly with ANTHROPIC_API_KEY.
    Lower latency, but billed per token; subscription does not apply here.

Both honor the same contract: given a list of source strings, return a list
of translated strings of the SAME length and order. We ask the model to
return a JSON array so a batch of new segments costs a single call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional, Protocol

logger = logging.getLogger("live-translate.translator")

CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "claude-haiku-4-5")
CLAUDE_TIMEOUT_S = float(os.getenv("TRANSLATE_TIMEOUT_S", "45"))

# Friendly names so the prompt reads naturally regardless of the code passed in.
_LANG_NAMES = {
    "vi": "Vietnamese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "th": "Thai",
    "id": "Indonesian",
}


def lang_name(code: str) -> str:
    return _LANG_NAMES.get(code.lower(), code)


def _build_prompt(texts: list[str], target_lang: str) -> str:
    target = lang_name(target_lang)
    payload = json.dumps(texts, ensure_ascii=False)
    return (
        f"You are a professional real-time meeting interpreter. Translate each "
        f"string in the JSON array below into {target}. Preserve meaning, names, "
        f"numbers and technical terms; keep it natural and concise. Do NOT add "
        f"commentary. If a string is already in {target}, return it unchanged.\n\n"
        f"Return ONLY a JSON array of strings, same length and order as the input, "
        f"nothing else.\n\n"
        f"Input:\n{payload}"
    )


def _extract_json_array(raw: str, expected_len: int) -> Optional[list[str]]:
    """Pull a JSON array of strings out of a model response, tolerating code
    fences or a stray sentence around it. Returns None if it can't be trusted."""
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    # Grab the outermost [...] span.
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        arr = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list):
        return None
    out = [str(x) for x in arr]
    if len(out) != expected_len:
        logger.warning("translation length mismatch: got %d want %d", len(out), expected_len)
        return None
    return out


class Translator(Protocol):
    async def translate(self, texts: list[str], target_lang: str) -> list[str]:
        ...

    async def warm(self) -> None:
        """Optional: pre-initialize any expensive resource. No-op by default."""
        ...


class ClaudeCliTranslator:
    """Subscription-powered: runs `claude -p` so translation draws on the
    logged-in Claude Code subscription instead of API credits."""

    async def warm(self) -> None:
        return None  # nothing to pre-connect; each call spawns fresh

    async def translate(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        prompt = _build_prompt(texts, target_lang)
        # Never let an API key leak into the CLI env — that would switch it to
        # per-token API billing and defeat the point of the subscription path.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        try:
            proc = await asyncio.create_subprocess_exec(
                CLAUDE_BIN,
                "-p",
                prompt,
                "--model",
                TRANSLATE_MODEL,
                "--output-format",
                "text",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("claude CLI translate timed out after %ss", CLAUDE_TIMEOUT_S)
            return texts  # fail open: show source text rather than nothing
        except FileNotFoundError:
            logger.error("`%s` not found on PATH — is Claude Code installed?", CLAUDE_BIN)
            return texts
        if proc.returncode != 0:
            logger.error("claude CLI exited %s: %s", proc.returncode, stderr.decode()[:500])
            return texts
        parsed = _extract_json_array(stdout.decode(), len(texts))
        return parsed if parsed is not None else texts


class PersistentClaudeTranslator:
    """Subscription-powered, but keeps ONE `claude` process warm via the Agent
    SDK so each translation is just a message round-trip (~2-3s) instead of
    paying the ~5s CLI boot on every call. Falls back to source text on any
    error, and self-heals by reconnecting.

    Measured: fresh `claude -p` per call ≈ 6s; warm SDK session ≈ 2.5s. The
    one-time connect cost is paid lazily on the first translation (in the
    background poller, so originals still stream instantly).
    """

    # Recycle the session periodically so a long meeting's conversation history
    # can't grow unbounded. Done in the background (double-buffered) so it never
    # stalls a translation.
    RECYCLE_AFTER = int(os.getenv("TRANSLATE_RECYCLE_AFTER", "100"))

    def __init__(self) -> None:
        self._client = None
        self._connect_lock = asyncio.Lock()
        self._query_lock = asyncio.Lock()  # one session -> serialize queries
        self._count = 0
        self._recycling = False

    async def _new_client(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        # No API key in the env -> the CLI uses the logged-in subscription.
        os.environ.pop("ANTHROPIC_API_KEY", None)
        opts = ClaudeAgentOptions(
            model=TRANSLATE_MODEL,
            allowed_tools=[],
            system_prompt=(
                "You are a real-time meeting interpreter. You translate text "
                "exactly as instructed and reply with ONLY the requested output "
                "(a JSON array of strings), never any commentary or tool use."
            ),
        )
        client = ClaudeSDKClient(options=opts)
        await client.connect()
        logger.info("persistent claude session connected (model=%s)", TRANSLATE_MODEL)
        return client

    async def warm(self) -> None:
        """Pre-connect the session so the ~connect cost is paid at startup, not
        on the first translation of a meeting."""
        if self._client is not None:
            return
        async with self._connect_lock:
            if self._client is None:
                try:
                    self._client = await self._new_client()
                    self._count = 0
                except Exception as e:  # noqa: BLE001
                    logger.error("persistent claude warm-up failed: %s", e)

    async def _ensure_client(self):
        if self._client is not None:
            return self._client
        async with self._connect_lock:
            if self._client is None:
                self._client = await self._new_client()
                self._count = 0
            return self._client

    async def _recycle(self) -> None:
        """Build a fresh session in the background, then swap it in atomically
        and retire the old one — no translation ever waits on a reconnect."""
        if self._recycling:
            return
        self._recycling = True
        try:
            fresh = await self._new_client()
            async with self._query_lock:
                old, self._client = self._client, fresh
                self._count = 0
            if old is not None:
                try:
                    await old.disconnect()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            logger.error("persistent claude recycle failed: %s", e)
        finally:
            self._recycling = False

    async def translate(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        from claude_agent_sdk import AssistantMessage, TextBlock

        prompt = _build_prompt(texts, target_lang)
        async with self._query_lock:
            try:
                client = await self._ensure_client()
                await client.query(prompt)
                out = ""
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                out += block.text
            except Exception as e:  # noqa: BLE001 - drop session, fail open, reconnect next call
                logger.error("persistent claude translate failed: %s", e)
                self._client = None
                return texts
            self._count += 1

        if self._count >= self.RECYCLE_AFTER and not self._recycling:
            asyncio.create_task(self._recycle())  # background, non-blocking

        parsed = _extract_json_array(out, len(texts))
        return parsed if parsed is not None else texts


class AnthropicApiTranslator:
    """API-key-powered: direct Messages API. Lower latency, billed per token."""

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic  # lazy import so subscription mode needs no SDK

        self._client = AsyncAnthropic()

    async def warm(self) -> None:
        return None  # HTTP client is cheap; nothing to pre-connect

    async def translate(self, texts: list[str], target_lang: str) -> list[str]:
        if not texts:
            return []
        prompt = _build_prompt(texts, target_lang)
        try:
            msg = await self._client.messages.create(
                model=TRANSLATE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:  # noqa: BLE001 - fail open on any API error
            logger.error("Anthropic API translate failed: %s", e)
            return texts
        raw = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        parsed = _extract_json_array(raw, len(texts))
        return parsed if parsed is not None else texts


def build_translator() -> Translator:
    backend = os.getenv("TRANSLATE_BACKEND", "subscription").strip().lower()
    if backend == "api":
        logger.info("translator backend: Anthropic API (model=%s)", TRANSLATE_MODEL)
        return AnthropicApiTranslator()
    if backend == "cli":
        logger.info("translator backend: Claude CLI spawn-per-call (model=%s)", TRANSLATE_MODEL)
        return ClaudeCliTranslator()
    # "subscription" (default): warm, persistent session — fastest subscription path.
    logger.info("translator backend: persistent Claude session / subscription (model=%s)", TRANSLATE_MODEL)
    return PersistentClaudeTranslator()
