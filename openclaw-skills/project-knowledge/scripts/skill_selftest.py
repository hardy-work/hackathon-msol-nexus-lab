#!/usr/bin/env python3
"""Small provider-neutral smoke test for the packaged skill contract."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(__file__).resolve().parent / "run.py"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
CASES = [
    ("ĐôNT làm vai trò gì trong dự án Nexus?", "in_kb"),
    ("Ai phụ trách API Login trong Sprint 1?", "in_kb"),
    ("ĐôNT đã tốn bao nhiêu giờ ở Sprint 1?", "in_kb"),
    ("TùngDV có làm task nào Sprint 1 không?", "confident_no"),
    ("Issue management có bản ghi nào không?", "not_in_kb"),
    ("Những người có task trong Sprint đầu tiên là ai?", "in_kb"),
    ("Sprint đầu tiên bắt đầu ngày nào?", "in_kb"),
    ("Tổng số task của Sprint 1 là bao nhiêu?", "in_kb"),
    ("Re-est của Sprint 1 là bao nhiêu giờ?", "in_kb"),
]


def main() -> int:
    failures = []
    env = os.environ.copy()
    env.setdefault("PROJECT_KNOWLEDGE_ACTOR", "local-demo")
    env.setdefault("PROJECT_KNOWLEDGE_ROLES", "project_member")
    env.setdefault("PROJECT_KNOWLEDGE_DEMO_MODE", "1")
    env.setdefault(
        "PROJECT_KNOWLEDGE_COVERAGE_GRANTS",
        '{"Đô":["project_knowledge:approve_coverage"]}',
    )
    env.setdefault(
        "PROJECT_KNOWLEDGE_APPROVAL_IDS",
        "nexus-demo-person-role-20260803,nexus-demo-person-task-20260803",
    )
    for query, expected in CASES:
        proc = subprocess.run(
            [sys.executable, str(RUN), "--project", "nexus", "--query", query, "--no-cache"],
            cwd=ROOT, text=True, capture_output=True, check=False,
            encoding="utf-8",
            env=env,
        )
        try:
            result = json.loads(proc.stdout)
            actual = result.get("status")
        except json.JSONDecodeError:
            actual = "invalid_json"
        if proc.returncode != 0 or actual != expected:
            failures.append((query, expected, actual, proc.stderr.strip()))
        else:
            print(f"✓ {expected:14s} {query}")
    if failures:
        for query, expected, actual, stderr in failures:
            print(f"✗ expected={expected} actual={actual}: {query}", file=sys.stderr)
            if stderr:
                print(stderr, file=sys.stderr)
        return 1
    print(f"✓ project-knowledge smoke test: {len(CASES)}/{len(CASES)} qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
