#!/usr/bin/env python3
"""Offline tests for automatic file identity and version registration."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import openpyxl
import yaml
from openpyxl.styles import PatternFill

import document_registry
import intake


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workbook(path: Path, value: str, styled: bool = False) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Plan"
    sheet["A1"] = "Task"
    sheet["B1"] = value
    if styled:
        sheet["A1"].fill = PatternFill(fill_type="solid", fgColor="FFFF00")
    book.save(path)


def write_registry(root: Path, original: Path, doc_id: str = "plan", version: int = 1) -> None:
    payload = {"documents": [{
        "doc_id": doc_id,
        "version": version,
        "original": original.relative_to(root).as_posix(),
        "kind": "xlsx",
        "sha256": digest(original),
        "status": "canonical",
        "current": True,
        "supersedes": None,
        "visibility": "internal",
        "extractor": "nexus",
        "raw_paths": ["raw/plan.md"],
    }]}
    (root / "documents.yml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-intake-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        current = root / "originals/plan.xlsx"
        formatted = root / "uploads/Plan.xlsx"
        updated = root / "uploads/Plan v2.xlsx"
        current.parent.mkdir(exist_ok=True)
        formatted.parent.mkdir(exist_ok=True)
        workbook(current, "old")
        workbook(formatted, "old", styled=True)
        workbook(updated, "new")
        write_registry(root, current)

        no_op = intake.decide(root, formatted)
        assert no_op["flow"] == "no_op"

        decision = intake.decide(root, updated)
        assert decision["flow"] == "reingest"
        assert decision["doc_id"] == "plan"
        assert decision["from_version"] == 1
        assert decision["to_version"] == 2
        registered = intake.register(root, updated, decision)
        assert registered["registered_original"] == "originals/plan@v2.xlsx"
        assert (root / registered["registered_original"]).exists()
        assert document_registry.current("plan", root)["version"] == 2
        assert document_registry.by_version("plan", 1, root)["current"] is False
        assert document_registry.by_version("plan", 2, root)["raw_paths"] == [
            "raw/plan@v2.md"
        ]
        assert intake.decide(root, updated)["flow"] == "duplicate"

    with tempfile.TemporaryDirectory(prefix="pk-intake-new-") as temp:
        root = Path(temp)
        (root / "originals").mkdir()
        source = root / "uploads/New Plan.xlsx"
        source.parent.mkdir()
        workbook(source, "first")
        (root / "documents.yml").write_text("documents: []\n", encoding="utf-8")
        decision = intake.decide(root, source)
        assert decision["flow"] == "initial_ingest"
        assert decision["version"] == 1
        intake.register(root, source, decision)
        assert document_registry.current("new-plan", root)["doc_id"] == "new-plan"
        assert document_registry.current("new-plan", root)["version"] == 1

    print("✓ intake self-test: 8/8 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
