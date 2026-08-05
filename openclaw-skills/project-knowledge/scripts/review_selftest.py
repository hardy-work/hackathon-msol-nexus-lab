#!/usr/bin/env python3
"""Offline contract test for Gate 3b consensus behavior.

Live Gate 3b needs Claude and remains a deployment/runtime check.  CI still
executes this harness so the K-vote gate cannot silently regress while offline.
"""
from __future__ import annotations

import review


def main() -> int:
    page = review.ROOT / "wiki/sources/nexus-plan.md"
    original = review.run_once
    try:
        review.run_once = lambda _prompt: {
            "verdict": "PASS", "findings": [], "checked": ["raw_paths"], "err": ""
        }
        verdict, _detail, _runs = review.review(page, k=3)
        assert verdict == "PASS"

        responses = iter([
            {"verdict": "PASS", "findings": [], "checked": [], "err": ""},
            {"verdict": "FINDING", "findings": [{
                "claim": "claim sai", "problem": "fixture finding", "source_says": "raw"
            }], "checked": [], "err": ""},
            {"verdict": "FINDING", "findings": [{
                "claim": "claim sai", "problem": "fixture finding", "source_says": "raw"
            }], "checked": [], "err": ""},
        ])
        review.run_once = lambda _prompt: next(responses)
        verdict, _detail, _runs = review.review(page, k=3)
        assert verdict == "FINDING"

        responses = iter([
            {"verdict": "PASS", "findings": [], "checked": ["raw_paths"], "err": ""},
            {"verdict": "UNVERIFIABLE", "findings": [{
                "claim": "chưa thể kiểm", "problem": "bằng chứng bị cắt", "source_says": ""
            }], "checked": [], "err": ""},
            {"verdict": "UNVERIFIABLE", "findings": [], "checked": [], "err": ""},
        ])
        review.run_once = lambda _prompt: next(responses)
        verdict, detail, _runs = review.review(page, k=3)
        assert verdict == "KHÔNG CHẮC"
        assert "không đủ bằng chứng" in detail
    finally:
        review.run_once = original

    print("✓ Gate 3b contract self-test: PASS consensus + majority FINDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
