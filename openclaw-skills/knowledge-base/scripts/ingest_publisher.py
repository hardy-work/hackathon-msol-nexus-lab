#!/usr/bin/env python3
"""Publish one gate-approved ingest without rebuilding tested artifacts.

The command commits only corpus paths from the isolated worktree, fast-forwards
the unchanged base branch, verifies the merged input digest, and transactionally
promotes the exact ``derived/`` directory covered by the release manifest.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_flow  # noqa: E402
import ingest_proposal  # noqa: E402
import ingest_runner  # noqa: E402
import release_manifest  # noqa: E402
import runtime_state  # noqa: E402
import versioning  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
ALLOWED_FILES = {
    "documents.yml",
    "originals/MANIFEST.sha256",
    "extract/van-docs.yml",
}
ALLOWED_PREFIXES = ("originals/", "raw/", "structured/", "wiki/", "ocr/")


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        [ingest_flow.git_executable(), *args], cwd=repo, text=True,
        capture_output=True,
    )
    if check and result.returncode:
        raise ValueError((result.stderr or result.stdout or "git failed").strip())
    return result.stdout.strip()


@contextlib.contextmanager
def publish_lock(state_root: Path) -> Iterator[None]:
    lock_path = runtime_state.state_dir(state_root) / "ingest-publish.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _changed_paths(worktree: Path) -> list[str]:
    tracked = _git(worktree, "diff", "--name-only", "HEAD").splitlines()
    untracked = _git(
        worktree, "ls-files", "--others", "--exclude-standard"
    ).splitlines()
    return sorted({path.strip() for path in [*tracked, *untracked] if path.strip()})


def _allowed_changes(worktree: Path, skill: Path) -> list[str]:
    skill_rel = skill.relative_to(worktree).as_posix()
    prefix = skill_rel + "/"
    changes = _changed_paths(worktree)
    if not changes:
        return []
    rejected: list[str] = []
    for path in changes:
        if not path.startswith(prefix):
            rejected.append(path)
            continue
        relative = path[len(prefix):]
        if relative in ALLOWED_FILES or relative.startswith(ALLOWED_PREFIXES):
            continue
        rejected.append(path)
    if rejected:
        raise ValueError(f"worktree có thay đổi ngoài corpus ingest: {rejected}")
    return changes


def _commit_worktree(worktree: Path, skill: Path, proposal: dict[str, Any]) -> str:
    changes = _allowed_changes(worktree, skill)
    if changes:
        _git(worktree, "add", "--", *changes)
        source_name = str((proposal.get("source") or {}).get("name") or "document")
        proposal_id = str(proposal["proposal_id"])
        message = f"ingest(kb): {source_name}\n\nProposal: {proposal_id}"
        _git(
            worktree, "-c", "user.name=NexusBot", "-c",
            "user.email=nexusbot@localhost", "commit", "-m", message,
        )
    head = _git(worktree, "rev-parse", "HEAD")
    if not head:
        raise ValueError("không xác định được ingest branch commit")
    return head


def _verify_artifact_copy(derived: Path, manifest: dict[str, Any]) -> None:
    errors: list[str] = []
    for relative, metadata in (manifest.get("artifacts") or {}).items():
        if not relative.startswith("derived/"):
            errors.append(f"artifact path ngoài derived/: {relative}")
            continue
        path = derived / relative[len("derived/"):]
        if not path.is_file():
            errors.append(f"thiếu {relative}")
            continue
        if path.stat().st_size != int(metadata.get("size", -1)):
            errors.append(f"size lệch {relative}")
            continue
        if release_manifest.sha256(path) != metadata.get("sha256"):
            errors.append(f"sha256 lệch {relative}")
        if len(errors) >= 20:
            break
    if errors:
        raise ValueError("artifact copy không khớp release manifest: " + "; ".join(errors))


def _promote_derived(source_skill: Path, canonical_skill: Path,
                     manifest: dict[str, Any]) -> None:
    source = source_skill / "derived"
    if not source.is_dir():
        raise ValueError("worktree thiếu derived/")
    parent = canonical_skill.parent
    token = uuid.uuid4().hex
    staging = parent / f".knowledge-base-derived-stage-{token}"
    backup = parent / f".knowledge-base-derived-backup-{token}"
    shutil.copytree(source, staging)
    _verify_artifact_copy(staging, manifest)
    current = canonical_skill / "derived"
    moved_current = False
    try:
        if current.exists() or current.is_symlink():
            os.replace(current, backup)
            moved_current = True
        os.replace(staging, current)
    except Exception:
        if not current.exists() and moved_current and backup.exists():
            os.replace(backup, current)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if backup.exists():
        shutil.rmtree(backup)


def _record_publish_failure(proposal_id: str, root: Path, error: Exception) -> None:
    try:
        proposal = ingest_proposal.load(proposal_id, root)
        proposal.setdefault("events", []).append({
            "type": "publish_failed",
            "at": ingest_runner._now(),
            "error": f"{type(error).__name__}: {error}",
        })
        proposal.setdefault("execution", {})["publish_error"] = (
            f"{type(error).__name__}: {error}"
        )
        ingest_proposal.save(proposal, root)
    except Exception:
        pass


def publish(proposal_id: str, *, root: Path = ROOT,
            runtime_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    proposal = ingest_proposal.load(proposal_id, root)
    if proposal.get("status") != "ready_to_publish":
        raise ingest_proposal.ProposalError(
            f"chỉ ready_to_publish mới được publish, hiện là {proposal.get('status')}"
        )
    ingest_proposal._assert_source_unchanged(proposal)
    execution = proposal.get("execution") or {}
    worktree = Path(str(execution.get("worktree") or "")).resolve()
    branch = str(execution.get("branch") or "")
    base = str(execution.get("base") or "main")
    base_commit = str(execution.get("base_commit") or "")
    if not branch or not base_commit or not (worktree / ".git").exists():
        raise ValueError("proposal thiếu worktree/branch/base_commit hợp lệ")

    repo = ingest_flow.REPO.resolve()
    canonical_skill = ingest_flow.skill_root(repo)
    configured_runtime = os.getenv("KNOWLEDGE_BASE_RUNTIME_ROOT", "").strip()
    if runtime_root is None and not configured_runtime:
        raise ValueError(
            "thiếu KNOWLEDGE_BASE_RUNTIME_ROOT: phải trỏ tới skill canonical "
            "(hoặc symlink resolve về canonical) trước khi publish"
        )
    runtime_root = (
        runtime_root or Path(configured_runtime)
    ).resolve()
    if runtime_root != canonical_skill.resolve():
        raise ValueError(
            "runtime root phải resolve tới canonical skill (dùng symlink nếu cần); "
            "publisher từ chối copy nhiều thư mục không atomic"
        )
    source_skill = ingest_flow.skill_root(worktree)

    try:
        with publish_lock(root):
            manifest = release_manifest.load(source_skill)
            release_manifest.validate(source_skill)
            validation = execution.get("validation") or {}
            release_info = validation.get("release") or {}
            if release_info.get("input_sha256") != manifest.get("input_sha256"):
                raise ValueError("proposal validation không khớp release manifest")

            branch_commit = _commit_worktree(worktree, source_skill, proposal)
            current_branch = _git(repo, "branch", "--show-current")
            if current_branch != base:
                raise ValueError(f"repo canonical phải ở branch {base}, hiện là {current_branch}")
            dirty = _git(repo, "status", "--porcelain", "--untracked-files=all")
            if dirty:
                raise ValueError("repo canonical có thay đổi chưa commit; từ chối publish")
            current_head = _git(repo, "rev-parse", "HEAD")
            already_merged = subprocess.run(
                [ingest_flow.git_executable(), "merge-base", "--is-ancestor",
                 branch_commit, current_head], cwd=repo,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0
            if not already_merged:
                if current_head != base_commit:
                    raise ValueError(
                        "base branch đã thay đổi sau khi ingest được test; cần rebase/rerun"
                    )
                _git(repo, "merge", "--ff-only", branch)

            merged_input = versioning.digest_hashes(versioning.file_hashes(canonical_skill))
            if merged_input != manifest.get("input_sha256"):
                raise ValueError(
                    "input digest sau merge không khớp worktree đã test; không promote artifact"
                )
            _promote_derived(source_skill, canonical_skill, manifest)
            release_manifest.validate(canonical_skill)
            freshness = versioning.check(canonical_skill)
            if freshness.get("state") != "fresh" or (
                (freshness.get("indexes") or {}).get("errors")
            ):
                raise ValueError("canonical corpus không fresh sau promote")

            result = ingest_runner.record_published(
                proposal_id, corpus_version=str(manifest["corpus_version"]),
                runtime_reloaded=True, root=root,
            )
            result["execution"].update({
                "publish_commit": _git(repo, "rev-parse", "HEAD"),
                "release_manifest": release_manifest.RELATIVE_PATH.as_posix(),
                "release_input_sha256": manifest["input_sha256"],
                "runtime_reload_mode": "digest-auto-reload",
                "runtime_root": str(canonical_skill),
            })
            ingest_proposal.save(result, root)
            return result
    except Exception as exc:
        _record_publish_failure(proposal_id, root, exc)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish one approved KB ingest")
    parser.add_argument("proposal_id")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="proposal state/corpus root used by the runner")
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = publish(
            args.proposal_id, root=args.root,
            runtime_root=args.runtime_root,
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            json.JSONDecodeError, ingest_proposal.ProposalError) as exc:
        print(f"✗ publish: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
