#!/usr/bin/env python3
"""Build deterministic Nexus wiki pages from extracted facts."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from document_registry import current  # noqa: E402
import build_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"
DOC = current("nexus-plan")
VERSION = int(DOC["version"])


def main():
    people = json.loads((RAW / "nexus-people.facts.json").read_text(encoding="utf-8"))["facts"]
    source_paths = [f"raw/{p.name}" for p in sorted(RAW.glob("nexus-*.md"))]
    (WIKI / "sources").mkdir(parents=True, exist_ok=True)
    (WIKI / "entities").mkdir(parents=True, exist_ok=True)

    links = " · ".join(f"[[{slug}]]" for slug in people)
    source = """---
page: source
name: "Nexus Plan"
doc_id: nexus-plan
version: """ + str(VERSION) + """
domain: nexus
visibility: internal
raw_paths:
""" + "".join(f"  - {p}\n" for p in source_paths) + """---

# Nexus Plan

Nguồn này là workbook kế hoạch dự án Nexus, gồm kế hoạch nguồn lực, tổng quan dự án,
lịch tổng, backlog, sprint, rủi ro, issue và Config. Các bảng được giữ nguyên ở tầng
`raw/` và tra cứu định lượng qua DuckDB; trang này chỉ là mục lục có cấu trúc.

## Các trang nhân sự

""" + links + """

## Nguồn

- `doc_id`: nexus-plan
- `raw_paths`: các bảng Nexus được trích từ `originals/nexus-plan.xlsx`.
"""
    (WIKI / "sources/nexus-plan.md").write_text(source, encoding="utf-8")

    for slug, info in people.items():
        role = (info.get("roles") or [None])[0]
        role_line = f"role: {role}\n" if role else ""
        raw_paths = ["raw/nexus-config.md", "raw/nexus-sprint1.md", "raw/nexus-people.md"]
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
task_count: {{ facts_ref: "raw/nexus-people.facts.json#{slug}.task_count" }}
estimate_h: {{ facts_ref: "raw/nexus-people.facts.json#{slug}.estimate_h" }}
actual_h: {{ facts_ref: "raw/nexus-people.facts.json#{slug}.actual_h" }}
raw_paths:
""" + "".join(f"  - {p}\n" for p in raw_paths) + f"""---

# {info['label']}

Thành viên được khai trong Config của [[nexus-plan]], thuộc dự án Nexus.

## Ghi chú

{note.rstrip()}

## Phạm vi

Trang này chỉ phủ dữ liệu đã nạp từ workbook Nexus Plan. Các bảng chưa có dữ liệu
không được suy diễn thành “không có”.
"""
        (WIKI / f"entities/{slug}.md").write_text(body, encoding="utf-8")
    count = build_index.build()
    print(f"✓ Nexus wiki: 1 source + {len(people)} entity pages · index {count} pages")


if __name__ == "__main__":
    main()
