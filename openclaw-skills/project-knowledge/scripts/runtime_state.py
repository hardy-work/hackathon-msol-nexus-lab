#!/usr/bin/env python3
"""Resolve persistent runtime state outside rebuildable corpus artifacts."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def state_dir(root: Path = ROOT) -> Path:
    """Return the writable operational-state directory for one runtime root.

    The corpus itself remains read-only.  `.runtime` is intentionally outside
    `originals/`, `raw/`, `structured/`, `wiki/` and `derived/`; production can
    replace it with a separate persistent volume.
    """
    default = Path(root).resolve() / ".runtime"
    path = Path(os.getenv("PROJECT_KNOWLEDGE_STATE_DIR", str(default))).expanduser().resolve()
    corpus_dirs = tuple(Path(root).resolve() / name
                        for name in ("originals", "raw", "structured", "wiki", "derived"))
    corpus_files = tuple(Path(root).resolve() / name
                         for name in ("documents.yml", "schema.yml", "coverage.yml", "access.yml"))
    if path == Path(root).resolve() or any(path == item or item in path.parents
                                          for item in (*corpus_dirs, *corpus_files)):
        raise ValueError(f"PROJECT_KNOWLEDGE_STATE_DIR nằm trong corpus read-only: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(name: str, root: Path = ROOT) -> Path:
    return state_dir(root) / name
