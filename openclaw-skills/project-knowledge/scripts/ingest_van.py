#!/usr/bin/env python3
"""STAGE 4 (luồng VĂN) — WIKI-INGEST: trang `source` cho tài liệu văn xuôi.

  structured/<doc_id>.md + raw provenance + contract --[ Opus ]--> wiki/sources/<doc_id>.md

Song song với `ingest.py` (chỉ làm entity-person của corpus handy). Việc NẶNG (soạn
nội dung theo hợp đồng) → dùng models.HEAVY.

Như ingest.py: LLM KHÔNG được cấp quyền ghi file. Nó trả nội dung ra stdout, script
này mới ghi — một cửa duy nhất, không thể lỡ tay chạm originals/ hay raw/.

Trang `source` (theo CLAUDE.md §3): bắt buộc page/name/raw_paths/doc_id + DIMENSION
`domain`. Thân bài là BẢN TÓM TẮT CÓ CẤU TRÚC trung thành với tài liệu — KHÔNG chép
trọn (raw/ đã giữ trọn), KHÔNG bịa. Tài liệu `ocr: true` là bản máy đọc → ghi rõ cảnh
báo, số trong đó không phải nguyên văn.

  python3 scripts/ingest_van.py --doc chinh-sach-attt
  python3 scripts/ingest_van.py --all
  python3 scripts/ingest_van.py --doc chinh-sach-attt --fresh
  python3 scripts/ingest_van.py --doc chinh-sach-attt --fresh-page \
      wiki/sources/chinh-sach-attt--chuong-2.md
"""
import json
import os
import re
import unicodedata
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
import build_index  # noqa: E402
import numeric_guard  # noqa: E402
import structure  # noqa: E402
from artifact_paths import artifact_path  # noqa: E402
from document_registry import current as current_document  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
G, R, D, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

# Wiki ingest is deliberately cheaper than the generic ``HEAVY`` lane.  The
# caller can still opt into Opus with ``PROJECT_KNOWLEDGE_WIKI_MODEL=opus`` (or
# the legacy heavy-model variable), while a long document defaults to Sonnet.
WIKI_MODEL = (os.getenv("PROJECT_KNOWLEDGE_WIKI_MODEL")
              or os.getenv("PROJECT_KNOWLEDGE_HEAVY_MODEL", "sonnet"))

# The full repository contract is useful for humans and gates, but repeating it
# in every chapter prompt spends thousands of input tokens without adding a new
# fact.  The deterministic validators below remain authoritative; this compact
# prompt only tells the model how to format a candidate that those validators
# will check.
PROMPT_CONTRACT_SUMMARY = """
Generate only one Markdown `source` page; the caller writes the file. Do not use
tools, read files, or add commentary/code fences. Required frontmatter fields:
page, name, doc_id, version, domain, visibility, raw_paths; a chapter page also
has section and part_of. Do not add project. The body is a faithful Vietnamese
structured summary of only the supplied source scope, preserving chapter/article
structure and all conditions, thresholds, and procedures that are mentioned.
Never invent, calculate, round, or combine numbers. If several values have
separate units (45 days, 30 days, 03 days), keep them separate; never write
45/30/03. OCR numbers must be labelled as OCR and never declared as facts.
End with the exact requested `## Nguồn` provenance lines.
""".strip()

PROMPT_SCHEMA_SUMMARY = """
This is a `source` page. `domain` must be the supplied valid dimension value;
visibility is public, internal, or restricted. `raw_paths` must point to the
supplied registered raw artifact. Numeric frontmatter declarations are allowed
only for non-OCR sources and must contain facts, unit, and src that point to the
exact source location. For OCR sources, declare no facts.
""".strip()

