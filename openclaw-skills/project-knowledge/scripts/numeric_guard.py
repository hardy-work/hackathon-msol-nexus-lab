#!/usr/bin/env python3
"""numeric_guard — MỘT cơ chế, HAI chính sách.

  policy=ingest   Gate 2 · lúc vào  raw/     : giá trị phải là số thật, có unit, có src
  policy=answer   Gate 4 · lúc ra câu trả lời: mọi con số phải truy được về một khai báo
                                               `facts` có nguồn — raw/*.facts.json (luồng
                                               SỐ) HOẶC frontmatter trang wiki `source`/
                                               `case-study` (luồng VĂN, CLAUDE.md §1.2).

Luồng VĂN không sinh .facts.json ở Stage 2 (số văn xuôi cần LLM hiểu ngữ cảnh mới rút
được), nên số đo của tài liệu văn xuôi được khai ở frontmatter trang wiki đã-qua-Gate
(3a lint + 3b duyệt) rồi nạp vào đây. Định danh văn bản (số hiệu luật, mã tài liệu, số
Điều/Chương) KHÔNG phải số đo — che (MASK) như ô Excel/phiên bản. Tài liệu OCR là bản
ĐOÁN: số ở đó KHÔNG được đăng ký (LUẬT OCR) — chỉ nêu trong thân bài kèm cảnh báo đối
chiếu bản gốc.

Vì sao cần Gate 4 dù đã có Gate 2: Gate 2 chỉ canh đường VÀO. Bậc 3 sinh văn bản
tự do — nó có thể tự cộng 5 con số rồi in ra một số chưa từng tồn tại. Prompt đã
cấm việc đó, nhưng **cấm bằng lời nhắc không phải là cổng**. Đây là cổng.

Nguyên tắc chặn: thà không trả lời còn hơn trả lời một con số không truy được nguồn.
"""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"


class Halt(Exception):
    """Gate chặn. Không ghi/không trả kết quả, dừng và báo người."""


# ------------------------------------------------- policy=ingest · GATE 2
def check_ingest(name, value, unit, src):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Halt(f"GATE 2 · {name}: {value!r} không phải số "
                   f"(kiểu {type(value).__name__}) @ {src}")
    if not unit:
        raise Halt(f"GATE 2 · {name}: thiếu unit @ {src}")
    if not src:
        raise Halt(f"GATE 2 · {name}: thiếu src")
    return {"value": value, "unit": unit, "src": src}


# ------------------------------------------------- policy=answer · GATE 4
# Số KHÔNG phải giá trị đo lường — che đi trước khi soi.
MASK = [
    r"\d{4}-\d{2}-\d{2}",                  # ngày ISO: 2025-12-09
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",  # ngày dd/mm/yyyy · dd-mm-yyyy (VĂN hay dùng)
    # ĐỊNH DANH văn bản (luồng VĂN) — KHÔNG phải số đo, giống ô Excel / phiên bản.
    # Đặt TRƯỚC mẫu ô Excel: nếu không, '[A-Z]{1,3}\d+' nuốt 'QH13' và bỏ sót năm.
    r"\b\d+/\d{4}/[A-ZĐ]+\d*(?:[-–][A-ZĐ]+\d*)*", # số hiệu luật: 86/2015/QH13, 72/2013/NĐ-CP
    r"\b[A-Z]{2,}(?:\.[A-Z0-9]+)+",         # mã tài liệu: MOR.BO.PRO.01
    r"(?:Điều|Chương|Mục|Khoản|Điểm)\s*\d+(?:\s*[-–]\s*\d+)?",  # tham chiếu điều khoản: Điều 12, Điều 39–48
    r"\bv\d+(?:\.\d+)*",                   # phiên bản: v2.1
    r"§[\d.]+",                            # tham chiếu mục: §5.3
    r"\b[A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?", # ô Excel: H14, B3:B11
    r"[Ss]print\s*\d+(?:\s*[-–]\s*\d+)?",  # Sprint 0, Sprint 0–7
    r"\bbậc\s*\d",                         # bậc 1
    r"\b\d+\.\d+\.",                       # số thứ tự mục: 2.4.
    r"\b2\.\d+\.Sprint",                   # tên sheet
]

