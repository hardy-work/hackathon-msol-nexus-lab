#!/usr/bin/env python3
"""Contract test for mandatory BM25 + Chroma indexes."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import bm25_index
import build_rag_indexes
import embed_index
import rag_index

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    previous = os.environ.get("PROJECT_KNOWLEDGE_EMBEDDING_BACKEND")
    os.environ["PROJECT_KNOWLEDGE_EMBEDDING_BACKEND"] = "hash"
    try:
        with tempfile.TemporaryDirectory(prefix="pk-rag-index-") as temp:
            root = Path(temp) / "skill"

            def ignore(_path: str, names: list[str]) -> set[str]:
                return {name for name in names if name in {"derived", ".runtime", "__pycache__"}}

            shutil.copytree(ROOT, root, ignore=ignore)
            manifest = build_rag_indexes.build(root)
            assert manifest["bm25"]["backend"] == "bm25s"
            assert manifest["vector"]["backend"] == "chroma"
            assert rag_index.ready(root), rag_index.required_errors(root)
            assert bm25_index.KeywordIndex(root).search("Authentication task")
            assert embed_index.Semantic(root).search("công việc xác thực")

            (root / "wiki/index.md").write_text(
                (root / "wiki/index.md").read_text(encoding="utf-8") + "\nchanged\n",
                encoding="utf-8",
            )
            assert any("digest" in error for error in rag_index.required_errors(root))
    finally:
        if previous is None:
            os.environ.pop("PROJECT_KNOWLEDGE_EMBEDDING_BACKEND", None)
        else:
            os.environ["PROJECT_KNOWLEDGE_EMBEDDING_BACKEND"] = previous

    print("✓ mandatory RAG index self-test: BM25 + Chroma + digest binding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
