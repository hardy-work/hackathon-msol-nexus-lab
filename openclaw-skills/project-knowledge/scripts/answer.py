#!/usr/bin/env python3
"""TRUY VẤN 4 BẬC · 3 LOẠI KẾT QUẢ.

  Bậc 1  TRUY VẤN CÓ CẤU TRÚC   derived/facts.duckdb + DIMENSION + coverage
                                 tất định · là bậc DUY NHẤT được nói "chắc chắn không"
  Bậc 2  TÌM KIẾM TỪ KHOÁ        wiki/*.md
  Bậc 3  LLM ĐỌC TRANG WIKI      claude -p (chỉ bật bằng --llm)
  Bậc 4  NGUỒN THÔ               raw/*.md

  Kết quả:  CÓ  ·  CHẮC CHẮN KHÔNG  ·  KHÔNG TÌM THẤY

Ba loại kết quả KHÔNG thay thế nhau được. "Không tìm thấy" nghĩa là kho không
biết; "chắc chắn không" nghĩa là kho biết là không có. Nói nhầm cái sau thành
cái trước chỉ mất thông tin; nói nhầm cái trước thành cái sau là NÓI DỐI.

  python3 scripts/answer.py "câu hỏi"
"""
import re
import json
import sys
import unicodedata
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numeric_guard
import models

# Bậc 2 NGỮ NGHĨA (vector bge-m3 trên TRANG WIKI). Lười nạp: model ~2GB nên CHỈ nạp
# khi thật sự dùng (câu mở, LLM bật). Không có chỉ mục / thiếu thư viện -> None,
# hệ tự lui về keyword thuần, không sập.
_SEM = False


def SEM():
    global _SEM
    if _SEM is False:
        try:
            from embed_index import Semantic
            _SEM = Semantic()
        except Exception as e:
            print(f"{D}(bậc 2 vector tắt: {type(e).__name__}){OFF}")
            _SEM = None
    return _SEM


def semantic_pages(q, k=6):
    sem = SEM()
    if sem is None:
        return []
    try:
        return [p for _, p in sem.search(q, k=k)]
    except Exception:
        return []


def rrf_merge(rank_lists, keep=6, pin=(), k0=60):
    """Reciprocal Rank Fusion (node 77): hợp nhất nhiều bảng xếp hạng thành một.
    Trang đứng cao ở NHIỀU bảng thì lên đầu. `pin` = trang ép giữ trước (định danh
    đóng: người / tài liệu được nhắc đích danh)."""
    score = {}
    for lst in rank_lists:
        for rank, it in enumerate(lst):
            score[it] = score.get(it, 0.0) + 1.0 / (k0 + rank + 1)
    ordered = [it for it, _ in sorted(score.items(), key=lambda x: -x[1])]
    seen, out = set(), []
    for it in list(pin) + ordered:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out[:keep]

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "derived" / "facts.duckdb"
RAW = ROOT / "raw"

