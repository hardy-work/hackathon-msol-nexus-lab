#!/usr/bin/env python3
"""Curated, one-process Nexus Knowledge Base showcase.

The default path is deterministic and network-free. It exercises the same
long-lived runtime used by adapters while keeping the presentation compact.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def configure_demo_environment() -> None:
    """Provide explicit offline-demo authority without weakening production defaults."""
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    os.environ.setdefault("KNOWLEDGE_BASE_ACTOR", "local-demo")
    os.environ.setdefault("KNOWLEDGE_BASE_ROLES", "project_member")
    os.environ.setdefault("KNOWLEDGE_BASE_DEMO_MODE", "1")
    os.environ.setdefault("KNOWLEDGE_BASE_STATE_DIR", str(ROOT / ".runtime" / "demo"))
    os.environ.setdefault(
        "KNOWLEDGE_BASE_COVERAGE_GRANTS",
        json.dumps({"Đô": ["knowledge_base:approve_coverage"]}, ensure_ascii=False),
    )
    os.environ.setdefault(
        "KNOWLEDGE_BASE_APPROVAL_IDS",
        "nexus-demo-person-role-20260803,nexus-demo-person-task-20260803",
    )


# runtime_state resolves its database paths at import time, so configure first.
configure_demo_environment()
sys.path.insert(0, str(ROOT / "scripts"))

import versioning  # noqa: E402
from runtime_engine import KnowledgeRuntime  # noqa: E402


@dataclass(frozen=True)
class Scenario:
    title: str
    question: str
    expected_status: str
    purpose: str
    history: tuple[dict[str, str], ...] = field(default_factory=tuple)
    require_citations: bool = False
    require_route: str | None = None
    require_effective_query: bool = False
    require_proposal: bool = False


SCENARIOS = (
    Scenario(
        "Tra cứu dữ liệu có cấu trúc",
        "ĐôNT làm vai trò gì trong dự án Nexus?",
        "in_kb",
        "Trả lời trực tiếp từ facts, không cần LLM.",
        require_citations=True,
    ),
    Scenario(
        "Hiểu câu hỏi nối tiếp",
        "còn SơnBH thì sao?",
        "in_kb",
        "Khôi phục chủ đề từ lượt hỏi trước thay vì bắt người dùng lặp lại.",
        history=({"role": "user", "content": "ĐôNT làm vai trò gì?"},),
        require_citations=True,
        require_effective_query=True,
    ),
    Scenario(
        "Số liệu có provenance",
        "ĐôNT đã bỏ ra bao nhiêu giờ trong Sprint 1?",
        "in_kb",
        "Số chỉ được xuất bản khi Gate 4 truy ngược được đúng nguồn.",
        require_citations=True,
    ),
    Scenario(
        "Quan hệ nhiều bước qua graph",
        "Những người liên quan đến Authentication là ai?",
        "in_kb",
        "Duyệt quan hệ task–assignee thay vì suy đoán từ từ khóa.",
        require_citations=True,
        require_route="graph",
    ),
    Scenario(
        "Phủ định có chứng cứ",
        "TùngDV có task nào trong Sprint 1 không?",
        "confident_no",
        "Chỉ khẳng định không khi dimension đóng và coverage đã được duyệt.",
        require_citations=True,
    ),
    Scenario(
        "Kho biết rằng mình chưa biết",
        "Có issue nào trong Issue management không?",
        "not_in_kb",
        "Không biến dữ liệu trống/chưa được ký coverage thành kết luận không tồn tại.",
    ),
    Scenario(
        "Ranh giới write action",
        "Cập nhật task API Login sang Done",
        "not_in_kb",
        "Knowledge Base từ chối ghi và chỉ tạo proposal cần approval.",
        require_proposal=True,
    ),
)


def validate(scenario: Scenario, payload: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if payload.get("status") != scenario.expected_status:
        problems.append(
            f"status={payload.get('status')!r}, expected={scenario.expected_status!r}"
        )
    if scenario.require_citations and not payload.get("citations"):
        problems.append("thiếu citation")
    if scenario.require_route and (payload.get("route") or {}).get("name") != scenario.require_route:
        problems.append(f"route không phải {scenario.require_route!r}")
    if scenario.require_effective_query and not payload.get("effective_query"):
        problems.append("follow-up chưa tạo effective_query")
    if scenario.require_proposal:
        proposals = payload.get("suggested_actions") or []
        if not proposals:
            problems.append("write request chưa tạo proposal")
        elif not proposals[0].get("requires_approval"):
            problems.append("proposal không yêu cầu approval")
    return problems


def run_showcase(*, use_cache: bool = True) -> dict[str, Any]:
    freshness = versioning.check(ROOT)
    if freshness.get("state") != "fresh":
        return {
            "ok": False,
            "freshness": freshness,
            "cases": [],
            "errors": ["Corpus chưa fresh; chạy bash scripts/run_all.sh trước khi demo."],
        }

    runtime = KnowledgeRuntime()
    cases: list[dict[str, Any]] = []
    all_errors: list[str] = []
    for index, scenario in enumerate(SCENARIOS, start=1):
        started = time.perf_counter()
        payload = runtime.query(
            "nexus",
            scenario.question,
            actor=os.environ["KNOWLEDGE_BASE_ACTOR"],
            roles=os.environ["KNOWLEDGE_BASE_ROLES"],
            history=list(scenario.history),
            use_cache=use_cache,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        problems = validate(scenario, payload)
        all_errors.extend(f"Bước {index}: {problem}" for problem in problems)
        cases.append(
            {
                "index": index,
                "title": scenario.title,
                "purpose": scenario.purpose,
                "question": scenario.question,
                "expected_status": scenario.expected_status,
                "elapsed_ms": elapsed_ms,
                "passed": not problems,
                "problems": problems,
                "result": payload,
            }
        )
    return {
        "ok": not all_errors,
        "mode": "deterministic-offline",
        "project": "nexus",
        "freshness": freshness,
        "cases": cases,
        "errors": all_errors,
    }


def compact_citations(citations: list[str], limit: int = 3) -> str:
    shown = citations[:limit]
    suffix = f" (+{len(citations) - limit} nguồn)" if len(citations) > limit else ""
    return "; ".join(shown) + suffix


def print_human(report: dict[str, Any]) -> None:
    freshness = report.get("freshness") or {}
    print("NEXUS · KNOWLEDGE BASE SHOWCASE")
    print(
        f"Corpus: {freshness.get('version') or 'unknown'} · "
        f"freshness={freshness.get('state', 'unknown')} · "
        f"as_of={freshness.get('as_of') or 'unknown'}"
    )
    print("Runtime: deterministic, offline, one process")

    for case in report.get("cases", []):
        result = case["result"]
        route = (result.get("route") or {}).get("name")
        meta = [
            result.get("status", "unknown"),
            result.get("confidence", "none"),
            f"tier {result.get('tier', 0)}",
            f"{case['elapsed_ms']:.2f} ms",
        ]
        if route:
            meta.append(f"route {route}")
        if result.get("cache_hit"):
            meta.append("cache hit")

        print(f"\n[{case['index']}/{len(report['cases'])}] {case['title']}")
        print(f"Mục đích: {case['purpose']}")
        print(f"Hỏi: {case['question']}")
        if result.get("effective_query"):
            print(f"Hiểu thành: {result['effective_query']}")
        print(f"Trả lời: {result.get('answer', '')}")
        print("Kết quả: " + " · ".join(meta))
        citations = result.get("citations") or []
        if citations:
            print("Nguồn: " + compact_citations(citations))
        proposals = result.get("suggested_actions") or []
        if proposals:
            proposal = proposals[0]
            print(
                "Proposal: "
                f"{proposal.get('status')} · requires_approval={proposal.get('requires_approval')} · "
                f"permission={proposal.get('required_permission')}"
            )
        if case["problems"]:
            print("LỖI CONTRACT: " + "; ".join(case["problems"]))

    passed = sum(case["passed"] for case in report.get("cases", []))
    print(f"\nSHOWCASE CONTRACT: {passed}/{len(report.get('cases', []))} bước đạt")
    for error in report.get("errors", []):
        print(f"- {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the curated Nexus LLM Wiki showcase")
    parser.add_argument("--json", action="store_true", help="in một JSON report thay cho output trình bày")
    parser.add_argument("--check", action="store_true", help="chỉ in kết quả contract để dùng trong CI/self-test")
    parser.add_argument("--no-cache", action="store_true", help="bỏ query cache khi đo showcase")
    args = parser.parse_args()

    report = run_showcase(use_cache=not args.no_cache)
    if args.check:
        passed = sum(case["passed"] for case in report.get("cases", []))
        marker = "✓" if report.get("ok") else "✗"
        print(f"{marker} showcase contract: {passed}/{len(report.get('cases', []))} bước đạt")
        for error in report.get("errors", []):
            print(f"- {error}")
    elif args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
