#!/usr/bin/env python3
"""Runtime cache, conversation and external coverage authorization tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import access_control
import answer
from conversation import ConversationStore
from query_cache import QueryCache, cache_key


def main() -> int:
    allowed = access_control.AccessContext("demo", frozenset({"project_member"}))
    kb = answer.KB(access=allowed)
    os.environ.pop("PROJECT_KNOWLEDGE_COVERAGE_GRANTS", None)
    os.environ.pop("PROJECT_KNOWLEDGE_APPROVAL_IDS", None)
    assert not kb.signed("person_task")
    os.environ["PROJECT_KNOWLEDGE_COVERAGE_GRANTS"] = (
        '{"Đô":["project_knowledge:approve_coverage"]}'
    )
    os.environ["PROJECT_KNOWLEDGE_APPROVAL_IDS"] = "nexus-demo-person-task-20260803"
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
        cache.close()

        store = ConversationStore(Path(temp) / "conversation.sqlite3")
        store.append("thread", "user", "q")
        store.append("thread", "assistant", "a")
        assert [m["role"] for m in store.history("thread")] == ["user", "assistant"]
        store.close()
    print("✓ runtime self-test: 6/6 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