PROMPT = """Bạn đang thực hiện STAGE 4 (WIKI-INGEST) của hệ thống LLM-wiki.
Nhiệm vụ: viết trang `wiki/sources/{doc_id}.md` — trang loại `source` cho MỘT tài liệu.

===== HỢP ĐỒNG (CLAUDE.md) =====
{contract}

===== SCHEMA MÁY ĐỌC (schema.yml) =====
{schema}

===== TÀI LIỆU ĐÃ QUA STAGE 3 (structured/{doc_id}.md) =====
Đây là TOÀN BỘ nội dung được phép dùng. Không dùng gì ngoài đây.
{ocr_note}
{raw}

===== YÊU CẦU =====
1. Bạn đang SINH nội dung file (script khác sẽ ghi ra đĩa — bạn KHÔNG có quyền đọc/ghi
   file, đừng giả định file đã tồn tại hay đi kiểm tra). Trả về ĐÚNG nội dung file
   markdown, ký tự ĐẦU TIÊN là `-` của dòng `---`. KHÔNG rào ```, KHÔNG một dòng lời dẫn
   nào trước `---`, KHÔNG lời bàn/tự-đánh-giá/checklist nào SAU nội dung trang.
2. Frontmatter BẮT BUỘC, đúng thứ tự:
   page: source
   name: "{title}"
   doc_id: {doc_id}
   version: {version}
   domain: {domain}          # DIMENSION — chọn đúng giá trị này, không đổi
   visibility: {visibility}
   raw_paths:
     - {raw_path}
   KHÔNG thêm `project` (tài liệu này không thuộc dự án phần mềm nào).
{facts_rule}
3. Thân bài: TÓM TẮT CÓ CẤU TRÚC, trung thành, tiếng Việt. Bám bố cục thật của tài
   liệu (Chương/Điều/Mục). Nêu được: tài liệu này là gì, phạm vi/đối tượng áp dụng,
   và các nhóm nội dung chính (liệt kê theo Chương/Điều, mỗi mục 1 câu cô đọng).
4. TUYỆT ĐỐI KHÔNG bịa. Chỉ viết điều CÓ trong tài liệu trên. Không suy diễn ngoài văn bản.
5. Con số trong thân bài: nếu nhắc một con số thì phải là số CÓ THẬT trong tài liệu và
   ghi rõ đang trích từ đâu (vd "theo Điều 12"). Không tự cộng/suy ra số mới. Số hiệu
   văn bản (Luật 86/2015/QH13), mã tài liệu, số Điều/Chương là ĐỊNH DANH — cứ nêu tự do,
   không phải "số đo".
{ocr_rule}
6. Kết bài có một mục "## Nguồn" ghi: doc_id, và raw_paths.
7. Gọn, đủ để người đọc biết tài liệu chứa gì và tra tiếp ở đâu — KHÔNG chép nguyên văn.
"""


SECTION_PROMPT = """Bạn đang thực hiện STAGE 4 (WIKI-INGEST) của hệ thống LLM-wiki.
Nhiệm vụ: viết trang `wiki/sources/{doc_id}--{slug}.md` — trang loại `source` cho MỘT
CHƯƠNG của tài liệu "{title}": **{section_title}**.

Trang tổng quan của tài liệu đã có và chỉ tóm tắt bố cục. Trang này là nơi nội dung
chương thật sự được đánh chỉ mục để tra cứu, nên nó phải CHI TIẾT hơn hẳn: đi theo
từng Điều, giữ đủ điều kiện/ngưỡng/thủ tục để người đọc trả lời được câu hỏi cụ thể
mà không phải mở tài liệu gốc.

SCOPE GUARD: Nếu phần trích được cấp không có một Điều/khoản đánh số, không được
nhắc đến số hiệu bị thiếu hoặc tự suy ra khoảng số từ mục lục. Chỉ ghi nội dung có
trong đúng phần trích; nếu cần cảnh báo, nói "phần trích không có nội dung này"
nhưng không nêu lại số hiệu vắng mặt.

===== HỢP ĐỒNG (CLAUDE.md) =====
{contract}

===== SCHEMA MÁY ĐỌC (schema.yml) =====
{schema}

===== NỘI DUNG CHƯƠNG (trích structured/{doc_id}.md) =====
Đây là TOÀN BỘ nội dung được phép dùng. Không dùng gì ngoài đây, kể cả kiến thức về
các chương khác của tài liệu.
{ocr_note}
{raw}

===== YÊU CẦU =====
1. Trả về ĐÚNG nội dung file markdown, ký tự ĐẦU TIÊN là `-` của dòng `---`. KHÔNG rào
   ```, KHÔNG lời dẫn trước `---`, KHÔNG lời bàn/tự-đánh-giá SAU nội dung trang.
2. Frontmatter BẮT BUỘC, đúng thứ tự:
   page: source
   name: "{title} — {section_title}"
   doc_id: {doc_id}
   version: {version}
   domain: {domain}          # DIMENSION — chọn đúng giá trị này, không đổi
   visibility: {visibility}
   raw_paths:
     - {raw_path}
   section: "{section_title}"
   part_of: wiki/sources/{doc_id}.md
   KHÔNG thêm `project`.
{facts_rule}
3. Thân bài: đi theo TỪNG ĐIỀU của chương này, mỗi Điều một mục con, nêu đủ nghĩa vụ,
   điều kiện, thủ tục và ngưỡng. Đây KHÔNG phải bản tóm tắt một dòng — người đọc phải
   tra được chi tiết ở đây.
4. TUYỆT ĐỐI KHÔNG bịa. Chỉ viết điều CÓ trong nội dung chương trên.
5. Con số: phải là số CÓ THẬT trong chương này và ghi rõ trích từ Điều nào. Không tự
   cộng/suy ra số mới. Số hiệu văn bản, mã tài liệu, số Điều/Chương là ĐỊNH DANH.
{ocr_rule}
6. Kết bài có một mục "## Nguồn" ghi ĐÚNG BA dòng: doc_id, raw_paths, và trang tổng
   quan `wiki/sources/{doc_id}.md`. KHÔNG thêm dòng `version` hay bất kỳ số nào khác
   vào mục này — nó không phải nội dung chương, không cần trích dẫn lại.
"""


