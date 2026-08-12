#!/usr/bin/env python3
"""Offline contract test for Gate 3b consensus behavior.

Live Gate 3b needs Claude and remains a deployment/runtime check.  CI still
executes this harness so the K-vote gate cannot silently regress while offline.
"""
from __future__ import annotations

import threading

import review


def main() -> int:
    page = review.ROOT / "wiki/sources/nexus-plan.md"
    original = review.run_once
    try:
        # All K independent calls must be in flight together when workers=K.
        barrier = threading.Barrier(3, timeout=2)

        def concurrent_pass(_prompt):
            barrier.wait()
            return {
                "verdict": "PASS", "findings": [], "checked": ["raw_paths"], "err": ""
            }

        review.run_once = concurrent_pass
        verdict, _detail, _runs = review.review(page, k=3, workers=3)
        assert verdict == "PASS"

        review.run_once = lambda _prompt: {
            "verdict": "PASS", "findings": [], "checked": ["raw_paths"], "err": ""
        }
        verdict, _detail, _runs = review.review(page, k=3, workers=1)
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
        verdict, _detail, _runs = review.review(page, k=3, workers=1)
        assert verdict == "FINDING"

        responses = iter([
            {"verdict": "PASS", "findings": [], "checked": ["raw_paths"], "err": ""},
            {"verdict": "UNVERIFIABLE", "findings": [{
                "claim": "chưa thể kiểm", "problem": "bằng chứng bị cắt", "source_says": ""
            }], "checked": [], "err": ""},
            {"verdict": "UNVERIFIABLE", "findings": [], "checked": [], "err": ""},
        ])
        review.run_once = lambda _prompt: next(responses)
        verdict, detail, _runs = review.review(page, k=3, workers=1)
        assert verdict == "KHÔNG CHẮC"
        assert "không đủ bằng chứng" in detail

        responses = iter([
            {"verdict": "PASS", "findings": [], "checked": [], "err": ""},
            {"verdict": "PASS", "findings": [], "checked": [], "err": ""},
            {"verdict": "ERR", "findings": [], "checked": [], "err": "timeout"},
        ])
        review.run_once = lambda _prompt: next(responses)
        verdict, detail, _runs = review.review(page, k=3, workers=1)
        assert verdict == "KHÔNG CHẮC"
        assert "timeout" in detail
    finally:
        review.run_once = original

    print("✓ Gate 3b self-test: parallel K runs + consensus + fail-closed errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
