#!/usr/bin/env python3
"""Contract test for the boundary between query and upload skill routing.

OpenClaw owns the actual model-based skill selector.  This fixture documents
the deterministic signals that selector must preserve: an upload request with
an attachment goes to the ingest skill, a normal project question goes to the
query skill, and an ingest request without a file stops for the missing input.
It is deliberately not imported by the production gateway.
"""
from __future__ import annotations

from pathlib import Path

import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent
QUERY_SKILL = SKILLS_ROOT / "knowledge-base"
INGEST_SKILL = SKILL_DIR


def metadata(path: Path) -> dict:
    text = (path / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3, path
    payload = yaml.safe_load(parts[1]) or {}
    assert payload.get("name"), path
    assert payload.get("description"), path
    return payload


def route(text: str, has_attachment: bool) -> str:
    lowered = text.casefold()
    direct_ingest_terms = ("nạp", "nhập", "upload", "ingest")
    mutation_terms = ("thêm", "bổ sung", "cập nhật", "update", "sửa", "thay thế")
    knowledge_targets = (
        "file", "tài liệu", "dữ liệu", "wiki", "kb", "kho tri thức", "knowledge base")
    query_terms = ("ai ", "bao nhiêu", "khi nào", "task", "sprint", "role")
    wants_mutation = any(term in lowered for term in mutation_terms)
    has_knowledge_target = any(term in lowered for term in knowledge_targets)
    wants_ingest = (
        any(term in lowered for term in direct_ingest_terms)
        or (wants_mutation and has_knowledge_target)
    )
    wants_query = any(term in lowered for term in query_terms)
    if wants_ingest and has_attachment:
        return "knowledge-ingest"
    if wants_ingest and not has_attachment:
        return "missing_attachment"
    if wants_mutation and not has_knowledge_target:
        return "unknown"
    if wants_query:
        return "knowledge-base"
    return "unknown"


def main() -> int:
    query = metadata(QUERY_SKILL)
    ingest = metadata(INGEST_SKILL)
    assert query["name"] == "knowledge-base"
    assert ingest["name"] == "knowledge-ingest"
    assert "read-only" in query["description"]
    assert "allowlist" in ingest["description"]
    assert "isolated worktree" in ingest["description"]
    for trigger in ("thêm", "bổ sung", "cập nhật", "sửa", "thay thế"):
        assert trigger in ingest["description"], trigger

    cases = [
        ("@NexusBot nạp file Nexus Lab.xlsx vào Wiki", True,
         "knowledge-ingest"),
        ("@NexusBot upload tài liệu này", True,
         "knowledge-ingest"),
        ("@NexusBot thêm dữ liệu trong file này vào KB", True,
         "knowledge-ingest"),
        ("@NexusBot bổ sung tài liệu đính kèm vào wiki", True,
         "knowledge-ingest"),
        ("@NexusBot cập nhật tài liệu hiện có bằng file này", True,
         "knowledge-ingest"),
        ("@NexusBot sửa dữ liệu trong wiki theo Excel đính kèm", True,
         "knowledge-ingest"),
        ("@NexusBot thay thế tài liệu cũ bằng bản PDF này", True,
         "knowledge-ingest"),
        ("Ai phụ trách API Login trong Sprint 1?", False,
         "knowledge-base"),
        ("ĐôNT đã tốn bao nhiêu giờ ở Sprint 1?", False,
         "knowledge-base"),
        ("@NexusBot nạp tài liệu mới vào Wiki", False,
         "missing_attachment"),
        ("@NexusBot cập nhật dữ liệu trong KB", False,
         "missing_attachment"),
        ("@NexusBot sửa task NEX-12", False,
         "unknown"),
    ]
    for text, has_attachment, expected in cases:
        actual = route(text, has_attachment)
        assert actual == expected, (text, actual, expected)
        print(f"✓ {expected:26s} {text}")
    print(f"✓ skill routing contract: {len(cases)}/{len(cases)} qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
