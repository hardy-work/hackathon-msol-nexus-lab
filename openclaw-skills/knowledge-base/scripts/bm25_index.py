#!/usr/bin/env python3
"""STAGE 5 · DERIVE — mandatory BM25 lexical index over current wiki pages."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import bm25s

import rag_index

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / rag_index.BM25_DIR


def build(root: Path = ROOT, pages: list[tuple[str, str]] | None = None) -> dict:
    pages = pages if pages is not None else rag_index.wiki_pages(root)
    if not pages:
        raise RuntimeError("không có current wiki page để dựng BM25")
    corpus = [text for _, text in pages]
    tokens = bm25s.tokenize(corpus, stopwords=[], show_progress=False)
    retriever = bm25s.BM25(k1=1.5, b=0.75, corpus=corpus)
    retriever.index(tokens, show_progress=False)

    destination = root / rag_index.BM25_DIR
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    retriever.save(str(destination), corpus=corpus)
    (destination / "paths.json").write_text(
        json.dumps([path for path, _ in pages], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "backend": "bm25s",
        "path": rag_index.BM25_DIR,
        "documents": len(pages),
        "k1": 1.5,
        "b": 0.75,
    }


class KeywordIndex:
    """Read-only BM25 search facade used by the query runtime."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.directory = root / rag_index.BM25_DIR
        if not self.directory.is_dir():
            raise FileNotFoundError(
                f"chưa có {rag_index.BM25_DIR}; chạy scripts/build_rag_indexes.py"
            )
        self.paths = json.loads((self.directory / "paths.json").read_text(encoding="utf-8"))
        self.retriever = bm25s.BM25.load(str(self.directory), load_corpus=False, mmap=True)

    def search(self, query: str, k: int = 6,
               allowed: list[str] | set[str] | None = None) -> list[tuple[float, str]]:
        if not query.strip() or not self.paths:
            return []
        tokens = bm25s.tokenize([query], stopwords=[], show_progress=False)
        scores_k = min(len(self.paths), max(k * 8, k))
        results, scores = self.retriever.retrieve(
            tokens, k=scores_k, show_progress=False
        )
        allowed_set = set(allowed) if allowed else None
        hits: list[tuple[float, str]] = []
        for index, score in zip(results[0], scores[0]):
            path = self.paths[int(index)]
            value = float(score)
            if value <= 0 or (allowed_set is not None and path not in allowed_set):
                continue
            hits.append((value, path))
            if len(hits) >= k:
                break
        return hits


if __name__ == "__main__":
    import sys

    pages = rag_index.wiki_pages(ROOT)
    metadata = build(ROOT, pages)
    print(f"✓ {rag_index.BM25_DIR} · {metadata['documents']} trang · bm25s")
    if len(sys.argv) > 1:
        for score, path in KeywordIndex(ROOT).search(" ".join(sys.argv[1:])):
            print(f"  {score:.4f}  {path}")
