#!/usr/bin/env python3
"""Corpus versioning and freshness checks for Project Knowledge.

The derived database/vector index is only trustworthy relative to the inputs
from which it was built.  This module records a reproducible digest of the
original workbook plus committed raw/wiki/contract files and detects changes at
query time without blocking read-only answers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METADATA_NAME = "corpus_version.json"
EXCLUDED = {"MANIFEST.sha256", ".gitkeep", "log.md"}
INPUT_FILES = ("originals", "raw", "structured", "wiki", "schema.yml",
               "coverage.yml", "documents.yml", "access.yml")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in INPUT_FILES:
        path = root / name
        if path.is_dir():
            paths.extend(p for p in path.rglob("*") if p.is_file() and p.name not in EXCLUDED)
        elif path.is_file():
            paths.append(path)
    return sorted(paths)


def file_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): _sha256(p)
        for p in input_files(root)
    }


def digest_hashes(hashes: dict[str, str]) -> str:
    payload = "\n".join(f"{name}\t{value}" for name, value in sorted(hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_hashes(root: Path) -> dict[str, str]:
    return {
        name: value for name, value in file_hashes(root).items()
        if name.startswith("originals/")
    }


def build(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    hashes = file_hashes(root)
    sources = {name: value for name, value in hashes.items() if name.startswith("originals/")}
    input_sha = digest_hashes(hashes)
    source_sha = digest_hashes(sources)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata: dict[str, Any] = {
        "schema": "nexus-project-knowledge/v1",
        "project": "nexus",
        "version": f"nexus-{input_sha[:12]}",
        "generated_at": timestamp,
        "as_of": timestamp[:10],
        "input_sha256": input_sha,
        "source_sha256": source_sha,
        "files": hashes,
        "source_files": sources,
        "note": "derived artifacts are reproducible from originals/raw/wiki and contract files",
    }
    destination = root / "derived" / METADATA_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def check(root: Path) -> dict[str, Any]:
    """Return a machine-readable freshness status; never raises for missing metadata."""
    metadata_path = root / "derived" / METADATA_NAME
    if not metadata_path.exists():
        return {
            "state": "unknown",
            "reason": "derived/corpus_version.json chưa tồn tại; cần chạy scripts/run_all.sh",
            "version": None,
            "as_of": None,
            "changed_files": [],
        }
    try:
        recorded = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "state": "unknown",
            "reason": f"không đọc được metadata freshness: {type(exc).__name__}",
            "version": None,
            "as_of": None,
            "changed_files": [],
        }

    current = file_hashes(root)
    previous = recorded.get("files", {})
    changed = sorted({*current, *previous} - {
        name for name in set(current) & set(previous) if current[name] == previous[name]
    })
    state = "fresh" if not changed else "stale"
    reason = "derived khớp với originals/raw/wiki hiện tại" if state == "fresh" else (
        "đầu vào đã thay đổi sau lần build; chạy scripts/run_all.sh trước khi demo"
    )
    return {
        "state": state,
        "reason": reason,
        "version": recorded.get("version"),
        "as_of": recorded.get("as_of"),
        "generated_at": recorded.get("generated_at"),
        "input_sha256": recorded.get("input_sha256"),
        "current_input_sha256": digest_hashes(current),
        "changed_files": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/check Nexus corpus freshness metadata")
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--summary", action="store_true", help="chỉ in version và số file")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    result = build(root) if args.command == "build" else check(root)
    if args.summary:
        if args.command == "build":
            print(f"✓ {result.get('version')} · {len(result.get('files', {}))} input files · "
                  f"as_of={result.get('as_of')}")
        else:
            print(f"✓ freshness={result.get('state')} · {result.get('version')} · "
                  f"changed={len(result.get('changed_files', []))}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command == "build" or result["state"] == "fresh" else 1


if __name__ == "__main__":
    raise SystemExit(main())