CO, NO, NF = "CÓ", "CHẮC CHẮN KHÔNG", "KHÔNG TÌM THẤY"
G, R, Y, B, D, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[34m", "\033[2m", "\033[0m"

# Bảng bán cấu trúc (realign A) — 6 sheet đã nạp vào duckdb bậc 1 (bảng doc_cell),
# KHÔNG còn đọc raw. Data CÓ trong kho nhưng KHÔNG thuộc coverage.yml đã ký → bậc 1 chỉ
# nói CÓ / KHÔNG TÌM THẤY cho chúng, KHÔNG nói "chắc chắn không".
# Biên từ để "cr"/"roc"/"uat" không dính nhầm vào giữa chữ khác.
DOC_SHEETS = [
    (r"master schedule|lich tong", "nexus-master-schedule"),
    (r"\bbacklog\b",     "nexus-backlog"),
    (r"sprint\s*1",       "nexus-sprint1"),
    (r"risk|rui ro",     "nexus-risk"),
    (r"issue|van de",     "nexus-issue"),
    (r"summary|tong quan|lich sprint", "nexus-summary"),
    (r"resource|nguon luc", "nexus-resource-plan"),
]

# Các nhãn cột thường được hỏi bằng tiếng Việt.  Đây là ánh xạ định tuyến, không
# tạo thêm dữ liệu: giá trị cuối cùng vẫn phải lấy từ đúng ô trong `doc_cell`.
FIELD_PATTERNS = {
    "start": (r"^start date$", r"plan start date", r"actual start date"),
    "end": (r"^end date$", r"plan end date", r"actual end date"),
    "status": (r"^status$",),
    "pic": (r"^pic$", r"^assignee$", r"related assignee"),
    "task": (r"^task$", r"^task name$"),
    "priority": (r"^priority$",),
    "progress": (r"^progress$",),
    "remaining": (r"remaining",),
    "actual_effort": (r"actual effort", r"actual_h", r"thuc te"),
    "estimate": (r"estimate", r"uoc luong", r"re-estimated effort"),
    "scope": (r"^scope$", r"project scope", r"category milestone"),
    "person": (r"ten nhan su", r"^assignee$", r"^nguoi$"),
    "role": (r"^role$", r"^vai tro$"),
    "level": (r"xep hang", r"^level$"),
}


def inferred_docs(q):
    """Chọn sheet theo ngữ cảnh khi người hỏi không nêu tên sheet.

    Chỉ là định tuyến hẹp theo các trường/giá trị đã biết; nếu không chắc thì để
    bậc 2/3 xử lý thay vì đoán sheet.
    """
    qa = strip_accent(q)
    if re.search(r"nhung nguoi|nguoi co task|ai tham gia|liet ke .*nguoi", qa):
        return []
    if re.search(r"summary\s*project", qa):
        return ["nexus-summary"]
    if re.search(r"master\s*schedule|lich\s*(tong|trinh)", qa):
        return ["nexus-master-schedule"]
    if re.search(r"resource\s*plan|nguon luc|nhan su|xep hang", qa):
        return ["nexus-resource-plan"]
    if re.search(r"sprint\s*1", qa) and re.search(
            r"task|cong viec|priority|uu tien|status|trang thai|progress|tien do|remaining|con lai",
            qa):
        return ["nexus-sprint1"]
    if re.search(r"authentication|user profile|product catalog|shopping cart|order management",
                 qa) and re.search(r"bat dau|khoi dong|ket thuc|deadline|pic|status|trang thai",
                                   qa):
        return ["nexus-master-schedule"]
    # Tên task/field phổ biến đã nằm trong Sprint 1. Chỉ dùng khi câu hỏi có
    # dấu hiệu hỏi task, tránh kéo một câu mở bất kỳ vào bảng.
    if re.search(r"api\s+login|taskid|task|cong viec|priority|uu tien|remaining|con lai",
                 qa):
        return ["nexus-sprint1"]
    return []


def requested_field_keys(q):
    """Xác định cột cần trả, để không đổ cả dòng Excel vào câu trả lời."""
    qa = strip_accent(q)
    keys = []
    if re.search(r"actual\s+start|ngay\s+bat dau\s+thuc te", qa):
        keys.append("start")
    elif re.search(r"plan\s+start|ke hoach.*bat dau", qa):
        keys.append("start")
    elif re.search(r"bat dau|khoi dong|start date", qa):
        keys.append("start")
    if re.search(r"actual\s+end|ngay\s+ket thuc\s+thuc te", qa):
        keys.append("end")
    elif re.search(r"plan\s+end|ke hoach.*ket thuc", qa):
        keys.append("end")
    elif re.search(r"ket thuc|deadline|end date|han", qa):
        keys.append("end")
    if re.search(r"trang thai|tinh trang|\bstatus\b", qa):
        keys.append("status")
    if re.search(r"\bpic\b|phu trach|nguoi phu trach|ai phu trach", qa):
        keys.append("pic")
    if re.search(r"uu tien|\bpriority\b", qa):
        keys.append("priority")
    if re.search(r"\btask\b|cong viec|dau viec", qa):
        keys.append("task")
    if re.search(r"con lai|remaining", qa):
        keys.append("remaining")
    if re.search(r"tien do|\bprogress\b", qa):
        keys.append("progress")
    if re.search(r"actual effort|thuc te|da bo ra|da dung", qa):
        keys.append("actual_effort")
    if re.search(r"uoc luong|estimate|re-estimated|re-est", qa):
        keys.append("estimate")
    if re.search(r"scope|pham vi|milestone", qa):
        keys.append("scope")
    if re.search(r"ten nhan su|nhung nguoi|nhan su|nguoi nao", qa):
        keys.append("person")
    if re.search(r"vai tro|\brole\b", qa):
        keys.append("role")
    if re.search(r"xep hang|senior|middle|junior|level", qa):
        keys.append("level")
    return list(dict.fromkeys(keys))


def select_row_cells(row, q):
    """Chỉ giữ các ô trả lời câu hỏi; bỏ metadata như số dòng Excel."""
    keys = requested_field_keys(q)
    if not keys:
        return [(h, v, s) for _, h, v, s in row["cells"] if v]
    patterns = [pat for key in keys for pat in FIELD_PATTERNS.get(key, ())]
    picked = [(h, v, s) for _, h, v, s in row["cells"]
              if v and any(re.search(pat, strip_accent(h).lower()) for pat in patterns)]
    return picked or [(h, v, s) for _, h, v, s in row["cells"] if v]


def wants_list(q):
    qa = strip_accent(q)
    return bool(re.search(
        r"liet ke|danh sach|nhung|cac\s+|co .* nao|task nao|remaining|nhan su|scope nao|phan bo|the nao",
        qa))


def has_specific_value(q):
    qa = strip_accent(q)
    return bool(re.search(
        r"done|open|in progress|pending|cancel|highest|high|medium|low|"
        r"authentication|user profile|product catalog|shopping cart|order management|"
        r"api\s+login|bui\s+hong\s+son|nguyen\s+thanh\s+do|senior|junior|middle",
        qa))


def filter_structured_hits(kb, q, hits):
    """Lọc giá trị cột/đối tượng trước khi xếp hạng từ khoá.

    Từ chỉ câu hỏi như ``trạng thái`` không nằm trong blob giá trị, vì vậy chỉ
    chấm IDF có thể chọn nhầm một task khác. Các enum và subject đã biết phải
    được lọc theo ô tương ứng trước.
    """
    qa = strip_accent(q)
    rows = [row for _, row in hits]
    filtered = None
    for value in ("Open", "In progress", "Done", "Pending", "Cancel"):
        if strip_accent(value) in qa and re.search(r"trang thai|status", qa):
            filtered = [row for row in rows if any(
                strip_accent(v) == strip_accent(value)
                for _, h, v, _ in row["cells"] if strip_accent(h) == "status")]
            break
    if filtered is None:
        for value in ("Highest", "High", "Medium", "Low"):
            if strip_accent(value) in qa and re.search(r"uu tien|priority", qa):
                filtered = [row for row in rows if any(
                    strip_accent(v) == strip_accent(value)
                    for _, h, v, _ in row["cells"] if strip_accent(h) == "priority")]
                break
    if filtered is None and re.search(r"con lai|remaining", qa):
        filtered = [row for row in rows if any(
            h.lower().startswith("remaining") and v not in ("", "0", "0.0")
            for _, h, v, _ in row["cells"])]

    # Các subject đóng/ổn định trong workbook.  Nếu người dùng nói rõ subject,
    # mọi token của subject phải xuất hiện trong cùng dòng.
    subjects = [
        "api login", "authentication", "user profile management",
        "product catalog", "shopping cart", "order management",
        "bui hong son", "nguyen thanh do", "van ngoc long",
        "nguyen van vinh", "mai viet hoang", "do trung kien",
    ]
    for subject in subjects:
        if subject in qa:
            tokens = subject.split()
            candidate = filtered if filtered is not None else rows
            filtered = [row for row in candidate if all(
                tok in strip_accent(" ".join(v for _, _, v, _ in row["cells"]))
                for tok in tokens)]
            break
    if filtered is None:
        return hits
    return [(1.0 - i / max(len(filtered), 1), row) for i, row in enumerate(filtered)]


def docs_mentioned(q):
    """doc_id của sheet bảng được câu hỏi nhắc ĐÍCH DANH (theo tên sheet)."""
    qa = strip_accent(q)
    return [d for pat, d in DOC_SHEETS if re.search(pat, qa)]


def qterms(q):
    """Token tra cứu bảng: bỏ dấu + tách chữ/số, bỏ STOP và token ngắn.

    Chữ số ĐƠN cố ý bị loại: '3' khớp vào mọi ngày tháng, mã số, giờ công trong kho
    (đã thử — một câu hỏi ra 123 dòng rác). Muốn phân biệt Sprint 3 với Sprint 5 thì
    phải đi bằng cụm từ hoặc tên sheet, không phải bằng một chữ số trôi nổi."""
    return [t for t in re.findall(r"[a-z0-9]+", strip_accent(q)) if len(t) > 2 and t not in STOP]


# Nhãn cột trong file gốc là tiếng Anh/Nhật, người hỏi bằng tiếng Việt. Không có
# cầu nối này thì "sprint 3 bắt đầu ngày nào" không bao giờ chạm được cột "Start date"
# — dữ liệu nằm trong kho mà vẫn ra 'không tìm thấy'.
HEADER_SYNONYM = {
    "ngay": "date", "bat dau": "start", "khoi dong": "start", "ket thuc": "end",
    "han": "deadline", "trang thai": "status", "tinh trang": "status",
    "ghi chu": "note", "luu y": "note", "nguoi": "assignee", "phu trach": "assignee",
    "tien do": "progress", "uoc luong": "estimate", "cong viec": "task",
    "thuc te": "actual", "con lai": "remaining", "thang": "month", "tuan": "week",
    # nhãn cột vốn đã là tiếng Anh — người hỏi gõ thẳng chữ đó thì cũng là hỏi CỘT
    "note": "note", "status": "status", "date": "date", "assignee": "assignee",
}


def header_terms(q):
    """Từ khoá tiếng Việt -> từ khoá NHÃN CỘT tương ứng."""
    qa = strip_accent(q)
    return {en for vi, en in HEADER_SYNONYM.items() if vi in qa}


# Điều kiện GIỚI HẠN PHẠM VI mà bậc 1 phải xử lý được, nếu không thì phải IM LẶNG.
# Trả lời số của cả 8 sprint cho câu hỏi về 1 sprint là SAI MÀ KHÔNG BÁO —
# loại lỗi tệ nhất của hệ thống này. Thà không trả lời.
QUALIFIER = [
    (r"sprint\s*(\d)", "sprint"),
    (r"th[aá]ng\s*(\d{1,2})", "tháng"),
    (r"(qu[yý]\s*[1-4])", "quý"),
    (r"(nam\s*20\d\d)", "năm"),
    (r"(tu[aà]n\s*\d+)", "tuần"),
]


SPRINT_RANGE = [
    r"sprint\s*(\d)\s*(?:[-–—]|den|toi|->)\s*(?:sprint\s*)?(\d)",  # "Sprint 0-7", "Sprint 0 đến Sprint 7"
]


# Bậc 1 chỉ trả lời được AI / CÁI GÌ / BAO NHIÊU — tra cứu trên hàng dữ liệu.
# VÌ SAO / NHƯ THẾ NÀO / ĐÁNH GIÁ là câu hỏi diễn giải, dữ liệu không chứa câu trả lời.
# Trả lời "Duy không có task ở Sprint 3" cho câu "vì sao Duy không còn task" là
# đúng sự thật nhưng LẠC CÂU HỎI. Bậc 1 phải nhường cho bậc 3.
INTERPRETIVE = r"vi sao|tai sao|ly do|nguyen nhan|nhu the nao|ra sao|danh gia|nhan xet|giai thich|co nen"


def qualifiers(qa):
    """-> (tập số sprint được nhắc, điều kiện KHÁC mà bậc 1 không xử lý được)

    Phải hiểu DẢI. "Sprint 0-7" mà đọc thành {0} thì câu hỏi cả kỳ bị trả lời
    bằng số của riêng sprint 0 — sai mà không báo. Đã dính đúng lỗi này một lần."""
    sprints, rest = set(), qa
    for pat in SPRINT_RANGE:
        for a, b in re.findall(pat, qa):
            sprints |= set(range(min(int(a), int(b)), max(int(a), int(b)) + 1))
        rest = re.sub(pat, " ", rest)
    sprints |= {int(n) for n in re.findall(r"sprint\s*(\d)", rest)}
    others = [name for pat, name in QUALIFIER[1:] if re.search(pat, qa)]
    return sprints, others


def strip_accent(s):
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normalize_query(q):
    """Add only deterministic scope aliases; never invent a project fact."""
    first_sprint = re.search(r"sprint\s+đầu\s+tiên|sprint\s+đầu\b", q, re.I)
    if first_sprint:
        q = re.sub(r"sprint\s+đầu\s+tiên|sprint\s+đầu\b", "Sprint 1", q, flags=re.I)
    qa = strip_accent(q)
    extra = []
    if first_sprint:
        if re.search(r"bat dau|khoi dong|ngay nao|khi nao", qa):
            extra.append("Master schedule")
    if re.search(r"authentication\s+bat dau|authentication.*\b(start|begin)", qa):
        extra.append("Master schedule")
    if not extra:
        return q
    punctuation = ""
    match = re.search(r"([?.!]+)\s*$", q)
    if match:
        punctuation = match.group(1)
        q = q[:match.start()].rstrip()
    return q + " " + " ".join(extra) + punctuation


def sig(s):
    """Chữ ký: bỏ dấu + bỏ mọi ký tự không phải chữ/số. `[BE] Du`, `[BE]Du`,
    `be-du` đều -> 'bedu'. Nhãn PIC trong file viết dấu cách không nhất quán
    (`[BE] Du` vs `[FE]H.Anh`), nên khớp theo dấu cách là khớp theo lỗi đánh máy."""
    return re.sub(r"[^a-z0-9]", "", strip_accent(s))


class Result:
    def __init__(self, tier, outcome, answer, cites=None, reason="", sql=""):
        self.tier, self.outcome, self.answer = tier, outcome, answer
        self.cites, self.reason, self.sql = cites or [], reason, sql

    def show(self):
        col = {CO: G, NO: R, NF: Y}[self.outcome]
        print(f"{col}【{self.outcome}】{OFF} {D}bậc {self.tier}{OFF}\n")
        print(self.answer)
        if self.reason:
            print(f"\n{D}vì:{OFF} {self.reason}")
        if self.cites:
            print(f"\n{D}nguồn:{OFF}")
            for c in self.cites:
                print(f"  {D}·{OFF} {c}")


class KB:
    def __init__(self):
        if not DB.exists():
            sys.exit("chưa có derived/facts.duckdb — chạy: python3 scripts/build_db.py")
        self.con = duckdb.connect(str(DB), read_only=True)
        self.people = self.con.execute(
            "SELECT assignee,name,role,task_count,estimate_h,actual_h,page,src_task,src_actual "
            "FROM person").fetchall()
        self.roles = [r[0] for r in self.con.execute(
            "SELECT value FROM dim_value WHERE dimension='role'").fetchall()]
        self.vocab = {}
        for dim, value in self.con.execute(
                "SELECT dimension,value FROM dim_value ORDER BY dimension,value").fetchall():
            self.vocab.setdefault(dim, []).append(value)
        self.psprint = {(r[0], r[1]): r for r in self.con.execute(
            "SELECT assignee,sprint,task_count,estimate_h,actual_h,src FROM person_sprint"
        ).fetchall()}
        self.sprint_metrics = {}
        metrics_file = RAW / "nexus-sprint1.facts.json"
        if metrics_file.exists():
            data = json.loads(metrics_file.read_text(encoding="utf-8"))
            self.sprint_metrics = data.get("summary_facts", {})
        self.cov = {r[0]: r for r in self.con.execute(
            "SELECT relation,signed,complete_as_of,source,asserted_by FROM coverage").fetchall()}

        # bảng bán cấu trúc (6 sheet realign A): (doc,row) -> {sheet, cells:[(col,header,value,src)]}
        self.doc_rows = {}
        for doc, sheet, rn, col, hdr, val, src in self.con.execute(
            "SELECT doc,sheet,row_no,col,header,value,src FROM doc_cell "
            "ORDER BY doc,row_no,col").fetchall():
            d = self.doc_rows.setdefault(
                (doc, rn), {"doc": doc, "sheet": sheet, "row": rn, "cells": []})
            d["cells"].append((col, hdr, val, src))

        # blob tra cứu + bộ đếm độ hiếm (IDF), dựng một lần
        self._blob_of = {k: strip_accent(" ".join(v for _, _, v, _ in r["cells"]).lower())
                         for k, r in self.doc_rows.items()}
        self._blobs = list(self._blob_of.values())
        self._df = {}

        # (chữ_ký_đầy_đủ, slug). Chữ ký gồm cả tiền tố vai trò nên đủ phân biệt,
        # và bỏ qua khác biệt ngoặc/dấu cách giữa `[BE] Du` và `[BE]Du`.
        self.sigs = []
        for a, name, *_ in self.people:
            self.sigs.append((sig(name), a))   # "[BE] Du" -> "bedu"
            self.sigs.append((sig(a), a))      # "be-du"   -> "bedu"

    def signed(self, relation):
        c = self.cov.get(relation)
        return bool(c and c[1])

    def cov_note(self, relation):
        c = self.cov[relation]
        return f"coverage `{relation}` do {c[4]} ký, đầy đủ tính đến {c[2]} ({c[3]})"

    def unsigned_downgrade(self, relation, what):
        c = self.cov.get(relation)
        who = c[4] if c else "(không có bản ghi)"
        return Result(1, NF, f"Kho không dám khẳng định: {what}",
                      reason=f"điều kiện ③ PHẠM VI chưa thoả — `coverage.yml` quan hệ "
                             f"`{relation}` chưa có người ký (asserted_by = {who!r}). "
                             f"Chưa ký thì chỉ được nói 'không tìm thấy', không được nói "
                             f"'chắc chắn không'.")

    def idf(self, term):
        """Độ hiếm của một từ trong kho. Đếm từ ĐƠN GIẢN (số dòng có chứa) — đây là
        thứ phân biệt 'Hùng Vương' (1 dòng) với 'tài liệu' (hàng trăm dòng).

        Không có nó thì mọi từ nặng như nhau, và câu hỏi khớp 5 chữ chung trông
        'chắc' hơn câu khớp 2 chữ hiếm — sai hẳn."""
        import math
        if term not in self._df:
            self._df[term] = sum(1 for b in self._blobs if term in b) or 0
        return math.log((1 + len(self._blobs)) / (1 + self._df[term]))

    def doc_row_search(self, q, docs=None, limit=6, terms=None):
        """Tìm DÒNG trong `doc_cell` khớp từ khoá. Tất định, không LLM.
        -> [(tỉ_lệ_khớp_theo_IDF, row)] giảm dần. `docs` giới hạn trong tập doc_id.
        `terms` cho phép người gọi bỏ trước các từ chỉ CỘT (chúng không bao giờ nằm
        trong giá trị ô, để lại chỉ làm loãng mẫu số)."""
        terms = terms if terms is not None else qterms(q)
        if not terms:
            return []
        total = sum(self.idf(t) for t in terms) or 1.0
        scored = []
        for (doc, rn), row in self.doc_rows.items():
            if docs and doc not in docs:
                continue
            blob = self._blob_of[(doc, rn)]
            hit = [t for t in terms if t in blob]
            if hit:
                scored.append((sum(self.idf(t) for t in hit) / total, row))
        scored.sort(key=lambda x: (-x[0], x[1]["doc"], x[1]["row"]))
        return scored[:limit]

    def find_people(self, q):
        """Khớp theo CHỮ KÝ ĐẦY ĐỦ (có tiền tố vai trò), bỏ qua ngoặc/dấu cách.

        Cố ý KHÔNG khớp tên trần ('lan', 'du', 'duy', 'minh'): trong tiếng Việt
        chúng đụng từ thường — 'bao nhiêu lần'->lan, 'duy nhất'->duy, 'chứng minh'
        ->minh — gây khớp nhầm IM LẶNG. Chỉ khớp trên định danh đóng, không khớp
        trên mảnh tên mờ. Hệ quả: gõ trống 'Lan' sẽ không bắt; phải '[QC] LAN'
        hoặc 'QC LAN'. Nhập nhằng thì thà không bắt còn hơn bắt nhầm."""
        qsig = sig(q)
        hits = []
        for s, slug in self.sigs:
            if len(s) >= 4 and s in qsig and slug not in hits:
                hits.append(slug)
        return hits

    def person(self, slug):
        return next(p for p in self.people if p[0] == slug)


def col_direction(qa):
    """Câu hỏi có hỏi ĐÍCH DANH một CỘT theo vai trò không, kiểu "X follow ai" /
    "ai follow X"? -> (cột_lọc_chủ_ngữ, cột_đọc_đáp_án). Không có thì trả None —
    khi đó rơi về tra cứu chung (khớp bất kỳ cột nào, có thể lẫn chiều)."""
    if re.search(r"\bai\b.{0,30}\b(follow|theo\s*doi)\b", qa):
        return ("following", "assignee")   # "ai follow X" -> X nằm ở cột Following, đáp án ở Assignee
    if re.search(r"\b(follow|theo\s*doi)\b.{0,30}\bai\b", qa):
        return ("assignee", "following")   # "X follow ai" -> X nằm ở cột Assignee, đáp án ở Following
    return None


def doc_answer(kb, q, docs):
    """Trả lời từ bảng bán cấu trúc (BẬC 1, tất định). CÓ + ô nguồn nếu tìm được dòng;
    KHÔNG TÌM THẤY nếu không. TUYỆT ĐỐI không "chắc chắn không" — các sheet này đã NẠP
    nhưng CHƯA KÝ coverage."""
    people = kb.find_people(q)
    direction = col_direction(strip_accent(q)) if len(people) == 1 else None
    if direction:
        # Câu hỏi biết CỘT nào là chủ ngữ, CỘT nào là đáp án — không được trộn hai
        # chiều (ai follow X mà cứ liệt kê cả dòng X follow ai). Lọc đúng cột.
        subj_kw, ans_kw = direction
        subj_label = kb.person(people[0])[1]
        subj_sig = sig(subj_label)
        matched = []
        for (doc, rn), row in kb.doc_rows.items():
            if doc not in docs:
                continue
            headers = [h for _, h, _, _ in row["cells"]]
            if not (any(subj_kw in strip_accent(h).lower() for h in headers)
                    and any(ans_kw in strip_accent(h).lower() for h in headers)):
                continue
            subj_val = next((v for _, h, v, _ in row["cells"]
                              if subj_kw in strip_accent(h).lower()), None)
            if subj_val and sig(subj_val) == subj_sig:
                ans = next(((h, v, s) for _, h, v, s in row["cells"]
                            if ans_kw in strip_accent(h).lower()), None)
                matched.append((row, ans))
        if not matched:
            return Result(1, NF,
                f"Không có dòng nào trong {', '.join(docs)} có cột `{subj_kw}` = "
                f"'{subj_label}'.",
                reason="lọc theo CỘT (không phải khớp bất kỳ đâu trong dòng) — "
                       "tất định trên bảng `doc_cell`, CHƯA KÝ coverage.")
        lines, cites = [], []
        for row, ans in matched:
            val = ans[1] if ans and ans[1] else "(trống)"
            lines.append(f"- `{row['sheet']}` — **{subj_label}** "
                         f"({subj_kw}) → **{ans[0] if ans else ans_kw}**: {val}")
            if ans:
                cites.append(ans[2])
        return Result(1, CO, "\n".join(lines), cites=cites,
            reason=f"lọc cột `{subj_kw}` = '{subj_label}', đọc riêng cột `{ans_kw}` — "
                   "tất định, không trộn hai chiều của quan hệ. Sheet ĐÃ NẠP nhưng "
                   "CHƯA KÝ coverage.")

    field_keys = requested_field_keys(q)
    if docs and field_keys and (docs == ["nexus-summary"] or
                                (wants_list(q) and not has_specific_value(q))):
        # Câu liệt kê theo một cột (scope, nhân sự...) không cần từ khoá giá trị
        # cụ thể; quét đúng sheet rồi chỉ xuất cột được hỏi.
        hits = [(1.0, row) for (doc, _), row in kb.doc_rows.items()
                if doc in docs and select_row_cells(row, q)]
    else:
        hits = kb.doc_row_search(q, docs=docs, limit=60)
    hits = filter_structured_hits(kb, q, hits)
    # Câu nhắc NGƯỜI (định danh đóng) nhưng KHÔNG hỏi cột cụ thể (direction=None ở
    # trên) -> lọc còn dòng có chữ ký người đó ở BẤT KỲ cột nào, gạt nhiễu chữ chung.
    if people and hits:
        # câu nhắc NGƯỜI -> giữ MỌI dòng của người đó (vd "LAN có task nào không").
        labels = [sig(kb.person(s)[1]) for s in people]
        filt = [(sc, row) for sc, row in hits
                if any(lab in sig(" ".join(v for _, _, v, _ in row["cells"])) for lab in labels)]
        if filt:
            hits = filt
    elif hits and not wants_list(q):
        # câu tra cứu ĐÍCH DANH (không nhắc người) -> chỉ giữ dòng khớp NHIỀU từ khoá
        # nhất, gạt dòng chỉ dính một chữ chung ("Document"/"date"). Một câu hỏi cụ thể
        # nên ra một đáp án cụ thể, không phải bảng liệt kê.
        top = hits[0][0]
        hits = [(sc, row) for sc, row in hits if sc == top]
    if (re.search(r"bao nhieu|may|so\s+", strip_accent(q))
            and "scope" in requested_field_keys(q)):
        scope_rows = [row for (doc, _), row in kb.doc_rows.items()
                      if doc in docs and any(
                          h.strip().lower() == "scope" and v for _, h, v, _ in row["cells"])]
        if scope_rows:
            cites = [next(s for _, h, v, s in row["cells"] if h.strip().lower() == "scope" and v)
                     for row in scope_rows]
            return Result(1, CO,
                          f"**{len(scope_rows)} scope** trong {', '.join(docs)}.",
                          cites=cites,
                          reason="đếm các dòng Scope đã nạp trong bảng `doc_cell`; không tự suy diễn ngoài sheet.")
    if not hits:
        return Result(1, NF,
            f"Không thấy dòng nào khớp trong bảng đã nạp ({', '.join(docs)}).",
            reason="các sheet này ĐÃ NẠP vào bậc 1 (bảng `doc_cell`) nhưng CHƯA KÝ "
                   "coverage → chỉ nói 'không tìm thấy', không nói 'chắc chắn không'.")
    who = ", ".join(kb.person(s)[1] for s in people) if people else ""
    head = (f"Các dòng của **{who}** trong bảng đã nạp "
            f"(phần đã nạp, CHƯA KÝ coverage nên không đảm bảo ĐỦ):\n") if who else ""
    lines, cites = [], []
    for _, row in hits[:5]:
        selected = select_row_cells(row, q)
        cells = " · ".join(f"**{h}**: {v}" for h, v, _ in selected)
        lines.append(f"- `{row['sheet']}` — {cells}")
        if selected:
            cites.append(selected[0][2])
    more = f"\n_… và các dòng khác (xem `doc_cell`)._" if len(hits) > 5 else ""
    return Result(1, CO, head + "\n".join(lines) + more, cites=cites,
        reason="tra thẳng bảng `doc_cell` (bậc 1, SQL/tất định), mỗi ô truy được về "
               "nguồn. Các sheet này ĐÃ NẠP nhưng CHƯA KÝ coverage — nên là 'CÓ, tra "
               "được', KHÔNG phải khẳng định đầy đủ hay phủ định.")


def doc_fallback(kb, q):
    """Lưới cuối của BẬC 1: quét MỌI dòng đã nạp trong `doc_cell` (cả 8 sheet sprint,
    cả cột không khai MEASURE như `Note`). Chỉ chạy khi các bậc khác đã bó tay.

    Đã nạp thì phải tra được — không được để dữ liệu nằm trong kho mà hỏi ra "không
    tìm thấy". Nhưng ngưỡng phải CHẶT: khớp lỏng sẽ biến 'kho không biết' thành một
    dòng bất kỳ có chung một chữ, tức là nói bừa. Đòi ≥2 từ khoá và ≥60% số từ."""
    # Tách câu hỏi làm hai phần: từ chỉ DÒNG (khớp vào giá trị ô) và từ chỉ CỘT
    # ("ngày nào", "trạng thái" — khớp vào nhãn cột). Gộp chung hai loại vào một phép
    # chấm điểm là sai: từ chỉ cột không bao giờ xuất hiện trong giá trị, nên nó chỉ
    # kéo tỉ lệ khớp xuống và giết câu hỏi hợp lệ.
    want = header_terms(q)
    col_words = {t for vi in HEADER_SYNONYM if vi in strip_accent(q) for t in vi.split()}
    terms = [t for t in qterms(q) if t not in col_words]
    if len(terms) < 2:
        return None
    hits = [(sc, row) for sc, row in kb.doc_row_search(q, limit=400, terms=terms)
            if not want or any(w in strip_accent(h).lower()
                               for _, h, _, _ in row["cells"] for w in want)]
    if not hits:
        return None
    # Ngưỡng theo KHỐI LƯỢNG NGHĨA đã khớp (IDF), không theo số từ. Đã thử đếm từ
    # phẳng ở 60%: câu "ai viết tài liệu thiết kế màn hình đăng nhập" khớp 5/8 chữ
    # chung vào dòng "tìm hiểu tài liệu màn hình đăng KÝ" — đúng chữ, sai hẳn nghĩa,
    # lại kèm nguồn trông rất thuyết phục. Đó đúng là loại nói sai hệ này sinh ra để
    # chặn. Tính theo IDF thì 5 chữ chung đó nhẹ, không qua nổi cổng.
    # 0.6 nằm giữa hai nhóm đã đo: câu khớp thật 0.73–1.00, câu khớp nhầm 0.30–0.37.
    top = hits[0][0]
    if top < 0.6:
        return None
    hits = [(sc, row) for sc, row in hits if sc == top]
    lines, cites = [], []
    for _, row in hits[:8]:
        picked = [(h, v, s) for _, h, v, s in row["cells"]
                  if v and any(w in strip_accent(h).lower() for w in want)] if want else []
        if picked:
            key = next((v for _, h, v, _ in row["cells"] if v), "")
            lines.append(f"- `{row['sheet']}` **{key}** — "
                         + " · ".join(f"**{h}**: {v}" for h, v, _ in picked))
            cites.append(picked[0][2])
            continue
        cells = " · ".join(f"**{h}**: {v}" for h, v, _ in select_row_cells(row, q))
        lines.append(f"- `{row['sheet']}` — {cells}")
        selected = select_row_cells(row, q)
        if selected:
            cites.append(selected[0][2])
    more = f"\n_… và {len(hits) - 8} dòng nữa (xem `doc_cell`)._" if len(hits) > 8 else ""
    return Result(1, CO, "\n".join(lines) + more, cites=cites,
        reason=f"không bậc nào khác trả lời được, nhưng {len(hits)} dòng trong bảng "
               f"`doc_cell` khớp {top:.0%} khối lượng nghĩa của câu hỏi (chấm theo độ "
               f"hiếm của từ) — tra thẳng SQL, mỗi ô truy được về ô Excel gốc. Đây là 'tra được các dòng này', KHÔNG phải khẳng "
               "định ĐỦ: các sheet này CHƯA KÝ coverage.")


# ------------------------------------------------------- BẬC 1 · có cấu trúc
def tier1(kb, q):
    q = normalize_query(q)
    qa = strip_accent(q)
    who = kb.find_people(q)
    if re.search(INTERPRETIVE, qa):
        return None          # nhường bậc 3

    sprints, others = qualifiers(qa)
    full_range = sprints == {1}                # Nexus hiện có một Sprint 1
    one_sprint = next(iter(sprints)) if len(sprints) == 1 else None

    if len(sprints) > 1 and not full_range:
        return Result(1, NF,
            f"Bậc 1 KHÔNG trả lời câu này — nó hỏi một tập sprint rời rạc "
            f"({sorted(sprints)}), mà kho chỉ có số theo TỪNG sprint và số của CẢ KỲ.",
            reason="cộng một tập con tuỳ ý là TÍNH TOÁN, không phải tra cứu. Muốn có "
                   "con số đó thì phải thêm một phép tổng hợp ở Stage 2 rồi mới trả lời — "
                   "không được cộng ngay lúc trả lời.")

    if others:
        return Result(1, NF,
            f"Bậc 1 KHÔNG trả lời câu này — có điều kiện phạm vi nó không xử lý được: "
            f"{', '.join(others)}.",
            reason="dữ liệu chỉ được tổng hợp theo NGƯỜI và theo SPRINT. Không có trục "
                   "thời gian theo tháng/quý/tuần. Trả lời bằng số của cả kỳ sẽ là SAI "
                   "MÀ KHÔNG BÁO — nên bậc 1 chọn im lặng.")

    # --- 0. câu nhắc ĐÍCH DANH một sheet bảng (Backlog/CR/Master schedule/…) -> tra
    # thẳng bảng doc_cell ở BẬC 1 (SQL, tất định, số truy về ô). KHÔNG đọc raw.
    docs = docs_mentioned(q) or inferred_docs(q)

    # Config chỉ có danh mục tech_stack, chưa có quan hệ người–tech_stack.  Trả
    # đúng phần kho biết và nói rõ phần thiếu, không suy ra ai dùng công nghệ nào.
    tech_value_mentioned = any(strip_accent(v) in qa for v in kb.vocab.get("tech_stack", []))
    ambiguous_devops_role = "devops" in qa and re.search(r"co ai (?:lam|la|phu trach)", qa)
    if (tech_value_mentioned and not ambiguous_devops_role) or re.search(
            r"tech\s*[-_ ]?stack|cong nghe|cong cu", qa):
        configured = kb.vocab.get("tech_stack", [])
        if re.search(r"ai |nguoi|phu trach|lam javascript|lam java", qa):
            return Result(1, NF,
                "Kho có danh mục tech-stack chuẩn nhưng chưa có mapping người–tech-stack; "
                "không thể xác định ai làm công nghệ này.",
                cites=["raw/nexus-config.md (Config!G2:G15)",
                       "raw/nexus-config.facts.json :: vocabulary.tech_stack"],
                reason="workbook chỉ khai báo vocabulary `tech_stack`, không có cột liên kết với assignee.")
        if "config" in qa or "khai bao" in qa or "danh muc" in qa:
            return Result(1, CO,
                "Các tech-stack được khai báo trong Config: "
                + ", ".join(f"**{v}**" for v in configured),
                cites=["raw/nexus-config.md (Config!G2:G15)",
                       "raw/nexus-config.facts.json :: vocabulary.tech_stack"],
                reason="đây là danh mục chuẩn của workbook, không phải mapping người–tech-stack.")
        return Result(1, NF,
            "Kho chưa có mapping tech-stack đang được dùng trong dự án.",
            cites=["raw/nexus-config.md (Config!G2:G15)"],
            reason="Config chỉ có danh mục tech-stack; dữ liệu nguồn chưa liên kết công nghệ với người hoặc task.")

    # --- 0a. ngày bắt đầu của sprint là trường Summary project, không phải ngày
    # của từng task trong Sprint 1.
    if sprints == {1} and re.search(r"bat dau|khoi dong|start date", qa):
        for (doc, _), row in kb.doc_rows.items():
            if doc != "nexus-summary":
                continue
            sprint_cell = next((c for c in row["cells"] if c[1] == "Sprint"), None)
            start_cell = next((c for c in row["cells"] if c[1] == "Start date"), None)
            if sprint_cell and strip_accent(sprint_cell[2]) == "sprint 1" and start_cell:
                return Result(1, CO, f"Sprint 1 bắt đầu ngày **{start_cell[2]}**.",
                              cites=[start_cell[3], "raw/nexus-summary.facts.json"],
                              reason="tra trực tiếp Summary project, cột `Start date`, dòng Sprint 1.")

    if sprints == {1} and re.search(r"ket thuc|end date|deadline", qa):
        for (doc, _), row in kb.doc_rows.items():
            if doc != "nexus-summary":
                continue
            sprint_cell = next((c for c in row["cells"] if c[1] == "Sprint"), None)
            end_cell = next((c for c in row["cells"] if c[1] == "End date"), None)
            if sprint_cell and strip_accent(sprint_cell[2]) == "sprint 1" and end_cell:
                return Result(1, CO, f"Sprint 1 kết thúc ngày **{end_cell[2]}**.",
                              cites=[end_cell[3], "raw/nexus-summary.facts.json"],
                              reason="tra trực tiếp Summary project, cột `End date`, dòng Sprint 1.")

    if sprints == {1} and re.search(r"tien do|progress", qa):
        for (doc, _), row in kb.doc_rows.items():
            if doc != "nexus-summary":
                continue
            sprint_cell = next((c for c in row["cells"] if c[1] == "Sprint"), None)
            progress_cell = next((c for c in row["cells"] if c[1] == "Progress"), None)
            if sprint_cell and strip_accent(sprint_cell[2]) == "sprint 1" and progress_cell:
                return Result(1, CO, f"Tiến độ Sprint 1 là **{progress_cell[2]}**.",
                              cites=[progress_cell[3], "raw/nexus-summary.facts.json"],
                              reason="tra trực tiếp Summary project, cột `Progress`, dòng Sprint 1.")

    if "summary project" in qa and re.search(r"status|trang thai|tinh trang", qa):
        for (doc, _), row in kb.doc_rows.items():
            if doc != "nexus-summary":
                continue
            status_cell = next((c for c in row["cells"] if c[1] == "Status"), None)
            if status_cell:
                return Result(1, CO, f"Summary project đang ở trạng thái **{status_cell[2]}**.",
                              cites=[status_cell[3], "raw/nexus-summary.facts.json"],
                              reason="tra trực tiếp Summary project, cột `Status`.")

    # --- 0b. aggregate đã khai báo nguồn, không tự cộng tại thời điểm trả lời
    count_question = bool(re.search(r"bao nhieu|may|so\s+", qa))
    status_match = next((v for v in kb.sprint_metrics.get("status_counts", {})
                         if strip_accent(v) in qa), None)
    priority_match = next((v for v in kb.sprint_metrics.get("priority_counts", {})
                           if strip_accent(v) in qa), None)
    if sprints in ({1}, set()) and count_question and status_match:
        metric = kb.sprint_metrics["status_counts"][status_match]
        return Result(1, CO, f"**{metric['value']} task** có trạng thái **{status_match}** trong Sprint 1.",
                      cites=["raw/nexus-sprint1.facts.json", metric["src"]],
                      reason="đếm trạng thái được khai báo tại Stage 2 từ toàn bộ dòng Sprint 1.")
    if sprints in ({1}, set()) and count_question and priority_match:
        metric = kb.sprint_metrics["priority_counts"][priority_match]
        return Result(1, CO, f"**{metric['value']} task** có mức ưu tiên **{priority_match}** trong Sprint 1.",
                      cites=["raw/nexus-sprint1.facts.json", metric["src"]],
                      reason="đếm mức ưu tiên được khai báo tại Stage 2 từ toàn bộ dòng Sprint 1.")
    if (not docs or docs == ["nexus-sprint1"]) and not who and sprints in ({1}, set()) and re.search(r"(tong|bao nhieu|so)\s+.*task|task.*(tong|tat ca)", qa):
        metric = kb.sprint_metrics.get("task_count")
        if metric:
            scope = "Sprint 1" if sprints else "corpus hiện nạp (Sprint 1)"
            return Result(1, CO, f"**{metric['value']} task** trong {scope}.",
                          cites=["raw/nexus-sprint1.facts.json", metric["src"]],
                          reason="aggregate được khai báo tại Stage 2 từ toàn bộ dòng task; không cộng ngẫu nhiên lúc trả lời.")
    if re.search(r"re[- ]?est|re estimated", qa) and "sprint 1" in qa:
        for (doc, _), row in kb.doc_rows.items():
            if doc != "nexus-summary":
                continue
            sprint_cell = next((c for c in row["cells"] if c[1] == "Sprint"), None)
            reest_cell = next((c for c in row["cells"] if c[1] == "Re-est (h)"), None)
            if sprint_cell and strip_accent(sprint_cell[2]) == "sprint 1" and reest_cell:
                return Result(1, CO, f"**{reest_cell[2]} giờ** Re-est của Sprint 1.",
                              cites=[reest_cell[3], "raw/nexus-summary.facts.json"],
                              reason="tra trực tiếp Summary project, cột `Re-est (h)`, dòng Sprint 1.")

    if re.search(r"\b(cap nhat|sua|ghi|log|tao|doi|update|create)\b", qa, re.I):
        return Result(1, NF,
                      "Đây là yêu cầu ghi/cập nhật dữ liệu, không phải câu hỏi tra cứu.",
                      reason="Project Knowledge chỉ tạo action proposal; action skill riêng phải kiểm tra quyền và xin approval trước khi ghi.")
    if not who and sprints == {1} and re.search(r"(tong|bao nhieu|so)\s+.*(effort|gio|thoi gian)|effort.*(tong|thuc te)", qa):
        metric = kb.sprint_metrics.get("actual_h")
        if metric:
            return Result(1, CO, f"**{metric['value']} giờ** actual effort của Sprint 1.",
                          cites=["raw/nexus-sprint1.facts.json", metric["src"]],
                          reason="aggregate actual effort được khai báo tại Stage 2 từ các task Sprint 1.")
    if docs and not who and not (
            docs == ["nexus-sprint1"] and re.search(r"nhung nguoi|nguoi co task|ai tham gia", qa)):
        return doc_answer(kb, q, docs)

    # --- 1. phạm vi kín: có ai làm task mà không khai trong Config không
    if "config" in qa and ("khai" in qa or "khong duoc khai" in qa):
        if not kb.signed("person_task"):
            return kb.unsigned_downgrade("person_task", "danh sách người làm task là đầy đủ")
        return Result(1, NO,
            "Không có. Mọi `assignee` xuất hiện trong Sprint 1 đều nằm trong `Config!H2:H15`.",
            cites=["raw/nexus-people.md", "scripts/extract_nexus.py :: assignee mapping"],
            reason="Stage 2 kiểm tra điều này ở mức máy: rollup HALT nếu gặp assignee "
                   "ngoài Config. Pipeline chạy xanh ⇒ phạm vi kín. " + kb.cov_note("person_task"))

    # --- 2. có ai làm <X> không   (X là giá trị của DIMENSION role)
    m = re.search(r"co ai (?:lam|la|phu trach) (.+?)\s*(?:khong|ko)\s*\??\s*$", qa)
    if m:
        term = m.group(1).strip()
        match = [r for r in kb.roles if strip_accent(r) == term]
        if not kb.signed("person_role"):
            return kb.unsigned_downgrade("person_role", f"không ai làm '{term}'")
        if not match:
            return Result(1, NO, f"Không. Dự án **nexus** không có vai trò `{m.group(1)}`.",
                cites=["schema.yml :: dimensions.role", "raw/nexus-config.md (Config!K2:K15)"],
                reason="① `role` được lưu thành hàng dữ liệu · ② `role` là DIMENSION **đóng**, "
                       f"enum đầy đủ là {' · '.join(kb.roles)} — `{m.group(1)}` không nằm trong đó · "
                       "③ " + kb.cov_note("person_role") + ". Ba điều kiện đủ ⇒ được nói chắc chắn không.")
        role = match[0]
        got = [p for p in kb.people if p[2] == role]
        if got:
            return Result(1, CO, f"Có: " + ", ".join(f"**{p[1]}**" for p in got),
                          cites=[p[6] for p in got])
        return Result(1, NO, f"Không ai được khai vai trò `{role}` trong dự án.",
                      reason=kb.cov_note("person_role"))

    # --- 2b. ai phụ trách <role>   (chỉ nhận khi <role> nằm trong enum)
    m = re.search(r"^ai (?:dang )?(?:phu trach|lam) (?:phan )?(.+?)\s*(?:cua .*)?\??$", qa)
    if m and not who:
        term = m.group(1).strip()
        match = [r for r in kb.roles if strip_accent(r) == term]
        if match:
            got = [p for p in kb.people if p[2] == match[0]]
            if got:
                return Result(1, CO, ", ".join(f"**{p[1]}**" for p in got),
                    cites=[p[6] for p in got],
                    reason=f"lọc trên DIMENSION `role` = `{match[0]}`.")
            if kb.signed("person_role"):
                return Result(1, NO, f"Không ai được khai vai trò `{match[0]}`.",
                              reason=kb.cov_note("person_role"))
        # term không nằm trong enum role -> KHÔNG phải câu hỏi bậc 1 trả được

    # --- 3. <người> có task / tham gia sprint nào không
    if who and re.search(r"(khong|ko)\s*\??\s*$", qa) and re.search(r"task|cong viec|tham gia|sprint", qa):
        if not kb.signed("person_task"):
            return kb.unsigned_downgrade("person_task", "những người này không có task nào")
        # PHẢI tôn trọng điều kiện sprint. Đếm từ bảng tổng hợp cho câu hỏi về
        # một sprint cụ thể là lặp lại đúng bug đã sửa ở nhánh hỏi số.
        scoped = one_sprint is not None and not full_range
        where = f"Sprint {one_sprint}" if scoped else "Sprint 1"

        def n_task(slug):
            if scoped:
                row = kb.psprint.get((slug, one_sprint))
                return row[2] if row else 0
            return kb.person(slug)[3]

        zero = [kb.person(s) for s in who if n_task(s) == 0]
        nonzero = [kb.person(s) for s in who if n_task(s) > 0]
        src = ([f"raw/nexus-sprint{one_sprint}.md"] if scoped else ["raw/nexus-people.md"])
        if zero and not nonzero:
            names = ", ".join(f"**{p[1]}**" for p in zero)
            return Result(1, NO,
                f"Không. {names} được khai trong `Config!H2:H15` nhưng **0 task** trong {where}.",
                cites=[p[6] for p in zero] + src,
                reason="① task lưu thành hàng dữ liệu · ② `assignee` là DIMENSION đóng, "
                       "những người này CÓ trong enum nên câu hỏi hợp lệ · ③ "
                       + kb.cov_note("person_task")
                       + (f". Đếm trên `person_sprint` WHERE sprint={one_sprint}." if scoped else ""))
        parts = [f"**{p[1]}**: {n_task(p[0])} task trong {where}" for p in nonzero]
        parts += [f"**{p[1]}**: 0 task trong {where}" for p in zero]
        return Result(1, CO, "; ".join(parts), cites=[p[6] for p in nonzero + zero] + src)

    # --- 4. so sánh
    if "so sanh" in qa and len(who) >= 2:
        ps = [kb.person(s) for s in who]
        lines = [f"- **{p[1]}** — {p[5]} h thực tế / {p[4]} h ước lượng, {p[3]} task" for p in ps]
        return Result(1, CO, "\n".join(lines),
            cites=[f"{p[6]} → {p[8]}" for p in ps],
            reason="hai con số lấy từ hai `facts_ref` riêng; kho KHÔNG tự cộng trừ rồi "
                   "ghi kết quả vào wiki.")

    # --- 5. hỏi về một người cụ thể
    if who:
        p = kb.person(who[0])
        if re.search(r"vai tro|role|lam gi", qa):
            if p[2]:
                return Result(1, CO, f"**{p[1]}** — vai trò `{p[2]}`.", cites=[p[6]],
                              reason="`role` là DIMENSION, giá trị nằm trong enum Config!K2:K15.")
            return Result(1, NF, f"Kho không biết vai trò của **{p[1]}**.",
                cites=[p[6]],
                reason="nhãn PIC không có tiền tố vai trò nên `role` bị bỏ trống. Đây là "
                       "THIẾU DỮ LIỆU — không được suy ra là người này không có vai trò.")
        # có nhắc ĐÚNG MỘT sprint -> phải lọc theo sprint đó, không được dùng tổng hợp
        if one_sprint is not None and not full_range:
            row = kb.psprint.get((p[0], one_sprint))
            if row is None:
                if not kb.signed("person_task"):
                    return kb.unsigned_downgrade(
                        "person_task", f"{p[1]} không có task nào ở Sprint {one_sprint}")
                return Result(1, NO,
                    f"Không. **{p[1]}** không có đầu việc nào trong **Sprint {one_sprint}**.",
                    cites=[p[6], f"raw/nexus-sprint{one_sprint}.md"],
                    reason=f"Sprint {one_sprint} nằm trong phạm vi đã ký, và bảng "
                           f"`person_sprint` không có dòng nào cho người này. "
                           + kb.cov_note("person_task"))
            return Result(1, CO,
                f"**{p[1]}** · **Sprint {one_sprint}** — **{row[4]} giờ** thực tế "
                f"(ước lượng {row[3]} h), {row[2]} task.",
                cites=[f"{p[6]} → {row[5]}"],
                reason=f"lọc `person_sprint` WHERE assignee={p[0]!r} AND sprint={one_sprint}. "
                       f"KHÔNG dùng bảng tổng hợp 8 sprint.")

        if re.search(r"bao nhieu task|may task|so task", qa):
            return Result(1, CO, f"**{p[1]}** — **{p[3]} task** trong Sprint 1.",
                          cites=[f"{p[6]} → {p[7]}"])
        if re.search(r"gio|effort|cong|thoi gian", qa):
            return Result(1, CO,
                f"**{p[1]}** — **{p[5]} giờ** thực tế (ước lượng {p[4]} h), {p[3]} task "
                f"— **tổng Sprint 1**.",
                cites=[f"{p[6]} → {p[8]}"])
        # CHỈ nhận câu hỏi nhận dạng. Trước đây đây là fallback ôm mọi câu có tên
        # người -> câu hỏi mở ("vì sao...", "đảm nhiệm gì...") bị bậc 1 trả lời
        # chung chung và không bao giờ xuống được bậc 3. Bậc 1 phải biết im lặng.
        if re.search(r"la ai|thong tin|gioi thieu|ho so", qa):
            return Result(1, CO,
                f"**{p[1]}** — vai trò `{p[2] or 'không xác định'}`, {p[3]} task, {p[5]} h thực tế.",
                cites=[p[6]])

    # --- 6. liệt kê vai trò
    if re.search(r"vai tro nao|nhung vai tro|co vai tro gi|role nao", qa):
        return Result(1, CO, "Các vai trò: " + " · ".join(f"`{r}`" for r in kb.roles),
            cites=["raw/nexus-config.md (Config!K2:K15)", "schema.yml :: dimensions.role"],
            reason="đây là enum ĐẦY ĐỦ, không phải danh sách tìm được — nên có thể "
                   "khẳng định không còn vai trò nào khác.")

    # --- 7. liệt kê người tham gia
    if re.search(r"liet ke|nhung ai|nhung nguoi|ai (da )?tham gia|danh sach", qa):
        got = sorted([p for p in kb.people if p[3] > 0], key=lambda p: -p[3])
        return Result(1, CO,
            "\n".join(f"- **{p[1]}** — {p[3]} task, {p[5]} h" for p in got),
            cites=["raw/nexus-people.md"],
            reason=f"{len(kb.people)} người khai trong Config, {len(got)} người thực sự có task. "
                   + kb.cov_note("person_task") if kb.signed("person_task") else "")

    # --- 8. chỉ số toàn dự án
    metrics = {"tong effort": "effort_sprint_0_7", "sprint 0": "effort_sprint_0_7",
               "tien do": "progress_overall", "toan bo he thong": "effort_all_system"}
    for kw, metric in metrics.items():
        if kw in qa:
            row = kb.con.execute(
                "SELECT value,unit,src FROM project_metric WHERE metric=?", [metric]).fetchone()
            if row:
                v = f"{row[0]:.4%}" if row[1] == "ratio" else f"{row[0]} {row[1]}"
                raw = f" (giá trị nguyên văn: `{row[0]}`)" if row[1] == "ratio" else ""
                return Result(1, CO, f"**{v}**{raw}", cites=[f"wiki/sources/… → {row[2]}"])

    return None


# ---------------------------------------------------------- BẬC 2 · từ khoá
STOP = set("la gi co khong ko cua va cho nao bao nhieu the nhung mot cac o trong "
           "du an hay duoc nay do ai lam".split())


def tier2(kb, q):
    # GIỮ NGUYÊN DẤU và khớp theo biên từ. Bỏ dấu ở đây làm "chỉ" == "chi",
    # "phí" == "phi" -> khớp giả, và câu "không tìm thấy" biến thành "có". Đã bị một lần.
    terms = [t for t in re.findall(r"\w+", q.lower(), re.UNICODE)
             if strip_accent(t) not in STOP and len(t) > 2]
    if not terms:
        return Result(2, NF, "Câu hỏi không có từ khoá nào để tìm.")
    pats = {t: re.compile(rf"(?<!\w){re.escape(t)}(?!\w)", re.UNICODE) for t in terms}
    best = []
    # wiki/ (tầng tuyển): khớp biên từ trên cả trang — xương sống eval phụ thuộc, giữ nguyên.
    for p in sorted((ROOT / "wiki").rglob("*.md")):
        if p.name == "log.md":
            continue
        body = p.read_text(encoding="utf-8").lower()
        hit = [t for t in terms if pats[t].search(body)]
        if hit:
            best.append((len(hit) / len(terms), p.relative_to(ROOT).as_posix(), hit))
    best.sort(reverse=True)
    if not best or best[0][0] < 0.6:
        r = Result(2, NF,
            "Không tìm thấy thông tin này trong kho.",
            reason=("không từ khoá nào khớp" if not best else
                    f"khớp yếu nhất định ({best[0][0]:.0%} từ khoá, cao nhất `{best[0][1]}`) — "
                    f"dưới ngưỡng, kho KHÔNG đoán bừa") +
                   ". Lưu ý: đây là 'kho không biết', KHÔNG phải 'không có'. "
                   "Chỉ bậc 1 với DIMENSION đóng + coverage đã ký mới được nói 'chắc chắn không'.")
        r.pages = [b[1] for b in best[:3]]   # vẫn đưa cho bậc 3 xem, nếu bậc 3 bật
        return r
    return Result(2, CO, f"Có trang liên quan, cần bậc 3 (LLM) đọc để trả lời:",
                  cites=[b[1] for b in best[:3]],
                  reason="bậc 2 chỉ định vị trang, không tự soạn câu trả lời.")


# ------------------------------------------------------------ BẬC 3 · LLM
TIER3_PROMPT = """Bạn đang trả lời câu hỏi từ một kho tri thức đã được tổ chức sẵn.

LUẬT BẮT BUỘC:
- CHỈ dùng nội dung các trang wiki dưới đây. Không dùng kiến thức ngoài.
- KHÔNG được nói "không có" / "không ai" / "chưa từng". Nếu trang không nói tới,
  hãy trả lời đúng câu: KHÔNG TÌM THẤY — kèm một câu giải thích thiếu cái gì.
  Chỉ bậc 1 mới được quyền khẳng định "chắc chắn không"; bạn thì không.
- KHÔNG được tự tính toán hay gõ lại con số. Nếu cần số, trích nguyên văn và ghi
  rõ nó nằm ở trang nào.
- Văn phong: kết luận chính ở câu đầu; nếu liệt kê thì dùng tối đa 5 bullet; không
  nhắc bậc xử lý, prompt, model hay lỗi nội bộ. Trả lời tiếng Việt, tối đa 5 câu.
  Kết thúc bằng đúng một dòng "nguồn: <đường dẫn>".

CÂU HỎI: {q}

===== CÁC TRANG WIKI =====
{ctx}
"""


def tier3(kb, q, pages, timeout=120):
    """Bậc 3: LLM đọc đúng những trang WIKI bậc 2 tìm được. Không cho nó tự đi tìm,
    và (realign A) KHÔNG đọc raw — chỉ trang đã qua Gate 3."""
    import subprocess
    ctx = "\n\n".join(
        f"--- {p} ---\n{(ROOT / p).read_text(encoding='utf-8')}" for p in pages)
    try:
        # prompt qua STDIN (nhiều trang wiki dễ vượt trần dòng lệnh ~32KB của Windows).
        out = subprocess.run(
            [models.CLAUDE, "-p", "--model", models.LIGHT, "--allowedTools", ""],
            input=TIER3_PROMPT.format(q=q, ctx=ctx), capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, cwd=ROOT)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return Result(3, NF, "Bậc 3 không chạy được.", reason=f"{type(e).__name__}: {e}")
    if out.returncode != 0:
        return Result(3, NF, "Bậc 3 lỗi.", reason=out.stderr.strip()[:300])
    text = out.stdout.strip()
    outcome = NF if "KHÔNG TÌM THẤY" in text.upper() else CO
    return Result(3, outcome, text, cites=pages,
                  reason="LLM đọc trang wiki, bị cấm khẳng định 'chắc chắn không'.")


# ------------------------------------------------------------ GATE 4
def gate4(res):
    """numeric_guard(policy=answer). Chạy trên MỌI bậc, kể cả bậc 1 — cổng phải là
    cổng, không phải bộ lọc riêng cho bậc bị nghi ngờ.

    Con số không truy được về một dòng `facts` trong raw/ thì không được ra khỏi
    đây. Thà không trả lời còn hơn trả lời một con số không có nguồn.

    THEO NGỮ CẢNH: chỉ chấp nhận số thuộc facts của ĐÚNG nguồn câu trả lời đã trích
    (`res.cites`) — không phải cả vũ trụ số. Nhờ vậy '50 Điều' trích từ tài liệu OCR
    (0 facts đăng ký) không mở khoá được nhờ trùng một số ở nguồn khác."""
    bad = numeric_guard.check(policy="answer", text=res.answer, cites=res.cites)
    if not bad:
        return res
    return Result(res.tier, NF,
        "Đã CHẶN ở GATE 4 — câu trả lời chứa con số không truy được nguồn.",
        cites=res.cites,
        reason=f"numeric_guard(policy=answer) chặn: {bad}. Không con số nào trong "
               f"raw/*.facts.json khớp. Bậc {res.tier} đã sinh ra số này mà không có "
               f"`src` — có thể là tự tính. Kho không xuất bản số không có nguồn.\n"
               f"    (câu bị chặn: {res.answer.replace(chr(10), ' ')[:160]})")


def ask(kb, q, llm=True):
    """Bậc 1 tất định. Bậc 1 bó tay -> bậc 2 định vị trang -> bậc 3 đọc và trả lời.

    Bậc 3 BẬT MẶC ĐỊNH. Bậc 2 tự nó chỉ trả về "có trang liên quan", đó không phải
    câu trả lời. Tắt bằng llm=False (eval dùng, để tất định và nhanh)."""
    r = tier1(kb, q)
    if r:
        return gate4(r)

    # Vẫn còn trong BẬC 1: quét bảng đã nạp. Phải chạy TRƯỚC bậc 2 — sơ đồ quy định
    # bậc 1 (tất định) luôn thử trước, và bậc 2 chỉ trả về "có trang liên quan" chứ
    # không phải câu trả lời, nên để nó chen lên trước là mất câu trả lời có thật.
    fb = doc_fallback(kb, q)
    if fb:
        return gate4(fb)

    r2 = tier2(kb, q)
    pages = list(r2.cites or getattr(r2, "pages", []))
    # Bậc 2 chấm theo từ khoá nên tên ngắn bị lọc mất ("Du" 2 ký tự -> trượt trang
    # be-du.md). Nhưng ta BIẾT câu hỏi nhắc ai — `assignee` là DIMENSION đóng, khớp
    # được chính xác. Dùng từ vựng đóng để vá chỗ tìm kiếm mờ bị hụt.
    for slug in kb.find_people(q):
        pg = kb.person(slug)[6]
        if pg not in pages:
            pages.insert(0, pg)
    # BẬC 2 = keyword + vector, hợp nhất bằng RRF (chỉ khi LLM bật; eval tất định
    # thì bỏ qua, khỏi nạp model 2GB). Ép giữ trang định danh đóng (người được nhắc).
    if llm:
        pin = [kb.person(s)[6] for s in kb.find_people(q)]
        sem = semantic_pages(q, k=6)
        if sem:
            pages = rrf_merge([pages, sem], keep=6, pin=pin)
    if llm and pages:
        r3 = gate4(tier3(kb, q, pages))
        # Bậc 3 nói KHÔNG TÌM THẤY thì vẫn dùng câu của nó — nó nêu ĐÍCH DANH cái
        # đang thiếu, hữu ích hơn câu chung chung của bậc 2. Nhưng phải gắn kèm
        # lời cảnh báo của bậc 2, vì LLM không được phép tự nói câu đó.
        if r3.outcome == NF:
            r3.reason = (r3.reason + " Đây là 'kho không biết', KHÔNG phải 'không có' — "
                         "chỉ bậc 1 với DIMENSION đóng + coverage đã ký mới được nói "
                         "'chắc chắn không'.")
        return r3
    if r2.outcome == CO:   # bậc 3 tắt: đừng vờ như đã trả lời
        r2.outcome = NF
    return gate4(r2)


# Câu NỐI TIẾP RÚT GỌN: chỉ nhắc tên người, ý còn lại lấy từ câu trước.
# "vậy còn [BE] Du" / "còn Du thì sao" / "[BE] Du thì sao".
ELLIPSIS = re.compile(r"^\s*(?:vay\s+|the\s+)?(?:con\s+)?(.+?)\s*(?:thi\s+sao)?\s*[?.]?\s*$")


def flex_label(label):
    """Regex khớp một nhãn PIC bất kể ngoặc/dấu cách: '[QC] LAN' -> khớp cả '[QC]LAN'."""
    toks = re.findall(r"[A-Za-z0-9.]+", label)
    return re.compile(r"\[?\s*" + r"\s*\]?\s*".join(re.escape(t) for t in toks), re.I)


def resolve_ellipsis(kb, q, prev_q, prev_slug):
    """Nếu q chỉ là một tên người (không động từ/số/điều kiện) và câu trước có đúng
    một người -> thay tên trong câu trước. Trả (câu_viết_lại | None)."""
    if not prev_q or not prev_slug:
        return None
    who = kb.find_people(q)
    if len(who) != 1:
        return None
    # q phải "rỗng nghĩa" ngoài cái tên: bỏ tên đi thì không còn động từ/số/điều kiện
    m = ELLIPSIS.match(strip_accent(q))
    core = m.group(1) if m else strip_accent(q)
    core_wo_name = flex_label(kb.person(who[0])[1]).sub("", q)
    if re.search(r"\d|task|gio|effort|cong|vai tro|role|sprint|thang|bao nhieu",
                 strip_accent(core_wo_name)):
        return None                       # có nội dung riêng -> không phải nối tiếp
    old_label, new_label = kb.person(prev_slug)[1], kb.person(who[0])[1]
    rewritten, n = flex_label(old_label).subn(new_label, prev_q)
    return rewritten if n else None


def repl(kbase, use_llm):
    """Chế độ hỏi liên tục. Gõ câu hỏi, Enter. `!llm` bật/tắt bậc 3. Ctrl-D để thoát."""
    print(f"{D}chế độ hỏi liên tục · bậc 3 {'BẬT (~17s khi bậc 1 bó tay)' if use_llm else 'tắt'} "
          f"· `!llm` để đổi · Ctrl-D thoát{OFF}\n")
    prev_q, prev_slug = None, None
    while True:
        try:
            q = input(f"{B}?{OFF} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            continue
        if q.lower() == "!llm":   # nhận cả '!LLM' — gõ hoa không nên biến lệnh thành câu hỏi
            use_llm = not use_llm
            print(f"{D}bậc 3: {'BẬT (~17s/câu)' if use_llm else 'tắt'}{OFF}\n")
            continue
        rewritten = resolve_ellipsis(kbase, q, prev_q, prev_slug)
        if rewritten:
            print(f"{D}↳ hiểu là: {rewritten}{OFF}")
            q = rewritten
        print()
        ask(kbase, q, llm=use_llm).show()
        print()
        who = kbase.find_people(q)
        if len(who) == 1:                 # nhớ để câu sau nối tiếp được
            prev_q, prev_slug = q, who[0]


if __name__ == "__main__":
    if len(sys.argv) < 2 or set(sys.argv[1:]) <= {"--llm", "--no-llm", "-i"}:
        repl(KB(), "--no-llm" not in sys.argv)
        sys.exit(0)
    use_llm = "--no-llm" not in sys.argv
    question = " ".join(a for a in sys.argv[1:] if a not in ("--llm", "--no-llm"))
    kbase = KB()
    print(f"{B}?{OFF} {question}\n")
    ask(kbase, question, llm=use_llm).show()
