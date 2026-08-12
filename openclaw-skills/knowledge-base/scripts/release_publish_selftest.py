#!/usr/bin/env python3
"""Offline contract for release hashing and one-command artifact promotion."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

import ingest_flow
import ingest_proposal
import ingest_publisher
import release_manifest
import versioning


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _write_derived(root: Path) -> dict:
    (root / "derived/bm25").mkdir(parents=True, exist_ok=True)
    (root / "derived/chroma").mkdir(parents=True, exist_ok=True)
    (root / "derived/facts.duckdb").write_bytes(b"tested-duckdb")
    (root / "derived/graph.json").write_text(
        '{"nodes": [], "edges": []}\n', encoding="utf-8"
    )
    (root / "derived/bm25/paths.json").write_text(
        '["wiki/sources/upload.md"]\n', encoding="utf-8"
    )
    (root / "derived/chroma/chroma.sqlite3").write_bytes(b"tested-chroma")
    input_sha = versioning.digest_hashes(versioning.file_hashes(root))
    (root / "derived/rag_indexes.json").write_text(json.dumps({
        "schema": "nexus-rag-indexes/v1",
        "input_sha256": input_sha,
        "page_count": 1,
        "bm25": {"backend": "bm25s"},
        "vector": {"backend": "chroma", "collection": "nexus-wiki"},
    }), encoding="utf-8")
    versioning.build(root, generated_at="2026-08-12T00:00:00+00:00")
    return release_manifest.build(
        root, proposal_id="proposal-test", doc_id="upload", version=1,
        git_commit="base",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kb-release-publish-") as temp:
        temp_root = Path(temp)
        repo = temp_root / "repo"
        skill = repo / "openclaw-skills/knowledge-base"
        for directory in (
            "scripts", "originals", "raw", "structured", "wiki/sources",
        ):
            (skill / directory).mkdir(parents=True, exist_ok=True)
        (repo / ".gitignore").write_text(
            ".ingest-worktrees/\nopenclaw-skills/knowledge-base/derived/\n",
            encoding="utf-8",
        )
        (skill / "documents.yml").write_text("documents: []\n", encoding="utf-8")
        (skill / "scripts/.keep").write_text("fixture\n", encoding="utf-8")
        (skill / "schema.yml").write_text("dimensions: {}\n", encoding="utf-8")
        (skill / "coverage.yml").write_text("[]\n", encoding="utf-8")
        (skill / "access.yml").write_text("default_visibility: internal\n", encoding="utf-8")
        (skill / "wiki/index.md").write_text("# Index\n", encoding="utf-8")
        (skill / "wiki/log.md").write_text("# Log\n", encoding="utf-8")
        (skill / "originals/MANIFEST.sha256").write_text(
            "# empty base\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(repo), "-c", "user.name=fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "base",
        ], check=True)
        base_commit = _git(repo, "rev-parse", "HEAD")

        old_repo, old_skill = ingest_flow.REPO, ingest_flow.SKILL
        old_state = os.environ.get("KNOWLEDGE_BASE_STATE_DIR")
        state = temp_root / "state"
        os.environ["KNOWLEDGE_BASE_STATE_DIR"] = str(state)
        try:
            ingest_flow.REPO = repo
            ingest_flow.SKILL = skill
            branch, worktree = ingest_flow.prepare("upload", 1, "main")
            staged = ingest_flow.skill_root(worktree)
            source = temp_root / "upload.xlsx"
            source.write_bytes(b"xlsx-fixture")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            original = staged / "originals/upload.xlsx"
            original.write_bytes(source.read_bytes())
            (staged / "originals/MANIFEST.sha256").write_text(
                f"{source_hash}  upload.xlsx\n", encoding="utf-8"
            )
            (staged / "raw").mkdir(exist_ok=True)
            (staged / "wiki/sources").mkdir(parents=True, exist_ok=True)
            (staged / "raw/upload.md").write_text("raw upload\n", encoding="utf-8")
            (staged / "wiki/sources/upload.md").write_text(
                "---\npage: source\ndoc_id: upload\nversion: 1\n---\nsource\n",
                encoding="utf-8",
            )
            (staged / "documents.yml").write_text(yaml.safe_dump({"documents": [{
                "doc_id": "upload", "version": 1,
                "original": "originals/upload.xlsx", "sha256": source_hash,
                "current": True, "supersedes": None, "raw_paths": ["raw/upload.md"],
            }]}, sort_keys=False), encoding="utf-8")
            manifest = _write_derived(staged)
            assert release_manifest.validate(staged)["status"] == "pass"

            proposal_id = "proposal-test"
            proposal = {
                "schema": ingest_proposal.SCHEMA,
                "proposal_id": proposal_id,
                "status": "ready_to_publish",
                "source": {"path": str(source), "name": source.name,
                           "sha256": source_hash},
                "requested_by": {"user_id": "U0APQSSGKTM", "name": "fixture"},
                "events": [],
                "execution": {
                    "status": "gates_passed", "base": "main",
                    "base_commit": base_commit, "branch": branch,
                    "worktree": str(worktree),
                    "validation": {"release": {
                        "input_sha256": manifest["input_sha256"],
                    }},
                },
            }
            ingest_proposal.save(proposal, skill)
            old_runtime_root = os.environ.pop("KNOWLEDGE_BASE_RUNTIME_ROOT", None)
            try:
                try:
                    ingest_publisher.publish(proposal_id, root=skill)
                except ValueError as exc:
                    assert "KNOWLEDGE_BASE_RUNTIME_ROOT" in str(exc)
                else:
                    raise AssertionError("publish thiếu runtime root phải fail closed")
            finally:
                if old_runtime_root is not None:
                    os.environ["KNOWLEDGE_BASE_RUNTIME_ROOT"] = old_runtime_root
            published = ingest_publisher.publish(
                proposal_id, root=skill, runtime_root=skill
            )
            assert published["status"] == "published"
            assert (skill / "originals/upload.xlsx").read_bytes() == b"xlsx-fixture"
            assert (skill / "derived/facts.duckdb").read_bytes() == b"tested-duckdb"
            assert release_manifest.validate(skill)["status"] == "pass"

            (skill / "derived/graph.json").write_text("{}\n", encoding="utf-8")
            try:
                release_manifest.validate(skill)
            except ValueError as exc:
                assert "sha256 lệch" in str(exc) or "size lệch" in str(exc)
            else:
                raise AssertionError("artifact bị sửa phải fail release validation")
        finally:
            ingest_flow.REPO, ingest_flow.SKILL = old_repo, old_skill
            if old_state is None:
                os.environ.pop("KNOWLEDGE_BASE_STATE_DIR", None)
            else:
                os.environ["KNOWLEDGE_BASE_STATE_DIR"] = old_state

    print("✓ release/publish self-test: digest + ff-only merge + exact artifact promotion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
