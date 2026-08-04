#!/usr/bin/env python3
"""Plan an evidence-preserving re-ingest from one document version to another.

The planner never rewrites wiki content. It produces the exact raw diff and the
minimal page set for Stage 4, distinguishing 1:1 pages (supersede the page) from
N:1 pages (edit only claims sourced from the old raw paths).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path

import yaml

from document_registry import by_version

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(match.group(1)) or {} if match else {}


def artifact_key(root: Path, rel: str) -> str:
    path = root / rel
    if path.exists() and path.suffix.lower() == ".md":
        fm = frontmatter(path)
        if fm.get("raw_id"):
            value = str(fm["raw_id"])
        elif fm.get("sheet"):
            value = str(fm["sheet"])
        else:
            value = path.stem
    else:
        value = path.stem
    return re.sub(r"(?:[@._-](?:v|version)\d+)$", "", value, flags=re.I).casefold()


def _by_artifact(root: Path, paths: list[str]) -> dict[str, str]:
    out = {}
    for rel in paths:
        key = artifact_key(root, rel)
        if key in out:
            raise ValueError(f"raw_paths có hai artifact cùng identity `{key}`")
        out[key] = rel
    return out


def raw_diff(root: Path, old_paths: list[str], new_paths: list[str]) -> list[dict]:
    old_by_name = _by_artifact(root, old_paths)
    new_by_name = _by_artifact(root, new_paths)
    rows = []
    for name in sorted(set(old_by_name) | set(new_by_name)):
        old_rel, new_rel = old_by_name.get(name), new_by_name.get(name)
        before = (root / old_rel).read_text(encoding="utf-8").splitlines() if old_rel and (root / old_rel).exists() else []
        after = (root / new_rel).read_text(encoding="utf-8").splitlines() if new_rel and (root / new_rel).exists() else []
        diff = list(difflib.unified_diff(before, after, fromfile=old_rel or "/dev/null",
                                         tofile=new_rel or "/dev/null", lineterm=""))
        if diff:
            rows.append({"artifact": name, "old": old_rel, "new": new_rel,
                         "added_lines": sum(line.startswith("+") and not line.startswith("+++") for line in diff),
                         "removed_lines": sum(line.startswith("-") and not line.startswith("---") for line in diff),
                         "diff": diff})
    return rows


def impacted_pages(root: Path, old_paths: list[str]) -> list[dict]:
    old = set(old_paths)
    impacted = []
    for page in sorted((root / "wiki").rglob("*.md")):
        if page.name in {"index.md", "log.md"}:
            continue
        fm = frontmatter(page)
        refs = set(fm.get("raw_paths") or [])
        touched = sorted(refs & old)
        if not touched:
            continue
        page_type = fm.get("page")
        one_to_one = page_type in {"source", "case-study"} and refs <= old
        impacted.append({
            "page": page.relative_to(root).as_posix(),
            "page_type": page_type,
            "raw_paths_touched": touched,
            "strategy": "supersede_page" if one_to_one else "edit_claims_in_place",
        })
    return impacted


def build_plan(root: Path, doc_id: str, from_version: int, to_version: int) -> dict:
    old = by_version(doc_id, from_version, root)
    new = by_version(doc_id, to_version, root)
    if int(new.get("supersedes") or 0) != int(from_version):
        raise ValueError(f"{doc_id}@v{to_version} phải khai supersedes: {from_version}")
    old_paths = list(old.get("raw_paths") or [])
    new_paths = list(new.get("raw_paths") or [])
    if not old_paths or not new_paths:
        raise ValueError("cả hai version phải khai raw_paths trong documents.yml")
    return {
        "schema": "project-knowledge/reingest-plan/v1",
        "doc_id": doc_id,
        "from_version": from_version,
        "to_version": to_version,
        "branch": f"ingest/{doc_id}@v{to_version}",
        "raw_diff": raw_diff(root, old_paths, new_paths),
        "impacted_pages": impacted_pages(root, old_paths),
        "rules": {
            "one_to_one": "create new page version and set superseded_by on old page",
            "many_to_one": "replace only claims whose src/raw_path belongs to old version",
            "gate": "Gate 3a + Gate 3b must pass before merge",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--from-version", type=int, required=True)
    parser.add_argument("--to-version", type=int, required=True)
    args = parser.parse_args()
    plan = build_plan(ROOT, args.doc_id, args.from_version, args.to_version)
    destination = ROOT / "derived" / "reingest-plan.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"plan": destination.relative_to(ROOT).as_posix(),
                      "changed_raw": len(plan["raw_diff"]),
                      "impacted_pages": len(plan["impacted_pages"]),
                      "branch": plan["branch"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
