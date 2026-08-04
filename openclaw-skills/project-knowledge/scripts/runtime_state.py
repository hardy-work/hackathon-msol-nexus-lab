#!/usr/bin/env python3
"""Resolve persistent runtime state outside rebuildable corpus artifacts."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def state_dir() -> Path:
    path = Path(os.getenv("PROJECT_KNOWLEDGE_STATE_DIR", str(ROOT / ".runtime"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(name: str) -> Path:
    return state_dir() / name