# ---- ĐƠN VỊ (pha 2) --------------------------------------------------------
# Câu trả lời viết đơn vị bằng NHIỀU cách ("h" · "giờ" · "hour"); facts lưu một chuỗi
# chuẩn. Cần một bảng đồng nghĩa gom về DẠNG CHUẨN để so. Chỉ gom các đơn vị thực sự
# xuất hiện trong facts Nexus (hour/task). Từ
# KHÔNG có trong bảng -> coi như "không phải đơn vị nhận diện được" -> BỎ QUA khớp đơn
# vị (lùi về chỉ soi trị số) — giữ cổng khỏi báo động giả trên văn xuôi thường.
UNIT_SYN = {
    "hour": "hour", "hours": "hour", "h": "hour", "hrs": "hour",
    "giờ": "hour", "tiếng": "hour",
    "task": "task", "tasks": "task", "việc": "task", "công việc": "task",
    "phút": "minute", "minute": "minute", "minutes": "minute", "min": "minute",
    "tháng": "month", "month": "month", "months": "month",
    "năm": "year", "year": "year", "years": "year",
    "ký tự": "char", "ký-tự": "char", "char": "char",
    "character": "char", "characters": "char",
}
# Đơn vị facts -> dạng chuẩn. Đơn vị lạ giữ nguyên (lowercase) — câu trả lời sẽ không có
# từ nào map về nó nên không gây lệch giả. `ratio` không khớp vì '%' không phải từ chữ.
FACT_UNIT_CANON = {
    "hour": "hour", "task": "task", "ratio": "ratio",
    "ký tự": "char", "phút": "minute", "tháng": "month", "năm": "year",
}


def _canon_fact_unit(unit):
    if not unit:
        return None
    u = str(unit).strip().lower()
    return FACT_UNIT_CANON.get(u, u)


def _merge_units(dst, src):
    """Gộp dict {dạng-số: set(đơn vị)} nguồn vào đích (in-place)."""
    for k, v in src.items():
        dst.setdefault(k, set()).update(v)


