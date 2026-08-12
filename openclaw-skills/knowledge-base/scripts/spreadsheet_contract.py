#!/usr/bin/env python3
"""Deterministic completeness contract for generic XLSX ingest.

Generic spreadsheet pages are copied from an extracted raw artifact; no LLM
authors their prose.  This gate proves the copy is complete before such a page
may skip semantic Gate 3b.  It fails closed on a missing/extra cell, changed
formula/value, registry hash drift, or a raw/wiki body mismatch.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_paths  # noqa: E402
import document_registry  # noqa: E402
import markdown_source  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "knowledge-base/spreadsheet-completeness/v1"


def _normal(value: Any) -> Any:
    """Normalize JSON/openpyxl scalar differences without weakening equality."""
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _facts_cells(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for sheet in payload.get("sheets") or []:
        sheet_name = str(sheet.get("sheet") or "")
        if not sheet_name:
            raise ValueError("facts spreadsheet thiếu tên sheet")
        for row in sheet.get("rows") or []:
            for item in (row.get("cells") or {}).values():
                source = str(item.get("src") or "")
                if not source or not source.startswith(f"{sheet_name}!"):
                    raise ValueError(f"facts cell có source locator sai: {source!r}")
                if source in cells:
                    raise ValueError(f"facts khai trùng cell: {source}")
                cells[source] = {
                    "value": _normal(item.get("value")),
                    "formula": item.get("formula"),
                }
    return cells


def _review_cells(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for sheet in (payload.get("workbook") or {}).get("sheets") or []:
        for item in sheet.get("cells") or []:
            source = str(item.get("source") or "")
            if not source:
                raise ValueError("review artifact có cell thiếu source locator")
            if source in cells:
                raise ValueError(f"review artifact khai trùng cell: {source}")
            cells[source] = {
                "value": _normal(item.get("value")),
                "formula": item.get("formula"),
            }
    return cells


def _compare_cells(facts: dict[str, dict[str, Any]],
                   review: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    missing = sorted(set(review) - set(facts))
    extra = sorted(set(facts) - set(review))
    if missing:
        errors.append(f"facts thiếu {len(missing)} cell: {missing[:8]}")
    if extra:
        errors.append(f"facts thừa {len(extra)} cell: {extra[:8]}")
    for source in sorted(set(facts) & set(review)):
        actual = facts[source]
        expected = review[source]
        if actual.get("formula") != expected.get("formula"):
            errors.append(f"formula lệch tại {source}")
            continue
        # A formula without a cached value is represented as the formula text
        # by the raw extractor and as null + formula by the review artifact.
        # Formula equality already proves that cell in this case.
        if expected.get("formula") and expected.get("value") in (None, ""):
            continue
        if str(actual.get("value")) != str(expected.get("value")):
            errors.append(
                f"giá trị lệch tại {source}: facts={actual.get('value')!r} "
                f"review={expected.get('value')!r}"
            )
        if len(errors) >= 20:
            errors.append("dừng sau 20 sai lệch")
            break
    return errors


def is_deterministic_source_page(root: Path, relative: str,
                                 doc_id: str | None = None) -> bool:
    """Return whether a page is the exact machine-generated spreadsheet source."""
    path = root / relative
    if not path.is_file():
        return False
    try:
        metadata, _ = markdown_source.parse(path)
    except (OSError, ValueError):
        return False
    if metadata.get("page") != "source":
        return False
    page_doc_id = str(metadata.get("doc_id") or "")
    if not page_doc_id or (doc_id and page_doc_id != str(doc_id)):
        return False
    if relative != f"wiki/sources/{page_doc_id}.md":
        return False
    try:
        document = document_registry.by_version(
            page_doc_id, int(metadata.get("version")), root
        )
    except (KeyError, TypeError, ValueError):
        return False
    return (
        document.get("extractor") == "spreadsheet"
        and metadata.get("generated_by") == "scripts/ingest_spreadsheet.py"
    )


def validate(root: Path, doc_id: str, *, version: int | None = None,
             review_artifact_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    document = (
        document_registry.by_version(doc_id, version, root)
        if version is not None else document_registry.current(doc_id, root)
    )
    if document.get("extractor") != "spreadsheet":
        raise ValueError(f"{doc_id} không dùng generic spreadsheet extractor")

    original = root / str(document["original"])
    actual_source_hash = document_registry.sha256(original)
    if actual_source_hash != document.get("sha256"):
        raise ValueError("original SHA-256 lệch documents.yml")

    raw_path = artifact_paths.artifact_path(root, document, doc_id, "md")
    facts_path = artifact_paths.artifact_path(root, document, doc_id, "facts")
    page_path = root / "wiki" / "sources" / f"{doc_id}.md"
    for required in (raw_path, facts_path, page_path):
        if not required.is_file():
            raise ValueError(f"thiếu spreadsheet artifact: {required.relative_to(root)}")

    raw_metadata, raw_body = markdown_source.parse(raw_path)
    page_metadata, page_body = markdown_source.parse(page_path)
    if raw_metadata.get("doc_id") != doc_id:
        raise ValueError("raw frontmatter sai doc_id")
    if int(raw_metadata.get("version", 0)) != int(document["version"]):
        raise ValueError("raw frontmatter sai version")
    if not is_deterministic_source_page(
        root, page_path.relative_to(root).as_posix(), doc_id
    ):
        raise ValueError("wiki page không phải deterministic spreadsheet source")
    if page_metadata.get("raw_paths") != [raw_path.relative_to(root).as_posix()]:
        raise ValueError("wiki page không trỏ đúng một raw spreadsheet hiện tại")
    if raw_body != page_body:
        raise ValueError("wiki source body không byte-equivalent với raw body")

    facts_payload = json.loads(facts_path.read_text(encoding="utf-8"))
    if facts_payload.get("doc_id") != doc_id:
        raise ValueError("facts JSON sai doc_id")
    if int(facts_payload.get("version", 0)) != int(document["version"]):
        raise ValueError("facts JSON sai version")
    facts = _facts_cells(facts_payload)
    if not facts:
        raise ValueError("spreadsheet không có cell nào sau extraction")

    review_count = None
    if review_artifact_path is not None:
        review_payload = json.loads(review_artifact_path.read_text(encoding="utf-8"))
        review_source = review_payload.get("source") or {}
        if review_source.get("sha256") != actual_source_hash:
            raise ValueError("review artifact không cùng SHA-256 với original đã đăng ký")
        review = _review_cells(review_payload)
        errors = _compare_cells(facts, review)
        if errors:
            raise ValueError("; ".join(errors))
        review_count = len(review)

    return {
        "schema": SCHEMA,
        "status": "pass",
        "doc_id": doc_id,
        "version": int(document["version"]),
        "source_sha256": actual_source_hash,
        "cell_count": len(facts),
        "review_cell_count": review_count,
        "raw_path": raw_path.relative_to(root).as_posix(),
        "page_path": page_path.relative_to(root).as_posix(),
        "gate3b_policy": "deterministic-source-contract",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate generic XLSX completeness")
    parser.add_argument("--doc", required=True)
    parser.add_argument("--version", type=int)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--review-artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(
            args.root, args.doc, version=args.version,
            review_artifact_path=args.review_artifact,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"✗ spreadsheet completeness: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
