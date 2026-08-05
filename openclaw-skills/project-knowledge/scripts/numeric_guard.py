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
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from artifact_paths import current_versions, frontmatter_is_current, payload_is_current
import filesystem_boundary

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
    # ĐỊNH DANH văn bản (luồng VĂN) — KHÔNG phải số đo, giống ô Excel / phiên bản.
    # Đặt TRƯỚC mẫu ô Excel: nếu không, '[A-Z]{1,3}\d+' nuốt 'QH13' và bỏ sót năm.
    r"\b\d+/\d{4}/[A-ZĐ]+\d*(?:[-–][A-ZĐ]+\d*)*", # số hiệu luật: 86/2015/QH13, 72/2013/NĐ-CP
    r"\b[A-Z]{2,}(?:\.[A-Z0-9]+)+",         # mã tài liệu: MOR.BO.PRO.01
    r"(?:Điều|Chương|Mục|Khoản|Điểm)\s*\d+(?:\s*[-–]\s*\d+)?",  # tham chiếu điều khoản: Điều 12, Điều 39–48
    r"\bv\d+(?:\.\d+)*",                   # phiên bản: v2.1
    r"§[\d.]+",                            # tham chiếu mục: §5.3
    r"\b[A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?", # ô Excel: H14, B3:B11
    r"\b[A-Z]{1,10}-\d+\b",                # mã task: AU-1, NEX-123
    r"[Ss]print\s*\d+(?:\s*[-–]\s*\d+)?",  # Sprint 0, Sprint 0–7
    r"\bbậc\s*\d",                         # bậc 1
    r"\b\d+\.\d+\.",                       # số thứ tự mục: 2.4.
    r"\b2\.\d+\.Sprint",                   # tên sheet
]

DATE_TOKEN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"
)
TRANSFORM_TOKEN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b|"
    r"(?<![\w.])\d[\d.,]*(?![\w.])"
)

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


