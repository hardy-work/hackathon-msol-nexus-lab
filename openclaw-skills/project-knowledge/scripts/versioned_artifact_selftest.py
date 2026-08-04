#!/usr/bin/env python3
"""Regression tests for current-only versioned artifacts and provenance."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import yaml

import artifact_paths
import build_db
import structure


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pk-versioned-") as td:
        root = Path(td)
        for directory in ("originals", "raw", "wiki/entities", "wiki/sources", "derived"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        old, new = b"old", b"new"
        (root / "originals/v1.xlsx").write_bytes(old)
        (root / "originals/v2.xlsx").write_bytes(new)
        (root / "documents.yml").write_text(yaml.safe_dump({"documents": [
            {"doc_id": "nexus-plan", "version": 1, "original": "originals/v1.xlsx",
             "sha256": sha(old), "current": False},
            {"doc_id": "nexus-plan", "version": 2, "original": "originals/v2.xlsx",
             "sha256": sha(new), "current": True, "supersedes": 1,
             "raw_paths": ["raw/nexus-sprint1@v2.md"]},
        ]}, sort_keys=False), encoding="utf-8")
        (root / "schema.yml").write_text("dimensions: {}\n", encoding="utf-8")
        (root / "coverage.yml").write_text("[]\n", encoding="utf-8")

        document = {"doc_id": "nexus-plan", "version": 2,
                    "raw_paths": ["raw/nexus-sprint1@v2.md"]}
        assert artifact_paths.artifact_rel(document, "nexus-sprint1", "md").as_posix() == \
            "raw/nexus-sprint1@v2.md"
        assert artifact_paths.artifact_rel(document, "nexus-sprint1", "facts").as_posix() == \
            "raw/nexus-sprint1@v2.facts.json"
        assert not artifact_paths.payload_is_current(
            {"doc_id": "nexus-plan", "version": 1}, root)
        assert artifact_paths.payload_is_current(
            {"doc_id": "nexus-plan", "version": 2}, root)

        raw = root / "raw/note@v2.md"
        structured = root / "structured.md"
        raw.write_text(f"---\ndoc_id: nexus-plan\nversion: 2\nsha256: {sha(new)}\n---\n45 giờ\n",
                       encoding="utf-8")
        structured.write_text("---\ndoc_id: nexus-plan\nversion: 1\n"
                              "source_sha256: stale\n---\n45 giờ\n", encoding="utf-8")
        assert structure.validate_source_metadata("nexus-plan", raw, structured)

        for version, value, filename in ((1, 10, "nexus-sprint1.facts.json"),
                                         (2, 20, "nexus-sprint1@v2.facts.json")):
            payload = {"doc_id": "nexus-plan", "version": version,
                       "facts": {"do-nt": {
                           "task_count": {"value": value, "unit": "task", "src": "A1"},
                           "estimate_h": {"value": 1, "unit": "hour", "src": "A1"},
                           "actual_h": {"value": 1, "unit": "hour", "src": "A1"},
                       }}}
            (root / "raw" / filename).write_text(json.dumps(payload), encoding="utf-8")

        old_root, old_db = build_db.ROOT, build_db.DB
        build_db.ROOT, build_db.DB = root, root / "derived/facts.duckdb"
        try:
            build_db.main()
            import duckdb
            con = duckdb.connect(str(build_db.DB), read_only=True)
            rows = con.execute("SELECT task_count FROM person_sprint").fetchall()
            con.close()
            assert rows == [(20,)], rows
        finally:
            build_db.ROOT, build_db.DB = old_root, old_db

    print("✓ versioned artifact self-test: 6/6 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
