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
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
DERIVED = ROOT / "derived"
LINK = re.compile(r"\[\[([^\]]+)\]\]")

# DIMENSION ở frontmatter -> kiểu cạnh nối tới nút giá trị.
DIM_REL = {"role": "has_role", "project": "in_project",
           "domain": "in_domain", "assignee": "is"}


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
            edges.append({"from": pid, "to": tgt, "rel": "mentions"})
        # cạnh theo DIMENSION
        for dim, rel in DIM_REL.items():
            val = fm.get(dim)
            if not val:
                continue
            for one in (val if isinstance(val, list) else [val]):
                vid = f"{dim}:{one}"
                dim_nodes[vid] = {"id": vid, "type": "dimension",
                                  "dim": dim, "value": one}
                edges.append({"from": pid, "to": vid, "rel": rel})

    graph = {
        "nodes": list(nodes.values()) + list(dim_nodes.values()),
        "edges": edges,
        "meta": {"pages": len(nodes), "dimension_nodes": len(dim_nodes),
                 "edges": len(edges),
                 "note": "dẫn xuất từ wiki/ (typed links + DIMENSION); không commit"},
    }
    DERIVED.mkdir(exist_ok=True)
    (DERIVED / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def main():
    g = build()
    m = g["meta"]
    print(f"✓ derived/graph.json — {m['pages']} trang + {m['dimension_nodes']} nút DIMENSION, "
          f"{m['edges']} cạnh")
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
