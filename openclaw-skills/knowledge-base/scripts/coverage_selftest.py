#!/usr/bin/env python3
"""Offline tests for the prose-page completeness gate."""
from __future__ import annotations

import sys

import coverage


def main() -> int:
    source = """
## Điều 32. Tài sản
32.1. Thương hiệu
32.2. Cơ sở vật chất
### 32.4. Máy tính
32.4.1. Bảo quản
## Điều 33. Bí mật
33.1. Nội bộ
33.1.1. Nhân sự
"""
    complete = """
---
page: source
---
## Điều 32. Tài sản
- **32.1.** Thương hiệu
- **32.2.** Cơ sở vật chất
### 32.4. Máy tính
- **32.4.1.** Bảo quản
## Điều 33. Bí mật
- **33.1.** Nội bộ
- **33.1.1.** Nhân sự
## Nguồn
- doc_id: demo
"""
    report = coverage.check(source, complete)
    assert report["status"] == "pass", report
    assert report["complete"] is True, report

    missing = complete.replace("- **33.1.1.** Nhân sự\n", "")
    report = coverage.check(source, missing)
    assert report["status"] == "fail", report
    assert report["missing"] == ["33.1.1"], report

    marked = missing.replace(
        "## Nguồn", "> [Chưa bao phủ: 33.1.1] Chưa có trong bản trích.\n\n## Nguồn")
    report = coverage.check(source, marked)
    assert report["status"] == "pass" and report["complete"] is False, report
    assert report["marked_not_covered"] == ["33.1.1"], report

    unexpected = complete.replace("## Điều 33. Bí mật", "## Điều 34. Ngoài source\n\n## Điều 33. Bí mật")
    report = coverage.check(source, unexpected)
    assert report["status"] == "fail", report
    assert report["unexpected"] == ["34"], report

    # Inline references and source/footer metadata must not masquerade as coverage.
    prose = complete.replace("- **33.1.1.** Nhân sự\n", "- Xem Điều 33.1.1 trong tài liệu gốc.\n")
    report = coverage.check(source, prose)
    assert report["missing"] == ["33.1.1"], report
    print("completeness coverage self-test: 4/4 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
