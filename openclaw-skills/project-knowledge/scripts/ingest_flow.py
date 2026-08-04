#!/usr/bin/env python3
"""Prepare and run the reviewed ingest flow in an isolated git worktree.

This script never merges to main. A human reviews the worktree diff after Gate
3 and performs the merge explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from document_registry import by_version
import intake
import reingest

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


def skill_root(worktree: Path) -> Path:
    """Accept either a repository worktree or a direct skill-root path."""
    nested = worktree / SKILL.relative_to(REPO)
    return nested if nested.is_dir() else worktree


def execute(worktree: Path, doc_id: str, version: int, review: bool) -> None:
    skill = skill_root(worktree)
    doc = by_version(doc_id, version, skill)
    scripts = skill / "scripts"
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    run([sys.executable, str(scripts / "gate1_integrity.py")], skill, env)
    run([sys.executable, str(scripts / "inventory.py")], skill, env)
    extractor = doc.get("extractor")
    if extractor == "nexus":
        run([sys.executable, str(scripts / "extract_nexus.py")], skill, env)
        if doc.get("supersedes") is not None:
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_one_to_one_pages(skill, plan)
            reingest.write_plan(skill, plan)
        run([sys.executable, str(scripts / "build_nexus_wiki.py")], skill, env)
    elif extractor == "van":
        run([sys.executable, str(scripts / "extract_van.py"), "--doc", doc_id], skill, env)
        run([sys.executable, str(scripts / "structure.py"), "--doc", doc_id], skill, env)
        if doc.get("supersedes") is not None:
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_one_to_one_pages(skill, plan)
            reingest.write_plan(skill, plan)
        run([sys.executable, str(scripts / "ingest_van.py"), "--doc", doc_id], skill, env)
    else:
        raise RuntimeError(
            f"document `{doc_id}@v{version}` có extractor `{extractor or 'missing'}` "
            "chưa được triển khai; chỉ Nexus XLSX và luồng văn DOCX/PDF được phép chạy"
        )
    run([sys.executable, str(scripts / "lint.py")], skill, env)
    if review:
        run([sys.executable, str(scripts / "review.py"), "--all"], skill, env)
    run([sys.executable, str(scripts / "build_db.py")], skill, env)
    run([sys.executable, str(scripts / "build_graph.py")], skill, env)
    run([sys.executable, str(scripts / "build_rag_indexes.py")], skill, env)
    run([sys.executable, str(scripts / "versioning.py"), "build", "--summary"], skill, env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path,
                        help="file upload; intake sẽ nhận diện identity/version")
    parser.add_argument("--doc-id",
                        help="xác nhận identity hiện có, hoặc dùng cùng --version ở legacy mode")
    parser.add_argument("--version", type=int,
                        help="version đã đăng ký ở legacy mode")
    parser.add_argument("--base", default="main")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worktree")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--review", dest="review", action="store_true", default=True,
                        help="chạy Gate 3b; mặc định bật khi ingest/run")
    parser.add_argument("--no-review", dest="review", action="store_false",
                        help="chỉ dùng cho fixture/offline; không được merge khi chưa review")
    args = parser.parse_args()
    if args.prepare and args.worktree:
        parser.error("dùng --prepare hoặc --worktree, không dùng đồng thời")
    if args.file and args.version is not None:
        parser.error("--version chỉ dùng ở legacy mode, không dùng cùng --file")

    if args.file:
        decision = intake.decide(SKILL, args.file, confirmed_doc_id=args.doc_id)
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        if decision["flow"] in {"identity_review", "duplicate", "no_op"}:
            if args.run:
                parser.error(f"intake flow `{decision['flow']}` không có version để chạy")
            return 2 if decision["flow"] == "identity_review" else 0
        version = int(decision.get("version") or decision.get("to_version"))
        branch = None
        if args.prepare:
            branch, worktree = prepare(str(decision["doc_id"]), version, args.base)
            target = skill_root(worktree)
        elif args.worktree:
            worktree = Path(args.worktree).resolve()
            target = skill_root(worktree)
        else:
            if args.run:
                parser.error("--run với --file cần --prepare hoặc --worktree")
            return 0
        registered = intake.register(target, args.file, decision)
        print(json.dumps({"registered": registered, "branch": branch, "worktree": str(worktree)},
                         ensure_ascii=False, indent=2))
        if args.run:
            execute(worktree, str(decision["doc_id"]), version, args.review)
            print("✓ gates passed; review git diff and merge manually")
        return 0

    if not args.doc_id or args.version is None:
        parser.error("cần --file, hoặc legacy mode với cả --doc-id và --version")
    if args.prepare:
        branch, worktree = prepare(args.doc_id, args.version, args.base)
        print(f"✓ {branch} -> {worktree}")
    else:
        worktree = Path(args.worktree).resolve() if args.worktree else REPO
    by_version(args.doc_id, args.version, skill_root(worktree))
    if args.run:
        execute(worktree, args.doc_id, args.version, args.review)
        print("✓ gates passed; review git diff and merge manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
