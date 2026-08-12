#!/usr/bin/env python3
"""Regression tests for Gate 4 citation existence and numeric provenance."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace

import answer
import filesystem_boundary
import numeric_guard


def main() -> int:
    kb = answer.KB()

    valid_page = answer.Result(
        1, answer.CO, "ĐôNT", cites=["wiki/entities/do-nt.md"]
    )
    assert answer.gate4(valid_page, kb).outcome == answer.CO

    valid_locator = answer.Result(
        2, answer.CO, "Authentication", cites=["Sprint 1!B10"]
    )
    assert answer.gate4(valid_locator, kb).outcome == answer.CO

    missing = answer.Result(
        2, answer.CO, "ĐôNT", cites=["wiki/entities/does-not-exist.md"]
    )
    blocked = answer.gate4(missing, kb)
    assert blocked.outcome == answer.NF
    assert blocked.cites == []
    assert "citation" in blocked.reason

    malformed = answer.Result(
        1, answer.CO, "0", cites=["wiki/sources/… → Summary project!D4"]
    )
    assert answer.gate4(malformed, kb).outcome == answer.NF

    with tempfile.TemporaryDirectory(prefix="pk-gate4-markdown-") as tmp:
        root = Path(tmp)
        for directory in ("originals", "raw", "wiki/sources", "derived"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        original = root / "originals/manual.md"
        original.write_text("Nguồn Markdown", encoding="utf-8")
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        (root / "documents.yml").write_text(
            "documents:\n"
            "  - doc_id: manual\n"
            "    version: 1\n"
            "    original: originals/manual.md\n"
            f"    sha256: {digest}\n"
            "    kind: text/markdown\n"
            "    current: true\n"
            "    supersedes: null\n"
            "    raw_paths:\n"
            "      - raw/manual.md\n",
            encoding="utf-8",
        )
        (root / "raw/manual.md").write_text(
            "---\nraw_id: manual\ndoc_id: manual\nversion: 1\n"
            "kind: markdown\nextractor: scripts/extract_markdown.py\n---\n"
            "Giờ làm việc là 40 giờ mỗi tuần.\n",
            encoding="utf-8",
        )
        (root / "wiki/sources/manual.md").write_text(
            "---\npage: source\ndoc_id: manual\nversion: 1\n"
            "raw_paths:\n  - raw/manual.md\n---\n# Manual\n",
            encoding="utf-8",
        )
        fake_kb = SimpleNamespace(
            root=root,
            boundary=filesystem_boundary.ReadOnlyCorpus(root),
        )
        valid = answer.gate4(
            answer.Result(3, answer.CO, "40 giờ mỗi tuần.",
                          cites=["wiki/sources/manual.md"]),
            fake_kb,
        )
        assert valid.outcome == answer.CO, valid.reason
        invented = answer.gate4(
            answer.Result(3, answer.CO, "41 giờ mỗi tuần.",
                          cites=["wiki/sources/manual.md"]),
            fake_kb,
        )
        assert invented.outcome == answer.NF
        numeric_guard.reset(root)

    print("✓ Gate 4 citation self-test: facts + current Markdown provenance + missing citation blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
