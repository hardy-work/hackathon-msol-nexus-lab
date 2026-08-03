#!/usr/bin/env python3
"""STAGE 6 — PUBLISH: dựng derived/facts.duckdb từ wiki/ + raw/.

derived/ KHÔNG commit. Xoá đi chạy lại là ra y hệt.
Con số trong DB không lấy từ wiki/ — wiki/ chỉ giữ con trỏ `facts_ref`;
script này đi theo con trỏ về `raw/*.facts.json` để lấy giá trị gốc.
"""
import json
import re
import sys
from pathlib import Path

import duckdb
import yaml
import document_registry

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "derived" / "facts.duckdb"


def acl_values(metadata):
    return [metadata.get("visibility", "internal"),
            json.dumps(metadata.get("allowed_roles", []), ensure_ascii=False),
            json.dumps(metadata.get("allowed_users", []), ensure_ascii=False)]


def resolve(ref):
    fpath, dotted = ref.split("#", 1)
    node = json.loads((ROOT / fpath).read_text(encoding="utf-8"))
    node = node.get("facts", node)
    for part in dotted.split("."):
        node = node[part]
    return node


def frontmatter(p):
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def main():
    schema = yaml.safe_load((ROOT / "schema.yml").read_text(encoding="utf-8"))
    cov = yaml.safe_load((ROOT / "coverage.yml").read_text(encoding="utf-8"))
    DB.parent.mkdir(exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))

    con.execute("""CREATE TABLE dim_value(
        dimension VARCHAR, value VARCHAR, label VARCHAR, source VARCHAR)""")
    for dim, spec in schema["dimensions"].items():
        vals = spec["values"]
        pairs = vals.items() if isinstance(vals, dict) else ((v, v) for v in vals)
        for v, label in pairs:
            con.execute("INSERT INTO dim_value VALUES (?,?,?,?)",
                        [dim, v, label, spec["source"]])

    con.execute("""CREATE TABLE person(
        assignee VARCHAR PRIMARY KEY, name VARCHAR, role VARCHAR, project VARCHAR,
        page VARCHAR, task_count BIGINT, estimate_h DOUBLE, actual_h DOUBLE,
        src_task VARCHAR, src_actual VARCHAR, visibility VARCHAR,
        allowed_roles VARCHAR, allowed_users VARCHAR)""")
    for p in sorted((ROOT / "wiki" / "entities").glob("*.md")):
        fm = frontmatter(p)
        if fm.get("page") != "entity-person":
            continue
        n = {k: resolve(fm[k]["facts_ref"]) for k in ("task_count", "estimate_h", "actual_h")}
        con.execute("INSERT INTO person VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            fm["assignee"], fm["name"], fm.get("role"), fm["project"],
            p.relative_to(ROOT).as_posix(),
            int(n["task_count"]["value"]), float(n["estimate_h"]["value"]),
            float(n["actual_h"]["value"]),
            n["task_count"]["src"], n["actual_h"]["src"], *acl_values(fm)])

    # Số theo TỪNG sprint. Thiếu bảng này, bậc 1 chỉ có bảng tổng hợp nên câu
    # "LAN trong sprint 7" bị trả lời bằng số của cả 8 sprint — sai mà không báo.
    con.execute("""CREATE TABLE person_sprint(
        assignee VARCHAR, sprint INTEGER, task_count BIGINT,
        estimate_h DOUBLE, actual_h DOUBLE, src VARCHAR, visibility VARCHAR,
        allowed_roles VARCHAR, allowed_users VARCHAR)""")
    nexus_acl = document_registry.current("nexus-plan", ROOT)
    for p in sorted((ROOT / "raw").glob("*-sprint[0-9].facts.json")):
        n = int(re.search(r"sprint(\d)", p.name).group(1))
        for slug, v in json.loads(p.read_text(encoding="utf-8"))["facts"].items():
            con.execute("INSERT INTO person_sprint VALUES (?,?,?,?,?,?,?,?,?)", [
                slug, n, int(v["task_count"]["value"]),
                float(v.get("estimate_h", {}).get("value", 0)),
                float(v.get("actual_h", {}).get("value", 0)),
                v["task_count"]["src"], *acl_values(nexus_acl)])

    # BẢNG BÁN CẤU TRÚC (kind: rows) -> mỗi Ô một dòng, GIỮ ô nguồn. Đây là nhà của
    # 6 sheet realign hướng A: bậc 1 SQL tra thẳng, số truy được về ô, KHÔNG đọc raw.
    # Nạp ≠ ký: các doc này không nằm trong coverage → bậc 1 chỉ nói CÓ / KHÔNG TÌM THẤY,
    # không nói "chắc chắn không".
    con.execute("""CREATE TABLE doc_cell(
        doc VARCHAR, sheet VARCHAR, row_no INTEGER, col VARCHAR,
        header VARCHAR, value VARCHAR, value_num DOUBLE, src VARCHAR,
        visibility VARCHAR, allowed_roles VARCHAR, allowed_users VARCHAR)""")
    for p in sorted((ROOT / "raw").glob("*.facts.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        # Mọi nguồn có row-record đều vào đây: `kind: rows` (bảng bán cấu trúc) VÀ
        # `kind: table` (sheet sprint — ngoài phần gộp MEASURE còn giữ nguyên từng dòng
        # đủ mọi cột, nên cột như `Note` tra được thay vì biến mất).
        if not d.get("rows") or not d.get("sheet"):
            continue
        doc_acl = document_registry.current(d.get("doc_id", "nexus-plan"), ROOT)
        doc_id = p.name[:-len(".facts.json")]   # 'x.facts.json' -> 'x' (KHÔNG dùng .stem: ra 'x.facts')
        for rec in d["rows"]:
            for col, c in rec["cells"].items():
                con.execute("INSERT INTO doc_cell VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                    doc_id, d["sheet"], rec["row"], col, c["header"],
                    c["value"], c.get("value_num"), c["src"], *acl_values(doc_acl)])

    con.execute("""CREATE TABLE project_metric(
        project VARCHAR, metric VARCHAR, value DOUBLE, unit VARCHAR, src VARCHAR,
        visibility VARCHAR, allowed_roles VARCHAR, allowed_users VARCHAR)""")
    for p in sorted((ROOT / "wiki" / "sources").glob("*.md")):
        fm = frontmatter(p)
        for k, v in fm.items():
            if isinstance(v, dict) and "facts_ref" in v:
                n = resolve(v["facts_ref"])
                # trang source có thể chỉ có `domain`, không `project` (tài liệu Mor) →
                # dùng .get, KHÔNG index cứng `fm["project"]` (sẽ KeyError). project NULL hợp lệ.
                con.execute("INSERT INTO project_metric VALUES (?,?,?,?,?,?,?,?)",
                            [fm.get("project"), k, float(n["value"]), n["unit"], n["src"],
                             *acl_values(fm)])

    # BẢNG QUYẾT ĐỊNH "CHẮC CHẮN KHÔNG" — điều kiện ③.
    # Repo metadata is only an approval REQUEST/RECEIPT. Runtime authorization
    # is checked independently in answer.KB.signed(); a YAML edit cannot grant
    # itself permission to produce a confident negative.
    con.execute("""CREATE TABLE coverage(
        entity VARCHAR, relation VARCHAR, complete_as_of VARCHAR,
        source VARCHAR, asserted_by VARCHAR, signed_date VARCHAR,
        approval_id VARCHAR, required_permission VARCHAR, note VARCHAR)""")
    for c in cov:
        by = str(c.get("asserted_by") or "")
        con.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?,?,?)", [
            c["entity"], c["relation"], c["complete_as_of"], c["source"],
            by, c.get("signed_date", ""), c.get("approval_id", ""),
            c.get("required_permission", ""), c.get("note", "")])

    for t in ("dim_value", "person", "person_sprint", "doc_cell", "project_metric", "coverage"):
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {n:4d} dòng")
    incomplete = con.execute(
        "SELECT relation FROM coverage WHERE signed_date='' OR approval_id='' "
        "OR required_permission='' OR asserted_by LIKE 'TODO%'").fetchall()
    con.close()
    if incomplete:
        print(f"\n⚠ coverage THIẾU RECEIPT: {[r[0] for r in incomplete]}"
              f"\n  -> runtime sẽ hạ 'chắc chắn không' xuống 'không biết'.")
    print(f"\n✓ {DB.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
