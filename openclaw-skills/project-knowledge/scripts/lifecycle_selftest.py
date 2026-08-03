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
        (root / "wiki/sources/plan.md").write_text(
            "---\npage: source\nraw_paths: [raw/plan@v1.md]\n---\n", encoding="utf-8")
        registry = {"documents": [
            {"doc_id": "plan", "version": 1, "original": "originals/plan-v1.docx",
             "sha256": digest(old_original), "current": False, "raw_paths": ["raw/plan@v1.md"]},
            {"doc_id": "plan", "version": 2, "original": "originals/plan-v2.docx",
             "sha256": digest(new_original), "current": True, "supersedes": 1,
             "raw_paths": ["raw/plan@v2.md"]},
        ]}
        (root / "documents.yml").write_text(
            yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
        assert document_registry.current("plan", root)["version"] == 2
        plan = reingest.build_plan(root, "plan", 1, 2)
        assert len(plan["raw_diff"]) == 1
        assert plan["impacted_pages"][0]["strategy"] == "supersede_page"
        assert plan["branch"] == "ingest/plan@v2"
    print("✓ lifecycle self-test: 4/4 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
