#!/usr/bin/env python3
"""STAGE 5 · DERIVE — mandatory Chroma vector index over current wiki pages.

The index stores one embedding per Gate-3-approved wiki page, matching the
architecture diagram.  BGE-M3 is the production default.  The explicit
``hash`` backend is only for offline/CI contract runs where downloading a
2GB model is intentionally out of scope; it still exercises the real Chroma
store and query path.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

import numpy as np

import rag_index

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "BAAI/bge-m3"
HASH_MODEL_NAME = "deterministic-hash-v1"
HASH_DIM = 384
_model = None


def embedding_backend() -> str:
    value = os.getenv("KNOWLEDGE_BASE_EMBEDDING_BACKEND", "sentence-transformers")
    value = value.strip().lower()
    if value not in {"sentence-transformers", "hash"}:
        raise ValueError(
            "KNOWLEDGE_BASE_EMBEDDING_BACKEND phải là "
            "sentence-transformers hoặc hash"
        )
    return value


def model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _hash_encode(texts: list[str]) -> np.ndarray:
    """Small deterministic embedding used only by offline CI/demo fixtures."""
    vectors = np.zeros((len(texts), HASH_DIM), dtype="float32")
    for row, text in enumerate(texts):
        tokens = re.findall(r"\w+", text.lower(), re.UNICODE)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % HASH_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vectors[row, index] += sign
        norm = float(np.linalg.norm(vectors[row]))
        if norm:
            vectors[row] /= norm
    return vectors


def encode(texts: list[str], backend: str | None = None) -> np.ndarray:
    backend = backend or embedding_backend()
    if backend == "hash":
        return _hash_encode(texts)
    return model().encode(
        texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False
    ).astype("float32")


def _client(root: Path):
    import chromadb
    from chromadb.config import Settings

    return chromadb.PersistentClient(
        path=str(root / rag_index.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def build(root: Path = ROOT, pages: list[tuple[str, str]] | None = None) -> dict:
    pages = pages if pages is not None else rag_index.wiki_pages(root)
    if not pages:
        raise RuntimeError("không có current wiki page để dựng Chroma")
    backend = embedding_backend()
    destination = root / rag_index.CHROMA_DIR
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    paths = [path for path, _ in pages]
    documents = [text for _, text in pages]
    vectors = encode(documents, backend)
    client = _client(root)
    collection = client.get_or_create_collection(
        name=rag_index.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[f"wiki-{index:06d}" for index in range(len(paths))],
        embeddings=vectors.tolist(),
        documents=documents,
        metadatas=[{"path": path} for path in paths],
    )
    return {
        "backend": "chroma",
        "path": rag_index.CHROMA_DIR,
        "collection": rag_index.CHROMA_COLLECTION,
        "documents": len(paths),
        "embedding_backend": backend,
        "model": MODEL_NAME if backend == "sentence-transformers" else HASH_MODEL_NAME,
        "dimension": int(vectors.shape[1]),
    }


class Semantic:
    """Read-only Chroma search facade for Bậc 2 semantic retrieval."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        manifest = rag_index.load_manifest(root)
        if not manifest or (manifest.get("vector") or {}).get("backend") != "chroma":
            raise FileNotFoundError(
                f"chưa có Chroma index; chạy {rag_index.MANIFEST} bằng "
                "scripts/build_rag_indexes.py"
            )
        self.backend = str((manifest.get("vector") or {}).get("embedding_backend", ""))
        self.client = _client(root)
        self.collection = self.client.get_collection(name=rag_index.CHROMA_COLLECTION)
        if self.collection.count() != int(manifest.get("page_count") or 0):
            raise RuntimeError("Chroma document count lệch rag_indexes.json")

    def search(self, query: str, k: int = 5,
               allowed: list[str] | set[str] | None = None) -> list[tuple[float, str]]:
        count = self.collection.count()
        if not query.strip() or not count:
            return []
        requested = min(count, max(k * 8, k))
        result = self.collection.query(
            query_embeddings=encode([query], self.backend).tolist(),
            n_results=requested,
            include=["metadatas", "distances"],
        )
        allowed_set = set(allowed) if allowed else None
        hits: list[tuple[float, str]] = []
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for metadata, distance in zip(metadatas, distances):
            path = str((metadata or {}).get("path", ""))
            if not path or (allowed_set is not None and path not in allowed_set):
                continue
            hits.append((1.0 - float(distance), path))
            if len(hits) >= k:
                break
        return hits


if __name__ == "__main__":
    import sys

    pages = rag_index.wiki_pages(ROOT)
    metadata = build(ROOT, pages)
    print(f"✓ {rag_index.CHROMA_DIR} · {metadata['documents']} trang · "
          f"{metadata['embedding_backend']}")
    if len(sys.argv) > 1:
        for score, path in Semantic(ROOT).search(" ".join(sys.argv[1:])):
            print(f"  {score:.4f}  {path}")
