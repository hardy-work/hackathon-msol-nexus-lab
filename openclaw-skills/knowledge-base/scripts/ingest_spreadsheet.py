#!/usr/bin/env python3
"""STAGE 4 — deterministic source wiki page for a generic XLSX workbook."""
from __future__ import annotations

import json
import sys
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
        raise FileNotFoundError(f"thiếu raw spreadsheet: {raw_path.relative_to(root)}")
    metadata, body = markdown_source.parse(raw_path)
    domain = str(document.get("domain") or "nexus")
    allowed = yaml.safe_load((root / "schema.yml").read_text(encoding="utf-8"))
    domains = set(allowed["dimensions"]["domain"]["values"])
    if domain not in domains:
        raise ValueError(f"domain `{domain}` chưa được curate trong schema.yml")
    raw_rel = raw_path.relative_to(root).as_posix()
    page = root / "wiki" / "sources" / f"{doc_id}.md"
    frontmatter = {
        "page": "source",
        "name": str(document.get("source_name") or doc_id),
        "doc_id": doc_id,
        "version": int(document["version"]),
        "domain": domain,
        "project": document.get("project", "nexus"),
        "visibility": document.get("visibility", "internal"),
        "source_name": str(document.get("source_name") or doc_id),
        "kind": document.get("kind", "xlsx"),
        "raw_paths": [raw_rel],
        "generated_by": "scripts/ingest_spreadsheet.py",
    }
    header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"---\n{header}\n---\n{body}", encoding="utf-8")
    return page


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if "--doc" not in args:
        print("Dùng: python3 scripts/ingest_spreadsheet.py --doc <doc_id>", file=sys.stderr)
        return 2
    doc_id = args[args.index("--doc") + 1]
    plan_path = args[args.index("--plan") + 1] if "--plan" in args else None
    try:
        document = document_registry.current(doc_id, ROOT)
        page_rel = f"wiki/sources/{doc_id}.md"
        if plan_path:
            plan = json.loads((ROOT / plan_path).read_text(encoding="utf-8"))
            if page_rel not in set(plan.get("page_actions", {}).get("write", [])):
                print(f"↷ {doc_id}: page không impacted, giữ nguyên")
                return 0
        page = ingest_one(ROOT, document)
        build_index.build()
        build_index.append_log([doc_id], "Stage 4 WIKI-INGEST (generic spreadsheet)")
    except (OSError, KeyError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"✗ {doc_id}: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {doc_id} → {page.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
