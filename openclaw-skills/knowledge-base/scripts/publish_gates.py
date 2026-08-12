#!/usr/bin/env python3
"""Fast release-blocking gates for one tested ingest worktree.

This is intentionally not the repository-wide regression suite.  It validates
the data and artifacts that will be published: immutable originals, registry,
lint/numeric/citation contracts, spreadsheet completeness where applicable,
DuckDB/graph/RAG readability, target-page coverage, and digest binding.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import document_registry  # noqa: E402
import embed_index  # noqa: E402
import gate1_integrity  # noqa: E402
import rag_index  # noqa: E402
import release_manifest  # noqa: E402
import spreadsheet_contract  # noqa: E402
import versioning  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "knowledge-base/publish-validation/v1"
REPORT_PATH = Path("derived/publish_validation.json")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _run(script: str, root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script)], cwd=root,
        text=True, capture_output=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        raise ValueError(f"{script} thất bại: {detail}")


def _gate1(root: Path) -> dict[str, Any]:
    manifest = root / "originals/MANIFEST.sha256"
    if not manifest.is_file():
        raise ValueError("Gate 1 thiếu originals/MANIFEST.sha256")
    current = gate1_integrity.scan() if root == gate1_integrity.ROOT else {
        path.relative_to(root / "originals").as_posix(): release_manifest.sha256(path)
        for path in sorted((root / "originals").rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.sha256", ".gitkeep"}
    }
    recorded: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, separator, relative = line.partition("  ")
        if not separator or not relative:
            raise ValueError("Gate 1 manifest có dòng không hợp lệ")
        recorded[relative] = digest
    missing = sorted(set(recorded) - set(current))
    new = sorted(set(current) - set(recorded))
    changed = sorted(
        name for name in set(current) & set(recorded)
        if current[name] != recorded[name]
    )
    if missing or new or changed:
        raise ValueError(
            f"Gate 1 lệch: missing={missing}, new={new}, changed={changed}"
        )
    return {"files": len(current), "status": "pass"}


def _target_pages(root: Path, doc_id: str, version: int) -> list[str]:
    pages: list[str] = []
    for relative, text in rag_index.wiki_pages(root):
        metadata = rag_index._frontmatter(text)
        try:
            matches = (
                str(metadata.get("doc_id") or "") == doc_id
                and int(metadata.get("version", 0)) == version
            )
        except (TypeError, ValueError):
            matches = False
        if matches:
            pages.append(relative)
    if not pages:
        raise ValueError(f"RAG corpus không có page current cho {doc_id}@v{version}")
    return pages


def _derived_smoke(root: Path, target_pages: list[str]) -> dict[str, Any]:
    freshness = versioning.check(root)
    index_errors = (freshness.get("indexes") or {}).get("errors") or []
    if freshness.get("state") != "fresh" or index_errors:
        raise ValueError(
            f"corpus/index stale: state={freshness.get('state')} errors={index_errors}"
        )

    database = root / "derived/facts.duckdb"
    if not database.is_file():
        raise ValueError("thiếu derived/facts.duckdb")
    connection = duckdb.connect(str(database), read_only=True)
    try:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    finally:
        connection.close()
    required_tables = {"dim_value", "person", "doc_cell", "coverage"}
    if not required_tables <= tables:
        raise ValueError(f"DuckDB thiếu tables: {sorted(required_tables - tables)}")

    graph_path = root / "derived/graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise ValueError("graph.json sai contract nodes/edges")

    paths = json.loads((root / "derived/bm25/paths.json").read_text(encoding="utf-8"))
    missing_bm25 = sorted(set(target_pages) - set(paths))
    if missing_bm25:
        raise ValueError(f"BM25 thiếu target pages: {missing_bm25}")

    semantic = embed_index.Semantic(root)
    result = semantic.collection.get(include=["metadatas"])
    vector_paths = {
        str((metadata or {}).get("path") or "")
        for metadata in result.get("metadatas") or []
    }
    missing_vector = sorted(set(target_pages) - vector_paths)
    if missing_vector:
        raise ValueError(f"Chroma thiếu target pages: {missing_vector}")
    return {
        "corpus_version": freshness.get("version"),
        "input_sha256": freshness.get("current_input_sha256"),
        "duckdb_tables": sorted(tables),
        "graph_nodes": len(graph["nodes"]),
        "graph_edges": len(graph["edges"]),
        "bm25_pages": len(paths),
        "vector_pages": len(vector_paths),
        "target_pages": target_pages,
    }


def run(root: Path, *, proposal_id: str, doc_id: str, version: int,
        review_artifact_path: Path | None = None,
        git_commit: str = "") -> dict[str, Any]:
    root = root.resolve()
    document = document_registry.by_version(doc_id, version, root)
    if not document.get("current"):
        raise ValueError(f"{doc_id}@v{version} không phải current version")

    checks: dict[str, Any] = {"gate1": _gate1(root)}
    # These are data/answer safety contracts, not the full code fixture suite.
    for script in ("lint.py", "numeric_guard.py", "access_control.py", "gate4_selftest.py"):
        _run(script, root)
        checks[script.removesuffix(".py")] = {"status": "pass"}

    if document.get("extractor") == "spreadsheet":
        checks["spreadsheet_completeness"] = spreadsheet_contract.validate(
            root, doc_id, version=version,
            review_artifact_path=review_artifact_path,
        )

    target_pages = _target_pages(root, doc_id, version)
    checks["derived"] = _derived_smoke(root, target_pages)
    report = {
        "schema": SCHEMA,
        "status": "pass",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "proposal_id": proposal_id,
        "doc_id": doc_id,
        "version": version,
        "checks": checks,
    }
    _atomic_json(root / REPORT_PATH, report)
    manifest = release_manifest.build(
        root, proposal_id=proposal_id, doc_id=doc_id, version=version,
        git_commit=git_commit,
    )
    release_manifest.validate(root)
    report["release"] = {
        "manifest": release_manifest.RELATIVE_PATH.as_posix(),
        "corpus_version": manifest["corpus_version"],
        "input_sha256": manifest["input_sha256"],
        "artifact_count": manifest["artifact_count"],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fast release-blocking ingest gates")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--review-artifact", type=Path)
    parser.add_argument("--git-commit", default="")
    args = parser.parse_args(argv)
    try:
        result = run(
            args.root, proposal_id=args.proposal_id, doc_id=args.doc_id,
            version=args.version, review_artifact_path=args.review_artifact,
            git_commit=args.git_commit,
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            json.JSONDecodeError) as exc:
        print(f"✗ publish gates: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
