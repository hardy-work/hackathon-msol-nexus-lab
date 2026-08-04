#!/usr/bin/env python3
"""STAGE 4 (phần cuối) — dựng lại `wiki/index.md` TẤT ĐỊNH từ trạng thái wiki/.

CLAUDE.md §4 buộc Stage 4 "cập nhật wiki/index.md, append wiki/log.md". Trước đây hai
việc này làm TAY → index trôi khỏi thực tế (thiếu trang, sai số đếm). Đây là bản MÁY:
đọc frontmatter mọi trang wiki + schema + coverage rồi sinh lại index — không có drift.

  - `index.md` được SINH LẠI trọn (như derived, nhưng nằm trong wiki/ vì là bậc-0 catalog).
  - `log.md` là nhật ký APPEND-ONLY → chỉ thêm dòng, không sinh lại.

ingest.py / ingest_van.py gọi build() + append_log() ở cuối main(). Chạy tay được:

  python3 scripts/build_index.py
"""
import json
import re
from datetime import date
from pathlib import Path

import yaml

import document_registry
from artifact_paths import frontmatter_is_current

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
RAW = ROOT / "raw"
ORIG = ROOT / "originals"

# Mô tả corpus cho người đọc (biên tập). Domain lạ vẫn được liệt kê, mô tả để trống.
DOMAIN_DESC = {
    "nexus": "corpus kế hoạch dự án Nexus (`nexus-plan.xlsx`).",
}


def frontmatter(p):
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    try:
        return yaml.safe_load(m.group(1)) if m else {}
    except yaml.YAMLError:
        return {}


def resolve(ref):
    fpath, dotted = ref.split("#", 1)
    node = json.loads((ROOT / fpath).read_text(encoding="utf-8"))
    node = node.get("facts", node)
    for part in dotted.split("."):
        node = node[part]
    return node


def _pages(sub):
    return sorted((WIKI / sub).glob("*.md")) if (WIKI / sub).exists() else []


def build():
    versions = document_registry.current_versions(ROOT)

    def current_pages(section):
        return [(p, fm) for p in _pages(section)
                for fm in [frontmatter(p)]
                if frontmatter_is_current(fm, ROOT, versions)]

    entities = current_pages("entities")
    sources = current_pages("sources")
    concepts = current_pages("concepts")
    cases = current_pages("case-studies")
    cov = yaml.safe_load((ROOT / "coverage.yml").read_text(encoding="utf-8")) or []

    n_pages = len(entities) + len(sources) + len(concepts) + len(cases)
    n_raw = len(list(RAW.glob("*.md")))
    n_orig = sum(1 for p in ORIG.glob("*")
                 if p.is_file() and p.name not in ("MANIFEST.sha256", ".gitkeep"))

    # corpus xuất hiện thật trong sources/case-studies (không liệt kê domain chưa dùng)
    domains = []
    for _, fm in sources + cases:
        d = fm.get("domain")
        if d and d not in domains:
            domains.append(d)

    out = ["# Chỉ mục kho tri thức", ""]
    out.append(f"Cập nhật ở Stage 4 (scripts/build_index.py). Trạng thái: "
               f"**{n_pages} trang · {n_raw} nguồn `raw/` · {n_orig} tài liệu gốc**.")
    out.append("")

    if domains:
        out += ["## Corpus (`domain`)", ""]
        for d in domains:
            out.append(f"- **{d}** — {DOMAIN_DESC.get(d, '(chưa mô tả)')}")
        out.append("")

    # --- Con người
    def task_count(fm):
        try:
            return int(resolve(fm["task_count"]["facts_ref"])["value"])
        except Exception:
            return -1

    if entities:
        out += ["## Con người — `entities/`", "",
                "| Trang | assignee | role | task (Sprint 1) |", "|---|---|---|---|"]
        for p, fm in sorted(entities, key=lambda pf: -task_count(pf[1])):
            slug = p.stem
            tc = task_count(fm)
            out.append(f"| [[{slug}]] | `{fm.get('assignee', '?')}` | "
                       f"{('`' + fm['role'] + '`') if fm.get('role') else '_n/a_'} | "
                       f"{tc if tc >= 0 else '?'} |")
        out += ["",
                "> Cột task ở đây là **bản sao để đọc nhanh**, không phải nguồn sự thật.",
                "> Nguồn sự thật là `facts_ref` trong frontmatter từng trang.", ""]

    # --- Nguồn
    out += ["## Nguồn — `sources/`", ""]
    if sources:
        out += ["| Trang | doc_id | domain | nguồn `raw/` |", "|---|---|---|---|"]
        for p, fm in sorted(sources, key=lambda pf: (pf[1].get("domain", ""), pf[0].stem)):
            npaths = len(fm.get("raw_paths") or [])
            ocr = " (OCR)" if npaths == 1 and _is_ocr(fm) else ""
            out.append(f"| [[{p.stem}]] | `{fm.get('doc_id', p.stem)}` | "
                       f"`{fm.get('domain', '—')}` | {npaths}{ocr} |")
    else:
        out.append("_(chưa có)_")
    out.append("")

    # --- Khái niệm
    out += ["## Khái niệm — `concepts/`", ""]
    out.append("\n".join(f"- [[{p.stem}]]" for p, _ in concepts) if concepts else "_(chưa có)_")
    out.append("")

    if cases:
        out += ["## Case study — `case-studies/`", ""]
        out += [f"- [[{p.stem}]] — domain `{fm.get('domain', '—')}`" for p, fm in cases]
        out.append("")

    # --- Coverage receipts. Runtime authorization is intentionally external;
    # this catalog must not imply that repository YAML grants permission.
    out += ["## Phạm vi có approval receipt — `coverage.yml`", "",
            "| quan hệ | phạm vi | tính đến | approval |", "|---|---|---|---|"]
    for c in cov:
        out.append(f"| `{c['relation']}` | {c['source'].split('::')[-1].strip()} "
                   f"| {c['complete_as_of']} | `{c.get('approval_id', '—')}` |")
    out += ["", "Receipt chỉ có hiệu lực khi runtime xác thực người ký, permission và approval id. "
            "Ngoài phạm vi đã xác thực, hệ thống **không** được trả lời \"chắc chắn không\".", ""]

    (WIKI / "index.md").write_text("\n".join(out), encoding="utf-8")
    return n_pages


def _is_ocr(fm):
    """Trang source OCR: nguồn raw có cờ ocr. Đọc raw để biết (frontmatter trang không giữ)."""
    for rel in fm.get("raw_paths") or []:
        p = ROOT / rel
        if p.exists() and "\nocr: true" in p.read_text(encoding="utf-8"):
            return True
    return False


def append_log(items, stage):
    """Append một khối Stage 4 vào wiki/log.md (append-only, không sinh lại)."""
    log = WIKI / "log.md"
    old = log.read_text(encoding="utf-8") if log.exists() else "# Nhật ký wiki\n"
    block = (f"\n## {date.today()} · {', '.join(items)} · {stage} · OK\n"
             f"- Sinh/cập nhật {len(items)} trang wiki; `build_index.py` đồng bộ lại `index.md`.\n")
    log.write_text(old.rstrip() + "\n" + block, encoding="utf-8")


if __name__ == "__main__":
    n = build()
    print(f"✓ wiki/index.md — {n} trang")
