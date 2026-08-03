#!/usr/bin/env python3
"""Offline contract checks for graph-derived task relations."""
from __future__ import annotations

from pathlib import Path

import graph_retrieval


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    graph = graph_retrieval.load(root)
    assert graph is not None and graph.available
    assert len(graph.task_hits("các task thuộc Authentication")) == 12
    answer = graph.direct_answer("Liệt kê các task thuộc Authentication")
    assert answer is not None
    assert "AU-1" in answer.answer and "SơnBH" in answer.answer
    context, citations = graph.context("các task thuộc Authentication")
    assert "task=AU-1" in context and "raw/nexus-sprint1.facts.json" in citations
    assert graph_retrieval.is_relation_query("task nào ảnh hưởng đến Authentication")
    print("✓ graph retrieval self-test: 5/5 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
