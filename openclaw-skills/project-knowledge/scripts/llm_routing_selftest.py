#!/usr/bin/env python3
"""Live demo contract for Haiku routing followed by Sonnet synthesis.

This is intentionally opt-in because it calls the configured Claude runtime.
The offline test suite covers the deterministic fallback contract separately;
when ``PROJECT_KNOWLEDGE_LLM=1`` is set for the demo, this check must prove that
the real Haiku route and tier-3 answer both ran.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402


QUESTION = (
    "Đánh giá cách Nexus Plan tổ chức thông tin và nêu điểm nổi bật cùng hạn chế; "
    "chỉ dùng câu chữ, không tự tạo hoặc tính bất kỳ con số nào."
)


def main() -> int:
    claude = models.CLAUDE
    if not Path(claude).exists() and shutil.which(claude) is None:
        print(f"✗ không tìm thấy Claude runtime: {claude}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env.update({
        "PROJECT_KNOWLEDGE_LLM": "1",
        "PROJECT_KNOWLEDGE_ACTOR": env.get("PROJECT_KNOWLEDGE_ACTOR", "local-demo"),
        "PROJECT_KNOWLEDGE_ROLES": env.get("PROJECT_KNOWLEDGE_ROLES", "project_member"),
        "PROJECT_KNOWLEDGE_DEMO_MODE": env.get("PROJECT_KNOWLEDGE_DEMO_MODE", "1"),
    })
    command = [
        sys.executable, str(ROOT / "scripts/run.py"),
        "--project", "nexus", "--query", QUESTION,
        "--actor", env["PROJECT_KNOWLEDGE_ACTOR"],
        "--roles", env["PROJECT_KNOWLEDGE_ROLES"],
        "--no-cache",
    ]
    try:
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=180)
    except subprocess.TimeoutExpired:
        print("✗ Haiku/Sonnet demo timeout (>180s)", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        print(proc.stdout, end="")
        print(proc.stderr, file=sys.stderr, end="")
        return 1
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"✗ run.py không trả JSON hợp lệ: {exc}", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        return 1

    route = payload.get("route") or {}
    errors = []
    if route.get("source") != "haiku":
        detail = f"; error={route.get('error')}" if route.get("error") else ""
        errors.append(f"router source={route.get('source')!r}, cần 'haiku'{detail}")
    if route.get("name") not in {"document", "semantic", "open", "graph"}:
        errors.append(f"route={route.get('name')!r} không phải retrieval route")
    if payload.get("tier") != 3:
        errors.append(f"tier={payload.get('tier')!r}, cần tier 3 Sonnet")
    if not payload.get("citations"):
        errors.append("tier 3 thiếu citation")
    if errors:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("✗ LLM routing self-test: " + "; ".join(errors), file=sys.stderr)
        return 1

    print(json.dumps({
        "ok": True,
        "models": {"router": models.CHEAP, "answer": models.LIGHT},
        "route": route,
        "tier": payload["tier"],
        "status": payload.get("status"),
        "citations": payload.get("citations"),
    }, ensure_ascii=False, indent=2))
    print("✓ LLM routing self-test: Haiku → retrieval → Sonnet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
