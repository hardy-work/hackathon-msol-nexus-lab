#!/usr/bin/env python3
"""Chấm độ phủ theo sheet/cột và các giới hạn dữ liệu của Nexus."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "scripts/run.py"
SUITE = ROOT / "questions_coverage.json"
sys.path.insert(0, str(ROOT / "scripts"))
from response_style import check_style  # noqa: E402


def main() -> int:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    env = os.environ.copy()
    env.setdefault("PROJECT_KNOWLEDGE_COVERAGE_GRANTS",
                   '{"Đô":["project_knowledge:approve_coverage"]}')
    env.setdefault("PROJECT_KNOWLEDGE_APPROVAL_IDS",
                   "nexus-demo-person-role-20260803,nexus-demo-person-task-20260803")
    failures = []
    passed = 0
    for case in suite["questions"]:
        proc = subprocess.run(
            [sys.executable, str(RUN), "--project", "nexus", "--query", case["q"],
             "--actor", "coverage-eval", "--roles", "project_member", "--no-cache"],
            cwd=ROOT, text=True, capture_output=True, check=False, env=env,
        )
        try:
            got = json.loads(proc.stdout)
        except json.JSONDecodeError:
            got = {"status": "invalid_json", "answer": proc.stdout, "citations": []}
        want = case["expect"]
        problems = []
        if got.get("status") != want["status"]:
            problems.append(f"status={got.get('status')} want={want['status']}")
        answer = str(got.get("answer", ""))
        for value in want.get("contains", []):
            if str(value) not in answer:
                problems.append(f"answer thiếu {value!r}")
        citations = " ".join(str(c) for c in got.get("citations", []))
        for source in want.get("must_cite", []):
            if source not in citations:
                problems.append(f"citation thiếu {source!r}")
        if want.get("action_requires_approval"):
            actions = got.get("suggested_actions", [])
            if not actions or not all(a.get("requires_approval") is True for a in actions):
                problems.append("action proposal không yêu cầu approval")
        problems.extend(check_style(got.get("status", "error"), answer, got.get("citations", [])))
        if problems:
            failures.append((case["id"], case["q"], problems))
            print(f"✗ {case['id']} [{case['group']}] {'; '.join(problems)}")
        else:
            passed += 1
            print(f"✓ {case['id']} [{case['group']}] {got['status']}")
    print(f"\nCOVERAGE EVAL  {passed}/{len(suite['questions'])}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
