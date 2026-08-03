#!/usr/bin/env python3
"""Parse Slack payloads without depending on the Slack SDK."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def verify_signature(raw_body: bytes, timestamp: str, signature: str,
                     signing_secret: str, tolerance: int = 300) -> bool:
    """Verify Slack v0 signature; callers must reject stale/invalid requests."""
    try:
        if abs(int(time.time()) - int(timestamp)) > tolerance:
            return False
    except (TypeError, ValueError):
        return False
    base = b"v0:" + str(timestamp).encode() + b":" + raw_body
    digest = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")


def _strip_mentions(text: str) -> str:
    import re
    return re.sub(r"<@[A-Z0-9]+>\s*", "", text or "").strip()


def parse(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized event or a URL-verification response descriptor."""
    if payload.get("type") == "url_verification":
        return {"kind": "url_verification", "challenge": payload.get("challenge", "")}

    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    if payload.get("type") == "event_callback" and not event:
        return {"kind": "ignored", "reason": "event_callback không có event"}
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"kind": "ignored", "reason": "bỏ qua message do bot tạo để tránh vòng lặp"}

    event_type = event.get("type", "slash_command")
    text = event.get("text", payload.get("text", ""))
    channel = event.get("channel", payload.get("channel_id", ""))
    user = event.get("user", payload.get("user_id", ""))
    ts = event.get("ts", payload.get("timestamp", ""))
    thread_ts = event.get("thread_ts") or payload.get("thread_ts") or ts

    if event_type not in {"app_mention", "message", "slash_command"}:
        return {"kind": "ignored", "reason": f"event type không hỗ trợ: {event_type}"}
    if not text.strip():
        return {"kind": "empty", "channel_id": channel, "user_id": user,
                "thread_ts": thread_ts, "event_ts": ts}
    return {
        "kind": "query",
        "event_type": event_type,
        "text": _strip_mentions(text),
        "channel_id": channel,
        "user_id": user,
        "thread_ts": thread_ts,
        "event_ts": ts,
        "response_url": payload.get("response_url", ""),
    }
