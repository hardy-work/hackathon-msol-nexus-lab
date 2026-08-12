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


def _repo_root() -> Path:
    """Resolve the Git repository used for isolated ingest worktrees.

    The deployed OpenClaw workspace is a runtime copy and intentionally does
    not contain ``.git``.  The host runner must therefore point at the
    checked-out repository explicitly.  Local development keeps the previous
    auto-discovery behaviour.
    """
    configured = os.getenv("KNOWLEDGE_BASE_REPO", "").strip()
    if configured:
        repo = Path(configured).expanduser().resolve()
        if (repo / ".git").exists():
            return repo
        raise RuntimeError(
            "KNOWLEDGE_BASE_REPO phải trỏ tới Git repository có .git: "
            f"{repo}"
        )
    for parent in (SKILL, *SKILL.parents):
        if (parent / ".git").exists():
            return parent
    raise RuntimeError(
        "Không tìm thấy Git repository. Khi chạy từ workspace deploy, "
        "hãy đặt KNOWLEDGE_BASE_REPO tới repo chính."
    )


REPO = _repo_root()


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


def _looks_like_skill_root(path: Path) -> bool:
    """Return whether ``path`` contains the corpus contract used by intake."""
    return (path / "documents.yml").is_file() and (path / "scripts").is_dir()


def skill_root(worktree: Path) -> Path:
    """Resolve the knowledge-base root in repo and runtime-copy layouts.

    The ingest runner is intentionally executed from the checked-out host
    repository.  Some deployments still import it from a copied OpenClaw
    skill, though, so ``SKILL`` may not be below ``REPO``.  In that case the
    worktree is the repository root and the canonical skill is normally under
    ``openclaw-skills/knowledge-base``.  Returning the repository root here
    would make intake look for ``documents.yml`` in the wrong directory.
    """
    worktree = Path(worktree).resolve()
    if _looks_like_skill_root(worktree):
        return worktree

    candidates: list[Path] = []
    try:
        candidates.append(worktree / SKILL.relative_to(REPO))
    except ValueError:
        # Runtime copy outside the host repository. Prefer the standard repo
        # layout, while allowing a custom relative path for another checkout.
        configured = os.getenv("KNOWLEDGE_BASE_SKILL_RELATIVE", "").strip()
        if configured:
            candidates.append(worktree / Path(configured))
        candidates.extend([
            worktree / "openclaw-skills" / SKILL.name,
            worktree / "skills" / SKILL.name,
            worktree / SKILL.name,
        ])

    for candidate in candidates:
        if _looks_like_skill_root(candidate):
            return candidate
    raise RuntimeError(
        "Không tìm thấy knowledge-base root trong worktree: "
        f"{worktree}. Cần documents.yml + scripts/ hoặc đặt "
        "KNOWLEDGE_BASE_SKILL_RELATIVE."
    )


def changed_wiki_pages(worktree: Path, skill: Path) -> list[str]:
    """Return changed wiki pages in an isolated repository worktree.

    A new ingest must review the pages it writes, not re-review the whole
    corpus. The latter is both wasteful and unsafe for source/index pages
    whose raw inputs can exceed the review model context. ``worktree`` is
    required to be a Git worktree here; direct skill-root fixtures run with
    ``review=False`` and should not silently skip Gate 3b.
    """
    try:
        skill_rel = skill.relative_to(worktree).as_posix()
    except ValueError as exc:
        raise RuntimeError(
            "Gate 3b cần isolated Git worktree để xác định các trang wiki thay đổi"
        ) from exc
    if not (worktree / ".git").exists():
        raise RuntimeError(
            "Gate 3b cần isolated Git worktree có .git; không chạy review trên "
            "workspace runtime trực tiếp"
        )

    result = subprocess.run(
        [git_executable(), "status", "--short", "--untracked-files=all"],
        cwd=worktree, capture_output=True, text=True, check=True,
    )
    prefix = f"{skill_rel}/wiki/"
    pages: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename status: review the destination path
            path = path.rsplit(" -> ", 1)[1]
        if not path.startswith(prefix) or not path.endswith(".md"):
            continue
        relative = path[len(skill_rel) + 1:]
        if relative in {"wiki/index.md", "wiki/log.md"}:
            continue
        if (worktree / path).is_file():
            pages.add(relative)
    return sorted(pages)


