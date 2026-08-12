#!/usr/bin/env python3
"""Offline tests for corpus version/freshness detection."""
from __future__ import annotations

import tempfile
from pathlib import Path

import versioning


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nexus-version-") as tmp:
        root = Path(tmp)
        (root / "originals").mkdir()
        (root / "raw").mkdir()
        (root / "wiki").mkdir()
        (root / "originals/nexus-plan.xlsx").write_bytes(b"v1")
        (root / "raw/facts.json").write_text("{}", encoding="utf-8")
        (root / "wiki/index.md").write_text("# v1", encoding="utf-8")
        (root / "schema.yml").write_text("dimensions: {}", encoding="utf-8")
        (root / "coverage.yml").write_text("[]", encoding="utf-8")

        metadata = versioning.build(root, generated_at="2026-08-03T00:00:00+00:00")
        assert metadata["version"].startswith("nexus-")
        fresh = versioning.check(root)
        assert fresh["state"] == "fresh"

        (root / "raw/facts.json").write_text('{"changed": true}', encoding="utf-8")
        stale = versioning.check(root)
        assert stale["state"] == "stale"
        assert "raw/facts.json" in stale["changed_files"]

    print("✓ version/freshness self-test: 3/3 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
