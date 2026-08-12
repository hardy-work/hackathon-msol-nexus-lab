#!/usr/bin/env python3
"""Offline contract checks for graph-derived task relations."""
from __future__ import annotations

from pathlib import Path
import json
import tempfile

import access_control
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
    with tempfile.TemporaryDirectory(prefix="pk-graph-acl-") as temp:
        root = Path(temp)
        (root / "derived").mkdir()
        (root / "access.yml").write_text(
            "default_visibility: internal\nvisibility_roles:\n  internal: [project_member]\n"
            "  restricted: [project_manager]\n", encoding="utf-8")
        (root / "derived/graph.json").write_text(json.dumps({
            "nodes": [
                {"id": "task:T-1", "type": "task", "task_id": "T-1",
                 "name": "Secret task", "visibility": "internal"},
                {"id": "secret-person", "type": "entity-person", "name": "Secret",
                 "visibility": "restricted"},
            ],
            "edges": [{"from": "task:T-1", "to": "secret-person", "rel": "assigned_to"}],
        }), encoding="utf-8")
        restricted = graph_retrieval.GraphIndex(root)
        hits = restricted.task_hits("Secret task", access=access_control.AccessContext(
            "member", frozenset({"project_member"})))
        assert len(hits) == 1 and hits[0].assignee is None
    print("✓ graph retrieval self-test: 6/6 qua")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
