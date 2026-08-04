#!/usr/bin/env python3
"""Identify and register an incoming source document without overwriting history.

The command is the Stage 0/1 boundary for file uploads.  It first produces an
immutable decision from the incoming file and the human-owned registry, then
optionally applies that decision to a staging root/worktree with ``--apply``.
It never merges or publishes a worktree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

import document_registry
from inventory import kind as detect_kind
from inventory import normalized_name

ROOT = Path(__file__).resolve().parent.parent
VERSION_SUFFIX = re.compile(r"(?:[@._-](?:v|version)\d+)$", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity_name(path: Path) -> str:
    """Normalize a filename while ignoring a version suffix."""
    value = normalized_name(path)
    return re.sub(r"-(?:v|version)\d+$", "", value, flags=re.IGNORECASE)


def file_kind(path: Path) -> str:
    return detect_kind(path, path.read_bytes()[:16])


def _json_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def semantic_digest(path: Path) -> str:
    """Hash semantic workbook cells, ignoring formatting-only changes."""
    if path.suffix.lower() != ".xlsx":
        return sha256(path)

    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=False, read_only=True)
    sheets = []
    try:
        for worksheet in workbook.worksheets:
            cells = []
            for row in worksheet.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cells.append([cell.coordinate, _json_value(cell.value)])
            sheets.append({"title": worksheet.title, "cells": cells})
    finally:
        workbook.close()
    payload = json.dumps(sheets, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _registered_kind(root: Path, document: dict[str, Any]) -> str:
    if document.get("kind"):
        return str(document["kind"])
    return file_kind(root / str(document["original"]))


def _versioned_path(path: str, version: int) -> str:
    source = Path(path)
    name = source.name
    if name.endswith(".facts.json"):
        suffix = ".facts.json"
        stem = name[:-len(suffix)]
    elif name.endswith(".fulltext.md"):
        suffix = ".fulltext.md"
        stem = name[:-len(suffix)]
    else:
        suffix = source.suffix
        stem = source.stem
    stem = VERSION_SUFFIX.sub("", stem)
    return (source.parent / f"{stem}@v{version}{suffix}").as_posix()


def _original_path(doc_id: str, version: int, source: Path) -> str:
    suffix = source.suffix.lower()
    return f"originals/{doc_id}@v{version}{suffix}"


def _same_doc_candidates(root: Path, documents: list[dict[str, Any]], source: Path) -> list[dict[str, Any]]:
    target_identity = identity_name(source)
    target_kind = file_kind(source)
    return [
        document for document in documents
        if identity_name(Path(str(document["original"]))) == target_identity
        and _registered_kind(root, document) == target_kind
    ]


def decide(root: Path, source: Path) -> dict[str, Any]:
    """Return a deterministic intake decision without mutating ``root``."""
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"file upload không tồn tại: {source}")

    documents = document_registry.load(root)
    source_hash = sha256(source)
    exact = [document for document in documents if document.get("sha256") == source_hash]
    if len(exact) > 1:
        raise ValueError("file trùng hash với nhiều version, cần human review")
    if exact:
        document = exact[0]
        return {
            "schema": "nexus-project-knowledge/intake-decision/v1",
            "flow": "duplicate",
            "source": str(source),
            "sha256": source_hash,
            "doc_id": document["doc_id"],
            "version": int(document["version"]),
            "reason": "sha256 trùng version đã đăng ký; không tạo version mới",
        }

    candidates = _same_doc_candidates(root, documents, source)
    candidate_ids = sorted({str(document["doc_id"]) for document in candidates})
    if not candidate_ids:
        return {
            "schema": "nexus-project-knowledge/intake-decision/v1",
            "flow": "initial_ingest",
            "source": str(source),
            "sha256": source_hash,
            "doc_id": identity_name(source),
            "version": 1,
            "reason": "không có document identity tương ứng trong registry",
        }
    if len(candidate_ids) != 1:
        raise ValueError(f"file khớp nhiều document identity: {candidate_ids}")

    doc_id = candidate_ids[0]
    document_registry.require_version_1(doc_id, root)
    current = document_registry.current(doc_id, root)
    current_source = root / str(current["original"])
    if semantic_digest(source) == semantic_digest(current_source):
        return {
            "schema": "nexus-project-knowledge/intake-decision/v1",
            "flow": "no_op",
            "source": str(source),
            "sha256": source_hash,
            "doc_id": doc_id,
            "version": int(current["version"]),
            "reason": "semantic content không đổi; chỉ khác binary/formatting",
        }

    versions = [int(document["version"]) for document in candidates]
    from_version = int(current["version"])
    to_version = max(versions) + 1
    return {
        "schema": "nexus-project-knowledge/intake-decision/v1",
        "flow": "reingest",
        "source": str(source),
        "sha256": source_hash,
        "doc_id": doc_id,
        "from_version": from_version,
        "to_version": to_version,
        "reason": f"semantic content thay đổi; tạo version mới supersedes v{from_version}",
    }


def _write_registry(root: Path, documents: list[dict[str, Any]]) -> None:
    path = root / "documents.yml"
    original = path.read_text(encoding="utf-8")
    prefix_lines = []
    for line in original.splitlines(keepends=True):
        if line.strip() == "documents:":
            break
        prefix_lines.append(line)
    rendered = yaml.safe_dump(
        {"documents": documents}, allow_unicode=True, sort_keys=False
    )
    path.write_text("".join(prefix_lines) + rendered, encoding="utf-8")


def _write_manifest(root: Path) -> bool:
    manifest = root / "originals/MANIFEST.sha256"
    if not manifest.exists():
        return False
    files = []
    for path in sorted((root / "originals").rglob("*")):
        if path.is_file() and path.name not in {"MANIFEST.sha256", ".gitkeep"}:
            files.append((path.relative_to(root / "originals").as_posix(), sha256(path)))
    lines = [
        "# GATE 1 — sha256 của originals/ (tầng bất biến). KHÔNG sửa tay.",
        "# Sinh bởi scripts/intake.py sau khi source được đăng ký trên staging branch.",
        "",
    ]
    lines.extend(f"{digest}  {relative}" for relative, digest in files)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def register(root: Path, source: Path, decision: dict[str, Any]) -> dict[str, Any]:
    """Apply an initial/re-ingest decision to a staging root/worktree."""
    if decision.get("flow") not in {"initial_ingest", "reingest"}:
        raise ValueError(f"flow `{decision.get('flow')}` không tạo version mới")

    source = Path(decision["source"]).expanduser().resolve()
    documents = document_registry.load(root)
    doc_id = str(decision["doc_id"])
    version = int(decision.get("version") or decision.get("to_version"))
    if decision["flow"] == "reingest":
        current = document_registry.current(doc_id, root)
        from_version = int(decision["from_version"])
        if int(current["version"]) != from_version:
            raise ValueError("registry đã đổi current version sau lúc tạo intake decision")
        original = _original_path(doc_id, version, source)
        raw_paths = [_versioned_path(str(path), version) for path in current.get("raw_paths") or []]
        new_document = dict(current)
        new_document.update({
            "version": version,
            "original": original,
            "sha256": sha256(source),
            "status": "canonical",
            "current": True,
            "supersedes": from_version,
            "raw_paths": raw_paths,
        })
        documents = [
            {**document, "current": False} if document.get("doc_id") == doc_id else document
            for document in documents
        ]
    else:
        if any(str(document.get("doc_id")) == doc_id for document in documents):
            raise ValueError(f"doc_id `{doc_id}` đã tồn tại; không được khởi tạo lại từ đầu")
        original = f"originals/{doc_id}{source.suffix.lower()}"
        new_document = {
            "doc_id": doc_id,
            "version": 1,
            "original": original,
            "kind": file_kind(source),
            "sha256": sha256(source),
            "status": "canonical",
            "current": True,
            "supersedes": None,
            "visibility": "internal",
            "extractor": "nexus" if doc_id == "nexus-plan" else "van",
            "raw_paths": [],
        }

    destination = root / original
    if destination.exists():
        raise FileExistsError(f"đích original đã tồn tại, không ghi đè: {original}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    documents.append(new_document)
    _write_registry(root, documents)
    manifest_updated = _write_manifest(root)
    return {
        **decision,
        "registered": True,
        "registered_original": original,
        "manifest_updated": manifest_updated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Automatic Project Knowledge file intake")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="staging/worktree skill root; mặc định là skill root hiện tại")
    parser.add_argument("--apply", action="store_true",
                        help="copy source và đăng ký version vào root; không merge/publish")
    args = parser.parse_args()
    root = args.root.resolve()
    decision = decide(root, args.file)
    result = register(root, args.file, decision) if args.apply else decision
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