# ------------------------------------------------- trang theo CHƯƠNG (tài liệu dài)
# Trang `source` cố ý là bản TÓM TẮT — prompt trên ghi rõ "KHÔNG chép nguyên văn",
# "đủ để người đọc biết tài liệu chứa gì và tra tiếp ở đâu". Với một tài liệu vài
# trang thì đúng. Với bản nội quy 38 trang thì trang wiki còn 9% độ dài structured,
# và "tra tiếp" KHÔNG CÓ CƠ CHẾ NÀO: truy hồi chỉ phục vụ `wiki/`, nên 91% nội dung
# không bao giờ được đánh chỉ mục. Kho tìm đúng trang, trang không chứa câu trả lời,
# Gate 4 nói `not_in_kb` — kho có tài liệu mà bảo không biết.
#
# Luồng SỐ không gặp chuyện này vì workbook sinh nhiều trang (mỗi người một trang).
# Luồng VĂN sinh đúng một trang cho mọi tài liệu, dài bao nhiêu cũng vậy. Nên tài liệu
# dài được cắt thêm trang theo CHƯƠNG — ranh giới có thật trong văn bản, không phải
# cửa sổ trượt — và mỗi trang chương đi qua đúng những cổng như trang tổng quan.
SECTION_MIN_CHARS = 20000
# Không dựa vào cú pháp markdown. `structured/` do Stage 3 sinh trên 8 khúc ĐỘC LẬP,
# nên cách đánh dấu tiêu đề không nhất quán: chương 3–5 và 8–9 có tiền tố `## `, còn
# chương 2, 6, 7, 10 là dòng trần. Nhận diện theo MẪU CHỮ, tiền tố `#` là tuỳ chọn.
CHAPTER_HEADING = re.compile(r"(?im)^[#\s]*(CHƯƠNG\s+(\d+)\.\s+[^\n]*?)\s*$")
# Dòng mục lục khớp y hệt tiêu đề thật, chỉ khác ở số trang cuối dòng.
TOC_TAIL = re.compile(r"\s\d+$")
FRONT_SECTION = ("phan-dau", "Phần đầu: bìa, kiểm soát tài liệu, mục lục")
FRONT_MIN_CHARS = 400


# Tên trang chương = <doc_id>--<slug>.md, và doc_id đã dài 45 ký tự (slug tên + dấu
# thời gian UTC + hash). Cộng tiền tố worktree nạp (`.ingest-worktrees/ingest-<doc_id>@v1/
# openclaw-skills/project-knowledge/`) thì đường dẫn tuyệt đối vượt 260 ký tự của Windows
# — cắt 60 làm `chuong-5-an-toan-ve-sinh-lao-dong-tai-noi-lam-viec` đủ để tràn. Cắt 28
# và bỏ mảnh từ dở ở cuối: tên vẫn đọc được, và còn dư chỗ cho doc_id dài hơn tài liệu
# này (đường dẫn dài nhất hiện tại 244/260).
SLUG_MAX = 28


def slugify(text):
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")
    if len(slug) <= SLUG_MAX:
        return slug
    return slug[:SLUG_MAX].rsplit("-", 1)[0]


def chapter_marks(body):
    """Vị trí tiêu đề chương THÂN BÀI: bỏ dòng mục lục, mỗi số chương lấy lần cuối."""
    last = {}
    for match in CHAPTER_HEADING.finditer(body):
        title = " ".join(match.group(1).split())
        if TOC_TAIL.search(title):
            continue
        last[match.group(2)] = (match.start(), title)
    marks = sorted(last.values())
    # Giữ dãy tăng dần theo vị trí lẫn số chương — một tiêu đề nhắc lại ở giữa thân
    # bài không được cắt tài liệu thành hai mảnh chồng nhau.
    kept, seen = [], -1
    for start, title in marks:
        number = int(CHAPTER_HEADING.match(title).group(2)) if CHAPTER_HEADING.match(title) else 0
        if number > seen:
            kept.append((start, title))
            seen = number
    return kept


