#!/usr/bin/env python3
"""Stage 0/1 inventory for immutable project originals.

It does not choose a canonical document or mutate originals.  It records file
identity, coarse format and duplicate hashes so a human can decide which
version is authoritative before a later ingest run.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from document_registry import load as load_registry


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def kind(path: Path, head: bytes) -> str:
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return {".xlsx": "xlsx", ".docx": "docx", ".pptx": "pptx"}.get(path.suffix.lower(), "zip")
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff"):
        return "image"
    return mimetypes.guess_type(path.name)[0] or "binary"


def normalized_name(path: Path) -> str:
    stem = path.stem.casefold()
    stem = re.sub(r"(?:[-_. ]+(?:final|copy|rev|revision|v)?\d*)+$", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


def content_chunks(path: Path, size: int = 4096) -> set[str]:
    chunks = set()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(size), b""):
            chunks.add(hashlib.blake2b(chunk, digest_size=8).hexdigest())
    return chunks


def near_duplicate_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = []
    chunks = {row["path"]: content_chunks(Path(row["absolute_path"])) for row in rows}
    for index, left in enumerate(rows):
        members = [left["path"]]
        reasons = []
        for right in rows[index + 1:]:
            name_score = SequenceMatcher(None, left["normalized_name"], right["normalized_name"]).ratio()
            a, b = chunks[left["path"]], chunks[right["path"]]
            content_score = len(a & b) / max(len(a | b), 1)
            size_ratio = min(left["size"], right["size"]) / max(left["size"], right["size"], 1)
            if content_score >= 0.60 or (name_score >= 0.72 and size_ratio >= 0.50):
                members.append(right["path"])
                reasons.append({"pair": [left["path"], right["path"]],
                                "name_similarity": round(name_score, 3),
                                "content_similarity": round(content_score, 3)})
        if len(members) > 1:
            groups.append({"documents": members, "reasons": reasons})
    return groups


def build(root: Path) -> dict[str, Any]:
    originals = root / "originals"
    registry = load_registry(root)
    registered = {str(doc["original"]): doc for doc in registry}
    documents = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in sorted(originals.rglob("*")):
        if not path.is_file() or path.name in {"MANIFEST.sha256", ".gitkeep"}:
            continue
        file_hash = digest(path)
        by_hash[file_hash].append(path.relative_to(originals).as_posix())
        head = path.read_bytes()[:16]
        rel_root = path.relative_to(root).as_posix()
        reg = registered.get(rel_root)
        documents.append({
            "path": path.relative_to(root).as_posix(),
            "absolute_path": str(path),
            "name": path.name,
            "normalized_name": normalized_name(path),
            "kind": kind(path, head),
            "mime": mimetypes.guess_type(path.name)[0],
            "size": path.stat().st_size,
            "sha256": file_hash,
            "doc_id": reg.get("doc_id") if reg else None,
            "version": reg.get("version") if reg else None,
            "canonical": bool(reg and reg.get("current") and reg.get("status") == "canonical"),
            "decision": "registered canonical" if reg else "pending human canonical review",
        })
    duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
    near = near_duplicate_groups(documents)
    unregistered = [row["path"] for row in documents if not row["doc_id"]]

    def resolved(paths: list[str]) -> bool:
        rels = [p if p.startswith("originals/") else f"originals/{p}" for p in paths]
        records = [registered.get(rel) for rel in rels]
        return all(records) and sum(bool(record.get("current")) for record in records) == 1

    unresolved_duplicates = [group for group in duplicates if not resolved(group)]
    unresolved_near = [group for group in near if not resolved(group["documents"])]
    for row in documents:
        row.pop("absolute_path", None)
    return {
        "schema": "nexus-project-inventory/v1",
        "documents": documents,
        "duplicates": duplicates,
        "near_duplicate_groups": near,
        "unresolved_duplicate_groups": unresolved_duplicates,
        "unresolved_near_duplicate_groups": unresolved_near,
        "unregistered": unregistered,
        "canonical_review_required": bool(unresolved_duplicates or unresolved_near or unregistered),
        "note": "inventory không tự chọn/bỏ tài liệu; documents.yml + human review quyết định canonical",
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    inventory = build(root)
    destination = root / "derived" / "inventory.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ inventory: {len(inventory['documents'])} originals · "
          f"{len(inventory['duplicates'])} exact · "
          f"{len(inventory['near_duplicate_groups'])} near-duplicate groups")
    if inventory["canonical_review_required"]:
        print("✗ HALT: cần người chọn canonical/đăng ký version trong documents.yml")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
