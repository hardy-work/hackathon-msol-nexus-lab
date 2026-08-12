#!/usr/bin/env python3
"""STAGE 4 — deterministic Wiki source page for Markdown documents."""
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_paths  # noqa: E402
import build_index  # noqa: E402
import document_registry  # noqa: E402
import markdown_source  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def ingest_one(root: Path, document: dict) -> Path:
    doc_id = str(document["doc_id"])
    raw_path = artifact_paths.artifact_path(root, document, doc_id, "md")
    if not raw_path.is_file():
        raise FileNotFoundError(f"thiếu raw Markdown: {raw_path.relative_to(root)}")
    metadata, body = markdown_source.parse(raw_path)
    schema = yaml.safe_load((root / "schema.yml").read_text(encoding="utf-8"))
    domain = markdown_source.domain(metadata, fallback=str(document.get("domain") or ""))
    allowed = schema["dimensions"]["domain"]["values"]
    allowed = set(allowed) if not isinstance(allowed, dict) else set(allowed)
    if domain not in allowed:
        raise ValueError(
            f"domain `{domain}` chưa được curate trong schema.yml; "
            "không tự thêm domain từ file upload"
        )

    raw_rel = raw_path.relative_to(root).as_posix()
    title = markdown_source.title(metadata, body, doc_id)
    page = root / "wiki" / "sources" / f"{doc_id}.md"
    frontmatter = {
        "page": "source",
        "name": title,
        "doc_id": doc_id,
        "version": int(document["version"]),
        "domain": domain,
        "visibility": document.get("visibility", "internal"),
        "raw_paths": [raw_rel],
        "generated_by": "scripts/ingest_markdown.py",
    }
    for key in ("source_name", "updated_at", "updated_by"):
        if document.get(key):
            frontmatter[key] = document[key]
    header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"---\n{header}\n---\n{body}", encoding="utf-8")
    return page


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--plan")
    args = parser.parse_args(argv)
    document = document_registry.current(args.doc, ROOT)
    page_rel = f"wiki/sources/{args.doc}.md"
    if args.plan:
        plan = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))
        if page_rel not in set(plan.get("page_actions", {}).get("write", [])):
            print(f"↷ {args.doc}: page không impacted, giữ nguyên")
            return 0
    try:
        page = ingest_one(ROOT, document)
    except (OSError, KeyError, ValueError, yaml.YAMLError) as exc:
        print(f"✗ {args.doc}: {exc}", file=sys.stderr)
        return 1
    build_index.build()
    build_index.append_log([args.doc], "Stage 4 WIKI-INGEST (Markdown)")
    print(f"✓ {args.doc} → {page.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