def split_sections(body):
    """Cắt structured theo CHƯƠNG. Trả [(slug, tiêu đề, nội dung)], phủ TOÀN BỘ body.

    Phần trước tiêu đề chương đầu tiên — bìa, bảng kiểm soát tài liệu, mục lục — thành
    một mục riêng chứ không bị bỏ: đó là nơi giữ ngày hiệu lực, phiên bản và người
    phê duyệt.
    """
    marks = chapter_marks(body)
    if len(marks) < 2:
        return []
    sections = []
    # Chỉ tách mục đầu khi nó có nội dung THẬT. `structured/` mở đầu bằng frontmatter
    # YAML do script sinh; nếu chương 1 bắt đầu ngay sau đó thì "phần đầu" chỉ còn vài
    # dòng metadata. Cấp một mục rỗng cho Stage 4 thì Opus không có gì để viết, nó viết
    # ghi chú "nội dung không có trong bản trích được cấp cho Stage 4" — và chữ
    # "Stage 4" thành một con số bịa làm cổng chặn cả tài liệu.
    if len(body[:marks[0][0]].strip()) >= FRONT_MIN_CHARS:
        sections.append((*FRONT_SECTION, body[:marks[0][0]]))
    for index, (start, title) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(body)
        sections.append((slugify(title), title, body[start:end]))
    return sections


def load_docs():
    spec_path = ROOT / "extract/van-docs.yml"
    if not spec_path.exists():
        return {}
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return {d["doc_id"]: d for d in spec["docs"]}


def validate_page(structured, page_text, root=ROOT):
    """Cổng Stage 4 luồng VĂN -> danh sách lỗi (rỗng = qua). Thuần, không gọi LLM.

    Trang sinh ra có HAI phần với hai loại luật khác nhau, phải soi bằng hai cổng:

      thân bài (văn xuôi)  -> check_transform(allow_loss=True): tóm tắt được phép bỏ
                              bớt, nhưng cấm bịa/làm tròn số.
      frontmatter (YAML)   -> check_page_declarations: đối chiếu ngược từng khai báo
                              `{facts, unit, src}` về đúng mục trong raw.

    Cho frontmatter đi qua cổng văn xuôi là SAI, và sai theo hướng chặn oan: trong
    `facts: 8, unit: "ký tự"` thì ký tự ngay sau số 8 là dấu phẩy, nên cổng đọc được
    cặp (8, không-đơn-vị) trong khi nguồn ghi (8, ký tự) — hai khoá khác nhau, và một
    con số khai ĐÚNG bị báo là "số mới/đổi/làm tròn". Cổng khai báo bên dưới chặt hơn
    cổng văn xuôi, nên tách ra không hề nới lỏng: nó đòi số phải nằm đúng mục `src`,
    chứ không chỉ tồn tại đâu đó trong tài liệu."""
    frontmatter, body = numeric_guard.split_frontmatter(page_text)
    problems, _ = numeric_guard.check_transform(structured, body, allow_loss=True)
    return problems + numeric_guard.check_page_declarations(frontmatter, root)


def _overview_teaser(section_text, limit=280):
    """Extract a short verbatim teaser for the deterministic overview.

    This is intentionally not a generated interpretation: it only reuses the
    first meaningful paragraph from the already validated Stage 3 artifact.
    The chapter page remains the detailed retrieval source.
    """
    text = re.sub(r"\[\[page\s+\d+\]\]", " ", section_text)
    text = re.sub(r"(?im)^\s*#{0,6}\s*CHƯƠNG\s+\d+\.[^\n]*$", "", text)
    for paragraph in re.split(r"\n\s*\n", text):
        one_line = " ".join(paragraph.split())
        if len(one_line) < 40:
            continue
        if one_line.startswith("---") or one_line.startswith("doc_id:"):
            continue
        one_line = one_line.replace("|", "\\|")
        return one_line if len(one_line) <= limit else one_line[:limit].rstrip() + "…"
    return "Nội dung chi tiết được lập chỉ mục tại trang chương tương ứng."


