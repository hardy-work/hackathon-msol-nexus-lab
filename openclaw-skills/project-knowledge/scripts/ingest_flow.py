#!/usr/bin/env python3
"""Prepare and run the reviewed ingest flow in an isolated git worktree.

This script never merges to main. A human reviews the worktree diff after Gate
3 and performs the merge explicitly.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from document_registry import by_version

SKILL = Path(__file__).resolve().parent.parent
REPO = next(parent for parent in SKILL.parents if (parent / ".git").exists())


def git_executable() -> str:
    found = shutil.which("git")
    if found:
        return found
    candidate = Path(r"C:\Program Files\Git\cmd\git.exe")
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError("không tìm thấy git")


def run(command: list[str], cwd: Path, env=None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def prepare(doc_id: str, version: int, base: str) -> tuple[str, Path]:
    branch = f"ingest/{doc_id}@v{version}"
    worktree = REPO / ".ingest-worktrees" / re_safe(branch)
    if worktree.exists():
        raise FileExistsError(f"worktree đã tồn tại: {worktree}")
    worktree.parent.mkdir(exist_ok=True)
    run([git_executable(), "worktree", "add", "-b", branch, str(worktree), base], REPO)
    return branch, worktree


def re_safe(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_.@" else "-" for ch in value)


def execute(worktree: Path, doc_id: str, version: int, review: bool) -> None:
    skill = worktree / SKILL.relative_to(REPO)
    doc = by_version(doc_id, version, skill)
    scripts = skill / "scripts"
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    run([sys.executable, str(scripts / "gate1_integrity.py")], skill, env)
    run([sys.executable, str(scripts / "inventory.py")], skill, env)
    extractor = doc.get("extractor")
    if extractor == "nexus":
        run([sys.executable, str(scripts / "extract_nexus.py")], skill, env)
        run([sys.executable, str(scripts / "build_nexus_wiki.py")], skill, env)
    else:
        run([sys.executable, str(scripts / "extract_van.py"), "--doc", doc_id], skill, env)
        run([sys.executable, str(scripts / "structure.py"), "--doc", doc_id], skill, env)
        run([sys.executable, str(scripts / "ingest_van.py"), "--doc", doc_id], skill, env)
    run([sys.executable, str(scripts / "lint.py")], skill, env)
    if review:
        run([sys.executable, str(scripts / "review.py"), "--all"], skill, env)
    run([sys.executable, str(scripts / "build_db.py")], skill, env)
    run([sys.executable, str(scripts / "build_graph.py")], skill, env)
    run([sys.executable, str(scripts / "versioning.py"), "build", "--summary"], skill, env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worktree")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--review", action="store_true")
    args = parser.parse_args()
    by_version(args.doc_id, args.version, SKILL)
    if args.prepare:
        branch, worktree = prepare(args.doc_id, args.version, args.base)
        print(f"✓ {branch} -> {worktree}")
    else:
        worktree = Path(args.worktree).resolve() if args.worktree else REPO
    if args.run:
        execute(worktree, args.doc_id, args.version, args.review)
        print("✓ gates passed; review git diff and merge manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
