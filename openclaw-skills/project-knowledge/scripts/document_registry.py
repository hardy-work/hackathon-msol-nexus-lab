#!/usr/bin/env python3
"""Human-owned document identity/version registry helpers."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "documents.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = payload.get("documents") or []
    seen = set()
    currents = {}
    for doc in docs:
        key = (str(doc.get("doc_id")), int(doc.get("version", 0)))
        if not key[0] or key[1] <= 0 or key in seen:
            raise ValueError(f"documents.yml có định danh/version không hợp lệ hoặc trùng: {key}")
        seen.add(key)
        if doc.get("current"):
            if key[0] in currents:
                raise ValueError(f"doc_id {key[0]} có nhiều version current")
            currents[key[0]] = key[1]
        original = root / str(doc.get("original", ""))
        if not original.exists():
            raise ValueError(f"original không tồn tại: {doc.get('original')}")
        actual = sha256(original)
        if actual != doc.get("sha256"):
            raise ValueError(f"sha256 registry lệch: {doc.get('original')}")
        supersedes = doc.get("supersedes")
        if supersedes is not None and int(supersedes) >= key[1]:
            raise ValueError(f"{key[0]}@v{key[1]} supersedes phải nhỏ hơn version hiện tại")
    for doc in docs:
        supersedes = doc.get("supersedes")
        if supersedes is not None and (str(doc["doc_id"]), int(supersedes)) not in seen:
            raise ValueError(
                f"{doc['doc_id']}@v{doc['version']} supersedes version không tồn tại: {supersedes}"
            )
    return docs


def current(doc_id: str, root: Path = ROOT) -> dict[str, Any]:
    matches = [doc for doc in load(root) if doc.get("doc_id") == doc_id and doc.get("current")]
    if len(matches) != 1:
        raise KeyError(f"không có đúng một version current cho {doc_id}")
    return matches[0]


def by_version(doc_id: str, version: int, root: Path = ROOT) -> dict[str, Any]:
    return next(doc for doc in load(root)
                if doc.get("doc_id") == doc_id and int(doc.get("version")) == int(version))


def current_versions(root: Path = ROOT) -> dict[str, int]:
    return {str(doc["doc_id"]): int(doc["version"])
            for doc in load(root) if doc.get("current")}