def build_overview_page(*, doc_id, title, domain, version, visibility,
                        raw_path, sections, is_ocr):
    """Build a lossless navigation page without a second LLM call.

    Chapter pages carry the facts and procedures.  The overview is deliberately
    deterministic: headings come from ``structured/`` and teasers are verbatim
    excerpts, so removing an expensive summarisation call cannot introduce a
    new claim or number.
    """
    frontmatter = {
        "page": "source",
        "name": title,
        "doc_id": doc_id,
        "version": version,
        "domain": domain,
        "visibility": visibility,
        "raw_paths": [raw_path],
    }
    header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    body = [
        f"# {title}",
        "",
        "## Tổng quan",
        "",
        "Đây là trang điều hướng của tài liệu nguồn. Nội dung chi tiết được tách theo "
        "từng chương để tra cứu; các đoạn giới thiệu dưới đây được trích từ bản "
        "structured đã kiểm tra, không phải diễn giải mới.",
    ]
    if is_ocr:
        body += [
            "",
            "Nguồn là bản OCR; các con số trong nội dung cần được đối chiếu với bản gốc.",
        ]
    body += ["", "## Nội dung chính", ""]
    for slug, section_title, section_text in sections:
        body.append(f"- [[{doc_id}--{slug}]] — **{section_title}**: "
                    f"{_overview_teaser(section_text)}")
    body += [
        "",
        "## Nguồn",
        "",
        f"- doc_id: {doc_id}",
        f"- raw_paths: {raw_path}",
    ]
    return f"---\n{header}\n---\n\n" + "\n".join(body) + "\n"


