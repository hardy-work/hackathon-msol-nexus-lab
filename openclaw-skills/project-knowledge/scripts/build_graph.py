#!/usr/bin/env python3
"""STAGE 6 (dẫn xuất) — dựng `derived/graph.json`: TẦNG BẬC 3 (quan hệ) của sơ đồ.

Bậc 1 = tra ô/hàng (duckdb). Bậc 2 = tìm trang theo từ khoá/vector. Bậc 3 = đi theo
QUAN HỆ giữa các thực thể. Nguồn quan hệ đã có sẵn trong wiki/: liên kết `[[x]]` hai chiều
+ giá trị DIMENSION ở frontmatter. Script này gom chúng thành một đồ thị tra được, KHÔNG
bịa thêm cạnh nào ngoài cái wiki đã khẳng định.

  - NODE: mỗi trang wiki (entity/source/concept/case-study) + mỗi GIÁ TRỊ DIMENSION
    (role:QC, project:handy, domain:mor…) như một nút — để nối những người cùng vai trò.
  - EDGE có kiểu:
      mentions     : trang A có `[[B]]` (đã qua lint hai chiều ở Gate 3a).
      has_role / in_project / in_domain / is : trang -> nút DIMENSION tương ứng.

Tầng dẫn xuất (§0): KHÔNG commit, dựng lại được từ wiki/. Xoá thì chạy lại script.

  python3 scripts/build_graph.py            # -> derived/graph.json
  python3 scripts/build_graph.py --stats    # in vài thống kê để soi nhanh
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
DERIVED = ROOT / "derived"
LINK = re.compile(r"\[\[([^\]]+)\]\]")

# DIMENSION ở frontmatter -> kiểu cạnh nối tới nút giá trị.
DIM_REL = {"role": "has_role", "project": "in_project",
           "domain": "in_domain", "assignee": "is"}


def slug(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def row_values(row):
    return {cell["header"].strip().casefold(): cell
            for cell in row.get("cells", {}).values() if cell.get("value") not in (None, "")}


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    try:
        return yaml.safe_load(m.group(1)) or {}, m.group(2)
    except yaml.YAMLError:
        return {}, text


def build():
    nodes, edges, dim_nodes = {}, [], {}

    def dimension_node(dim, value):
        vid = f"{dim}:{slug(value)}"
        dim_nodes[vid] = {"id": vid, "type": "dimension", "dim": dim, "value": value}
        return vid

    def edge(source, target, rel, src=None):
        item = {"from": source, "to": target, "rel": rel}
        if src:
            item["src"] = src
        edges.append(item)

    for p in sorted(WIKI.rglob("*.md")):
        if p.name in ("index.md", "log.md"):
            continue
        fm, body = frontmatter(p.read_text(encoding="utf-8"))
        pid = p.stem
        nodes[pid] = {
            "id": pid, "type": fm.get("page", "?"),
            "name": fm.get("name", pid),
            "dims": {d: fm[d] for d in DIM_REL if fm.get(d)},
        }
        # cạnh mentions từ [[link]] (thân bài + frontmatter)
        for tgt in set(LINK.findall(body) + LINK.findall(str(fm))):
            edge(pid, tgt, "mentions")
        # cạnh theo DIMENSION
        for dim, rel in DIM_REL.items():
            val = fm.get(dim)
            if not val:
                continue
            for one in (val if isinstance(val, list) else [val]):
                vid = f"{dim}:{one}"
                vid = dimension_node(dim, one)
                edge(pid, vid, rel)

    # Dựng node task từ facts có provenance.  Wiki entity pages chỉ đủ để nối
    # người/role; task rows mới cho phép đi nhiều bước task -> người -> sprint /
    # status / milestone. Không suy ra dependency nếu workbook không khai báo.
    task_facts = ROOT / "raw" / "nexus-sprint1.facts.json"
    task_count = 0
    if task_facts.exists():
        payload = json.loads(task_facts.read_text(encoding="utf-8"))
        people_by_name = {str(n.get("name")): pid for pid, n in nodes.items()
                          if n.get("type") == "entity-person"}
        current_category = None
        current_category_src = None
        for row in payload.get("rows", []):
            cells = row_values(row)
            task_cell = cells.get("taskid")
            name_cell = cells.get("task")
            if not task_cell or not task_cell.get("value"):
                continue
            task_id = str(task_cell["value"])
            task_node = f"task:{slug(task_id)}"
            task_name = str(name_cell.get("value", task_id)) if name_cell else task_id
            attrs = {
                "task_id": task_id,
                "name": task_name,
                "sprint": 1,
                "source": task_cell.get("src"),
            }
            if cells.get("category milestone", {}).get("value"):
                current_category = cells["category milestone"]["value"]
                current_category_src = cells["category milestone"].get("src")
            if current_category:
                attrs["category"] = current_category
            for header, key in (("role", "role"),
                                ("assignee", "assignee"), ("status", "status"),
                                ("priority", "priority")):
                if header in cells:
                    attrs[key] = cells[header].get("value")
            nodes[task_node] = {"id": task_node, "type": "task", **attrs}
            edge(task_node, dimension_node("sprint", "Sprint 1"), "in_sprint",
                 task_cell.get("src"))
            for key, rel, dim in (("category", "in_milestone", "category"),
                                  ("role", "has_role", "role"),
                                  ("status", "has_status", "task_status"),
                                  ("priority", "has_priority", "priority")):
                if attrs.get(key):
                    source = cells.get(key, {}).get("src")
                    if key == "category":
                        source = current_category_src
                    edge(task_node, dimension_node(dim, attrs[key]), rel, source)
            assignee = attrs.get("assignee")
            if assignee:
                person = people_by_name.get(assignee)
                if person:
                    edge(task_node, person, "assigned_to", cells["assignee"].get("src"))
                else:
                    edge(task_node, dimension_node("assignee", assignee), "assigned_to",
                         cells["assignee"].get("src"))
            for header, rel in (("blocked by", "blocked_by"), ("depends on", "depends_on"),
                                ("dependency", "depends_on")):
                dependency = cells.get(header, {}).get("value")
                if dependency:
                    for dep_id in re.findall(r"[A-Za-z]+-\d+", str(dependency)):
                        edge(task_node, f"task:{slug(dep_id)}", rel,
                             cells[header].get("src"))
            task_count += 1

    graph = {
        "nodes": list(nodes.values()) + list(dim_nodes.values()),
        "edges": edges,
        "meta": {"pages": sum(n.get("type") != "task" for n in nodes.values()),
                 "task_nodes": task_count, "dimension_nodes": len(dim_nodes),
                 "edges": len(edges),
                 "note": "dẫn xuất từ wiki/raw facts (typed links + DIMENSION); không commit"},
    }
    DERIVED.mkdir(exist_ok=True)
    (DERIVED / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def main():
    g = build()
    m = g["meta"]
    print(f"✓ derived/graph.json — {m['pages']} trang + {m.get('task_nodes', 0)} task + "
          f"{m['dimension_nodes']} nút DIMENSION, {m['edges']} cạnh")
    if "--stats" in sys.argv:
        by_rel = {}
        for e in g["edges"]:
            by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1
        for rel, n in sorted(by_rel.items(), key=lambda x: -x[1]):
            print(f"    {rel:12s} {n}")
        # ví dụ bậc 3: nhóm người theo role
        who = {}
        for e in g["edges"]:
            if e["rel"] == "has_role":
                who.setdefault(e["to"], []).append(e["from"])
        print("  nhóm theo vai trò:")
        for role, ppl in sorted(who.items()):
            print(f"    {role:14s} {', '.join(sorted(ppl))}")


if __name__ == "__main__":
    main()
