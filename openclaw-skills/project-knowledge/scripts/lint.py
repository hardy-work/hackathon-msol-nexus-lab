#!/usr/bin/env python3
"""GATE 3a — bốn lint chạy trên wiki/ sau Stage 4.

  lint-vocab    schema.yml  ==  raw/*.facts.json  (từ vựng không được drift)
  lint-schema   mọi trang đủ trường bắt buộc; giá trị DIMENSION nằm trong enum
  lint-refs     mọi raw_paths tồn tại; mọi liên kết [[x]] có đích; liên kết HAI CHIỀU
  lint-numbers  mọi MEASURE là facts_ref trỏ tới key có thật, HOẶC facts+unit+src

Đỏ ở đây = HALT. Không xuất bản. Đây là chỗ chặn LLM bịa.
Chạy:  python3 scripts/lint.py
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
RAW = ROOT / "raw"

RED, GRN, YEL, DIM, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"

errors: list[tuple[str, str, str]] = []   # (lint, nơi, thông điệp)
warns: list[tuple[str, str, str]] = []


def err(lint, where, msg):
    errors.append((lint, where, msg))


def warn(lint, where, msg):
    warns.append((lint, where, msg))


# ------------------------------------------------------------ nạp dữ liệu
def load_pages():
    """Đọc frontmatter của mọi wiki/**/*.md (trừ index/log)."""
    pages = {}
    for p in sorted(WIKI.rglob("*.md")):
        if p.name in ("index.md", "log.md"):
            continue
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        rel = p.relative_to(ROOT).as_posix()
        if not m:
            err("lint-schema", rel, "không có frontmatter")
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            err("lint-schema", rel, f"frontmatter hỏng: {e}")
            continue
        pages[rel] = {"path": p, "fm": fm, "body": m.group(2)}
    return pages


def load_facts():
    """Gom mọi raw/*.facts.json thành một bảng tra phẳng để lint-numbers dùng."""
    facts = {}
    for p in sorted(RAW.glob("*.facts.json")):
        facts[p.name] = json.loads(p.read_text(encoding="utf-8"))
    return facts


def resolve_ref(facts, ref):
    """'raw/handy-sprint0.facts.json#be-du.actual_h' -> node hoặc None."""
    if "#" not in ref:
        return None
    fpath, dotted = ref.split("#", 1)
    doc = facts.get(Path(fpath).name)
    if doc is None:
        return None
    node = doc.get("facts", doc)
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# --------------------------------------------------- 0. contract (CLAUDE.md)
# CLAUDE.md §2 hứa: "lint bắt buộc hai bản (CLAUDE.md ↔ schema.yml) khớp… không có
# drift thầm lặng." Trước đây KHÔNG có code nào đọc CLAUDE.md → lời hứa là hư cấu, và
# slug assignee đã trôi (fe-h-anh vs fe-hanh…) mà không cổng nào bắt. lint-contract
# biến lời hứa thành thật: parse §2 (enum DIMENSION) + §3 (DIMENSION theo loại trang)
# rồi assert khớp schema.yml. Mắt xích còn lại (schema.yml ↔ facts.json) do lint-vocab
# giữ — ba biểu diễn thành một chuỗi máy-kiểm.
def parse_md_dimensions(text):
    """§2 -> {dim: [values]} cho enum đóng, hoặc {dim: {slug: label}} cho assignee."""
    out = {}
    for m in re.finditer(r"^### `([a-z_]+)`.*?$(.*?)(?=^#{2,3} |\Z)", text, re.M | re.S):
        dim, block = m.group(1), m.group(2)
        rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", block, re.M)
        if rows:                                   # dạng bảng (assignee): slug | nhãn
            out[dim] = {s.strip(): l.strip() for s, l in rows}
            continue
        fence = re.search(r"```\n(.*?)```", block, re.S)
        if fence:                                  # dạng khối rào: a · b · c
            vals = []
            for line in fence.group(1).splitlines():
                vals += [v.strip() for v in line.split("·") if v.strip()]
            out[dim] = vals
    return out


def parse_md_pagetypes(text):
    """§3 -> {ptype: (required[], optional[])}. Ô 'DIMENSION bắt buộc' dạng
    '`a`, `b` (`c` tuỳ chọn)' → required={a,b}, optional={c}; '—' → rỗng."""
    out = {}
    sec = re.search(r"^## 3\..*?(?=^## 4\.)", text, re.M | re.S)
    block = sec.group(0) if sec else text
    for m in re.finditer(r"^\|\s*`([a-z-]+)`\s*\|\s*`[^`]+`\s*\|\s*(.*?)\s*\|", block, re.M):
        ptype, cell = m.group(1), m.group(2)
        opt = []
        for g in re.findall(r"\(([^)]*tuỳ chọn[^)]*)\)", cell):
            opt += re.findall(r"`([a-z_]+)`", g)
        req = [t for t in re.findall(r"`([a-z_]+)`", cell) if t not in opt]
        out[ptype] = (req, opt)
    return out


def lint_contract(schema):
    md = (ROOT / "CLAUDE.md")
    if not md.exists():
        err("lint-contract", "CLAUDE.md", "không tìm thấy CLAUDE.md để đối chiếu")
        return
    text = md.read_text(encoding="utf-8")

    parsed = parse_md_dimensions(text)
    for dim, spec in schema["dimensions"].items():
        want, got = spec["values"], parsed.get(dim)
        if got is None:
            err("lint-contract", "CLAUDE.md §2",
                f"schema.yml có DIMENSION `{dim}` nhưng CLAUDE.md §2 không có mục ### `{dim}`")
            continue
        if isinstance(want, dict):
            if got != want:
                only_md = {k: got[k] for k in got.keys() - want.keys()} or \
                          {k: (got[k], want.get(k)) for k in got if got[k] != want.get(k)}
                only_sc = {k: want[k] for k in want.keys() - got.keys()}
                err("lint-contract", "CLAUDE.md §2 ↔ schema.yml",
                    f"`{dim}` lệch — chỉ/khác ở CLAUDE.md: {only_md} · chỉ ở schema.yml: {only_sc}")
        elif set(got) != set(want):
            err("lint-contract", "CLAUDE.md §2 ↔ schema.yml",
                f"`{dim}` lệch — chỉ CLAUDE.md: {sorted(set(got)-set(want))} · "
                f"chỉ schema.yml: {sorted(set(want)-set(got))}")
    for dim in parsed:
        if dim not in schema["dimensions"]:
            err("lint-contract", "CLAUDE.md §2",
                f"CLAUDE.md §2 khai DIMENSION `{dim}` nhưng schema.yml không có")

    md_pt = parse_md_pagetypes(text)
    for ptype, spec in schema["page_types"].items():
        got = md_pt.get(ptype)
        if got is None:
            err("lint-contract", "CLAUDE.md §3", f"schema.yml có loại trang `{ptype}` nhưng §3 không có")
            continue
        req_md, opt_md = got
        req_sc = spec.get("required_dimensions", [])
        opt_sc = spec.get("optional_dimensions", [])
        if set(req_md) != set(req_sc):
            err("lint-contract", "CLAUDE.md §3 ↔ schema.yml",
                f"`{ptype}` DIMENSION bắt buộc lệch — CLAUDE.md: {sorted(req_md)} · schema.yml: {sorted(req_sc)}")
        if set(opt_md) != set(opt_sc):
            err("lint-contract", "CLAUDE.md §3 ↔ schema.yml",
                f"`{ptype}` DIMENSION tuỳ chọn lệch — CLAUDE.md: {sorted(opt_md)} · schema.yml: {sorted(opt_sc)}")


# ------------------------------------------------------------- 1. vocab
def lint_vocab(schema):
    cfgs = sorted(RAW.glob("*-config.facts.json"))
    cfg = cfgs[0] if cfgs else None
    if cfg is None or not cfg.exists():
        warn("lint-vocab", "raw/", "chưa có *-config.facts.json, bỏ qua đối chiếu")
        return
    v = json.loads(cfg.read_text(encoding="utf-8"))["vocabulary"]
    for dim, vals in v.items():
        if dim not in schema["dimensions"]:
            continue
        got = set(vals)
        spec = schema["dimensions"][dim]["values"]
        want = set(spec.values()) if isinstance(spec, dict) else set(spec)
        if got - want:
            err("lint-vocab", f"raw/{cfg.name}",
                f"{dim} ngoài schema.yml: {sorted(got - want)}")
        if want - got:
            warn("lint-vocab", "schema.yml",
                 f"{dim} khai nhưng sheet không có: {sorted(want - got)}")


def lint_observed(schema):
    """Giá trị DIMENSION thực gặp trong sprint có nằm trong enum không.
    Đây là chỗ bắt được lỗi gõ 'Brse' trong file gốc."""
    for p in sorted(RAW.glob("*-sprint*.facts.json")):
        obs = json.loads(p.read_text(encoding="utf-8")).get("observed_dimensions", {})
        for dim, vals in obs.items():
            spec = schema["dimensions"].get(dim)
            if not spec:
                continue
            allowed = spec["values"]
            allowed = set(allowed.values()) if isinstance(allowed, dict) else set(allowed)
            alias = (schema.get("aliases") or {}).get(dim, {})
            for bad in sorted(set(vals) - allowed):
                if bad in alias:
                    warn("lint-schema", f"raw/{p.name}",
                         f"{dim}='{bad}' là lỗi gõ trong file gốc → người đã duyệt quy về '{alias[bad]}'")
                else:
                    err("lint-schema", f"raw/{p.name}",
                        f"{dim}='{bad}' KHÔNG có trong enum {dim} — sai chính tả trong file gốc?")


# ------------------------------------------------------------ 2. schema
def lint_schema(schema, pages):
    types = schema["page_types"]
    for rel, pg in pages.items():
        fm = pg["fm"]
        ptype = fm.get("page")
        if ptype not in types:
            err("lint-schema", rel, f"page: '{ptype}' không phải loại trang hợp lệ")
            continue
        spec = types[ptype]
        if not rel.startswith(spec["dir"]):
            err("lint-schema", rel, f"loại '{ptype}' phải nằm trong {spec['dir']}/")
        for f in spec["required_fields"]:
            if f not in fm or fm[f] in (None, "", []):
                err("lint-schema", rel, f"thiếu trường bắt buộc `{f}`")
        for dim in spec["required_dimensions"] + spec.get("optional_dimensions", []):
            if dim not in fm:
                if dim in spec["required_dimensions"]:
                    err("lint-schema", rel, f"thiếu DIMENSION bắt buộc `{dim}`")
                continue
            allowed = schema["dimensions"][dim]["values"]
            allowed = set(allowed) if not isinstance(allowed, dict) else set(allowed)
            val = fm[dim]
            for one in (val if isinstance(val, list) else [val]):
                if one not in allowed:
                    err("lint-schema", rel,
                        f"{dim}='{one}' không nằm trong enum — LLM chỉ được CHỌN, không được BỊA")


# -------------------------------------------------------------- 3. refs
LINK = re.compile(r"\[\[([^\]]+)\]\]")


def lint_refs(pages):
    slugs = {Path(rel).stem: rel for rel in pages}

    for rel, pg in pages.items():
        for rp in pg["fm"].get("raw_paths") or []:
            if not (ROOT / rp).exists():
                err("lint-refs", rel, f"raw_paths trỏ tới file không tồn tại: {rp}")

    # liên kết hai chiều: A nhắc B thì B phải nhắc lại A
    out = {rel: set(LINK.findall(pg["body"]) + LINK.findall(str(pg["fm"]))) for rel, pg in pages.items()}
    for rel, targets in out.items():
        me = Path(rel).stem
        for t in targets:
            if t not in slugs:
                err("lint-refs", rel, f"liên kết [[{t}]] không có trang đích")
            elif me not in out[slugs[t]]:
                err("lint-refs", rel,
                    f"liên kết MỘT CHIỀU [[{t}]] — {slugs[t]} không trỏ ngược lại [[{me}]]")


# ----------------------------------------------------------- 4. numbers
NUMWORD = re.compile(r"(?<![\w.])\d[\d.,]*\s*(?:h|giờ|man-day|người)\b", re.I)


def lint_numbers(pages, facts):
    for rel, pg in pages.items():
        for k, v in pg["fm"].items():
            if not isinstance(v, dict):
                continue
            if "facts_ref" in v:
                if resolve_ref(facts, v["facts_ref"]) is None:
                    err("lint-numbers", rel, f"`{k}`: facts_ref không giải được → {v['facts_ref']}")
            elif "facts" in v:
                if not v.get("unit"):
                    err("lint-numbers", rel, f"`{k}`: chế độ sao chép nhưng thiếu `unit`")
                if not v.get("src"):
                    err("lint-numbers", rel, f"`{k}`: chế độ sao chép nhưng thiếu `src`")
            else:
                err("lint-numbers", rel, f"`{k}`: dict số phải có `facts_ref` hoặc `facts`")

        # số gõ tay lẫn trong thân bài — LLM không được tự viết con số
        for hit in NUMWORD.findall(pg["body"]):
            warn("lint-numbers", rel, f"con số gõ tay trong thân bài: '{hit.strip()}' — nên dùng facts_ref")


# ------------------------------------------------------------------ main
def main():
    schema = yaml.safe_load((ROOT / "schema.yml").read_text(encoding="utf-8"))
    pages = load_pages()
    facts = load_facts()

    lint_contract(schema)
    lint_vocab(schema)
    lint_observed(schema)
    lint_schema(schema, pages)
    lint_refs(pages)
    lint_numbers(pages, facts)

    print(f"GATE 3a · {len(pages)} trang wiki · {len(facts)} nguồn facts\n")
    for lint, where, msg in warns:
        print(f"{YEL}⚠ {lint:13s}{OFF} {DIM}{where}{OFF}  {msg}")
    for lint, where, msg in errors:
        print(f"{RED}✗ {lint:13s}{OFF} {DIM}{where}{OFF}  {msg}")

    if errors:
        print(f"\n{RED}GATE 3a ĐỎ — {len(errors)} lỗi. HALT: không xuất bản, ghi wiki/log.md, hỏi người.{OFF}")
        return 1
    print(f"\n{GRN}GATE 3a XANH{OFF} ({len(warns)} cảnh báo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
