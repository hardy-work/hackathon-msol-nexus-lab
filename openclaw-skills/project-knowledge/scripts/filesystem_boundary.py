#!/usr/bin/env python3
"""Filesystem boundary for the read-only knowledge query runtime.

The query side may read the reviewed corpus and derived indexes, but it must
never follow a path supplied by a corpus artifact outside the skill root.  The
runtime's cache/queue/telemetry are a separate operational state area and are
not part of this read-only corpus.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


class BoundaryError(ValueError):
    """Raised when a runtime path escapes the configured corpus boundary."""


CORPUS_DIRS = ("originals", "raw", "structured", "wiki", "derived")
CORPUS_FILES = ("documents.yml", "schema.yml", "coverage.yml", "access.yml")
STATE_DIR_NAME = ".runtime"


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class ReadOnlyCorpus:
    """Allowlisted, symlink-safe view of one skill/worktree root.

    This is a logical boundary: files are opened read-only by callers, while
    the OS/container should additionally mount the corpus read-only in
    production.  The class makes accidental path traversal fail closed even
    when the mount is misconfigured.
    """

    def __init__(self, root: Path):
        candidate = Path(root).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise BoundaryError(f"corpus root không phải thư mục: {candidate}")
        self.root = candidate

    def resolve(self, relative: str | Path, *, must_exist: bool = False) -> Path:
        """Resolve a corpus-relative path and reject absolute/traversal paths."""
        value = Path(relative)
        if value.is_absolute():
            raise BoundaryError(f"runtime chỉ nhận đường dẫn tương đối: {relative}")
        path = (self.root / value).resolve(strict=False)
        if not _inside(path, self.root):
            raise BoundaryError(f"đường dẫn vượt read-only corpus boundary: {relative}")
        if must_exist and not path.exists():
            raise FileNotFoundError(path)
        return path

    def read_text(self, relative: str | Path, *, encoding: str = "utf-8") -> str:
        return self.resolve(relative, must_exist=True).read_text(encoding=encoding)

    def read_bytes(self, relative: str | Path) -> bytes:
        return self.resolve(relative, must_exist=True).read_bytes()

    def exists(self, relative: str | Path) -> bool:
        return self.resolve(relative).exists()

    def files(self, relative_dir: str | Path, pattern: str = "*") -> Iterator[Path]:
        """Yield only real files below an allowlisted corpus-relative directory."""
        directory = self.resolve(relative_dir, must_exist=False)
        if not directory.is_dir():
            return
        for path in sorted(directory.rglob(pattern)):
            # resolve() catches symlinks which point outside the corpus.
            resolved = self.resolve(path.relative_to(self.root), must_exist=False)
            if path.is_symlink():
                raise BoundaryError(f"symlink không được phép trong corpus: {path}")
            if resolved.is_file():
                yield resolved

    def assert_safe(self) -> None:
        """Validate all corpus inputs/indexes before a long-lived runtime starts."""
        for name in CORPUS_FILES:
            path = self.resolve(name, must_exist=False)
            if path.exists() and path.is_symlink():
                raise BoundaryError(f"symlink không được phép: {name}")
        for name in CORPUS_DIRS:
            directory = self.resolve(name, must_exist=False)
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                # Do not follow a symlink merely to inspect it.
                if path.is_symlink():
                    target = path.resolve(strict=False)
                    if not _inside(target, self.root):
                        raise BoundaryError(
                            f"symlink thoát read-only corpus boundary: {path.relative_to(self.root)}"
                        )
                    raise BoundaryError(
                        f"symlink không được phép trong read-only corpus: {path.relative_to(self.root)}"
                    )
                if path.is_file():
                    self.resolve(path.relative_to(self.root), must_exist=True)

    def assert_state_separate(self, state: Path) -> Path:
        """Allow state in `.runtime` or a separate volume, never in corpus data."""
        resolved = Path(state).expanduser().resolve(strict=False)
        corpus_paths = [self.resolve(name, must_exist=False) for name in CORPUS_DIRS + CORPUS_FILES]
        if any(resolved == path or path in resolved.parents for path in corpus_paths):
            raise BoundaryError(
                f"runtime state không được nằm trong corpus read-only: {resolved}"
            )
        if resolved == self.root:
            raise BoundaryError("runtime state không được trỏ vào skill root")
        return resolved


def default_root() -> Path:
    return Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    corpus = ReadOnlyCorpus(default_root())
    corpus.assert_safe()
    print(f"✓ read-only corpus boundary: {corpus.root}")
