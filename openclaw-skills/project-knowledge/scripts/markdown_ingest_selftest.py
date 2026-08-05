#!/usr/bin/env python3
"""CI fixture for Markdown intake -> raw -> wiki source -> derived indexes."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import document_registry  # noqa: E402
import ingest_flow  # noqa: E402
import intake  # noqa: E402


SOURCE = """---
title: MOR Software JSC — Hồ sơ nhân sự chủ chốt
type: people-directory
org: MOR Software JSC
lang: vi
source:
  - https://example.test/mor
last_updated: 2026-08-05
---

# MOR Software JSC — Hồ sơ nhân sự chủ chốt

## Vũ Văn Tú

| Trường | Giá trị |
|---|---|
| Chức vụ | Co-founder & CEO |

Hồ sơ được lưu nguyên văn để truy xuất cùng provenance.
"""


def main() -> int:
    os.environ.setdefault("PROJECT_KNOWLEDGE_EMBEDDING_BACKEND", "hash")
    with tempfile.TemporaryDirectory(prefix="pk-markdown-ingest-") as temp:
        temp_root = Path(temp)
        staging = temp_root / "project-knowledge"

        def ignore(_path: str, names: list[str]) -> set[str]:
            return {name for name in names if name in {"derived", ".runtime", "__pycache__"}}

        shutil.copytree(ROOT, staging, ignore=ignore)
        incoming = temp_root / "mor-software-nhan-su.md"
        incoming.write_text(SOURCE, encoding="utf-8")

        decision = intake.decide(staging, incoming)
        assert decision["flow"] == "initial_ingest", decision
        assert decision["kind"] == "text/markdown"
        registered = intake.register(staging, incoming, decision)
        doc_id = decision["doc_id"]
        document = document_registry.current(doc_id, staging)
        assert document["extractor"] == "markdown"
        assert document["raw_paths"] == [f"raw/{doc_id}.md"]
        assert registered["registered_original"].endswith(f"{doc_id}.md")

        os.environ["PROJECT_KNOWLEDGE_STATE_DIR"] = str(temp_root / "runtime")
        ingest_flow.execute(staging, doc_id, 1, review=False)

        raw = staging / f"raw/{doc_id}.md"
        page = staging / f"wiki/sources/{doc_id}.md"
        assert raw.is_file()
        assert page.is_file()
        assert "Hồ sơ được lưu nguyên văn" in raw.read_text(encoding="utf-8")
        page_text = page.read_text(encoding="utf-8")
        assert "domain: mor-software" in page_text
        assert f"- raw/{doc_id}.md" in page_text
        assert (staging / "derived/facts.duckdb").is_file()
        assert (staging / "derived/graph.json").is_file()
        assert (staging / "derived/rag_indexes.json").is_file()

        incoming_v2 = temp_root / "mor-software-nhan-su-v2.md"
        incoming_v2.write_text(SOURCE.replace("Co-founder & CEO", "Chief Executive Officer"),
                               encoding="utf-8")
        decision_v2 = intake.decide(staging, incoming_v2, confirmed_doc_id=doc_id)
        assert decision_v2["flow"] == "reingest", decision_v2
        assert decision_v2["from_version"] == 1
        assert decision_v2["to_version"] == 2
        intake.register(staging, incoming_v2, decision_v2)
        ingest_flow.execute(staging, doc_id, 2, review=False)

        current = document_registry.current(doc_id, staging)
        assert int(current["version"]) == 2
        assert current["raw_paths"] == [f"raw/{doc_id}@v2.md"]
        assert (staging / f"raw/{doc_id}@v2.md").is_file()
        history = staging / f"wiki/sources/{doc_id}@v1.md"
        assert history.is_file()
        assert f"superseded_by: wiki/sources/{doc_id}.md" in history.read_text(encoding="utf-8")

    print("✓ Markdown self-test: intake → raw → wiki source → derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
