#!/usr/bin/env python3
"""Negative tests for Gate 3a historical page metadata."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import yaml

import lint


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-lint-history-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "wiki/sources").mkdir(parents=True)
        old_original = root / "originals/plan-v1.docx"
        new_original = root / "originals/plan-v2.docx"
        old_original.write_bytes(b"old")
        new_original.write_bytes(b"new")
        (root / "raw/plan@v1.md").write_text("---\ndoc_id: plan\nversion: 1\n---\nold\n", encoding="utf-8")
        (root / "raw/plan@v2.md").write_text("---\ndoc_id: plan\nversion: 2\n---\nnew\n", encoding="utf-8")
        (root / "wiki/sources/plan.md").write_text(
            "---\npage: source\nname: Plan\ndoc_id: plan\nversion: 2\n"
            "raw_paths: [raw/plan@v2.md]\n---\n", encoding="utf-8")
        (root / "wiki/sources/plan@v1.md").write_text(
            "---\npage: source\nname: Plan\ndoc_id: plan\nversion: 1\n"
            "raw_paths: [raw/plan@v1.md]\n---\n[[missing-page]]\n", encoding="utf-8")
        (root / "documents.yml").write_text(yaml.safe_dump({"documents": [
            {"doc_id": "plan", "version": 1, "original": "originals/plan-v1.docx",
             "sha256": sha256(old_original), "current": False, "raw_paths": ["raw/plan@v1.md"]},
            {"doc_id": "plan", "version": 2, "original": "originals/plan-v2.docx",
             "sha256": sha256(new_original), "current": True, "supersedes": 1,
             "raw_paths": ["raw/plan@v2.md"]},
        ]}, sort_keys=False), encoding="utf-8")

        lint.errors.clear()
        historical = lint.lint_history(root)
        messages = [message for _kind, _where, message in lint.errors]
        assert len(historical) == 1
        assert any("thiếu superseded_by" in message for message in messages)
        assert any("missing-page" in message for message in messages)

    lint.errors.clear()
    print("✓ Gate 3a history self-test: thiếu superseded_by/link gãy đều bị chặn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