def review_changed_pages(worktree: Path, skill: Path, scripts: Path, env=None) -> None:
    """Run Gate 3b only for wiki pages written by this ingest."""
    pages = changed_wiki_pages(worktree, skill)
    if not pages:
        raise RuntimeError("ingest không tạo hoặc thay đổi trang wiki nào để review")
    for page in pages:
        run([sys.executable, str(scripts / "review.py"), "--page", page], skill, env)


def execute(worktree: Path, doc_id: str, version: int, review: bool) -> None:
    skill = skill_root(worktree)
    doc = by_version(doc_id, version, skill)
    scripts = skill / "scripts"
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    plan_path = None
    run([sys.executable, str(scripts / "gate1_integrity.py")], skill, env)
    run([sys.executable, str(scripts / "inventory.py")], skill, env)
    extractor = doc.get("extractor")
    if extractor == "nexus":
        run([sys.executable, str(scripts / "extract_nexus.py")], skill, env)
        if doc.get("supersedes") is not None:
            reingest.reconcile_artifacts(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_retired_pages(skill, plan)
            reingest.archive_one_to_one_pages(skill, plan)
            plan_path = reingest.write_plan(skill, plan)
        command = [sys.executable, str(scripts / "build_nexus_wiki.py")]
        if plan_path:
            command += ["--plan", str(plan_path.relative_to(skill))]
        run(command, skill, env)
    elif extractor == "spreadsheet":
        run([sys.executable, str(scripts / "extract_spreadsheet.py"), "--doc", doc_id],
            skill, env)
        if doc.get("supersedes") is not None:
            reingest.reconcile_artifacts(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_retired_pages(skill, plan)
            reingest.archive_one_to_one_pages(skill, plan)
            plan_path = reingest.write_plan(skill, plan)
        command = [sys.executable, str(scripts / "ingest_spreadsheet.py"), "--doc", doc_id]
        if plan_path:
            command += ["--plan", str(plan_path.relative_to(skill))]
        run(command, skill, env)
    elif extractor == "van":
        run([sys.executable, str(scripts / "extract_van.py"), "--doc", doc_id], skill, env)
        run([sys.executable, str(scripts / "structure.py"), "--doc", doc_id], skill, env)
        if doc.get("supersedes") is not None:
            reingest.reconcile_artifacts(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_retired_pages(skill, plan)
            reingest.archive_one_to_one_pages(skill, plan)
            plan_path = reingest.write_plan(skill, plan)
        command = [sys.executable, str(scripts / "ingest_van.py"), "--doc", doc_id]
        if plan_path:
            command += ["--plan", str(plan_path.relative_to(skill))]
        run(command, skill, env)
    elif extractor == "markdown":
        run([sys.executable, str(scripts / "extract_markdown.py"), "--doc", doc_id], skill, env)
        if doc.get("supersedes") is not None:
            reingest.reconcile_artifacts(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            plan = reingest.build_plan(
                skill, doc_id, int(doc["supersedes"]), int(version)
            )
            reingest.archive_retired_pages(skill, plan)
            reingest.archive_one_to_one_pages(skill, plan)
            plan_path = reingest.write_plan(skill, plan)
        command = [sys.executable, str(scripts / "ingest_markdown.py"), "--doc", doc_id]
        if plan_path:
            command += ["--plan", str(plan_path.relative_to(skill))]
        run(command, skill, env)
    else:
        raise RuntimeError(
            f"document `{doc_id}@v{version}` có extractor `{extractor or 'missing'}` "
            "chưa được triển khai; hiện hỗ trợ Nexus XLSX, generic XLSX, DOCX/PDF và Markdown"
        )
    run([sys.executable, str(scripts / "lint.py")], skill, env)
    if review:
        command = [sys.executable, str(scripts / "review.py")]
        if plan_path:
            command += ["--plan", str(plan_path.relative_to(skill))]
            run(command, skill, env)
        else:
            review_changed_pages(worktree, skill, scripts, env)
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
