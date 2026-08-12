#!/usr/bin/env python3
"""Content-addressed release manifest for tested Knowledge Base artifacts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import versioning  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "knowledge-base/release-manifest/v1"
RELATIVE_PATH = Path("derived/release_manifest.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_files(root: Path) -> list[Path]:
    derived = root / "derived"
    if not derived.is_dir():
        raise ValueError("thiếu derived/ để tạo release manifest")
    destination = root / RELATIVE_PATH
    return sorted(
        path for path in derived.rglob("*")
        if path.is_file() and path != destination and not path.name.endswith(".tmp")
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def build(root: Path = ROOT, *, proposal_id: str = "", doc_id: str = "",
          version: int | None = None, git_commit: str = "") -> dict[str, Any]:
    root = root.resolve()
    corpus_path = root / "derived/corpus_version.json"
    if not corpus_path.is_file():
        raise ValueError("thiếu derived/corpus_version.json")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    input_sha = versioning.digest_hashes(versioning.file_hashes(root))
    if corpus.get("input_sha256") != input_sha:
        raise ValueError("corpus_version không khớp input hiện tại")

    artifacts = {
        path.relative_to(root).as_posix(): {
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
        for path in artifact_files(root)
    }
    required = {
        "derived/facts.duckdb",
        "derived/graph.json",
        "derived/rag_indexes.json",
        "derived/corpus_version.json",
        "derived/bm25/paths.json",
    }
    missing = sorted(required - set(artifacts))
    if missing:
        raise ValueError(f"release thiếu artifact bắt buộc: {missing}")
    if not any(name.startswith("derived/chroma/") for name in artifacts):
        raise ValueError("release thiếu Chroma artifact")

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "proposal_id": proposal_id,
        "doc_id": doc_id,
        "document_version": version,
        "git_commit": git_commit,
        "corpus_version": corpus.get("version"),
        "input_sha256": input_sha,
        "source_sha256": corpus.get("source_sha256"),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    _atomic_json(root / RELATIVE_PATH, payload)
    return payload


def load(root: Path = ROOT) -> dict[str, Any]:
    path = root / RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"thiếu {RELATIVE_PATH.as_posix()}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("release manifest hỏng JSON") from exc
    if payload.get("schema") != SCHEMA:
        raise ValueError("release manifest sai schema")
    return payload


def validate(root: Path = ROOT, *, expected_input_sha256: str | None = None,
             strict_files: bool = True) -> dict[str, Any]:
    root = root.resolve()
    payload = load(root)
    current_input = versioning.digest_hashes(versioning.file_hashes(root))
    expected = expected_input_sha256 or payload.get("input_sha256")
    if current_input != expected or payload.get("input_sha256") != expected:
        raise ValueError("release input digest không khớp corpus hiện tại")

    recorded = payload.get("artifacts") or {}
    errors: list[str] = []
    for relative, metadata in recorded.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"thiếu {relative}")
            continue
        if path.stat().st_size != int(metadata.get("size", -1)):
            errors.append(f"size lệch {relative}")
            continue
        if sha256(path) != metadata.get("sha256"):
            errors.append(f"sha256 lệch {relative}")
        if len(errors) >= 20:
            break
    if strict_files:
        actual = {path.relative_to(root).as_posix() for path in artifact_files(root)}
        extra = sorted(actual - set(recorded))
        if extra:
            errors.append(f"artifact ngoài manifest: {extra[:10]}")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "pass",
        "corpus_version": payload.get("corpus_version"),
        "input_sha256": current_input,
        "artifact_count": len(recorded),
        "manifest": RELATIVE_PATH.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/validate a KB release manifest")
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--proposal-id", default="")
    parser.add_argument("--doc-id", default="")
    parser.add_argument("--version", type=int)
    parser.add_argument("--git-commit", default="")
    args = parser.parse_args(argv)
    try:
        result = (
            build(
                args.root, proposal_id=args.proposal_id, doc_id=args.doc_id,
                version=args.version, git_commit=args.git_commit,
            )
            if args.command == "build" else validate(args.root)
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"✗ release manifest: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
