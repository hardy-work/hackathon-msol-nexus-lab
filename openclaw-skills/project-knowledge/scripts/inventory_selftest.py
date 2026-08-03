#!/usr/bin/env python3
"""Offline inventory tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import inventory


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nexus-inventory-") as tmp:
        root = Path(tmp)
        (root / "originals").mkdir()
        (root / "originals/a.xlsx").write_bytes(b"PK\x03\x04demo")
        (root / "originals/b.xlsx").write_bytes(b"PK\x03\x04demo")
        result = inventory.build(root)
        assert result["documents"][0]["kind"] == "xlsx"
        assert result["canonical_review_required"] is True
        assert result["duplicates"] == [["a.xlsx", "b.xlsx"]]
    print("✓ inventory self-test: 3/3 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
