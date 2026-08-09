#!/usr/bin/env python3
"""numeric_guard — MỘT cơ chế, BA chính sách.

  policy=ingest   Gate 2 · lúc vào  raw/     : giá trị phải là số thật, có unit, có src
  policy=declare  Gate 3a · lúc khai số trên trang wiki (chế độ CHÉP của luồng VĂN):
                                               giá trị phải có mặt ĐÚNG mục mà `src` trỏ
                                               tới, đúng đơn vị — xem §declare bên dưới
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
    # Tham chiếu điều khoản: Điều 12, Điều 39–48. KHÔNG phân biệt hoa/thường: văn bản
    # pháp quy tiếng Việt viết tiêu đề chương in hoa toàn bộ ("CHƯƠNG 2. HỢP ĐỒNG LAO
    # ĐỘNG"), và bản chỉ khớp "Chương" để lọt số chương thành số đo.
    r"(?i:Điều|Chương|Mục|Khoản|Điểm)\s*\d+(?:\s*[-–]\s*\d+)?",
    # Số hiệu tiêu chuẩn: ISO 9001, TCVN 5687:2010. Mẫu ô Excel bên dưới đòi chữ DÍNH
    # số nên không bắt dạng có khoảng trắng, và một tài liệu nhắc ISO 9001 hai lần
    # (mở bài + phần chi tiết) đủ để pha đếm trị số báo "số mới 9001".
    r"(?i:ISO/IEC|ISO|IEC|TCVN|QCVN)\s*\d+(?::\d{4})?",
    r"\[\[page \d+\]\]",                   # marker trang do extract_van chèn
    r"\bv\d+(?:\.\d+)*",                   # phiên bản: v2.1
    # Nhãn kiểm soát tài liệu tiếng Việt, đứng trong footer chạy trang. Con số sau
    # chúng là ĐỊNH DANH phiên bản/lần in, không phải số đo. Chấp nhận cả bản OCR mất
    # dấu ('Lan ban hanh') vì footer là chỗ OCR hỏng nặng nhất.
    r"(?:Phiên|Phien)\s*(?:bản|ban)\s*:?\s*[\d.]+",
    r"(?:Lần|Lan)\s*(?:ban\s*hành|ban\s*hanh)\s*:?\s*[\d.]+",
    r"§[\d.]+",                            # tham chiếu mục: §5.3
    r"\b[A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?", # ô Excel: H14, B3:B11
    r"\b[A-Z]{1,10}-\d+\b",                # mã task: AU-1, NEX-123
    r"[Ss]print\s*\d+(?:\s*[-–]\s*\d+)?",  # Sprint 0, Sprint 0–7
    r"\bbậc\s*\d",                         # bậc 1
    r"\b\d+\.\d+\.",                       # số thứ tự mục: 2.4.
    # Cùng số thứ tự mục nhưng OCR đọc dấu chấm cuối thành dấu phẩy: '42.29,'.
    # Thắt chặt hơn bản có dấu chấm (tối đa 2 chữ số mỗi vế, phải hết từ) vì dấu
    # phẩy còn là dấu thập phân/phân cách nghìn — không được nuốt '1.234,' hay '43,5'.
    r"\b\d{1,2}\.\d{1,2},(?=\s|$)",        # số thứ tự mục hỏng dấu: 42.29,
    r"\b2\.\d+\.Sprint",                   # tên sheet
]

# Số thứ tự mục MỞ ĐẦU MỘT DÒNG, không có dấu chấm cuối: '2.1 Nội dung', '- 43.7',
# '**2.4** ...'. Trang wiki theo chương liệt kê từng Điều nên viết dạng này là tự nhiên,
# và MASK ở trên chỉ bắt dạng có chấm cuối.
#
# Riêng luật này KHÔNG thể là regex thuần. Che theo vị trí đầu dòng thôi là chưa đủ: một
# số ĐO cũng mở đầu dòng được ('43.1 giờ' trong ô bảng hoặc trong câu trả lời), và che
# nó đi là mở một lỗ thật — cổng mất khả năng bắt số bịa. Tiêu chí phân biệt chắc chắn
# nằm ở chữ ĐỨNG SAU: số hiệu mục theo sau là chữ thường ('2.1 Người lao động'), số đo
# theo sau là ĐƠN VỊ ('43.1 giờ'). Nên phải tra UNIT_SYN, việc regex không làm được.
CLAUSE_MARKER = re.compile(r"(?m)^[ \t>|*\-#]*\*{0,2}(\d+(?:\.\d+){1,3})\*{0,2}[.):]?(?=\s|$)")
# Số thứ tự DANH SÁCH markdown: '2. Bản thân Người lao động bị ốm'. Không có dấu chấm
# bên trong nên CLAUSE_MARKER không bắt; phải đòi dấu chấm/ngoặc NGAY SAU chữ số để
# không nuốt '40 giờ mỗi tuần' đứng đầu dòng.
LIST_MARKER = re.compile(r"(?m)^[ \t>|*\-#]*\*{0,2}(\d{1,3})\*{0,2}[.)](?=\s|$)")


def clause_marker_spans(text):
    """Khoảng của số hiệu mục/số thứ tự đầu dòng — bỏ qua nếu ngay sau là ĐƠN VỊ."""
    spans = []
    for pattern in (CLAUSE_MARKER, LIST_MARKER):
        for match in pattern.finditer(text):
            if unit_after(text[match.end():]) is None:
                spans.append(match.span(1))
    return spans


DATE_TOKEN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"
)
TRANSFORM_TOKEN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b|"
    r"(?<![\w.])\d[\d.,]*(?![\w.])"
)

# ---- ĐƠN VỊ (pha 2) --------------------------------------------------------
# Câu trả lời viết đơn vị bằng NHIỀU cách ("h" · "giờ" · "hour"); facts lưu một chuỗi
# chuẩn. Cần một bảng đồng nghĩa gom về DẠNG CHUẨN để so. Từ
# KHÔNG có trong bảng -> coi như "không phải đơn vị nhận diện được" -> BỎ QUA khớp đơn
# vị (lùi về chỉ soi trị số) — giữ cổng khỏi báo động giả trên văn xuôi thường.
#
# Bảng đầu tiên chỉ phủ workbook Nexus (hour/task). Văn bản hành chính tiếng Việt dùng
# một bộ đơn vị khác hẳn — 'ngày' là đơn vị dày đặc nhất trong một bản nội quy lao động
# (45 ngày báo trước, 12 ngày phép, 30 ngày...) mà lại không có trong bảng, nên phần
# khớp đơn vị tự tắt cho đúng những con số quan trọng nhất. Bổ sung theo đúng nguyên
# tắc cũ: chỉ thêm đơn vị THỰC SỰ gặp trong corpus, không thêm cho đủ bộ.
UNIT_SYN = {
    "hour": "hour", "hours": "hour", "h": "hour", "hrs": "hour",
    "giờ": "hour", "tiếng": "hour",
    "task": "task", "tasks": "task", "việc": "task", "công việc": "task",
    "phút": "minute", "minute": "minute", "minutes": "minute", "min": "minute",
    "ngày": "day", "day": "day", "days": "day",
    "tuần": "week", "week": "week", "weeks": "week",
    "tháng": "month", "month": "month", "months": "month",
    "năm": "year", "year": "year", "years": "year",
    "lần": "time", "lượt": "time",
    "đồng": "vnd", "vnd": "vnd", "vnđ": "vnd",
    # KHÔNG có 'người'. Nó gần như không bao giờ là đơn vị đo trong corpus này, nhưng
    # 'Người lao động' là cụm dày đặc nhất của một bản nội quy — nhận nó làm đơn vị thì
    # mọi số hiệu mục đứng trước ('2.1 Người lao động có nghĩa vụ…') hoá thành số đo
    # '2.1 person', và số hiệu mục thì không được che nữa.
    "ký tự": "char", "ký-tự": "char", "char": "char",
    "character": "char", "characters": "char",
}
# Đơn vị facts -> dạng chuẩn. Đơn vị lạ giữ nguyên (lowercase) — câu trả lời sẽ không có
# từ nào map về nó nên không gây lệch giả. `ratio` không khớp vì '%' không phải từ chữ.
FACT_UNIT_CANON = {
    "hour": "hour", "task": "task", "ratio": "ratio",
    "ký tự": "char", "phút": "minute", "tháng": "month", "năm": "year",
    "ngày": "day", "tuần": "week", "lần": "time", "đồng": "vnd",
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


def decimal_text(value):
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
def numeric_forms(value, unit=None):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return set()
    exact = decimal_text(value)
    if exact is None:
        return set()
    forms = {exact}
    # Percentage is only equivalent for an explicitly registered ratio.
    # A fact "43 hours" must never unlock an answer "4300".
    if _canon_fact_unit(unit) == "ratio":
        percent = decimal_text(Decimal(str(value)) * Decimal("100"))
        if percent is not None:
            forms.add(percent)
    return forms


def date_form(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return f"date:{value}" if DATE_TOKEN.fullmatch(value) else None


def declared_forms(value, unit=None):
    """Dạng chuẩn của MỘT giá trị khai báo, cùng bảng mã với `transform_numbers`."""
    stamp = date_form(value)
    return {stamp} if stamp else numeric_forms(value, unit)


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


def unit_after(tail):
    """Đọc đơn vị NGAY SAU con số (tối đa 2 từ chữ, cho 'ký tự') -> dạng chuẩn hoặc
    None. None = không nhận diện được đơn vị -> bỏ qua khớp đơn vị cho token này.

    Chỉ nhìn trong CÙNG MỘT DÒNG. Bản trước dùng `\\s*` nên vắt qua cả dòng trống và
    nhặt chữ đầu của đoạn sau làm đơn vị: footer chạy trang `Lần ban hành: 1.0` ⏎⏎
    `Ngày ban hành:` sinh ra một "số đo 1 ngày" không hề tồn tại. Số đo và đơn vị của
    nó luôn đứng cạnh nhau trong một dòng; qua dấu xuống dòng là sang ý khác."""
    match = re.match(r"[^\S\n]*([^\W\d_]+)(?:[^\S\n]+([^\W\d_]+))?", tail, re.UNICODE)
    if not match:
        return None
    first = match.group(1).lower()
    if match.group(2):
        pair = first + " " + match.group(2).lower()
        if pair in UNIT_SYN:
            return UNIT_SYN[pair]
    return UNIT_SYN.get(first)


def masked_spans(text):
    """Khoảng của các token ĐỊNH DANH (không phải số đo) — che theo VỊ TRÍ THẬT.

    Bản trước soi một cửa sổ ±12 ký tự quanh mỗi con số rồi bỏ qua con số đó nếu cửa
    sổ chạm bất kỳ mẫu định danh nào. Hệ quả là định danh nuốt luôn số đo đứng cạnh:
    'Điều 7: 8 ký tự' mất số 8, 'Sprint 1 có 20 task' mất số 20 — số đo thật biến mất
    khỏi cả hai vế nên Stage 3 im lặng bỏ sót, và khi văn bản được sắp xếp lại cho số
    ra xa định danh thì nó bỗng thành 'số mới' và chặn oan.

    Với cổng khai báo thì đây là lỗi chí mạng: cửa sổ luôn BẮT ĐẦU bằng chính locator
    ('Điều 7'), nên số cần đối chiếu gần như luôn nằm trong 12 ký tự của nó.

    `AnswerGuard.check` vốn đã che theo vị trí (re.sub toàn cục); đây là đưa hai đường
    về cùng một luật."""
    spans = []
    for pattern in MASK:
        spans.extend(match.span() for match in re.finditer(pattern, text))
    spans.extend(clause_marker_spans(text))
    return spans


def _overlaps(span, spans):
    start, end = span
    return any(start < masked_end and masked_start < end
               for masked_start, masked_end in spans)


DOTTED = re.compile(r"\d+(?:\.\d+){1,3}")


def known_identifiers(text):
    """Chuỗi số nằm TRONG vùng đã che của một văn bản — tập định danh của nó.

    `37.4.` trong nguồn được che (số thứ tự mục có chấm cuối). Bản tóm tắt nhắc lại
    nó giữa câu, không dấu chấm cuối — cùng một định danh, nhưng vế kia không che nên
    cổng đọc ra một "số mới 37.4". Đây là BẤT ĐỐI XỨNG giữa hai vế, không phải bịa số.

    Chỉ nhận những chuỗi ĐÃ được vế nguồn coi là định danh. Không suy đoán gì thêm:
    một con số chưa từng xuất hiện trong nguồn vẫn là số mới, và một số đo thật trong
    nguồn không nằm trong vùng che nên không lọt vào tập này."""
    return {match.group(0)
            for start, end in masked_spans(text)
            for match in DOTTED.finditer(text[start:end])}


def transform_numbers(text, identifiers=()):
    """Return [(canonical, recognized_unit, original)] for prose transformation gates.

    `identifiers`: chuỗi số mà VẾ KIA đã coi là định danh — bỏ qua luôn ở vế này."""
    rows = []
    masked = masked_spans(text)
    known = set(identifiers)
    for match in TRANSFORM_TOKEN.finditer(text):
        # Ignore document/task identifiers, section references and spreadsheet cells.
        if _overlaps(match.span(), masked):
            continue
        token = match.group(0)
        if token.rstrip(".,") in known:
            continue
        rows.append((_canonical_transform_number(token),
                     unit_after(text[match.end():]), token))
    return rows


def _units_of(rows, number):
    """Bộ đếm đơn vị nhận diện được của MỘT trị số (bỏ qua token không rõ đơn vị)."""
    return Counter(u for n, u, _ in rows if n == number and u)


def check_transform(before, after, *, allow_loss=False):
    """Numeric transform gate — HAI PHA: trị số trước, đơn vị sau.

    Stage 3 uses the strict default (no new number and no lost unit-bearing
    number). Stage 4 summaries pass ``allow_loss=True`` because omission is
    allowed, while invention/rounding is still blocked.

    Vì sao tách hai pha. Bản trước so theo CẶP `(trị số, đơn vị)`, nên chỉ cần đơn vị
    đổi cách nhận diện là cặp khoá đổi và cổng báo "số mới" — dù trị số không hề đổi.
    Hai đường đi hoàn toàn hợp lệ vấp phải điều này:

      * dàn lại thành bảng    '40 giờ'  ->  '| 40 | giờ |'   (40,hour) -> (40,None)
      * phục hồi dấu tiếng Việt '40 gid' ->  '40 giờ'        (40,None) -> (40,hour)

    Cả hai đều bị báo là bịa số, còn số bịa thật thì lẫn vào giữa đống nhiễu đó. Tách
    ra thì mỗi pha nói đúng một chuyện: pha 1 trả lời "có con số nào chưa từng tồn tại
    không" — đây mới là câu hỏi chống bịa, và nó KHÔNG được nới. Pha 2 chỉ xét những
    trị số có mặt ở cả hai vế, nên đổi đơn vị thật (giờ -> phút) vẫn là lỗi cứng, còn
    được/mất chú thích đơn vị chỉ là cảnh báo. An toàn vì trang structured không phải
    nguồn sự thật: số chỉ thành `facts` qua Gate 3a, nơi `check_declaration()` đối
    chiếu cả trị số lẫn đơn vị với raw/ — và với nguồn OCR thì LUẬT OCR chặn từ đầu.
    """
    src = transform_numbers(before)
    # Định danh của vế nguồn cũng là định danh ở vế đích: `37.4.` là số thứ tự mục dù
    # bản tóm tắt nhắc lại nó thành `37.4` giữa câu.
    dst = transform_numbers(after, known_identifiers(before))
    errors, warnings = [], []

    # ---- PHA 1 · TRỊ SỐ. Bịa/làm tròn là lỗi cứng, không quan tâm đơn vị.
    src_values = Counter(n for n, _, _ in src)
    dst_values = Counter(n for n, _, _ in dst)
    if allow_loss:
        # Bản TÓM TẮT: nhắc lại một giá trị không phải là bịa. Trang wiki nêu "mỗi năm
        # 1 lần" ở thân bài rồi nhắc lại trong ghi chú OCR — so theo BỘI SỐ thì bản thứ
        # hai thành "số mới" và cả trang bị chặn. Câu hỏi đúng ở đây là "có giá trị nào
        # KHÔNG CÓ trong nguồn không", nên so theo TẬP. Đổi giá trị vẫn bị bắt: `11 lần`
        # là một trị số khác và không có trong nguồn.
        invented = set(dst_values) - set(src_values)
    else:
        # Stage 3 chép lại nguyên văn: bội số có nghĩa, thừa một bản cũng là sai lệch.
        invented = dst_values - src_values
    for number in invented:
        errors.append(f"số mới/đổi/làm tròn `{number}`")
    if not allow_loss:
        for number, count in (src_values - dst_values).items():
            # Chỉ MẤT SỐ CÓ ĐƠN VỊ mới là lỗi cứng. Phải hỏi "có instance mang đơn vị
            # nào biến mất không", chứ không phải "giá trị này có ở đâu đó mang đơn vị
            # không": `36` xuất hiện 4 lần — 2 lần là `36 tháng`, 2 lần trần trong số
            # hiệu — và khi một bản TRẦN rơi thì cả hai `36 tháng` vẫn còn nguyên.
            # Gán nhãn theo toàn bộ nguồn thì số trần rơi bị báo thành mất `36 month`.
            gone = _units_of(src, number) - _units_of(dst, number)
            message = f"rơi {count}× `{number}`" + (f" {'/'.join(sorted(gone))}" if gone else "")
            (errors if gone else warnings).append(message)

    # ---- PHA 2 · ĐƠN VỊ, chỉ cho trị số còn nguyên ở cả hai vế.
    for number in sorted(set(src_values) & set(dst_values)):
        gained = _units_of(dst, number) - _units_of(src, number)
        lost = _units_of(src, number) - _units_of(dst, number)
        if gained and lost:
            errors.append(f"đổi đơn vị `{number}`: "
                          f"{'/'.join(sorted(lost))} -> {'/'.join(sorted(gained))}")
        elif gained:
            warnings.append(f"`{number}` được gắn đơn vị {'/'.join(sorted(gained))}")
        elif lost and not allow_loss:
            warnings.append(f"`{number}` mất chú thích đơn vị {'/'.join(sorted(lost))}")
    return errors, warnings


# ------------------------------------ policy=declare · GATE 3a/WIKI · KHAI SỐ
# Luồng SỐ an toàn vì LLM KHÔNG gõ số: trang wiki chỉ giữ `facts_ref` trỏ vào
# raw/*.facts.json do script sinh, nên giá trị không thể lệch by construction.
#
# Luồng VĂN không có .facts.json (số văn xuôi phải hiểu ngữ cảnh mới rút được), nên
# trang wiki khai `{facts, unit, src}` ở chế độ CHÉP — LLM gõ lại con số. Mất tính bất
# biến trên, phải bù bằng một cổng riêng, nếu không Gate 4 sẽ đi xác thực câu trả lời
# của LLM bằng chính lời khai trước đó của LLM.
#
# `check_transform` KHÔNG thay được cổng này: nó chỉ hỏi "số này có mặt đâu đó trong
# nguồn không". Gán 12 (thời hạn lưu log) cho `chu_ky_doi_mat_khau` vẫn lọt, vì 12 có
# thật ở chỗ khác trong tài liệu. Cổng này hỏi câu chặt hơn: "số này có mặt ĐÚNG chỗ
# `src` trỏ tới không, và đơn vị ở đó có khớp không".
SRC_SEP = "::"
SECTION_MARKER = re.compile(
    r"^\s{0,3}#{1,6}\s|"                       # tiêu đề markdown
    r"(?:Điều|Chương|Mục|Khoản|Điểm)\s*\d+|"   # đơn vị văn bản pháp quy
    r"\[\[page\s*\d+\]\]",                     # marker trang PDF
    re.M)
SECTION_WINDOW_MAX = 4000   # trần cửa sổ khi không tìm được ranh giới mục kế tiếp

_boundaries: dict[str, object] = {}
_raw_docs: dict[tuple[str, str], tuple[dict, str] | None] = {}


def _corpus(root):
    key = str(Path(root).resolve())
    if key not in _boundaries:
        _boundaries[key] = filesystem_boundary.ReadOnlyCorpus(Path(root))
    return _boundaries[key]


def split_frontmatter(text):
    """-> (frontmatter dict, body). Không có frontmatter -> ({}, text)."""
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text or "", re.S)
    if not match:
        return {}, text or ""
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), match.group(2)


def _raw_document(root, rel):
    """Đọc MỘT file raw qua boundary -> (frontmatter, body), None nếu không đọc được."""
    key = (str(Path(root).resolve()), str(rel))
    if key not in _raw_docs:
        try:
            corpus = _corpus(root)
            corpus.resolve(rel, must_exist=True)
            _raw_docs[key] = split_frontmatter(corpus.read_text(rel))
        except (filesystem_boundary.BoundaryError, FileNotFoundError, OSError,
                UnicodeDecodeError):
            _raw_docs[key] = None
    return _raw_docs[key]


def parse_src(src):
    """'raw/x.md :: Điều 7' -> ('raw/x.md', 'Điều 7'). Không có '::' -> (path, None)."""
    text = str(src or "").strip()
    if not text:
        return None, None
    if SRC_SEP in text:
        path, locator = text.split(SRC_SEP, 1)
        return path.strip() or None, locator.strip() or None
    return text, None


def locate_sections(body, locator):
    """Các cửa sổ văn bản mà `locator` trỏ tới; [] nếu không tìm thấy locator.

    Cửa sổ chạy từ chỗ locator xuất hiện tới ranh giới mục KẾ TIẾP (tiêu đề, Điều/
    Chương/Mục kế, marker `[[page N]]`) — đủ chứa câu khai số mà không nuốt sang mục
    khác. Đây là thứ phân biệt "số có trong tài liệu" với "số có ĐÚNG chỗ được trích".
    Khoảng trắng và hoa/thường được bỏ qua; dấu tiếng Việt thì không."""
    tokens = str(locator or "").split()
    if not tokens:
        return []
    pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens), re.I)
    windows = []
    for match in pattern.finditer(body):
        nxt = SECTION_MARKER.search(body, match.end())
        end = nxt.start() if nxt else len(body)
        windows.append(body[match.start():min(end, match.start() + SECTION_WINDOW_MAX)])
    return windows


def check_declaration(field, declaration, root: Path = ROOT):
    """Kiểm MỘT khai báo số chế độ chép của trang wiki -> danh sách lỗi (rỗng = qua).

    Đối xứng với `facts_ref`: ref không giải được là lỗi cứng, thì giá trị chép không
    đối chiếu được cũng phải là lỗi cứng."""
    value = declaration.get("facts")
    unit = declaration.get("unit")
    src = declaration.get("src")
    errors = []
    if not unit:
        errors.append("chế độ sao chép nhưng thiếu `unit`")
    if not src:
        errors.append("chế độ sao chép nhưng thiếu `src`")
        return errors
    forms = declared_forms(value, unit)
    if not forms:
        errors.append(f"`facts` không phải số đo hay ngày: {value!r}")
        return errors

    raw_rel, locator = parse_src(src)
    document = _raw_document(root, raw_rel) if raw_rel else None
    if document is None:
        errors.append(f"`src` không trỏ tới nguồn raw đọc được trong corpus: {src!r}")
        return errors
    raw_fm, body = document
    if not frontmatter_is_current(raw_fm, Path(root)):
        errors.append(f"`src` trỏ tới raw không phải bản current: {raw_rel}")
        return errors
    # LUẬT OCR thực thi ở CODE, không chỉ ở prompt: bản OCR là bản ĐOÁN nên số trong đó
    # không được đăng ký làm sự thật. Trạng thái OCR lấy từ raw (do script ghi), KHÔNG
    # lấy từ frontmatter trang wiki (do LLM ghi — nó có thể quên khai).
    if raw_fm.get("ocr") in (True, "true"):
        errors.append(f"LUẬT OCR: {raw_rel} là bản OCR (bản đoán), cấm khai số làm sự thật")
        return errors

    if locator:
        windows = locate_sections(body, locator)
        if not windows:
            errors.append(f"`src` trỏ tới mục không tồn tại trong {raw_rel}: {locator!r}")
            return errors
        where = f"{raw_rel} :: {locator}"
    else:
        windows = [body]
        where = raw_rel

    seen_units: set = set()
    for window in windows:
        for canonical, near_unit, _ in transform_numbers(window):
            if canonical in forms:
                if near_unit is None:
                    return errors          # đơn vị không nhận diện được -> không soi tiếp
                seen_units.add(near_unit)
    if not seen_units:
        errors.append(
            f"giá trị {value!r} không có mặt tại {where} — `check_transform` chỉ hỏi "
            f"'số có trong tài liệu không', cổng này hỏi 'có đúng chỗ đã trích không'")
        return errors
    declared = _canon_fact_unit(unit)
    if declared and declared not in seen_units:
        errors.append(f"đơn vị lệch tại {where}: khai {unit!r} nhưng nguồn ghi "
                      f"{sorted(seen_units)}")
    return errors


def page_ocr_source(frontmatter, root: Path = ROOT):
    """`raw_paths` đầu tiên là bản OCR, hoặc None.

    Trạng thái OCR lấy từ raw do script ghi, KHÔNG chỉ từ trường `ocr` của trang wiki:
    trang do LLM soạn có thể quên khai, và LUẬT OCR không được phụ thuộc vào việc LLM
    có nhớ hay không."""
    if (frontmatter or {}).get("ocr") in (True, "true"):
        return str((frontmatter.get("raw_paths") or ["(trang tự khai ocr)"])[0])
    for raw_rel in (frontmatter or {}).get("raw_paths") or []:
        document = _raw_document(root, str(raw_rel))
        if document and document[0].get("ocr") in (True, "true"):
            return str(raw_rel)
    return None


def check_page_declarations(frontmatter, root: Path = ROOT):
    """Kiểm mọi khai báo chép của MỘT trang wiki -> danh sách lỗi."""
    errors = []
    declarations = {k: v for k, v in (frontmatter or {}).items()
                    if isinstance(v, dict) and "facts" in v}
    # Trang dựng từ nguồn OCR không được khai số, kể cả khi `src` trỏ nơi khác.
    ocr_source = page_ocr_source(frontmatter, root) if declarations else None
    if ocr_source:
        return [f"LUẬT OCR: trang dựng từ nguồn OCR {ocr_source} — "
                f"không được khai bất kỳ trường số nào"]
    for field, declaration in declarations.items():
        errors += [f"`{field}`: {message}"
                   for message in check_declaration(field, declaration, root)]
    return errors


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

    _decimal_text = staticmethod(decimal_text)
    _date_form = staticmethod(date_form)

    def _forms(self, v, unit=None):
        return numeric_forms(v, unit)

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
                # Trạng thái lấy từ raw do script ghi, không chỉ từ trường trang tự khai.
                is_ocr = page_ocr_source(fm, self.root) is not None
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
                    elif "facts" in v and not is_ocr:
                        # Chế độ chép: LLM gõ lại con số, nên phải đối chiếu ngược về
                        # đúng mục `src` trỏ tới TRƯỚC khi cho nó làm sự thật của Gate 4.
                        # Gate 3a đã chặn ở lúc xuất bản; đây là lớp fail-closed thứ hai
                        # để runtime không tin một khai báo chưa kiểm.
                        if check_declaration(k, v, self.root):
                            continue
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
                # Source pages may deliberately keep structured numbers only
                # in their paired raw/*.facts.json (for example a generic
                # workbook whose cells were not curated into frontmatter one
                # by one).  Load those current sibling facts into the page's
                # citation scope.  The registry/path check remains mandatory;
                # a stale or unregistered facts file cannot unlock a number.
                for raw_rel in fm.get("raw_paths") or []:
                    raw_rel = str(raw_rel)
                    if raw_rel.endswith(".fulltext.md"):
                        facts_rel = raw_rel[:-len(".fulltext.md")] + ".facts.json"
                    elif raw_rel.endswith(".md"):
                        facts_rel = raw_rel[:-len(".md")] + ".facts.json"
                    else:
                        continue
                    try:
                        facts_path = self.boundary.resolve(facts_rel, must_exist=True)
                        data = json.loads(self.boundary.read_text(facts_rel))
                    except (filesystem_boundary.BoundaryError, FileNotFoundError,
                            OSError, json.JSONDecodeError):
                        continue
                    if not payload_is_current(data, self.root, path=facts_path):
                        continue
                    self._collect(data, bucket, ubucket)
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

    _unit_after = staticmethod(unit_after)

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
        _boundaries.clear()
        _raw_docs.clear()
        return
    key = str(Path(root).resolve())
    _guards.pop(key, None)
    _boundaries.pop(key, None)
    for cached in [k for k in _raw_docs if k[0] == key]:
        _raw_docs.pop(cached, None)


def check_answer(text, cites=None, root: Path = ROOT):
    key = str(Path(root).resolve())
    if key not in _guards:
        _guards[key] = AnswerGuard(Path(root))
    return _guards[key].check(text, cites)


def check(policy, **kw):
    """Một cửa vào cho ba chính sách."""
    if policy == "ingest":
        return check_ingest(kw["name"], kw["value"], kw["unit"], kw["src"])
    if policy == "answer":
        return check_answer(kw["text"], kw.get("cites"), kw.get("root", ROOT))
    if policy == "declare":
        return check_page_declarations(kw["frontmatter"], kw.get("root", ROOT))
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
