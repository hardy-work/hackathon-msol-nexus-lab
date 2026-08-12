#!/usr/bin/env python3
"""Runtime cache, conversation and external coverage authorization tests."""
from __future__ import annotations

import os
import tempfile
import json
import sqlite3
from pathlib import Path

import access_control
import answer
from conversation import ConversationStore
from query_cache import QueryCache, cache_key
import telemetry


def main() -> int:
    allowed = access_control.AccessContext("demo", frozenset({"project_member"}))
    kb = answer.KB(access=allowed)
    os.environ.pop("KNOWLEDGE_BASE_COVERAGE_GRANTS", None)
    os.environ.pop("KNOWLEDGE_BASE_APPROVAL_IDS", None)
    assert not kb.signed("person_task")
    os.environ["KNOWLEDGE_BASE_COVERAGE_GRANTS"] = (
        '{"Đô":["knowledge_base:approve_coverage"]}'
    )
    os.environ["KNOWLEDGE_BASE_APPROVAL_IDS"] = "nexus-demo-person-task-20260803"
    assert kb.signed("person_task")
    rewritten = answer.resolve_ellipsis(kb, "còn SơnBH thì sao",
                                        "ĐôNT làm vai trò gì?", "do-nt")
    assert rewritten == "SơnBH làm vai trò gì?"

    with tempfile.TemporaryDirectory(prefix="pk-runtime-") as temp:
        cache = QueryCache(Path(temp) / "cache.sqlite3")
        key_a = cache_key("nexus", "q", "v1", allowed.fingerprint, False)
        key_b = cache_key("nexus", "q", "v2", allowed.fingerprint, False)
        cache.put(key_a, "v1", {"answer": "a"})
        assert cache.get(key_a) == {"answer": "a"} and cache.get(key_b) is None
        cache.con.execute("UPDATE cache SET expires_at=0 WHERE key=?", (key_a,))
        cache.con.commit()
        assert cache.get(key_a) is None
        cache.close()

        os.environ["KNOWLEDGE_BASE_CONVERSATION_MAX_PER_THREAD"] = "8"
        store = ConversationStore(Path(temp) / "conversation.sqlite3")
        for index in range(12):
            store.append("thread", "user" if index % 2 == 0 else "assistant", str(index))
        assert len(store.history("thread", limit=20)) == 8
        store.con.execute("UPDATE message SET created_at='2000-01-01 00:00:00'")
        store.con.commit()
        store.append("thread", "user", "new")
        assert [m["content"] for m in store.history("thread", limit=20)] == ["new"]
        store.close()
        telemetry_path = Path(temp) / "telemetry.sqlite3"
        telemetry.record("query", path=telemetry_path, query="secret question",
                         actor="U-secret", status="in_kb", duration_ms=1)
        con = sqlite3.connect(telemetry_path)
        fields = json.loads(con.execute("SELECT fields FROM event").fetchone()[0])
        con.close()
        assert "query" not in fields and "actor" not in fields
        assert telemetry.summary(telemetry_path)["events"] == 1
    print("✓ runtime self-test: 11/11 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
