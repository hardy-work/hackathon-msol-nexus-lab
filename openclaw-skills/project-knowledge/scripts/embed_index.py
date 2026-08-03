#!/usr/bin/env python3
"""STAGE 5 · DERIVE — chỉ mục NGỮ NGHĨA (bậc 2 vector) trên TRANG WIKI.

Theo sơ đồ (node 36/77): embed CẢ TRANG wiki đã tổng hợp, KHÔNG index chunk thô.
Trang wiki là đơn vị đã qua Gate 3; embed nó giữ nguyên nguyên tắc "chỉ đọc thứ đã
duyệt". Model bge-m3 chạy LOCAL (không cần API key) — đa ngữ Việt/Nhật/Anh, hợp corpus.

Chroma là overkill cho vài chục trang → vector store = một file numpy trong derived/
(tầng dẫn xuất, .gitignore, xoá đi dựng lại được). Cùng vai trò, ít phụ thuộc hơn.

  python3 scripts/embed_index.py            # dựng chỉ mục
  python3 scripts/embed_index.py "câu hỏi"  # dựng xong thử tra
"""
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
VEC = ROOT / "derived" / "wiki_vectors.npz"
MODEL_NAME = "BAAI/bge-m3"

_model = None


def model():
    """Nạp bge-m3 một lần. Nặng (~2GB RAM, ~5s) nên lười — chỉ nạp khi thật cần."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def wiki_pages():
    """(rel_path, text) của các trang NỘI DUNG. Bỏ index.md (catalog của bậc 0) và
    log.md (nhật ký, không phải tri thức)."""
    out = []
    for p in sorted(WIKI.rglob("*.md")):
        if p.name in ("index.md", "log.md"):
            continue
        out.append((p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8")))
    return out


def build():
    pages = wiki_pages()
    if not pages:
        print("không có trang wiki nào để embed")
        return 1
    texts = [t for _, t in pages]
    vecs = model().encode(texts, normalize_embeddings=True,
                          batch_size=8, show_progress_bar=False).astype("float32")
    VEC.parent.mkdir(exist_ok=True)
    np.savez(VEC, vecs=vecs, paths=np.array([p for p, _ in pages]), model=MODEL_NAME)
    print(f"✓ {VEC.relative_to(ROOT)} · {len(pages)} trang wiki · dim {vecs.shape[1]} · {MODEL_NAME}")
    return 0


class Semantic:
    """Tra ngữ nghĩa: cosine giữa câu hỏi và từng TRANG wiki (vector đã chuẩn hoá
    nên cosine = tích vô hướng)."""

    def __init__(self):
        if not VEC.exists():
            raise FileNotFoundError("chưa có derived/wiki_vectors.npz — chạy: "
                                    "python3 scripts/embed_index.py")
        d = np.load(VEC, allow_pickle=False)
        self.vecs = d["vecs"]
        self.paths = [str(x) for x in d["paths"]]

    def search(self, q, k=5):
        """-> [(điểm_cosine, trang)] giảm dần."""
        qv = model().encode([q], normalize_embeddings=True).astype("float32")[0]
        sims = self.vecs @ qv
        order = np.argsort(-sims)[:k]
        return [(float(sims[i]), self.paths[i]) for i in order]


if __name__ == "__main__":
    q = " ".join(a for a in sys.argv[1:])
    rc = build()
    if rc == 0 and q:
        print(f"\ntop trang cho: {q!r}\n")
        for sc, p in Semantic().search(q, k=5):
            print(f"  {sc:5.3f}  {p}")
    sys.exit(rc)
