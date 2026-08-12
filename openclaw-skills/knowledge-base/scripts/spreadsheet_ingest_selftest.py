#!/usr/bin/env python3
"""Offline test for generic XLSX -> raw -> source wiki page lane."""
from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
from pathlib import Path

import openpyxl
import yaml

import document_registry
import extract_spreadsheet
import ingest_flow
import ingest_spreadsheet
import numeric_guard
import review_artifact
import spreadsheet_contract


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_dimensions(source: Path, target: Path) -> None:
    """Create a valid XLSX whose worksheet XML omits optional dimensions."""
    with zipfile.ZipFile(source) as input_zip, zipfile.ZipFile(
        target, "w"
    ) as output_zip:
        for info in input_zip.infolist():
            data = input_zip.read(info.filename)
            if (
                info.filename.startswith("xl/worksheets/")
                and info.filename.endswith(".xml")
            ):
                data = re.sub(rb"<dimension\b[^>]*/>", b"", data, count=1)
            output_zip.writestr(info, data)


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
        normal_source = root / "normal.xlsx"
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Data"
        sheet["A1"] = "Task"
        sheet["B1"] = "Hours"
        sheet["A2"] = "NEX-1"
        sheet["B2"] = 12.5
        sheet["C2"] = "=B2*2"
        book.save(normal_source)
        without_dimensions(normal_source, source)
        with zipfile.ZipFile(source) as archive:
            worksheet_xml = archive.read("xl/worksheets/sheet1.xml")
            assert b"<dimension" not in worksheet_xml
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
        artifact = review_artifact.build(source, proposal_id="dimensionless")
        assert sum(len(item["cells"]) for item in artifact["workbook"]["sheets"]) == 5
        assert artifact["workbook"]["sheets"][0]["max_row"] == 2
        assert artifact["workbook"]["sheets"][0]["max_column"] == 3
        page = ingest_spreadsheet.ingest_one(root, document)
        assert page == root / "wiki/sources/upload.md"
        assert "raw/upload.md" in page.read_text(encoding="utf-8")
        bundle = review_artifact.write_bundle(
            artifact, root / ".runtime/review"
        )
        contract = spreadsheet_contract.validate(
            root, "upload", review_artifact_path=Path(bundle["json_path"])
        )
        assert contract["cell_count"] == 5
        assert contract["review_cell_count"] == 5
        assert contract["gate3b_policy"] == "deterministic-source-contract"

        original_page = page.read_text(encoding="utf-8")
        page.write_text(original_page + "invented\n", encoding="utf-8")
        try:
            spreadsheet_contract.validate(root, "upload")
        except ValueError as exc:
            assert "byte-equivalent" in str(exc)
        else:
            raise AssertionError("wiki body khác raw phải bị completeness gate chặn")
        page.write_text(original_page, encoding="utf-8")
        original_changed = ingest_flow.changed_wiki_pages
        original_run = ingest_flow.run
        try:
            ingest_flow.changed_wiki_pages = lambda _worktree, _skill: [
                "wiki/sources/upload.md"
            ]

            def unexpected_llm(*_args, **_kwargs):
                raise AssertionError("deterministic XLSX source không được gọi LLM review")

            ingest_flow.run = unexpected_llm
            ingest_flow.review_changed_pages(
                root, root, root / "scripts", "upload", 1
            )
        finally:
            ingest_flow.changed_wiki_pages = original_changed
            ingest_flow.run = original_run
        guard = numeric_guard.AnswerGuard(root)
        assert "12.5" in guard.by_page["wiki/sources/upload.md"]
        assert guard.check("12.5", cites=["wiki/sources/upload.md"]) == []
    print("✓ generic spreadsheet ingest self-test: xlsx → raw/facts → wiki qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
