#!/usr/bin/env python3
"""Ingest a Slack app_mention event and its already-fetched replies.

The gateway can fetch replies with Slack ``conversations.replies`` and pass the
event payload here.  This adapter deliberately does not fetch arbitrary channel
history or accept a thread id from the user's text.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from thread_store import ThreadStore, canonical_thread_id


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def normalize_event(payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    event = payload.get("event", payload)
    if not isinstance(event, dict) or event.get("type") != "app_mention":
        raise ValueError("chỉ nhận Slack event type=app_mention")
    channel_id = str(event.get("channel") or event.get("channel_id") or "").strip()
    event_ts = str(event.get("ts") or "").strip()
    thread_ts = str(event.get("thread_ts") or event_ts).strip()
    if not channel_id or not event_ts or not thread_ts:
        raise ValueError("app_mention thiếu channel hoặc ts")
    root = dict(event)
    root["thread_ts"] = thread_ts
    replies = payload.get("replies", [])
    if not isinstance(replies, list):
        raise ValueError("replies phải là một list")
    messages = [root]
    for raw in replies:
        if not isinstance(raw, dict):
            raise ValueError("mỗi reply phải là object")
        message = dict(raw)
        message_channel = str(message.get("channel") or channel_id).strip()
        if message_channel != channel_id:
            raise ValueError("reply khác channel với app_mention")
        reply_thread = str(message.get("thread_ts") or thread_ts).strip()
        if reply_thread != thread_ts:
            raise ValueError("reply nằm ngoài thread của app_mention")
        message["thread_ts"] = thread_ts
        messages.append(message)
    return channel_id, thread_ts, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Lưu Slack app_mention theo đúng thread")
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--print-context", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(args.event.read_text(encoding="utf-8"))
        channel_id, thread_ts, messages = normalize_event(payload)
        store = ThreadStore(args.db)
        thread_id = canonical_thread_id(channel_id, thread_ts)
        # Upsert makes the adapter safe when Slack retries an event.
        stored = store.append_messages(channel_id, thread_ts, messages)
        if args.summary is not None:
            store.set_summary(thread_id, args.summary)
        result: dict[str, Any] = {
            "thread_id": thread_id,
            "stored_messages": stored,
            "stats": store.stats(),
        }
        if args.print_context:
            result["context"] = store.context(thread_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        store.close()
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