class AnswerGuard:
    """Số hợp lệ = số có thật, gắn NGUỒN. Hai chế độ:

      - TOÀN CỤC (không truyền cites): số nào có mặt ở BẤT KỲ nguồn nào cũng qua. Thô —
        một số ở nguồn khác có thể trùng. Giữ cho self-test/back-compat.
      - THEO NGỮ CẢNH (truyền cites): số phải có mặt trong facts của ĐÚNG nguồn câu trả
        lời đã trích. Đây là cổng thật: câu trích noi-quy (OCR, 0 facts) không mở khoá
        được số đo của nguồn khác.

    Chỉ mục nguồn dựng một lần: theo TRANG wiki, theo FILE raw, theo SHEET. Một `cite`
    (chuỗi kiểu 'wiki/entities/qc-lan.md → 2.8.Sprint 7!G10') resolve bằng cách khớp
    substring với khoá của ba chỉ mục rồi hợp các tập dạng-số lại."""

    def __init__(self):
        self.values: set[str] = set()          # TOÀN CỤC (fallback / self-test)
        self.provenance: dict[str, str] = {}
        self.value_units: dict[str, set] = {}   # TOÀN CỤC: dạng-số -> {đơn vị chuẩn}
        self.by_page: dict[str, set] = {}       # đường dẫn trang wiki -> dạng-số
        self.by_file: dict[str, set] = {}       # stem file raw -> dạng-số
        self.by_sheet: dict[str, set] = {}      # tên sheet (2.8.Sprint 7) -> dạng-số
        self.units_by_page: dict[str, dict] = {}   # trang  -> {dạng-số: {đơn vị}}
        self.units_by_file: dict[str, dict] = {}   # file   -> {dạng-số: {đơn vị}}
        self.units_by_sheet: dict[str, dict] = {}  # sheet  -> {dạng-số: {đơn vị}}
        for f in sorted(RAW.glob("*.facts.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            bucket: set = set()
            ubucket: dict = {}
            self._collect(data, bucket, ubucket)  # -> self.values/value_units (toàn cục) + bucket/ubucket (cục bộ)
            stem = f.name[:-len(".facts.json")]
            self.by_file.setdefault(stem, set()).update(bucket)
            _merge_units(self.units_by_file.setdefault(stem, {}), ubucket)
            if data.get("sheet"):
                self.by_sheet.setdefault(data["sheet"], set()).update(bucket)
                _merge_units(self.units_by_sheet.setdefault(data["sheet"], {}), ubucket)
        self._load_wiki_facts()
        # Số CẤU TRÚC (đếm bản ghi, ≤20): tất định, không phải số đo -> cho phép TOÀN CỤC.
        self.structural = {str(n) for n in range(0, 21)}

    # dạng trình bày tất định của một số: 148.0 -> {148}, 0.9959 -> {99.59, 0.9959, …}
    def _forms(self, v):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return set()
        forms = {repr(v), str(v)}
        if isinstance(v, float):
            if v.is_integer():
                forms.add(str(int(v)))
            forms |= {f"{v:.{d}f}" for d in range(0, 7)}          # làm tròn
            forms |= {f"{v * 100:.{d}f}" for d in range(0, 5)}    # dạng phần trăm
        return {f.rstrip("0").rstrip(".") if "." in f else f for f in forms}

    def _collect(self, node, bucket, ubucket):
        """Đi khắp facts.json: mỗi {value,src} -> dạng-số vào self.values (toàn cục) VÀ
        bucket (cục bộ theo file/sheet); đơn vị -> value_units + ubucket. Token nguyên
        văn ('09') giữ nguyên."""
        if isinstance(node, dict):
            if "value" in node and "src" in node:
                u = _canon_fact_unit(node.get("unit"))
                for f in self._forms(node["value"]):
                    self.values.add(f); bucket.add(f)
                    self.provenance.setdefault(f, node["src"])
                    if u:
                        self.value_units.setdefault(f, set()).add(u)
                        ubucket.setdefault(f, set()).add(u)
                if isinstance(node.get("text"), str):
                    self.values.add(node["text"]); bucket.add(node["text"])
                    self.provenance.setdefault(node["text"], node["src"])
            for v in node.values():
                self._collect(v, bucket, ubucket)
        elif isinstance(node, list):
            for v in node:
                self._collect(v, bucket, ubucket)

    def _wiki_resolve(self, ref):
        try:
            fpath, dotted = ref.split("#", 1)
            node = json.loads((ROOT / fpath).read_text(encoding="utf-8"))
            node = node.get("facts", node)
            for part in dotted.split("."):
                node = node[part]
            return node
        except Exception:
            return None

    def _load_wiki_facts(self):
        """Số đo của trang wiki -> by_page[đường dẫn] (và toàn cục). Cả hai chế độ khai:
        `facts_ref` (trỏ raw) và `facts` chép."""
        for sub in ("entities", "sources", "case-studies", "concepts"):
            for p in sorted((WIKI / sub).glob("*.md")) if (WIKI / sub).exists() else []:
                m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
                if not m:
                    continue
                try:
                    fm = yaml.safe_load(m.group(1)) or {}
                except yaml.YAMLError:
                    continue
                # LUẬT OCR: trang OCR là bản ĐOÁN — KHÔNG đăng ký số (thực thi ở CODE).
                is_ocr = fm.get("ocr") in (True, "true")
                bucket: set = set()
                ubucket: dict = {}
                for k, v in fm.items():
                    if not isinstance(v, dict):
                        continue
                    node = None
                    if "facts_ref" in v:
                        node = self._wiki_resolve(v["facts_ref"])
                        val, src = (node.get("value"), node.get("src", "")) if node else (None, "")
                        unit = node.get("unit") if node else None
                    elif "facts" in v and v.get("src") and not is_ocr:
                        val, src = v["facts"], v["src"]
                        unit = v.get("unit")
                    else:
                        continue
                    u = _canon_fact_unit(unit)
                    for f in self._forms(val):
                        self.values.add(f); bucket.add(f)
                        self.provenance.setdefault(f, src)
                        if u:
                            self.value_units.setdefault(f, set()).add(u)
                            ubucket.setdefault(f, set()).add(u)
                path = p.relative_to(ROOT).as_posix()
                self.by_page[path] = bucket
                self.units_by_page[path] = ubucket

    def _resolve_cite(self, cite):
        """Một chuỗi cite -> (tập dạng-số, {dạng-số: {đơn vị}}) của các nguồn nó nhắc
        tới (khớp substring)."""
        out: set = set()
        uout: dict = {}
        for path, forms in self.by_page.items():
            if path in cite:
                out |= forms
                _merge_units(uout, self.units_by_page.get(path, {}))
        for sheet, forms in self.by_sheet.items():
            if sheet and sheet in cite:
                out |= forms
                _merge_units(uout, self.units_by_sheet.get(sheet, {}))
        for stem, forms in self.by_file.items():
            if stem in cite:
                out |= forms
                _merge_units(uout, self.units_by_file.get(stem, {}))
        return out, uout

    @staticmethod
    def _unit_after(tail):
        """Đọc đơn vị NGAY SAU con số (tối đa 2 từ chữ, cho 'ký tự') -> dạng chuẩn hoặc
        None. None = không nhận diện được đơn vị -> bỏ qua khớp đơn vị cho token này."""
        m = re.match(r"\s*([^\W\d_]+)(?:\s+([^\W\d_]+))?", tail, re.UNICODE)
        if not m:
            return None
        w1 = m.group(1).lower()
        if m.group(2):
            two = w1 + " " + m.group(2).lower()
            if two in UNIT_SYN:
                return UNIT_SYN[two]
        return UNIT_SYN.get(w1)

    def check(self, text, cites=None):
        """-> danh sách con số KHÔNG truy được nguồn.

        cites có -> chỉ chấp nhận số thuộc facts của nguồn đã trích (ngữ cảnh).
        cites rỗng/None -> lùi về tập TOÀN CỤC (self-test, back-compat)."""
        masked = text
        for pat in MASK:
            masked = re.sub(pat, " ", masked)
        if cites:
            scope: set = set()
            uscope: dict = {}
            for c in cites:
                sf, su = self._resolve_cite(str(c))
                scope |= sf
                _merge_units(uscope, su)
            valid = scope | self.structural
        else:
            valid = self.values | self.structural
            uscope = self.value_units
        bad = []
        for m in re.finditer(r"(?<![\w.])\d+(?:[.,]\d+)?", masked):
            tok = m.group(0)
            norm = tok.replace(",", ".")
            norm = norm.rstrip("0").rstrip(".") if "." in norm else norm
            forms = {norm}
            if norm.isdigit():                       # '06 tháng' == '6 tháng', '01' == '1'
                forms.add(norm.lstrip("0") or "0")
            if not (forms & valid):
                bad.append(tok)                      # trị số không truy được nguồn
                continue
            # ĐƠN VỊ (pha 2): trị số truy được, NHƯNG nếu kề một đơn vị nhận diện được mà
            # số này chỉ đăng ký với đơn vị KHÁC (không có đơn vị đang nêu) -> LỆCH ĐƠN VỊ,
            # chặn. "8 ký tự" qua; "8 phút" chặn (8 đăng ký là ký tự). Chỉ chặn khi lệch
            # DƯƠNG: số có đăng ký đơn vị trong phạm vi mà không khớp — số cấu trúc thuần
            # (đếm bản ghi, không đơn vị) không có regs nên miễn, giữ nguyên hành vi cũ.
            unit = self._unit_after(masked[m.end():])
            if unit:
                regs: set = set()
                for f in forms:
                    regs |= uscope.get(f, set())
                if regs and unit not in regs:
                    bad.append(tok)
        return bad


_guard = None


def check_answer(text, cites=None):
    global _guard
    if _guard is None:
        _guard = AnswerGuard()
    return _guard.check(text, cites)


def check(policy, **kw):
    """Một cửa vào cho cả hai chính sách."""
    if policy == "ingest":
        return check_ingest(kw["name"], kw["value"], kw["unit"], kw["src"])
    if policy == "answer":
        return check_answer(kw["text"], kw.get("cites"))
    raise ValueError(f"policy không hợp lệ: {policy}")


if __name__ == "__main__":
    import sys

    g = AnswerGuard()
    nwiki = sum(1 for sub in ("sources", "case-studies")
                for p in (WIKI / sub).glob("*.md") if (WIKI / sub).exists())
    print(f"{len(g.values)} dạng số hợp lệ từ {len(list(RAW.glob('*.facts.json')))} nguồn "
          f"facts + {nwiki} trang wiki VĂN")

    # Corpus-specific regression cases (Nexus Plan).
    CASES = [
        ("43 giờ — có nguồn", "43 giờ", None, []),
        ("43.1 giờ — bịa", "43.1 giờ", None, ["43.1"]),
        ("10 task — đúng trang", "10 task", ["wiki/entities/son-bh.md"], []),
        ("10 giờ — lệch đơn vị", "10 giờ", ["wiki/entities/son-bh.md"], ["10"]),
        ("43 phút — lệch đơn vị", "43 phút", ["wiki/entities/son-bh.md"], ["43"]),
        ("ngày ISO — định danh", "2026-07-27", None, []),
        ("0 task — số cấu trúc", "0 task", ["wiki/entities/tung-dv.md"], []),
        ("999 giờ — bịa", "999 giờ", None, ["999"]),
    ]
    fails = 0
    for label, text, cites, want in CASES:
        got = g.check(text, cites=cites)
        ok = got == want
        fails += not ok
        verdict = "CHẶN " + str(got) if got else "qua"
        note = "" if ok else f"  ✗ mong {'CHẶN ' + str(want) if want else 'qua'}"
        print(f"  {'✓' if ok else '✗'} {label:36s} -> {verdict}{note}")
    if fails:
        print(f"✗ numeric_guard self-test: {fails}/{len(CASES)} FAIL")
        sys.exit(1)
    print(f"✓ numeric_guard self-test: {len(CASES)}/{len(CASES)} qua")
