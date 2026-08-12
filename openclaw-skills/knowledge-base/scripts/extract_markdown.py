#!/usr/bin/env python3
"""STAGE 2 — deterministic extractor for Markdown source documents.

Markdown is already a structured, human-readable format.  This lane therefore
keeps its body verbatim and adds only machine provenance to ``raw/``.  It is
deliberately separate from the DOCX/PDF lane: no LLM structure pass and no
numeric rewriting are needed for a Markdown upload.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_paths  # noqa: E402
import document_registry  # noqa: E402
import markdown_source  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_documents(root: Path) -> list[dict]:
    return [doc for doc in document_registry.load(root)
            if doc.get("current") and (
                doc.get("extractor") == "markdown"
                or doc.get("kind") == "text/markdown"
            )]


def extract_one(root: Path, document: dict) -> Path:
    doc_id = str(document["doc_id"])
    original = root / str(document["original"])
    if not original.is_file():
        raise FileNotFoundError(f"thiếu Markdown original: {document['original']}")

    metadata, body = markdown_source.parse(original)
    raw_path = artifact_paths.artifact_path(root, document, doc_id, "md")
    raw_rel = raw_path.relative_to(root).as_posix()
    declared = {str(path) for path in document.get("raw_paths") or []}
    if raw_rel not in declared:
        raise ValueError(
            f"documents.yml chưa khai raw path `{raw_rel}` cho {doc_id}@v{document['version']}"
        )

    raw_metadata = {
        "raw_id": doc_id,
        "doc_id": doc_id,
        "version": int(document["version"]),
        "kind": "markdown",
        "source_file": str(document["original"]),
        "source_name": str(document.get("source_name") or original.name),
        "sha256": sha256(original),
        "extractor": "scripts/extract_markdown.py",
        "lang": metadata.get("lang") or document.get("lang") or "vi",
        "page_type": "source",
        "title": markdown_source.title(
            metadata, body, str(document.get("title") or original.stem)
        ),
    }
    for key in ("type", "org", "domain", "source", "last_updated"):
        if key in metadata:
            raw_metadata[key] = metadata[key]
        elif key in document:
            raw_metadata[key] = document[key]
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    header = yaml.safe_dump(raw_metadata, allow_unicode=True, sort_keys=False).strip()
    raw_path.write_text(f"---\n{header}\n---\n{body}", encoding="utf-8")
    return raw_path


def main(argv: list[str]) -> int:
    only = argv[argv.index("--doc") + 1] if "--doc" in argv else None
    documents = markdown_documents(ROOT)
    if only:
        documents = [doc for doc in documents if str(doc["doc_id"]) == only]
        if not documents:
            print(f"✗ {only}: không phải current Markdown document", file=sys.stderr)
            return 1

    made = 0
    for document in documents:
        try:
            output = extract_one(ROOT, document)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"✗ {document['doc_id']}: {exc}", file=sys.stderr)
            continue
        print(f"✓ {document['doc_id']} → {output.relative_to(ROOT)}")
        made += 1
    print(f"\n{made} Markdown document(s) → raw/")
    return 0 if made == len(documents) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
