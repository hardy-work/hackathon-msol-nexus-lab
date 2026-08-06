#!/usr/bin/env python3
"""Offline test for generic XLSX -> raw -> source wiki page lane."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import openpyxl
import yaml

import document_registry
import extract_spreadsheet
import ingest_spreadsheet
import numeric_guard


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-spreadsheet-") as temp:
        root = Path(temp)
        for directory in ("originals", "raw", "wiki/sources", "wiki/entities"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "schema.yml").write_text(yaml.safe_dump({
            "dimensions": {"domain": {"values": ["nexus"]}},
        }, sort_keys=False), encoding="utf-8")
        (root / "coverage.yml").write_text("[]\n", encoding="utf-8")
        source = root / "originals/upload.xlsx"
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Data"
        sheet["A1"] = "Task"
        sheet["B1"] = "Hours"
        sheet["A2"] = "NEX-1"
        sheet["B2"] = 12.5
        sheet["C2"] = "=B2*2"
        book.save(source)
        (root / "documents.yml").write_text(yaml.safe_dump({"documents": [{
            "doc_id": "upload", "version": 1,
            "original": "originals/upload.xlsx", "source_name": "upload.xlsx",
            "kind": "xlsx", "sha256": digest(source), "status": "canonical",
            "current": True, "supersedes": None, "visibility": "internal",
            "extractor": "spreadsheet", "raw_paths": ["raw/upload.md"],
        }]}, sort_keys=False), encoding="utf-8")
        document = document_registry.current("upload", root)
        raw, facts, cells = extract_spreadsheet.extract_one(root, document)
        assert raw == root / "raw/upload.md"
        assert facts == root / "raw/upload.facts.json"
        assert cells == 5
        raw_text = raw.read_text(encoding="utf-8")
        assert "Data!B2" in raw_text and "NEX-1" in raw_text
        assert "Data!C2==B2*2 [formula: =B2*2]" in raw_text
        facts_text = facts.read_text(encoding="utf-8")
        assert '"doc_id": "upload"' in facts_text
        page = ingest_spreadsheet.ingest_one(root, document)
        assert page == root / "wiki/sources/upload.md"
        assert "raw/upload.md" in page.read_text(encoding="utf-8")
        guard = numeric_guard.AnswerGuard(root)
        assert "12.5" in guard.by_page["wiki/sources/upload.md"]
        assert guard.check("12.5", cites=["wiki/sources/upload.md"]) == []
    print("✓ generic spreadsheet ingest self-test: xlsx → raw/facts → wiki qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
