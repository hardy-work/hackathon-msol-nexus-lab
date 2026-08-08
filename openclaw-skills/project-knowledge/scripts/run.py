#!/usr/bin/env python3
"""JSON CLI entrypoint backed by the long-lived-capable runtime engine.

stdout của tiến trình này LÀ hợp đồng: NexusBot và mọi evaluator đều `json.loads` nó.
Thư viện bên thứ ba không tôn trọng hợp đồng đó — `bm25s` in "resource module not
available on Windows" ra stdout ngay lúc import, đủ để mọi câu trả lời thành
`invalid_json` trên Windows dù retrieval hoàn toàn đúng. Không đoán trước được thư viện
nào sẽ in gì, nên chặn theo cơ chế: mọi thứ ghi stdout trong lúc import và lúc chạy đều
bị đẩy sang stderr; chỉ payload JSON cuối cùng được ghi ra stdout thật.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

_STDOUT = sys.stdout
with contextlib.redirect_stdout(sys.stderr):
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
        with contextlib.redirect_stdout(sys.stderr):
            payload = default_runtime().query(
                args.project, args.query, llm=use_llm, actor=args.actor, roles=args.roles,
                history=history, use_cache=not args.no_cache,
            )
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=_STDOUT)
    return {"error": 1, "forbidden": 3}.get(payload.get("status"), 0)


if __name__ == "__main__":
    raise SystemExit(main())
