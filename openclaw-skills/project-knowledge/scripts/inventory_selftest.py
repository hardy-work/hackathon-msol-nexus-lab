#!/usr/bin/env python3
"""Offline inventory tests."""
from __future__ import annotations

import tempfile
import hashlib
from pathlib import Path

import inventory


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nexus-inventory-") as tmp:
        root = Path(tmp)
        (root / "originals").mkdir()
        (root / "documents.yml").write_text("documents: []\n", encoding="utf-8")
        (root / "originals/a.xlsx").write_bytes(b"PK\x03\x04demo")
        (root / "originals/b.xlsx").write_bytes(b"PK\x03\x04demo")
        result = inventory.build(root)
        assert result["documents"][0]["kind"] == "xlsx"
        assert result["canonical_review_required"] is True
        assert result["duplicates"] == [["a.xlsx", "b.xlsx"]]
        sha = hashlib.sha256(b"PK\x03\x04demo").hexdigest()
        (root / "documents.yml").write_text(
            "documents:\n"
            f"  - {{doc_id: plan, version: 1, original: originals/a.xlsx, sha256: {sha}, current: false}}\n"
            f"  - {{doc_id: plan, version: 2, original: originals/b.xlsx, sha256: {sha}, current: true, supersedes: 1}}\n",
            encoding="utf-8",
        )
        reviewed = inventory.build(root)
        assert reviewed["duplicates"] and reviewed["canonical_review_required"] is False
    print("✓ inventory self-test: 4/4 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
