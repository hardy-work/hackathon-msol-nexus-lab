#!/usr/bin/env python3
"""Plan an evidence-preserving re-ingest from one document version to another.

The planner produces the exact raw diff and the minimal page set for Stage 4,
distinguishing 1:1 pages (supersede the page) from N:1 pages (edit only claims
sourced from the old raw paths). Its archive helper moves 1:1 pages only after
the plan has passed its registry/artifact checks.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
from pathlib import Path

import yaml

from document_registry import by_version, require_version_1

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(match.group(1)) or {} if match else {}


def _artifact_kind(rel: str) -> str:
    name = Path(rel).name
    if name.endswith(".facts.json"):
        return "facts"
    if name.endswith(".fulltext.md"):
        return "fulltext"
    return Path(name).suffix.lower().lstrip(".") or "file"


def artifact_key(root: Path, rel: str) -> str:
    path = root / rel
    name = path.name
    if name.endswith(".facts.json"):
        value = name[:-len(".facts.json")]
    elif name.endswith(".fulltext.md"):
        value = name[:-len(".fulltext.md")]
    elif path.exists() and name.endswith(".md"):
        fm = frontmatter(path)
        if fm.get("raw_id"):
            value = str(fm["raw_id"])
        elif fm.get("sheet"):
            value = str(fm["sheet"])
        else:
            value = path.stem
    else:
        value = path.stem
    identity = re.sub(r"(?:[@._-](?:v|version)\d+)$", "", value, flags=re.I).casefold()
    return f"{identity}::{_artifact_kind(rel)}"


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


def _require_artifacts(root: Path, paths: list[str], label: str) -> None:
    missing = [rel for rel in paths if not (root / rel).is_file()]
    if missing:
        raise ValueError(f"{label} thiếu artifact đã đăng ký: {', '.join(missing)}")


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
    # A re-ingest is an update to an existing document identity.  Do not let a
    # partially registered document (for example v2 without v1) enter this
    # path: it must be repaired/initially ingested by a human first.
    require_version_1(doc_id, root)
    old = by_version(doc_id, from_version, root)
    new = by_version(doc_id, to_version, root)
    if int(new.get("supersedes") or 0) != int(from_version):
        raise ValueError(f"{doc_id}@v{to_version} phải khai supersedes: {from_version}")
    old_paths = list(old.get("raw_paths") or [])
    new_paths = list(new.get("raw_paths") or [])
    if not old_paths or not new_paths:
        raise ValueError("cả hai version phải khai raw_paths trong documents.yml")
    _require_artifacts(root, old_paths, f"{doc_id}@v{from_version}")
    _require_artifacts(root, new_paths, f"{doc_id}@v{to_version}")
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


def _archive_path(root: Path, page_rel: str, version: int) -> Path:
    page = root / page_rel
    stem = page.stem
    stem = re.sub(r"@v\d+$", "", stem, flags=re.IGNORECASE)
    return page.with_name(f"{stem}@v{version}{page.suffix}")


def archive_one_to_one_pages(root: Path, plan: dict) -> list[dict]:
    """Move 1:1 pages to an immutable versioned path before rebuilding them.

    The new ingest can then write the canonical page path again.  The archived
    page keeps its old provenance and explicitly points at the replacement;
    current-page readers ignore it because its frontmatter still carries the
    superseded document version.
    """
    archived = []
    from_version = int(plan["from_version"])
    for item in plan.get("impacted_pages", []):
        if item.get("strategy") != "supersede_page":
            continue
        page_rel = str(item["page"])
        page = root / page_rel
        target = _archive_path(root, page_rel, from_version)
        if not page.is_file():
            raise ValueError(f"trang 1:1 cần archive không tồn tại: {page_rel}")
        if target.exists():
            raise FileExistsError(
                f"trang archive đã tồn tại, không ghi đè: {target.relative_to(root).as_posix()}"
            )
        text = page.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            raise ValueError(f"trang 1:1 thiếu frontmatter, không archive: {page_rel}")
        if re.search(r"(?m)^superseded_by:", match.group(1)):
            raise ValueError(f"trang 1:1 đã có superseded_by, cần human review: {page_rel}")
        replacement = page.relative_to(root).as_posix()
        updated_header = match.group(1).rstrip() + f"\nsuperseded_by: {replacement}\n"
        archived_text = f"---\n{updated_header}---\n" + text[match.end():]
        page.write_text(archived_text, encoding="utf-8")
        shutil.move(str(page), str(target))
        archived.append({
            "old_page": page_rel,
            "archived_page": target.relative_to(root).as_posix(),
            "superseded_by": replacement,
        })
    plan["archived_pages"] = archived
    return archived


def write_plan(root: Path, plan: dict) -> Path:
    destination = root / "derived" / "reingest-plan.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--from-version", type=int, required=True)
    parser.add_argument("--to-version", type=int, required=True)
    args = parser.parse_args()
    plan = build_plan(ROOT, args.doc_id, args.from_version, args.to_version)
    destination = write_plan(ROOT, plan)
    print(json.dumps({"plan": destination.relative_to(ROOT).as_posix(),
                      "changed_raw": len(plan["raw_diff"]),
                      "impacted_pages": len(plan["impacted_pages"]),
                      "branch": plan["branch"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
