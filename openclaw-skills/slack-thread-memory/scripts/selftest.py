#!/usr/bin/env python3
"""Offline contract tests for the isolated, thread-scoped store."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from thread_store import ThreadStore, canonical_thread_id, default_state_dir, redact_text


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def message(ts: str, text: str, *, thread_ts: str | None = None, user: str = "U1", **extra):
    value = {"ts": ts, "thread_ts": thread_ts or "1.000", "user": user, "text": text}
    value.update(extra)
    return value


def main() -> int:
    assert "project-knowledge" not in str(default_state_dir()).lower()
    assert redact_text("token=xoxb-secret password=hunter2") == (
        "token=[REDACTED] password=[REDACTED]"
    )
    with tempfile.TemporaryDirectory(prefix="slack-thread-memory-") as temp:
        store = ThreadStore(Path(temp) / "threads.sqlite3")
        store.append_messages("C1", "1.000", [
            message("1.000", "@bot hãy xem tiến độ"),
            message("1.001", "Đã xong phần ingest", user="U2"),
        ])
        store.append_messages("C1", "2.000", [
            message("2.000", "Thread khác không được lẫn vào" , thread_ts="2.000"),
        ])
        first = canonical_thread_id("C1", "1.000")
        second = canonical_thread_id("C1", "2.000")
        assert [item["text"] for item in store.history(first)] == [
            "@bot hãy xem tiến độ", "Đã xong phần ingest"
        ]
        assert store.context(first)["messages"]
        assert all(item["text"] != "Thread khác không được lẫn vào"
                   for item in store.context(first)["messages"])

        # Upsert an edit rather than creating a duplicate message.
        store.append_message("C1", "1.000",
                             message("1.001", "Đã xong phần wiki", user="U2", edited=True))
        assert [item["text"] for item in store.history(first)][-1] == "Đã xong phần wiki"
        assert store.stats() == {"threads": 2, "messages": 3}

        # Deleted messages stay auditable but never enter answer context.
        store.append_message("C1", "2.000",
                             message("2.000", "đã xóa", thread_ts="2.000", deleted=True))
        assert store.history(second) == []
        assert len(store.history(second, include_deleted=True)) == 1

        store.set_summary(first, "Tóm tắt thread")
        assert store.context(first)["summary"] == "Tóm tắt thread"
        try:
            store.append_message("C1", "1.000", message("1.002", "sai scope", thread_ts="9.000"))
        except ValueError:
            pass
        else:
            raise AssertionError("message ngoài thread phải bị từ chối")
        store.close()
    print("✓ Slack thread-memory self-test: 8/8 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
