#!/usr/bin/env python3
"""STAGE 5 · DERIVE — build mandatory BM25 and Chroma indexes together."""
from __future__ import annotations

from pathlib import Path

import bm25_index
import embed_index
import rag_index

ROOT = Path(__file__).resolve().parent.parent


def build(root: Path = ROOT) -> dict:
    pages = rag_index.wiki_pages(root)
    if not pages:
        raise RuntimeError("không có current wiki page để dựng retrieval indexes")
    bm25 = bm25_index.build(root, pages)
    vector = embed_index.build(root, pages)
    return rag_index.write_manifest(root, page_count=len(pages), bm25=bm25, vector=vector)


def main() -> int:
    manifest = build(ROOT)
    print(f"✓ {rag_index.MANIFEST} · {manifest['page_count']} trang · "
          f"BM25={manifest['bm25']['backend']} · "
          f"vector={manifest['vector']['backend']}:{manifest['vector']['embedding_backend']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
