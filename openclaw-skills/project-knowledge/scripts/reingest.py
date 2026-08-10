#!/usr/bin/env python3
"""Plan and apply an evidence-preserving re-ingest from one version to another.

The planner produces the raw diff and the minimal page write-set for Stage 4.
Unchanged generated artifacts and pages are retained byte-for-byte; 1:1 pages
are superseded, while generated pages whose identity disappeared are retired.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

import document_registry
from document_registry import by_version, require_version_1
from artifact_paths import artifact_rel

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


def _artifact_paths(root: Path, document: dict) -> list[str]:
    """Include implicit facts companions for legacy md-only registry entries.

    `raw_paths` dùng dấu gạch chéo. `Path.with_suffix()` trả về dạng của HĐH, nên
    trên Windows bạn đồng hành sinh ra là `raw\\plan@v1.facts.json` — không khớp
    chuỗi nào trong `known`, dù file đó đã được khai. Đường dẫn bị thêm lần thứ hai,
    rồi `_by_artifact` thấy hai path cùng quy về `plan::facts` và chặn. Chuẩn hoá về
    posix để phép so sánh nằm trên cùng một bảng chữ.
    """
    paths = list(document.get("raw_paths") or [])
    known = set(paths)
    for rel in list(paths):
        if not str(rel).endswith(".md"):
            continue
        facts = Path(rel).with_suffix(".facts.json").as_posix()
        if facts not in known and (root / facts).is_file():
            paths.append(facts)
            known.add(facts)
    return paths


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


def _semantic_artifact_digest(root: Path, rel: str) -> str:
    """Digest generated raw content while ignoring version-only metadata."""
    path = root / rel
    if path.name.endswith(".facts.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("version", None)
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if path.suffix.lower() in {".md", ".fulltext"} or path.name.endswith(".fulltext.md"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^version:\s*\d+\s*$", "version: <version>", text)
        text = re.sub(r"@v\d+", "", text, flags=re.IGNORECASE)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconcile_artifacts(root: Path, doc_id: str, from_version: int, to_version: int) -> dict:
    """Reuse vN-1 raw artifacts whose semantic content did not change.

    Intake initially allocates versioned paths for every generated artifact so
    extractors cannot overwrite v1.  After extraction, this reconciliation
    removes version-only copies and makes the vN registry retain the old path
    for unchanged artifacts.  That is what allows a clean page-level diff.
    """
    old = by_version(doc_id, from_version, root)
    new = by_version(doc_id, to_version, root)
    old_by_name = _by_artifact(root, _artifact_paths(root, old))
    new_by_name = _by_artifact(root, _artifact_paths(root, new))
    selected: dict[str, str] = {}
    reused, changed = [], []

    for name, new_rel in new_by_name.items():
        old_rel = old_by_name.get(name)
        if old_rel and _semantic_artifact_digest(root, old_rel) == _semantic_artifact_digest(root, new_rel):
            selected[name] = old_rel
            if old_rel != new_rel:
                (root / new_rel).unlink(missing_ok=True)
            reused.append({"artifact": name, "path": old_rel})
        else:
            selected[name] = new_rel
            changed.append({"artifact": name, "old": old_rel, "new": new_rel})

    for name, old_rel in old_by_name.items():
        if name not in new_by_name:
            changed.append({"artifact": name, "old": old_rel, "new": None})

    ordered_paths = [selected[artifact_key(root, rel)]
                     for rel in list(new.get("raw_paths") or [])]
    documents = document_registry.load(root)
    updated = []
    for document in documents:
        if str(document.get("doc_id")) == str(doc_id) and int(document["version"]) == int(to_version):
            document = dict(document)
            document["raw_paths"] = ordered_paths
        updated.append(document)
    document_registry.write(root, updated)
    return {"reused_artifacts": reused, "changed_artifacts": changed,
            "raw_paths": ordered_paths}


def _page_inventory(root: Path, doc_id: str, extractor: str | None = None) -> tuple[set[str], set[str]]:
    """Return expected/existing generated pages for one document identity."""
    expected = {f"wiki/sources/{doc_id}.md"}
    if doc_id != "nexus-plan":
        # Tài liệu văn xuôi dài sinh thêm một trang cho mỗi CHƯƠNG
        # (`wiki/sources/<doc_id>--<slug>.md`). Không kể chúng vào `existing` thì
        # re-ingest coi chúng là trang lạ và bỏ mặc: bản v2 có trang tổng quan mới
        # nhưng vẫn còn nguyên các trang chương của v1.
        existing = {page.relative_to(root).as_posix()
                    for page in sorted((root / "wiki/sources").glob(f"{doc_id}--*.md"))}
        if extractor != "markdown":
            expected |= existing
        source = root / f"wiki/sources/{doc_id}.md"
        if source.is_file():
            existing.add(source.relative_to(root).as_posix())
        return expected, existing
    document = document_registry.current(doc_id, root)
    facts_path = root / artifact_rel(document, "nexus-people", "facts")
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    expected.update(f"wiki/entities/{slug}.md" for slug in payload.get("facts", {}))
    existing = set()
    for page in sorted((root / "wiki/entities").glob("*.md")):
        fm = frontmatter(page)
        if (fm.get("page") == "entity-person" and fm.get("project") == "nexus"
                and not fm.get("retired")):
            existing.add(page.relative_to(root).as_posix())
    source = root / "wiki/sources/nexus-plan.md"
    if source.is_file():
        existing.add(source.relative_to(root).as_posix())
    return expected, existing


def impacted_pages(root: Path, old_paths: list[str], doc_id: str | None = None,
                   from_version: int | None = None,
                   one_to_one_paths: list[str] | None = None) -> list[dict]:
    old = set(old_paths)
    one_to_one = set(one_to_one_paths or old_paths)
    impacted = []
    for page in sorted((root / "wiki").rglob("*.md")):
        if page.name in {"index.md", "log.md"}:
            continue
        fm = frontmatter(page)
        if fm.get("retired"):
            continue
        if doc_id and str(fm.get("doc_id")) == str(doc_id) and fm.get("version") is not None:
            try:
                if from_version is not None and int(fm["version"]) != int(from_version):
                    continue
            except (TypeError, ValueError):
                continue
        refs = set(fm.get("raw_paths") or [])
        touched = sorted(refs & old)
        if not touched:
            continue
        page_type = fm.get("page")
        is_one_to_one = page_type in {"source", "case-study"} and refs <= one_to_one
        impacted.append({
            "page": page.relative_to(root).as_posix(),
            "page_type": page_type,
            "raw_paths_touched": touched,
            "strategy": "supersede_page" if is_one_to_one else "edit_claims_in_place",
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
    old_paths = _artifact_paths(root, old)
    new_paths = _artifact_paths(root, new)
    if not old_paths or not new_paths:
        raise ValueError("cả hai version phải khai raw_paths trong documents.yml")
    _require_artifacts(root, old_paths, f"{doc_id}@v{from_version}")
    _require_artifacts(root, new_paths, f"{doc_id}@v{to_version}")
    raw_rows = raw_diff(root, old_paths, new_paths)
    changed_old_paths = [str(row["old"]) for row in raw_rows if row.get("old")]
    impacted = impacted_pages(root, changed_old_paths, doc_id=doc_id,
                              from_version=from_version, one_to_one_paths=old_paths)
    expected_pages, existing_pages = _page_inventory(
        root, doc_id, extractor=str(new.get("extractor") or "")
    )
    removed_pages = sorted(existing_pages - expected_pages)
    # A renderer change may retire pages that were impacted by the old
    # extractor. Those pages must go through the retired-page path, not the
    # one-to-one supersede path; otherwise their superseded_by points to a
    # chapter page that the new renderer no longer creates.
    impacted = [item for item in impacted if item["page"] not in removed_pages]
    if doc_id == "nexus-plan":
        # A foreign page may cite a shared raw artifact, but it is not owned by
        # this document's renderer and must never be rewritten/retired here.
        impacted = [item for item in impacted if item["page"] in existing_pages]
    new_pages = sorted(expected_pages - existing_pages)
    write_pages = {str(item["page"]) for item in impacted if item["page"] not in removed_pages}
    write_pages.update(new_pages)
    if doc_id == "nexus-plan" and (
            new_pages or removed_pages or "wiki/sources/nexus-plan.md" not in existing_pages):
        write_pages.add("wiki/sources/nexus-plan.md")
    return {
        "schema": "project-knowledge/reingest-plan/v2",
        "doc_id": doc_id,
        "from_version": from_version,
        "to_version": to_version,
        "branch": f"ingest/{doc_id}@v{to_version}",
        "raw_diff": raw_rows,
        "changed_raw_paths": changed_old_paths,
        "impacted_pages": impacted,
        "new_pages": new_pages,
        "removed_pages": removed_pages,
        "page_actions": {
            "write": sorted(write_pages),
            "archive": removed_pages,
        },
        "rules": {
            "one_to_one": "create new page version and set superseded_by on old page",
            "many_to_one": "rewrite only impacted pages; preserve untouched pages byte-for-byte",
            "removed_page": "archive retired page and exclude it from current retrieval",
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


def archive_retired_pages(root: Path, plan: dict) -> list[dict]:
    """Archive generated pages whose source identity disappeared in the new version."""
    retired = []
    from_version = int(plan["from_version"])
    to_version = int(plan["to_version"])
    doc_id = str(plan["doc_id"])
    retired_by = f"wiki/sources/{doc_id}.md"
    for page_rel in plan.get("removed_pages", []):
        page = root / str(page_rel)
        target = _archive_path(root, str(page_rel), from_version)
        if not page.is_file():
            raise ValueError(f"trang cần retire không tồn tại: {page_rel}")
        if target.exists():
            raise FileExistsError(
                f"trang retired đã tồn tại, không ghi đè: {target.relative_to(root).as_posix()}"
            )
        text = page.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            raise ValueError(f"trang cần retire thiếu frontmatter: {page_rel}")
        header = yaml.safe_load(match.group(1)) or {}
        header.update({
            "doc_id": doc_id,
            "version": from_version,
            "retired": True,
            "retired_in": to_version,
            "retired_by": retired_by,
        })
        updated_header = yaml.safe_dump(header, allow_unicode=True, sort_keys=False).rstrip()
        page.write_text(f"---\n{updated_header}\n---\n" + text[match.end():], encoding="utf-8")
        shutil.move(str(page), str(target))
        retired.append({
            "old_page": str(page_rel),
            "retired_page": target.relative_to(root).as_posix(),
            "retired_by": retired_by,
        })
    plan["retired_pages"] = retired
    return retired


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
