#!/usr/bin/env python3
"""Offline regression tests for document versioning and re-ingest planning."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import yaml

import document_registry
import reingest


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-lifecycle-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "wiki/sources").mkdir(parents=True)
        old_original, new_original = b"old", b"new"
        (root / "originals/plan-v1.docx").write_bytes(old_original)
        (root / "originals/plan-v2.docx").write_bytes(new_original)
        (root / "raw/plan@v1.md").write_text(
            "---\nraw_id: plan\ndoc_id: plan\nversion: 1\n---\nold line\n", encoding="utf-8")
        (root / "raw/plan@v2.md").write_text(
            "---\nraw_id: plan\ndoc_id: plan\nversion: 2\n---\nnew line\n", encoding="utf-8")
        (root / "raw/plan@v1.facts.json").write_text('{"value": "old"}\n', encoding="utf-8")
        (root / "raw/plan@v2.facts.json").write_text('{"value": "new"}\n', encoding="utf-8")
        (root / "wiki/sources/plan.md").write_text(
            "---\npage: source\ndoc_id: plan\nversion: 1\nraw_paths: [raw/plan@v1.md]\n---\n", encoding="utf-8")
        registry = {"documents": [
            {"doc_id": "plan", "version": 1, "original": "originals/plan-v1.docx",
             "sha256": digest(old_original), "current": False,
             "raw_paths": ["raw/plan@v1.md", "raw/plan@v1.facts.json"]},
            {"doc_id": "plan", "version": 2, "original": "originals/plan-v2.docx",
             "sha256": digest(new_original), "current": True, "supersedes": 1,
             "raw_paths": ["raw/plan@v2.md", "raw/plan@v2.facts.json"]},
        ]}
        (root / "documents.yml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        assert document_registry.current("plan", root)["version"] == 2
        plan = reingest.build_plan(root, "plan", 1, 2)
        assert len(plan["raw_diff"]) == 2
        assert {row["artifact"] for row in plan["raw_diff"]} == {"plan::md", "plan::facts"}
        assert plan["impacted_pages"][0]["strategy"] == "supersede_page"
        assert plan["branch"] == "ingest/plan@v2"
        archived = reingest.archive_one_to_one_pages(root, plan)
        assert archived == [{
            "old_page": "wiki/sources/plan.md",
            "archived_page": "wiki/sources/plan@v1.md",
            "superseded_by": "wiki/sources/plan.md",
        }]
        assert not (root / "wiki/sources/plan.md").exists()
        archived_text = (root / "wiki/sources/plan@v1.md").read_text(encoding="utf-8")
        assert "superseded_by: wiki/sources/plan.md" in archived_text

        decision = document_registry.classify_intake("plan", root)
        assert decision["flow"] == "reingest"
        assert decision["from_version"] == 2
        assert decision["to_version"] == 3

        new_decision = document_registry.classify_intake("new-plan", root)
        assert new_decision == {
            "flow": "initial_ingest",
            "doc_id": "new-plan",
            "version": 1,
            "reason": "doc_id chưa có trong documents.yml",
        }

        broken_root = root / "broken"
        broken_root.mkdir()
        (broken_root / "originals").mkdir()
        broken_original = b"v2-only"
        (broken_root / "originals/plan-v2.docx").write_bytes(broken_original)
        (broken_root / "documents.yml").write_text(
            yaml.safe_dump({"documents": [
                {"doc_id": "broken", "version": 2,
                 "original": "originals/plan-v2.docx",
                 "sha256": digest(broken_original), "current": True},
            ]}, sort_keys=False), encoding="utf-8")
        try:
            document_registry.classify_intake("broken", broken_root)
        except ValueError as exc:
            assert "version 1" in str(exc)
        else:
            raise AssertionError("registry thiếu v1 không được vào re-ingest")
        try:
            reingest.build_plan(broken_root, "broken", 2, 3)
        except ValueError as exc:
            assert "version 1" in str(exc)
        else:
            raise AssertionError("re-ingest plan phải chặn registry thiếu v1")
    print("✓ lifecycle self-test: 8/8 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
