#!/usr/bin/env python3
"""Build deterministic Nexus wiki pages from extracted facts.

With ``--plan`` this is a selective page writer: only pages listed by the
re-ingest plan are rendered, while the index is always regenerated from the
resulting corpus.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from document_registry import current  # noqa: E402
from artifact_paths import artifact_rel  # noqa: E402
import build_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"
DOC = current("nexus-plan")
VERSION = int(DOC["version"])
SOURCE_NAME = str(DOC.get("source_name") or Path(str(DOC["original"])).name)
SOURCE_KIND = str(DOC.get("kind") or Path(str(DOC["original"])).suffix.lstrip(".") or "unknown")


def _load_plan(path: str | None) -> dict | None:
    if not path:
        return None
    plan_path = Path(path)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    return json.loads(plan_path.read_text(encoding="utf-8"))


def main(plan_path: str | None = None):
    plan = _load_plan(plan_path)
    write_pages = set(plan.get("page_actions", {}).get("write", [])) if plan else None
    people_facts = artifact_rel(DOC, "nexus-people", "facts").as_posix()
    people = json.loads((ROOT / people_facts).read_text(encoding="utf-8"))["facts"]
    if write_pages is not None:
        known_pages = {"wiki/sources/nexus-plan.md"}
        known_pages.update(f"wiki/entities/{slug}.md" for slug in people)
        unknown = sorted(write_pages - known_pages)
        if unknown:
            raise ValueError(
                "re-ingest plan có page Nexus chưa có renderer: " + ", ".join(unknown)
            )
    source_paths = [str(p) for p in DOC.get("raw_paths", [])
                    if str(p).endswith(".md")]
    if not source_paths:
        source_paths = [artifact_rel(DOC, raw_id, "md").as_posix()
                        for raw_id in ("nexus-backlog", "nexus-config", "nexus-issue",
                                       "nexus-master-schedule", "nexus-people",
                                       "nexus-resource-plan", "nexus-risk",
                                       "nexus-sprint1", "nexus-summary")]
    config_md = artifact_rel(DOC, "nexus-config", "md").as_posix()
    sprint_md = artifact_rel(DOC, "nexus-sprint1", "md").as_posix()
    people_md = artifact_rel(DOC, "nexus-people", "md").as_posix()
    raw_block = "".join(f"  - {p}\n" for p in source_paths)
    (WIKI / "sources").mkdir(parents=True, exist_ok=True)
    (WIKI / "entities").mkdir(parents=True, exist_ok=True)

    links = " · ".join(f"[[{slug}]]" for slug in people)
    source = f"""---
page: source
name: "Nexus Plan"
doc_id: nexus-plan
version: {VERSION}
domain: nexus
visibility: internal
source_name: {json.dumps(SOURCE_NAME, ensure_ascii=False)}
kind: {SOURCE_KIND}
raw_paths:
{raw_block}---

# Nexus Plan

Nguồn này là workbook kế hoạch dự án Nexus, gồm kế hoạch nguồn lực, tổng quan dự án,
lịch tổng, backlog, sprint, rủi ro, issue và Config. Các bảng được giữ nguyên ở tầng
`raw/` và tra cứu định lượng qua DuckDB; trang này chỉ là mục lục có cấu trúc.

## Các trang nhân sự

{links}

## Nguồn

- `doc_id`: nexus-plan
- `source_name`: {SOURCE_NAME}
- `kind`: {SOURCE_KIND}
- `raw_paths`: các bảng Nexus được trích từ `{DOC['original']}`.
"""
    written = []
    source_rel = "wiki/sources/nexus-plan.md"
    if write_pages is None or source_rel in write_pages:
        (WIKI / "sources/nexus-plan.md").write_text(source, encoding="utf-8")
        written.append(source_rel)

    for slug, info in people.items():
        page_rel = f"wiki/entities/{slug}.md"
        if write_pages is not None and page_rel not in write_pages:
            continue
        role = (info.get("roles") or [None])[0]
        role_line = f"role: {role}\n" if role else ""
        if info["task_count"]["value"] == 0:
            note = """Người này được khai trong Config nhưng rollup Sprint 1 ghi nhận **0 task**,
không có dòng task hoặc vai trò theo task trong nguồn raw. Số 0 vẫn chỉ dùng qua
`facts_ref`; không suy ra thêm tech-stack hay vai trò.
"""
        else:
            note = """Các task của người này nằm trong bảng Sprint 1. Vai trò theo dòng task được giữ ở
nguồn raw; số liệu task và effort chỉ dùng qua `facts_ref`, không chép lại trong wiki.
"""
        body = f"""---
page: entity-person
name: "{info['label']}"
assignee: {slug}
{role_line}project: nexus
visibility: internal
task_count: {{ facts_ref: "{people_facts}#{slug}.task_count" }}
estimate_h: {{ facts_ref: "{people_facts}#{slug}.estimate_h" }}
actual_h: {{ facts_ref: "{people_facts}#{slug}.actual_h" }}
raw_paths:
""" + "".join(f"  - {p}\n" for p in (config_md, sprint_md, people_md)) + f"""---

# {info['label']}

Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.

## Ghi chú

{note.rstrip()}

## Phạm vi

Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu
không được suy diễn thành “không có”.
"""
        (WIKI / f"entities/{slug}.md").write_text(body, encoding="utf-8")
        written.append(page_rel)
    if write_pages is not None and set(written) != write_pages:
        missing = sorted(write_pages - set(written))
        raise ValueError("renderer không thực thi đủ page_actions.write: " + ", ".join(missing))
    count = build_index.build()
    mode = f"selective {len(written)} page" if plan else f"full {len(written)} pages"
    print(f"✓ Nexus wiki: {mode} · index {count} pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", help="re-ingest plan; only its page_actions.write pages are rendered")
    args = parser.parse_args()
    main(args.plan)