def _canonical_transform_number(token):
    """Canonical numeric spelling for Stage 3 comparison (format-only changes OK)."""
    if DATE_TOKEN.fullmatch(token):
        return f"date:{token}"
    raw = token.strip()
    # Multiple separators of one kind are thousands separators. With one
    # separator, preserve decimal semantics unless exactly three trailing digits.
    if raw.count(",") + raw.count(".") > 1:
        raw = raw.replace(",", "").replace(".", "")
    elif "," in raw:
        left, right = raw.split(",", 1)
        raw = left + right if len(right) == 3 and len(left) >= 1 else left + "." + right
    elif "." in raw:
        left, right = raw.split(".", 1)
        if len(right) == 3 and len(left) > 3:
            raw = left + right
    try:
        dec = Decimal(raw)
    except InvalidOperation:
        return token
    text = format(dec, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def transform_numbers(text):
    """Return [(canonical, recognized_unit, original)] for prose transformation gates."""
    rows = []
    for match in TRANSFORM_TOKEN.finditer(text):
        token = match.group(0)
        # Ignore document/task identifiers, section references and spreadsheet cells.
        prefix = text[max(0, match.start() - 24):match.start()]
        whole = text[max(0, match.start() - 12):min(len(text), match.end() + 12)]
        if any(re.search(pat, whole) for pat in MASK):
            continue
        unit = AnswerGuard._unit_after(text[match.end():]) if "AnswerGuard" in globals() else None
        rows.append((_canonical_transform_number(token), unit, token))
    return rows


def check_transform(before, after, *, allow_loss=False):
    """Numeric transform gate.

    Stage 3 uses the strict default (no new number and no lost unit-bearing
    number). Stage 4 summaries pass ``allow_loss=True`` because omission is
    allowed, while invention/rounding is still blocked.
    """
    src = transform_numbers(before)
    dst = transform_numbers(after)
    src_counts = Counter((n, u) for n, u, _ in src)
    dst_counts = Counter((n, u) for n, u, _ in dst)
    errors, warnings = [], []
    for key, count in (dst_counts - src_counts).items():
        errors.append(f"số mới/đổi/làm tròn `{key[0]}`"
                      + (f" {key[1]}" if key[1] else ""))
    if not allow_loss:
        lost = src_counts - dst_counts
        for (number, unit), count in lost.items():
            message = f"rơi {count}× `{number}`" + (f" {unit}" if unit else "")
            (errors if unit else warnings).append(message)
    return errors, warnings


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

    def __init__(self, root: Path = ROOT):
        self.root = Path(root).resolve()
        self.boundary = filesystem_boundary.ReadOnlyCorpus(self.root)
        self.values: set[str] = set()          # TOÀN CỤC (fallback / self-test)
        self.provenance: dict[str, str] = {}
        self.value_units: dict[str, set] = {}   # TOÀN CỤC: dạng-số -> {đơn vị chuẩn}
        self.by_page: dict[str, set] = {}       # đường dẫn trang wiki -> dạng-số
        self.by_file: dict[str, set] = {}       # stem file raw -> dạng-số
        self.by_sheet: dict[str, set] = {}      # tên sheet (2.8.Sprint 7) -> dạng-số
        self.units_by_page: dict[str, dict] = {}   # trang  -> {dạng-số: {đơn vị}}
        self.units_by_file: dict[str, dict] = {}   # file   -> {dạng-số: {đơn vị}}
        self.units_by_sheet: dict[str, dict] = {}  # sheet  -> {dạng-số: {đơn vị}}
        versions = current_versions(self.root)
        for f in self.boundary.files("raw", "*.facts.json"):
            data = json.loads(self.boundary.read_text(f.relative_to(self.root)))
            if not payload_is_current(data, self.root, versions, path=f):
                continue
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
        # Không có "số nhỏ mặc nhiên an toàn". Mọi count, kể cả 0–20, phải tới từ
        # facts của đúng citation. Task/document identifiers được MASK riêng ở trên.

    @staticmethod
    def _decimal_text(value):
        """Biểu diễn thập phân chính xác, không sinh biến thể đã làm tròn."""
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        text = format(dec, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    # Dạng trình bày TƯƠNG ĐƯƠNG chính xác: 148.0 -> 148; 0.5125 -> 0.5125/51.25%.
    # Tuyệt đối không tạo 45.5 -> 46: flow coi làm tròn là sai dữ liệu.
    def _forms(self, v, unit=None):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return set()
        exact = self._decimal_text(v)
        if exact is None:
            return set()
        forms = {exact}
        # Percentage is only equivalent for an explicitly registered ratio.
        # A fact "43 hours" must never unlock an answer "4300".
        if _canon_fact_unit(unit) == "ratio":
            percent = self._decimal_text(Decimal(str(v)) * Decimal("100"))
            if percent is not None:
                forms.add(percent)
        return forms

    @staticmethod
    def _date_form(value):
        if not isinstance(value, str):
            return None
        value = value.strip()
        return f"date:{value}" if DATE_TOKEN.fullmatch(value) else None

    def _collect(self, node, bucket, ubucket):
        """Đi khắp facts.json: mỗi {value,src} -> dạng-số vào self.values (toàn cục) VÀ
        bucket (cục bộ theo file/sheet); đơn vị -> value_units + ubucket. Token nguyên
        văn ('09') giữ nguyên."""
        if isinstance(node, dict):
            if "value" in node and "src" in node:
                u = _canon_fact_unit(node.get("unit"))
                for f in self._forms(node["value"], node.get("unit")):
                    self.values.add(f); bucket.add(f)
                    self.provenance.setdefault(f, node["src"])
                    if u:
                        self.value_units.setdefault(f, set()).add(u)
                        ubucket.setdefault(f, set()).add(u)
                date_form = self._date_form(node["value"])
                if date_form:
                    self.values.add(date_form); bucket.add(date_form)
                    self.provenance.setdefault(date_form, node["src"])
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
            path = self.boundary.resolve(fpath, must_exist=True)
            node = json.loads(path.read_text(encoding="utf-8"))
            if not payload_is_current(node, self.root, path=path):
                return None
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
            for p in self.boundary.files(f"wiki/{sub}", "*.md"):
                m = re.match(r"^---\n(.*?)\n---\n",
                             self.boundary.read_text(p.relative_to(self.root)), re.S)
                if not m:
                    continue
                try:
                    fm = yaml.safe_load(m.group(1)) or {}
                except yaml.YAMLError:
                    continue
                if not frontmatter_is_current(fm, self.root):
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
                    for f in self._forms(val, unit):
                        self.values.add(f); bucket.add(f)
                        self.provenance.setdefault(f, src)
                        if u:
                            self.value_units.setdefault(f, set()).add(u)
                            ubucket.setdefault(f, set()).add(u)
                path = p.relative_to(self.root).as_posix()
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

        cites là list (kể cả list rỗng) -> chỉ chấp nhận facts của nguồn đã trích.
        cites=None -> lùi về tập TOÀN CỤC cho self-test/back-compat."""
        masked = text
        # Dates are project facts, not harmless identifiers. Validate the whole
        # date token first, then remove it so its year/month/day are not checked
        # again as independent numbers.
        date_bad = []
        date_spans = []
        if cites is not None:
            date_scope: set = set()
            date_units: dict = {}
            for c in cites:
                sf, su = self._resolve_cite(str(c))
                date_scope |= sf
                _merge_units(date_units, su)
        else:
            date_scope = self.values
            date_units = self.value_units
        for match in DATE_TOKEN.finditer(masked):
            if f"date:{match.group(0)}" not in date_scope:
                date_bad.append(match.group(0))
            date_spans.append(match.span())
        if date_spans:
            chars = list(masked)
            for start, end in date_spans:
                chars[start:end] = " " * (end - start)
            masked = "".join(chars)
        for pat in MASK:
            masked = re.sub(pat, " ", masked)
        if cites is not None:
            scope: set = set()
            uscope: dict = {}
            for c in cites:
                sf, su = self._resolve_cite(str(c))
                scope |= sf
                _merge_units(uscope, su)
            valid = scope
        else:
            valid = self.values
            uscope = self.value_units
        bad = list(date_bad)
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


_guards: dict[str, AnswerGuard] = {}


def reset(root: Path | None = None) -> None:
    """Drop the corpus-scoped guard after a new current version is built."""
    if root is None:
        _guards.clear()
    else:
        _guards.pop(str(Path(root).resolve()), None)


def check_answer(text, cites=None, root: Path = ROOT):
    key = str(Path(root).resolve())
    if key not in _guards:
        _guards[key] = AnswerGuard(Path(root))
    return _guards[key].check(text, cites)


def check(policy, **kw):
    """Một cửa vào cho cả hai chính sách."""
    if policy == "ingest":
        return check_ingest(kw["name"], kw["value"], kw["unit"], kw["src"])
    if policy == "answer":
        return check_answer(kw["text"], kw.get("cites"), kw.get("root", ROOT))
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
        ("ngày ISO — đúng nguồn", "2026-07-27", ["Summary project!D4"], []),
        ("ngày ISO — sai nguồn", "2026-07-28", ["Summary project!D4"], ["2026-07-28"]),
        ("0 task — đúng trang", "0 task", ["wiki/entities/tung-dv.md"], []),
        ("task id — định danh", "AU-1", [], []),
        ("999 giờ — bịa", "999 giờ", None, ["999"]),
    ]
    assert "46" not in g._forms(45.5, "hour"), "numeric guard không được cho phép làm tròn 45.5 -> 46"
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
