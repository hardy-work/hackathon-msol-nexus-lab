#!/usr/bin/env python3
"""Local Slack bridge: JSON stdin -> Slack response JSON stdout."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from format_message import format_result
from parse_event import parse

SKILL_ROOT = next(parent for parent in Path(__file__).resolve().parents
                  if (parent / "scripts" / "run.py").exists())
RUN = SKILL_ROOT / "scripts" / "run.py"


def query_project(text: str, *, actor: str = "", roles: list[str] | None = None,
                  history: list[dict] | None = None) -> dict:
    use_llm = os.getenv("PROJECT_KNOWLEDGE_LLM", "0").lower() in {"1", "true", "yes", "on"}
    args = [sys.executable, str(RUN), "--project", "nexus", "--query", text]
    if actor:
        args.extend(["--actor", actor])
    if roles is not None:
        args.extend(["--roles", ",".join(roles)])
    if history:
        args.extend(["--history-json", json.dumps(history, ensure_ascii=False)])
    if use_llm:
        args.append("--llm")
    proc = subprocess.run(
        args,
        cwd=SKILL_ROOT, text=True, capture_output=True, check=False,
    )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = {"status": "error", "answer": "Skill không trả JSON hợp lệ.",
                  "confidence": "none", "citations": [], "reason": proc.stderr.strip(),
                  "tier": 0, "project": "nexus", "suggested_actions": []}
    return result


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"payload JSON không hợp lệ: {exc}"}, ensure_ascii=False))
        return 2

    event = parse(payload)
    if event["kind"] == "url_verification":
        print(json.dumps({"challenge": event["challenge"]}, ensure_ascii=False))
        return 0
    if event["kind"] in {"ignored", "empty"}:
        print(json.dumps({"response_type": "ephemeral", "text": event.get("reason", "Hãy nhập câu hỏi dự án."),
                          "metadata": {"status": "not_in_kb", "project": "nexus"}}, ensure_ascii=False))
        return 0

    result = query_project(event["text"])
    response = format_result(result, thread_ts=event.get("thread_ts", ""))
    response["metadata"].update({"channel_id": event.get("channel_id", ""),
                                  "user_id": event.get("user_id", ""),
                                  "event_ts": event.get("event_ts", "")})
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
