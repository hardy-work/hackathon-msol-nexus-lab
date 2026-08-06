#!/usr/bin/env python3
"""JSON CLI entrypoint backed by the long-lived-capable runtime engine."""
from __future__ import annotations

import argparse
import json
import os

from runtime_engine import default_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Tra cứu Nexus Project Knowledge skill")
    parser.add_argument("--project", default="nexus")
    parser.add_argument("--query", required=True)
    llm = parser.add_mutually_exclusive_group()
    llm.add_argument("--llm", dest="llm", action="store_true",
                     help="bật Haiku router + Sonnet answer")
    llm.add_argument("--no-llm", dest="llm", action="store_false",
                     help="ép chạy deterministic, không gọi Claude")
    parser.set_defaults(llm=None)
    parser.add_argument("--actor", default=None)
    parser.add_argument("--roles", default=None)
    parser.add_argument("--history-json", default="[]")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    use_llm = args.llm
    if use_llm is None:
        use_llm = os.getenv("PROJECT_KNOWLEDGE_LLM", "0").lower() in {
            "1", "true", "yes", "on"
        }
    try:
        history = json.loads(args.history_json)
    except json.JSONDecodeError as exc:
        history = None
        payload = {"status": "error", "answer": "Conversation history không hợp lệ.",
                   "confidence": "none", "citations": [], "reason": str(exc),
                   "tier": 0, "project": args.project, "suggested_actions": []}
    else:
        payload = default_runtime().query(
            args.project, args.query, llm=use_llm, actor=args.actor, roles=args.roles,
            history=history, use_cache=not args.no_cache,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"error": 1, "forbidden": 3}.get(payload.get("status"), 0)


if __name__ == "__main__":
    raise SystemExit(main())
