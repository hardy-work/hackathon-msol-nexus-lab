#!/usr/bin/env python3
"""Evaluate representative PM/new-developer onboarding questions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from runtime_engine import KnowledgeRuntime

ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    suite = json.loads((ROOT / "questions_onboarding.json").read_text(encoding="utf-8"))
    local = ROOT / "questions_onboarding.local.json"
    if local.exists():
        local_suite = json.loads(local.read_text(encoding="utf-8"))
        suite["questions"].extend(local_suite.get("questions", []))
    runtime = KnowledgeRuntime()
    failures = []
    for case in suite["questions"]:
        result = runtime.query("nexus", case["q"], actor="onboarding-eval",
                               roles=["project_member"], use_cache=False)
        want = case["expect"]
        errors = []
        if result["status"] != want["status"]:
            errors.append(f"status={result['status']} != {want['status']}")
        blob = result.get("answer", "") + "\n" + "\n".join(result.get("citations", []))
        for value in want.get("contains", []):
            if value not in blob:
                errors.append(f"missing {value!r}")
        for value in want.get("must_cite", []):
            if not any(value in cite for cite in result.get("citations", [])):
                errors.append(f"missing citation {value!r}")
        if want.get("action_requires_approval") and not any(
                action.get("requires_approval") for action in result.get("suggested_actions", [])):
            errors.append("missing approval proposal")
        print(f"{'✓' if not errors else '✗'} {case['id']} [{case['persona']}] {result['status']}")
        failures.extend(f"{case['id']}: {error}" for error in errors)
    if failures:
        print("\n" + "\n".join(failures))
        return 1
    print(f"\nONBOARDING EVAL  {len(suite['questions'])}/{len(suite['questions'])}")
    return 0


if __name__ == "__main__":
    # Reuse demo approval authority so signed-negative behavior remains stable.
    os.environ.setdefault("PROJECT_KNOWLEDGE_COVERAGE_GRANTS",
                          '{"Đô":["project_knowledge:approve_coverage"]}')
    os.environ.setdefault("PROJECT_KNOWLEDGE_APPROVAL_IDS",
                          "nexus-demo-person-role-20260803,nexus-demo-person-task-20260803")
    raise SystemExit(main())
