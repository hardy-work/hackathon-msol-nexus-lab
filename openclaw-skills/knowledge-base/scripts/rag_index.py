#!/usr/bin/env python3
"""Shared contract for the mandatory Stage 5 retrieval indexes.

The indexes are derived from the current, Gate-3-approved wiki pages.  They are
never a source of truth: deleting ``derived/`` and rebuilding must produce the
same retrieval corpus.  The manifest binds both stores to the same input digest
so a runtime cannot silently use an index built from an older wiki.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

import artifact_paths
import document_registry
import versioning

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "derived/rag_indexes.json"
BM25_DIR = "derived/bm25"
CHROMA_DIR = "derived/chroma"
CHROMA_COLLECTION = "nexus-wiki"
SCHEMA = "nexus-rag-indexes/v1"


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def wiki_pages(root: Path = ROOT) -> list[tuple[str, str]]:
    """Return current wiki content only; historical snapshots are not indexed."""
    versions = document_registry.current_versions(root)
    pages: list[tuple[str, str]] = []
    for path in sorted((root / "wiki").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        text = path.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        if not artifact_paths.frontmatter_is_current(metadata, root, versions):
            continue
        pages.append((path.relative_to(root).as_posix(), text))
    return pages


def input_sha256(root: Path = ROOT) -> str:
    return versioning.digest_hashes(versioning.file_hashes(root))


def write_manifest(root: Path, *, page_count: int, bm25: dict, vector: dict) -> dict:
    payload = {
        "schema": SCHEMA,
        "input_sha256": input_sha256(root),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_count": int(page_count),
        "bm25": bm25,
        "vector": vector,
    }
    destination = root / MANIFEST
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return payload


def load_manifest(root: Path = ROOT) -> dict | None:
    path = root / MANIFEST
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def required_errors(root: Path = ROOT) -> list[str]:
    """Return errors that make the RAG retrieval layer not production-ready."""
    errors: list[str] = []
    manifest = load_manifest(root)
    if not manifest:
        return [f"thiếu hoặc hỏng {MANIFEST}"]
    if manifest.get("schema") != SCHEMA:
        errors.append(f"{MANIFEST} sai schema")
    expected = input_sha256(root)
    if manifest.get("input_sha256") != expected:
        errors.append("BM25/vector index không cùng digest với wiki/raw hiện tại")

    bm25 = manifest.get("bm25") or {}
    if bm25.get("backend") != "bm25s":
        errors.append("BM25 index không dùng backend bm25s")
    bm25_dir = root / BM25_DIR
    if not bm25_dir.is_dir() or not (bm25_dir / "paths.json").is_file():
        errors.append(f"thiếu {BM25_DIR}/")

    vector = manifest.get("vector") or {}
    if vector.get("backend") != "chroma":
        errors.append("vector index không dùng backend Chroma")
    chroma_dir = root / CHROMA_DIR
    if not chroma_dir.is_dir() or not any(chroma_dir.iterdir()):
        errors.append(f"thiếu persistent Chroma store {CHROMA_DIR}/")
    if vector.get("collection") != CHROMA_COLLECTION:
        errors.append("Chroma collection không đúng tên canonical")

    page_count = int(manifest.get("page_count") or 0)
    if page_count <= 0:
        errors.append("manifest không có wiki page nào được index")
    try:
        paths = json.loads((bm25_dir / "paths.json").read_text(encoding="utf-8"))
        if len(paths) != page_count:
            errors.append("BM25 page count lệch manifest")
    except (OSError, json.JSONDecodeError, TypeError):
        errors.append("BM25 paths.json không đọc được")
    return errors


def ready(root: Path = ROOT) -> bool:
    return not required_errors(root)
