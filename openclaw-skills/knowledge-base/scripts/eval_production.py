#!/usr/bin/env python3
"""Production-boundary evaluation: auth, context, cache and concurrency."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import access_control
import telemetry
from query_cache import cache_key
from runtime_engine import KnowledgeRuntime


def main() -> int:
    runtime = KnowledgeRuntime()
    checks = []

    checks.append(runtime.query("nexus", "ĐôNT làm vai trò gì?", actor="", roles=[],
                                use_cache=False)["status"] == "forbidden")
    checks.append(runtime.query("nexus", "ĐôNT làm vai trò gì?", actor="guest",
                                roles=["guest"], use_cache=False)["status"] == "forbidden")
    checks.append(runtime.query("nexus", "ĐôNT làm vai trò gì?", actor="member",
                                roles=["project_member"], use_cache=False)["status"] == "in_kb")

    old_grants = os.environ.pop("KNOWLEDGE_BASE_COVERAGE_GRANTS", None)
    old_ids = os.environ.pop("KNOWLEDGE_BASE_APPROVAL_IDS", None)
    unsigned = runtime.query("nexus", "TùngDV có task nào không?", actor="member",
                             roles=["project_member"], use_cache=False)
    checks.append(unsigned["status"] == "not_in_kb")
    os.environ["KNOWLEDGE_BASE_COVERAGE_GRANTS"] = (
        '{"Đô":["knowledge_base:approve_coverage"]}')
    os.environ["KNOWLEDGE_BASE_APPROVAL_IDS"] = "nexus-demo-person-task-20260803"
    signed = runtime.query("nexus", "TùngDV có task nào không?", actor="member",
                           roles=["project_member"], use_cache=False)
    checks.append(signed["status"] == "confident_no")

    follow = runtime.query(
        "nexus", "còn SơnBH thì sao", actor="member", roles=["project_member"], use_cache=False,
        history=[{"role": "user", "content": "ĐôNT làm vai trò gì?"}],
    )
    checks.append(follow.get("effective_query") == "SơnBH làm vai trò gì?")

    nonce_history = [{"role": "system", "content": f"eval-{time.time_ns()}"}]
    first = runtime.query("nexus", "API Login đang trạng thái gì?", actor="cache-user",
                          roles=["project_member"], history=nonce_history)
    second = runtime.query("nexus", "API Login đang trạng thái gì?", actor="cache-user",
                           roles=["project_member"], history=nonce_history)
    checks.append(not first["cache_hit"] and second["cache_hit"])

    member = access_control.AccessContext("member", frozenset({"project_member"}))
    manager = access_control.AccessContext("manager", frozenset({"project_manager"}))
    checks.append(not access_control.can_read_metadata(member, {"visibility": "restricted"}))
    checks.append(access_control.can_read_metadata(manager, {"visibility": "restricted"}))
    checks.append(cache_key("nexus", "q", "v", member.fingerprint, False) !=
                  cache_key("nexus", "q", "v", manager.fingerprint, False))

    questions = ["ĐôNT làm vai trò gì?", "Ai phụ trách API Login?",
                 "Authentication bắt đầu ngày nào?", "Ngân sách Nexus là bao nhiêu?"] * 4
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda q: runtime.query(
            "nexus", q, actor="load-user", roles=["project_member"], use_cache=False), questions))
    checks.append(all(result["status"] in {"in_kb", "not_in_kb"} for result in results))
    checks.append(telemetry.summary(hours=1)["events"] >= len(results))

    if old_grants is None:
        os.environ.pop("KNOWLEDGE_BASE_COVERAGE_GRANTS", None)
    else:
        os.environ["KNOWLEDGE_BASE_COVERAGE_GRANTS"] = old_grants
    if old_ids is None:
        os.environ.pop("KNOWLEDGE_BASE_APPROVAL_IDS", None)
    else:
        os.environ["KNOWLEDGE_BASE_APPROVAL_IDS"] = old_ids

    failed = [index + 1 for index, ok in enumerate(checks) if not ok]
    if failed:
        print(f"✗ production eval failed checks: {failed}")
        return 1
    print(f"✓ production boundary eval: {len(checks)}/{len(checks)} qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
