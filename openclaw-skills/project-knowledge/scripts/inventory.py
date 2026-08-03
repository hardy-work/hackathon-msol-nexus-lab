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
from collections import defaultdict
from pathlib import Path
from typing import Any


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


def build(root: Path) -> dict[str, Any]:
    originals = root / "originals"
    documents = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in sorted(originals.rglob("*")):
        if not path.is_file() or path.name in {"MANIFEST.sha256", ".gitkeep"}:
            continue
        file_hash = digest(path)
        by_hash[file_hash].append(path.relative_to(originals).as_posix())
        head = path.read_bytes()[:16]
        documents.append({
            "path": path.relative_to(root).as_posix(),
            "name": path.name,
            "kind": kind(path, head),
            "mime": mimetypes.guess_type(path.name)[0],
            "size": path.stat().st_size,
            "sha256": file_hash,
            "canonical": True,
            "decision": "pending human canonical review",
        })
    duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
    return {
        "schema": "nexus-project-inventory/v1",
        "documents": documents,
        "duplicates": duplicates,
        "canonical_review_required": bool(duplicates),
        "note": "inventory không tự chọn/bỏ tài liệu; Gate 1 vẫn là authority cho integrity",
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    inventory = build(root)
    destination = root / "derived" / "inventory.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ inventory: {len(inventory['documents'])} originals · "
          f"{len(inventory['duplicates'])} duplicate groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
