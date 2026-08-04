#!/usr/bin/env python3
"""Offline tests for the Haiku route contract (never calls the network)."""
from __future__ import annotations

import router


CASES = [
    ('{"route":"structured","confidence":0.98,"reason":"task lookup"}', "structured"),
    ('prefix {"route":"open","confidence":0.8,"reason":"needs synthesis"} suffix', "open"),
    ('{"route":"graph","confidence":0.9,"reason":"multi-hop relation"}', "graph"),
    ('{"route":"action","confidence":"0.9","reason":"write request"}', "action"),
]


def main() -> int:
    failures = []
    for text, expected in CASES:
        got = router.parse_response(text)
        if got is None or got.route != expected:
            failures.append((text, expected, None if got is None else got.route))

    for text in ("not json", '{"route":"unknown","confidence":1}', "{}"):
        if router.parse_response(text) is not None:
            failures.append((text, "None", "accepted"))

    heuristics = {
        "Cập nhật task API Login thành Done": "action",
        "Tại sao Sprint 1 bị chậm?": "open",
        "Ai phụ trách API Login?": "structured",
    }
    for query, expected in heuristics.items():
        got = router.heuristic_route(query).route
        if got != expected:
            failures.append((query, expected, got))

    if failures:
        for case in failures:
            print(f"✗ router case: {case}")
        return 1
    print(f"✓ router self-test: {len(CASES) + 3 + len(heuristics)} cases qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
