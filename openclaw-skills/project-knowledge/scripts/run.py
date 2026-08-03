#!/usr/bin/env python3
"""JSON entrypoint for the Nexus project-knowledge skill demo."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        # The skill is self-contained under openclaw-skills/project-knowledge.
        # Locate it from this file instead of assuming the monorepo root or the
        # caller's current working directory.
        if (parent / "scripts" / "answer.py").exists():
            return parent
    raise RuntimeError("không tìm thấy skill root có scripts/answer.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tra cứu Nexus Project Knowledge skill")
    parser.add_argument("--project", default="nexus", help="project id, demo hiện hỗ trợ nexus")
    parser.add_argument("--query", required=True, help="câu hỏi cần tra cứu")
    parser.add_argument("--llm", action="store_true",
                        help="bật Haiku router và bậc Sonnet cho câu hỏi mở")
    args = parser.parse_args()

    if args.project.lower() != "nexus":
        payload = {
            "status": "error",
            "answer": "Demo hiện chỉ hỗ trợ project nexus.",
            "confidence": "none",
            "citations": [],
            "reason": "project chưa có corpus hoặc adapter tương ứng.",
            "tier": 0,
            "project": args.project,
            "suggested_actions": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    root = repo_root()
    sys.path.insert(0, str(root / "scripts"))
    try:
        import answer

        kb = answer.KB()
        result = answer.ask(kb, args.query, llm=args.llm)
        status = {
            answer.CO: "in_kb",
            answer.NO: "confident_no",
            answer.NF: "not_in_kb",
        }.get(result.outcome, "error")
        confidence = {
            "in_kb": "high" if result.tier == 1 else "medium",
            "confident_no": "high",
            "not_in_kb": "none",
            "error": "none",
        }[status]
        payload = {
            "status": status,
            "answer": result.answer,
            "confidence": confidence,
            "citations": list(result.cites),
            "reason": result.reason,
            "tier": result.tier,
            "project": args.project,
            "suggested_actions": suggested_actions(args.query, status, result.cites),
        }
        freshness = getattr(kb, "freshness", None)
        if freshness is not None:
            payload["freshness"] = freshness
            payload["knowledge_version"] = freshness.get("version")
            payload["knowledge_as_of"] = freshness.get("as_of")
            if freshness.get("state") == "stale":
                warning = "Dữ liệu dẫn xuất có thể đã cũ; hãy chạy scripts/run_all.sh trước khi demo."
                payload["reason"] = f"{payload['reason']} {warning}".strip()
            elif freshness.get("state") == "unknown":
                warning = "Chưa xác nhận freshness của dữ liệu; hãy chạy scripts/run_all.sh trước khi demo."
                payload["reason"] = f"{payload['reason']} {warning}".strip()
        # Route telemetry is optional: deterministic Tier 1 answers do not need
        # a model call, while unresolved queries expose how the cheap router
        # selected the next retrieval tier.  Keep it machine-readable for Slack
        # and later audit/latency evaluation.
        if result.route is not None:
            payload["route"] = {
                "name": result.route.route,
                "confidence": result.route.confidence,
                "source": result.route.source,
                "reason": result.route.reason,
            }
    except Exception as exc:  # keep the agent contract machine-readable
        payload = {
            "status": "error",
            "answer": "Không thể truy vấn project knowledge.",
            "confidence": "none",
            "citations": [],
            "reason": f"{type(exc).__name__}: {exc}",
            "tier": 0,
            "project": args.project,
            "suggested_actions": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status != "error" else 1


def suggested_actions(query: str, status: str, citations: list[str]) -> list[dict[str, object]]:
    """Return proposals only; this skill never performs a write action."""
    if not re.search(r"\b(cập nhật|sửa|ghi|log|tạo|đổi|update|create)\b", query, re.I):
        return []
    return [{
        "type": "project_action",
        "status": "proposed",
        "requires_approval": True,
        "required_permission": "project_action:write",
        "approval_flow": "external_action_skill",
        "description": "Chuyển yêu cầu ghi/cập nhật sang action skill có permission; Project Knowledge không tự thay đổi dữ liệu.",
        "request": query,
        "context_status": status,
        "context_citations": list(citations),
    }]


if __name__ == "__main__":
    raise SystemExit(main())
