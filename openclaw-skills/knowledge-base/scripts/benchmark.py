#!/usr/bin/env python3
"""Repeatable latency benchmark for the long-lived Knowledge Base runtime."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from runtime_engine import KnowledgeRuntime

QUERIES = [
    "ĐôNT làm vai trò gì trong dự án Nexus?",
    "Ai phụ trách API Login trong Sprint 1?",
    "Authentication bắt đầu ngày nào?",
    "Tổng effort thực tế của Sprint 1 là bao nhiêu?",
    "Ngân sách tiền của Nexus là bao nhiêu?",
]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * p), len(ordered) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--cache", action="store_true", help="benchmark cache path instead of retrieval")
    parser.add_argument("--max-p95-ms", type=float)
    args = parser.parse_args()
    runtime = KnowledgeRuntime()
    # Warm DB/graph and populate cache when requested. BGE remains lazy because
    # deterministic onboarding queries should not pay its memory cost.
    for query in QUERIES:
        runtime.query("nexus", query, actor="benchmark", roles=["project_member"],
                      use_cache=args.cache)

    work = QUERIES * max(1, args.iterations)

    def call(query: str) -> tuple[float, str, bool]:
        started = time.perf_counter()
        result = runtime.query("nexus", query, actor="benchmark", roles=["project_member"],
                               use_cache=args.cache)
        return (time.perf_counter() - started) * 1000, result["status"], result.get("cache_hit", False)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        rows = list(pool.map(call, work))
    timings = [row[0] for row in rows]
    report = {
        "mode": "cache" if args.cache else "retrieval",
        "requests": len(rows), "concurrency": args.concurrency,
        "mean_ms": round(statistics.mean(timings), 3),
        "p50_ms": round(percentile(timings, 0.50), 3),
        "p95_ms": round(percentile(timings, 0.95), 3),
        "max_ms": round(max(timings), 3),
        "cache_hits": sum(row[2] for row in rows),
        "statuses": {status: sum(row[1] == status for row in rows)
                     for status in sorted({row[1] for row in rows})},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.max_p95_ms is not None and report["p95_ms"] > args.max_p95_ms else 0


if __name__ == "__main__":
    raise SystemExit(main())
