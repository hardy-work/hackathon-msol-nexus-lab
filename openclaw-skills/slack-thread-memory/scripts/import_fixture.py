#!/usr/bin/env python3
"""Import a local Slack thread fixture into the isolated thread store."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from thread_store import ThreadStore, canonical_thread_id


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_fixture(path: Path) -> tuple[str, str, str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture phải là JSON object")
    channel_id = str(payload.get("channel_id") or payload.get("channel") or "").strip()
    messages = payload.get("messages")
    if not channel_id or not isinstance(messages, list) or not messages:
        raise ValueError("fixture cần channel_id và messages không rỗng")
    first_ts = str(messages[0].get("ts") or messages[0].get("message_ts") or "").strip()
    thread_ts = str(payload.get("thread_ts") or first_ts).strip()
    if not thread_ts:
        raise ValueError("fixture thiếu thread_ts")
    channel_name = str(payload.get("channel_name") or "")
    normalized: list[dict] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("mỗi message phải là object")
        item = dict(message)
        # Slack root messages normally omit thread_ts; normalize it before
        # handing data to the strict store.
        item.setdefault("thread_ts", thread_ts)
        normalized.append(item)
    return channel_id, thread_ts, channel_name, normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Lưu fixture của một Slack thread")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--print-context", action="store_true")
    args = parser.parse_args()
    try:
        channel_id, thread_ts, channel_name, messages = load_fixture(args.fixture)
        store = ThreadStore(args.db)
        thread_id = canonical_thread_id(channel_id, thread_ts)
        count = store.append_messages(channel_id, thread_ts, messages,
                                       channel_name=channel_name)
        if args.summary is not None:
            store.set_summary(thread_id, args.summary)
        result = {"thread_id": thread_id, "stored_messages": count, "stats": store.stats()}
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
