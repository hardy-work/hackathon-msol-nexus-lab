#!/usr/bin/env python3
"""Regression tests for Gate 4 citation existence and numeric provenance."""
from __future__ import annotations

import answer


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

    print("✓ Gate 4 citation self-test: valid file/locator + missing citation blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