def _reuse_candidate(rel, scope, *, name, doc_id, version, raw_path,
                     domain, visibility, section_title=None):
    """Return a previously generated page only after running the current gates.

    Long documents are intentionally all-or-nothing, but an interrupted Claude
    run may already have produced valid drafts in ``derived/stage4-rejected``.
    Resume mode can reuse those drafts without weakening validation; stale or
    invalid drafts are ignored and regenerated normally.
    """
    candidates = []
    canonical = ROOT / rel
    if canonical.is_file():
        candidates.append(canonical)
    rejected = ROOT / "derived/stage4-rejected"
    if section_title:
        for path in sorted(rejected.glob(f"{name.split('--', 1)[0]}--*.md")):
            try:
                frontmatter, _ = numeric_guard.split_frontmatter(
                    path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if frontmatter.get("section") == section_title:
                candidates.append(path)
    else:
        candidates.append(rejected / f"{name}.md")
    seen = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
            frontmatter, _ = numeric_guard.split_frontmatter(text)
        except (OSError, UnicodeDecodeError):
            continue
        # A cache hit is safe only for the same registered source version and
        # raw artifact.  This prevents a cheaper resume path from masking a
        # changed document or accidentally mixing another chapter's page.
        try:
            page_version = int(frontmatter.get("version", -1))
        except (TypeError, ValueError):
            continue
        if (frontmatter.get("page") != "source"
                or str(frontmatter.get("doc_id")) != str(doc_id)
                or page_version != int(version)
                or frontmatter.get("domain") != domain
                or frontmatter.get("visibility") != visibility
                or list(frontmatter.get("raw_paths") or []) != [raw_path]):
            continue
        if section_title:
            if (frontmatter.get("section") != section_title
                    or frontmatter.get("part_of") != f"wiki/sources/{doc_id}.md"):
                continue
        elif "section" in frontmatter or "part_of" in frontmatter:
            continue
        if not validate_page(scope, text, ROOT):
            return text if text.endswith("\n") else text + "\n"
    return None


def ingest_one(doc_id, d, contract, schema, timeout=600, *, reuse_rejected=False,
               force_pages=()):
    try:
        registry = current_document(doc_id, ROOT)
    except (KeyError, ValueError) as exc:
        return None, 0.0, f"documents.yml chưa có current version hợp lệ: {exc}"
    raw_path = artifact_path(ROOT, registry, doc_id, "md")
    if not raw_path.exists():
        return None, 0.0, f"chưa có {raw_path.relative_to(ROOT)} (chạy extract_van.py trước)"
    raw = raw_path.read_text(encoding="utf-8")
    structured_path = ROOT / "structured" / f"{doc_id}.md"
    if not structured_path.exists():
        return None, 0.0, (f"chưa có structured/{doc_id}.md — Stage 3 là bắt buộc; "
                           f"chạy scripts/structure.py --doc {doc_id}")
    metadata_errors = structure.validate_source_metadata(doc_id, raw_path, structured_path)
    if metadata_errors:
        return None, 0.0, "structured không khớp raw: " + "; ".join(metadata_errors)
    structured = structured_path.read_text(encoding="utf-8")
    is_ocr = "\nocr: true" in raw or raw.startswith("ocr: true")
    ocr_note = ("\n[LƯU Ý: tài liệu này do OCR sinh (máy đọc ảnh) — có thể sai vài "
                "chữ/số. KHÔNG coi số ở đây là nguyên văn.]\n") if is_ocr else ""
    ocr_rule = ("   Tài liệu OCR: nếu nhắc số, PHẢI kèm 'theo bản OCR, cần đối chiếu bản gốc'."
                if is_ocr else "")
    # LUỒNG SỐ có .facts.json; VĂN thì không → số ĐO trong tài liệu chỉ truy được nếu
    # trang này khai chúng ở chế độ chép (CLAUDE.md §1.2). Gate 4 đọc đúng các khai báo
    # này để cho số Mor qua. OCR = bản đoán → CẤM khai facts (LUẬT OCR); số OCR chỉ nêu
    # trong thân bài kèm cảnh báo, KHÔNG được đăng ký làm sự thật.
    if is_ocr:
        facts_rule = (
            "   KHÔNG khai bất kỳ trường số `facts:` nào ở frontmatter — tài liệu này do OCR\n"
            "   sinh (bản đoán), số ở đây CẤM đăng ký làm sự thật (LUẬT OCR).")
    else:
        facts_rule = (
            "   Sau `raw_paths`, khai thêm các SỐ ĐO NGƯỠNG/CHU KỲ/SỐ LƯỢNG đáng tra của tài\n"
            "   liệu ở chế độ chép — mỗi số một trường frontmatter tên gợi nhớ (snake_case):\n"
            "     do_dai_mat_khau_toi_thieu: {{ facts: 8, unit: \"ký tự\", src: \"{raw_path} :: Điều 7\" }}\n"
            "   Quy tắc: (a) CHỈ khai số CÓ THẬT trong tài liệu, `src` trỏ đúng Điều/Mục chứa nó;\n"
            "   (b) mỗi trường bắt buộc đủ `facts` + `unit` + `src`; (c) chỉ khai số ĐO thật sự\n"
            "   đáng hỏi (ngưỡng, chu kỳ, số lượng) — BỎ QUA số hiệu văn bản/mã/số Điều (định danh);\n"
            "   (d) TUYỆT ĐỐI không tự tính/suy ra số mới. Không có số đo đáng khai thì bỏ trống mục này.\n"
            "   Cổng sẽ MỞ tài liệu ra đối chiếu: giá trị phải nằm ĐÚNG trong mục mà `src` nêu, và\n"
            "   đơn vị phải khớp chữ đứng cạnh số ở đó. Trỏ sai mục thì bị chặn, kể cả khi con số\n"
            "   có thật ở một mục khác. Không chắc số nằm ở mục nào thì ĐỪNG khai trường đó.") \
            .format(doc_id=doc_id, raw_path=raw_path.relative_to(ROOT).as_posix())
    facts_rule += (
        "\n   Numeric formatting rule: when the source lists multiple values with their own "
        "units (for example, 45 days, 30 days, and 03 days), preserve each value and "
        "unit separately. Do NOT combine them with `/` into a date-like token such as "
        "`45/30/03`; that token is not in the source.\n"
    )
    common = dict(
        doc_id=doc_id, title=d.get("title", doc_id), domain=d["domain"],
        version=int(registry["version"]), visibility=registry.get("visibility", "internal"),
        contract=PROMPT_CONTRACT_SUMMARY, schema=PROMPT_SCHEMA_SUMMARY, ocr_note=ocr_note,
        ocr_rule=ocr_rule, facts_rule=facts_rule,
        raw_path=raw_path.relative_to(ROOT).as_posix())

    sections = split_sections(structured) if len(structured) >= SECTION_MIN_CHARS else []
    pages, elapsed = [], 0.0
    text = _reuse_candidate(
        f"wiki/sources/{doc_id}.md", structured, name=doc_id,
        doc_id=doc_id, version=common["version"], raw_path=common["raw_path"],
        domain=common["domain"], visibility=common["visibility"]
    ) if reuse_rejected and f"wiki/sources/{doc_id}.md" not in force_pages else None
    dt = 0.0
    if text is None:
        text = build_overview_page(
            doc_id=doc_id, title=common["title"], domain=common["domain"],
            version=common["version"], visibility=common["visibility"],
            raw_path=common["raw_path"], sections=sections, is_ocr=is_ocr)
        problems = validate_page(structured, text, ROOT)
        err = (f"GATE 2/WIKI overview deterministic chặn: {'; '.join(problems)}"
               if problems else None)
        dt = 0.0
    else:
        err = None
    elapsed += dt
    # `text is None` phải chặn ở đây kể cả khi `err` rỗng: một thông báo lỗi rỗng từng
    # cho `None` lọt vào danh sách trang và làm sập lượt chạy ở bước ghi file.
    if err or text is None:
        return None, elapsed, err or "không có nội dung trang"
    pages.append((f"wiki/sources/{doc_id}.md", text))

    # Tài liệu dài: thêm một trang cho mỗi CHƯƠNG. Trang tổng quan vẫn giữ nguyên vai
    # trò mục lục; trang chương mới là chỗ nội dung thật sự vào được chỉ mục.
    sections = split_sections(structured) if len(structured) >= SECTION_MIN_CHARS else []
    for slug, section_title, section_text in sections:
        prompt = SECTION_PROMPT.format(raw=section_text, slug=slug,
                                       section_title=section_title, **common)
        page_rel = f"wiki/sources/{doc_id}--{slug}.md"
        text = (_reuse_candidate(
            page_rel, section_text, name=f"{doc_id}--{slug}",
            doc_id=doc_id, version=common["version"], raw_path=common["raw_path"],
            domain=common["domain"], visibility=common["visibility"],
            section_title=section_title
        ) if reuse_rejected and page_rel not in force_pages else None)
        dt = 0.0
        if text is None:
            text, dt, err = render(prompt, section_text, timeout,
                                   name=f"{doc_id}--{slug}")
        else:
            err = None
        elapsed += dt
        if err or text is None:
            return None, elapsed, f"[{slug}] {err or 'không có nội dung trang'}"
        pages.append((page_rel, text))
    return pages, elapsed, None


def dump_rejected(name, text):
    """Cổng chặn thì KHÔNG ghi wiki/ — nhưng bản bị từ chối phải xem được.

    Cùng lý do như derived/stage3-rejected/: chẩn đoán một dòng "số mới `29.3`" mà
    không có văn bản trong tay là đoán mò, và cách duy nhất để nhìn là chạy lại cả
    tài liệu bằng Opus. Ghi vào derived/ vì đây là trạng thái vận hành tái tạo được."""
    # Đây là công cụ CHẨN ĐOÁN — nó không bao giờ được làm hỏng lượt chạy. Bản đầu
    # ném FileNotFoundError khi đường dẫn vượt 260 ký tự của Windows (worktree nạp có
    # tiền tố dài sẵn), và một lượt Stage 4 chín phút chết ở dòng ghi log lỗi.
    try:
        out_dir = ROOT / "derived/stage4-rejected"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        return path.relative_to(ROOT).as_posix()
    except OSError as exc:
        return f"(không ghi được bản bị từ chối: {exc.__class__.__name__})"


# Một tài liệu dài là 11 lượt gọi nối tiếp, nên xác suất vấp lỗi tạm thời cộng dồn —
# đúng như Stage 3. Thử lại chỉ cho lỗi HẠ TẦNG; cổng chặn thì KHÔNG, vì đó là kết luận
# về nội dung và thử lại một kết luận cho tới khi nó đổi ý chính là cách phá cổng.
RETRIES = 3
RETRY_BACKOFF = 15


def render(prompt, scope, timeout, name="page"):
    """Gọi Opus (thử lại khi hạ tầng hỏng), dọn đầu ra, soi cổng với ĐÚNG phạm vi nguồn."""
    elapsed, last = 0.0, "không rõ"
    for attempt in range(1, RETRIES + 1):
        text, dt, failure = _render_once(prompt, scope, timeout, name)
        elapsed += dt
        if failure is None or not _retryable_failure(failure):
            return text, elapsed, failure
        last = failure
        if attempt < RETRIES:
            print(f"⟳ {name}: {last} — thử lại {attempt}/{RETRIES - 1}", file=sys.stderr)
            time.sleep(RETRY_BACKOFF * attempt)
    return None, elapsed, last


INFRA = "hạ tầng: "
NON_RETRYABLE_INFRA = (
    "monthly spend limit", "not logged in", "authentication", "unauthorized",
    "invalid api key", "invalid api_key", "permission denied", "credit balance",
)


def _retryable_failure(failure):
    """Only retry transient infrastructure errors, never quota/auth failures."""
    if not failure or not failure.startswith(INFRA):
        return False
    lowered = failure.lower()
    return not any(marker in lowered for marker in NON_RETRYABLE_INFRA)


def _render_once(prompt, scope, timeout, name):
    t0 = time.time()
    try:
        out = subprocess.run(
            # `--tools=` is the portable spelling for "no built-in tools".
            # Passing `--allowedTools`, "" works on POSIX shells but the
            # Windows Claude CLI treats the empty argv as a missing value.
            [models.CLAUDE, "-p", "--no-session-persistence", "--model", WIKI_MODEL, "--tools="],
            input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired:
        return None, time.time() - t0, f"{INFRA}quá {timeout}s"
    dt = time.time() - t0
    if out.returncode != 0:
        # Thông báo lỗi phải LUÔN khác rỗng. Bản trước trả `(out.stderr or "").strip()`
        # và khi CLI hỏng với stderr rỗng thì err là chuỗi rỗng — `if err:` không bắt,
        # `None` được nhét vào danh sách trang, và lượt chạy sập ở bước ghi file với
        # `TypeError: data must be str, not NoneType`.
        # Claude print mode may put quota/auth failures on stdout while leaving
        # stderr empty. Preserve that signal instead of reporting an opaque
        # ``code 1, stderr empty`` infrastructure error.
        detail = (out.stderr or out.stdout or "").strip()[:200] or "stderr rỗng"
        return None, dt, f"{INFRA}mã lỗi {out.returncode}: {detail}"
    text = (out.stdout or "").strip()
    text = re.sub(r"^```(?:markdown|yaml)?\n|\n```$", "", text).strip()
    # Output LLM không tất định: đôi khi thêm lời dẫn trước frontmatter. Cắt từ dòng
    # '---' đầu tiên. Không có '---' nào = thật sự hỏng.
    if not text.startswith("---"):
        m = re.search(r"(?m)^---\s*$", text)
        if not m:
            return None, dt, f"{INFRA}không tìm thấy frontmatter (---)"
        text = text[m.start():]
    problems = validate_page(scope, text, ROOT)
    if problems:
        where = dump_rejected(name, text)
        return None, dt, f"GATE 2/WIKI chặn: {'; '.join(problems)} — bản bị từ chối: {where}"
    return text + "\n", dt, None


def main():
    contract = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    schema = (ROOT / "schema.yml").read_text(encoding="utf-8")
    docs = load_docs()
    plan = None
    if "--plan" in sys.argv:
        plan_path = Path(sys.argv[sys.argv.index("--plan") + 1])
        if not plan_path.is_absolute():
            plan_path = ROOT / plan_path
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    write_pages = set(plan.get("page_actions", {}).get("write", [])) if plan else None

    force_pages = set()
    if "--fresh-page" in sys.argv:
        raw_pages = sys.argv[sys.argv.index("--fresh-page") + 1]
        for value in raw_pages.split(","):
            value = value.strip()
            if not value:
                continue
            force_pages.add(value if value.startswith("wiki/sources/")
                            else f"wiki/sources/{value}")

    if "--all" in sys.argv:
        targets = [k for k, d in docs.items() if d.get("page_type") == "source"]
    elif "--doc" in sys.argv:
        targets = [sys.argv[sys.argv.index("--doc") + 1]]
    else:
        sys.exit(__doc__)
    # Resume is the safe default: only current, gate-validated pages with the
    # same doc/version/raw provenance are reused.  ``--fresh`` is explicit
    # when a prompt/model change should regenerate every page; ``--fresh-page``
    # forces only named page paths and safely reuses the rest.
    reuse_rejected = "--fresh" not in sys.argv

    (ROOT / "wiki/sources").mkdir(parents=True, exist_ok=True)
    tot = 0.0
    done = []
    for doc_id in targets:
        if doc_id not in docs:
            print(f"{R}✗{OFF} {doc_id}: không có trong extract/van-docs.yml")
            continue
        page_rel = f"wiki/sources/{doc_id}.md"
        if write_pages is not None and page_rel not in write_pages:
            print(f"{D}↷{OFF} {doc_id}: page không impacted, giữ nguyên")
            continue
        pages, dt, err = ingest_one(
            doc_id, docs[doc_id], contract, schema, reuse_rejected=reuse_rejected,
            force_pages=force_pages)
        tot += dt
        if err:
            print(f"{R}✗{OFF} {doc_id:20s} {dt:5.1f}s  {err}")
            continue
        # Ghi TẤT CẢ hoặc KHÔNG GHI GÌ: một tài liệu nửa trang tổng quan mới, nửa trang
        # chương cũ là một kho tự mâu thuẫn. Lỗi ở trên đã `continue` trước khi tới đây.
        for rel, text in pages:
            (ROOT / rel).write_text(text, encoding="utf-8")
        done.append(doc_id)
        chars = sum(len(text) for _, text in pages)
        extra = f" (+{len(pages) - 1} trang chương)" if len(pages) > 1 else ""
        print(f"{G}✓{OFF} {doc_id:20s} {dt:5.1f}s  {chars:6d} ký tự → "
              f"wiki/sources/{doc_id}.md{extra}")

    # Stage 4 (phần cuối, CLAUDE.md §4): đồng bộ index.md + append log.md — bằng MÁY.
    if done:
        build_index.build()
        build_index.append_log(done, "Stage 4 WIKI-INGEST (source VĂN)")
        print(f"{D}→ cập nhật wiki/index.md + wiki/log.md ({len(done)} trang){OFF}")
    print(f"\n{len(targets)} trang · {tot:.0f}s")
    print(f"{D}-> chạy `python3 scripts/lint.py` (Gate 3a) trước khi tin.{OFF}")


if __name__ == "__main__":
    main()
