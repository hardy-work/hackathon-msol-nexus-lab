#!/usr/bin/env python3
"""STAGE 2 (luồng VĂN) — EXTRACT tài liệu văn xuôi .docx / .pdf.

  originals/*.docx|*.pdf  --[ extract/van-docs.yml ]-->  raw/<doc_id>.md

Song song với `extract.py` (luồng SỐ, .xlsx). Khác biệt cốt lõi:
  - Luồng SỐ: khai đích danh ô/cột -> raw/*.md + raw/*.facts.json (MEASURE truy được).
  - Luồng VĂN: nuốt TRỌN văn bản verbatim -> raw/<doc_id>.md (prose). KHÔNG sinh
    .facts.json ở đây; số trong văn xuôi do LLM sao ở Stage 4 (facts:{value,unit,src}).

Nguyên tắc GIỮ NGUYÊN của tầng 2: trích verbatim, KHÔNG sửa/làm tròn/bỏ bớt. Dọn văn
mạch lạc là việc của Stage 3 (STRUCTURE, cần LLM) — và ngay cả ở đó cũng CẤM đụng số.

Định tuyến theo đuôi (node gd1):
  .docx -> python-docx (đoạn + bảng->markdown)
  .pdf  -> pymupdf. Nếu <100 ký tự/trang -> coi là SCAN -> HALT, đòi OCR (nhánh hScan).

Provenance ghi vào frontmatter: doc_id · sha256 · extractor · lang · nguồn. KHÔNG ghi
mốc thời gian (giữ tính tái lập byte: xoá raw/ dựng lại y hệt — sha256 là neo bất biến).

  python3 scripts/extract_van.py                       # trích mọi doc (PDF scan chỉ CẢNH BÁO)
  python3 scripts/extract_van.py --doc chinh-sach-attt # một doc
  python3 scripts/extract_van.py --ocr                 # OCR tesseract (nhanh, kém với tiếng Việt)
  python3 scripts/extract_van.py --ocr-vision          # đọc bằng mô hình thị giác, 2 lượt đối chiếu
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which

import yaml
from document_registry import current as current_document
from artifact_paths import artifact_path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
R, G, Y, D, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"

SCAN_CHARS_PER_PAGE = 100   # dưới ngưỡng này = PDF ảnh, cần OCR


class Halt(Exception):
    """Gate/định tuyến chặn: dừng, báo người."""


class NeedOCR(Exception):
    """PDF là ảnh scan — phải qua nhánh OCR trước khi vào luồng VĂN."""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------- .docx
def extract_docx(path):
    """python-docx: giữ thứ tự đoạn; bảng -> markdown. Trả (body, meta)."""
    import docx
    from docx.document import Document as _Doc
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))

    def iter_block_items(parent):
        """Đi theo ĐÚNG THỨ TỰ tài liệu: đoạn và bảng xen kẽ (docx.paragraphs bỏ mất
        vị trí tương đối của bảng)."""
        body = parent.element.body
        for child in body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    lines, npar, ntab = [], 0, 0
    for blk in iter_block_items(doc):
        if isinstance(blk, Paragraph):
            t = blk.text.strip()
            if t:
                lines.append(t)
                npar += 1
        else:  # Table -> markdown, verbatim
            ntab += 1
            rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in blk.rows]
            if not rows:
                continue
            w = len(rows[0])
            lines.append("")
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("|" + "---|" * w)
            for r in rows[1:]:
                lines.append("| " + " | ".join(r) + " |")
            lines.append("")
    return "\n".join(lines), {"extractor": "python-docx", "paragraphs": npar, "tables": ntab}


# ---------------------------------------------------------------- .pdf
def extract_pdf(path):
    """pymupdf: text từng trang, chèn marker [[page N]]. <100 ký tự/trang -> SCAN."""
    import fitz
    doc = fitz.open(str(path))
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    total = sum(len(t) for t in pages)
    per_page = total / max(doc.page_count, 1)
    if per_page < SCAN_CHARS_PER_PAGE:
        raise NeedOCR(
            f"{doc.page_count} trang, {total} ký tự text ({per_page:.0f}/trang < "
            f"{SCAN_CHARS_PER_PAGE}) → PDF ẢNH. Cần OCR (ocrmypdf + tesseract -l vie) "
            f"rồi trích lại. Không ghi raw/ rỗng.")
    lines = []
    for i, t in enumerate(pages, 1):
        lines.append(f"[[page {i}]]")
        lines.append(t.strip())
        lines.append("")
    return "\n".join(lines), {"extractor": "pymupdf", "pages": doc.page_count}


# ---------------------------------------------------------------- OCR
# Nhánh hScan của sơ đồ. Ta KHÔNG dùng ocrmypdf (nó bắt buộc Ghostscript, chỉ để
# tạo PDF text-layer — thứ ta không cần). Cần TEXT thì render trang bằng pymupdf rồi
# đưa thẳng qua tesseract. Kết quả đánh dấu ocr: true → Stage 4 CẤM dùng làm số verbatim
# (OCR là bản ĐOÁN, không nguyên văn — node "LUẬT OCR").
#
# OCR là bước OPT-IN (--ocr), KHÔNG nằm trong run_all mặc định: nó chậm (render+OCR
# từng trang) và KHÔNG tất định (phụ thuộc phiên bản/model tesseract) — nên không thuộc
# cam kết "xoá raw/ dựng lại y hệt". Chạy có chủ đích, xem lại kết quả trước khi tin.


def find_tesseract():
    exe = which("tesseract") or (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists() else None)
    tessdata = os.environ.get("TESSDATA_PREFIX")
    if not tessdata:
        ud = Path(os.path.expanduser("~")) / "AppData/Local/tessdata"
        if (ud / "vie.traineddata").exists():
            tessdata = str(ud)
    return exe, tessdata


def ocr_pdf(path, lang="vie+eng", dpi=300):
    """Render mỗi trang -> PNG -> tesseract. Chèn marker [[page N]]. meta ocr=True."""
    import fitz
    exe, tessdata = find_tesseract()
    if not exe:
        raise Halt("cần OCR nhưng không thấy tesseract — cài rồi chạy lại "
                   "(hoặc đặt TESSDATA_PREFIX cho gói ngôn ngữ)")
    doc = fitz.open(str(path))
    lines = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(doc.page_count):
            png = str(Path(td) / f"p{i}.png")
            doc[i].get_pixmap(dpi=dpi).save(png)
            cmd = [exe, png, "stdout", "-l", lang]
            if tessdata:
                cmd += ["--tessdata-dir", tessdata]
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            lines.append(f"[[page {i + 1}]]")
            lines.append((out.stdout or "").strip())
            lines.append("")
    return "\n".join(lines), {"extractor": f"tesseract-ocr ({lang}, {dpi}dpi)",
                              "pages": doc.page_count, "ocr": True}


# -------------------------------------------------- OCR bằng mô hình thị giác
# Vì sao cần nhánh này. Trên một bản nội quy lao động scan (38 trang, ~125 DPI, chữ
# in rõ, người đọc được ngay) tesseract vẫn:
#   · giết dấu tiếng Việt hàng loạt — 'giờ'→'gid', 'lần'→'lan', 'cộng dồn'→'cộng d6n'
#   · đọc sai chữ số trên một dòng hoàn toàn sạch — '365 ngày' thành '385 ngày'
# Không cách xử lý ảnh nào cứu được (600dpi, nhị phân hoá, tăng tương phản, làm nét,
# đổi psm — bảy biến thể, không cái nào ra '365'). Hỏng dấu làm đơn vị không nhận diện
# được, nên số đo quan trọng nhất của tài liệu biến mất khỏi mọi cổng; hỏng chữ số thì
# không cổng nào phía sau bắt được vì sai nằm ở NGUỒN.
#
# Đọc bằng mô hình thị giác lấy đúng '365' và đủ dấu. Nhưng nó vẫn là bản ĐOÁN, nên
# LUẬT OCR giữ nguyên: meta['ocr']=True, số ở đây CẤM thành facts. Cái nó thay đổi là
# chất lượng bản đoán — từ mức phải vứt lên mức người duyệt được.
#
# HAI LƯỢT ĐỌC ĐỘC LẬP. Một mô hình đọc ảnh vẫn có thể sai. Chạy hai lượt riêng rồi
# đối chiếu: khác nhau về câu chữ thì bỏ qua (cách xuống dòng, khoảng trắng), nhưng
# khác nhau về BẤT KỲ CHỮ SỐ NÀO thì đánh dấu trang đó cần người xem. Đây là điều kiện
# yếu hơn "đúng" nhưng kiểm được: hai lượt độc lập cùng sai y hệt một chữ số là hiếm,
# còn hai lượt lệch nhau thì chắc chắn có ít nhất một lượt sai.
VISION_DPI = 200
VISION_WORKERS = 4
VISION_TIMEOUT = 300

VISION_PROMPT = """Đọc ảnh page.png trong thư mục hiện tại và chép lại TOÀN BỘ văn bản trên trang.

LUẬT CỨNG:
- Chép NGUYÊN XI: đủ dấu tiếng Việt, đúng từng chữ số, đúng từng dấu câu.
- Không sửa lỗi chính tả, không chuẩn hoá, không suy luận nội dung còn thiếu.
- Không tóm tắt, không bỏ header/footer, không bỏ số thứ tự khoản.
- Giữ đúng thứ tự dòng như trên trang. Bảng thì chép thành dòng, giữ đủ ô.
- Chỉ trả văn bản của trang. Không lời dẫn, không nhận xét, không code fence.
"""

VISION_DIGITS = re.compile(r"\d")


def _vision_read_page(png_dir):
    import models

    proc = subprocess.run(
        [models.CLAUDE, "-p", "--model", models.LIGHT, "--allowedTools", "Read"],
        input=VISION_PROMPT, capture_output=True, text=True, encoding="utf-8",
        timeout=VISION_TIMEOUT, cwd=png_dir,
    )
    if proc.returncode != 0:
        raise Halt(f"đọc ảnh lỗi: {(proc.stderr or '').strip()[:200]}")
    return re.sub(r"^```\w*\n|\n```$", "", (proc.stdout or "").strip()).strip()


def _digits_of(text):
    """Chuỗi mọi chữ số theo thứ tự — chữ ký số học của một trang."""
    return "".join(VISION_DIGITS.findall(text))


def _vision_one_page(args):
    index, page, dpi = args
    with tempfile.TemporaryDirectory(prefix="pkvis-") as td:
        # Thư mục làm việc chỉ chứa ĐÚNG một ảnh: model được cấp Read nhưng không có
        # gì khác trong tầm với. Nó không thấy corpus, không thấy trang khác.
        page.get_pixmap(dpi=dpi).save(str(Path(td) / "page.png"))
        first = _vision_read_page(td)
        second = _vision_read_page(td)
    agree = _digits_of(first) == _digits_of(second)
    return index, first, second, agree


def ocr_pdf_vision(path, dpi=VISION_DPI, workers=VISION_WORKERS):
    """Đọc PDF scan bằng mô hình thị giác, hai lượt độc lập, đối chiếu chữ số."""
    from concurrent.futures import ThreadPoolExecutor

    import fitz

    doc = fitz.open(str(path))
    jobs = [(i, doc[i], dpi) for i in range(doc.page_count)]
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, first, second, agree in pool.map(_vision_one_page, jobs):
            results[index] = (first, second, agree)
    lines, divergent = [], []
    for i in range(doc.page_count):
        first, _second, agree = results[i]
        if not agree:
            divergent.append(i + 1)
        lines += [f"[[page {i + 1}]]", first, ""]
    meta = {"extractor": f"vision-2pass ({models_light()}, {dpi}dpi)",
            "pages": doc.page_count, "ocr": True}
    if divergent:
        meta["vision_divergent_pages"] = divergent
    return "\n".join(lines), meta


def models_light():
    import models

    return models.LIGHT


# ------------------------------------------------------------- ghi raw
ROUTER = {".docx": extract_docx, ".pdf": extract_pdf}


def write_raw(doc_id, spec, body, meta, registry):
    src = Path(spec["original"])
    fm = [
        "---",
        f"raw_id: {doc_id}",
        f"doc_id: {doc_id}",
        f"version: {int(registry['version'])}",
        "kind: van",
        f"source_file: {spec['original']}",
        f"sha256: {sha256(ROOT / spec['original'])}",
        f"extractor: {meta['extractor']}",
        f"lang: {spec.get('lang', 'vi')}",
        f"page_type: {spec.get('page_type', 'source')}",
    ]
    for k in ("pages", "paragraphs", "tables"):
        if k in meta:
            fm.append(f"{k}: {meta[k]}")
    if meta.get("ocr"):
        fm.append("ocr: true   # OCR = bản ĐOÁN. Số ở đây CẤM làm verbatim ở Stage 4.")
    if meta.get("vision_divergent_pages"):
        pages = ", ".join(str(n) for n in meta["vision_divergent_pages"])
        fm.append(f"vision_divergent_pages: [{pages}]"
                  "   # hai lượt đọc lệch CHỮ SỐ — cần người đối chiếu bản gốc")
    if spec.get("title"):
        fm.append(f'title: "{spec["title"]}"')
    fm += [
        "generated_by: scripts/extract_van.py",
        "# TẦNG 2 — MÁY SINH. KHÔNG SỬA TAY. Đổi thì sửa extract/van-docs.yml rồi chạy lại.",
        "---",
        "",
        f"# {spec.get('title', doc_id)}",
        f"\nNguồn: `{src.name}` ({meta['extractor']})\n",
        body,
        "",
    ]
    out = artifact_path(ROOT, registry, doc_id, "md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(fm), encoding="utf-8")
    return out


def main(argv):
    spec = yaml.safe_load((ROOT / "extract/van-docs.yml").read_text(encoding="utf-8"))
    RAW.mkdir(exist_ok=True)
    only = argv[argv.index("--doc") + 1] if "--doc" in argv else None

    made, halted = 0, 0
    for d in spec["docs"]:
        doc_id = d["doc_id"]
        if only and doc_id != only:
            continue
        try:
            registry = current_document(doc_id, ROOT)
        except (KeyError, ValueError) as exc:
            print(f"{R}✗ {doc_id:20s} chưa đăng ký current version: {exc}{OFF}")
            halted += 1
            continue
        if registry.get("original") != d.get("original"):
            print(f"{R}✗ {doc_id:20s} original lệch documents.yml{OFF}")
            halted += 1
            continue
        path = ROOT / d["original"]
        if not path.exists():
            print(f"{R}✗ {doc_id:20s} thiếu file: {d['original']}{OFF}"); halted += 1; continue
        fn = ROUTER.get(path.suffix.lower())
        if not fn:
            print(f"{R}✗ {doc_id:20s} đuôi {path.suffix} chưa hỗ trợ{OFF}"); halted += 1; continue
        try:
            body, meta = fn(path)
        except NeedOCR as e:
            # OCR chạy MỘT LẦN, lưu text vào ocr/<doc_id>.ocr.txt (có commit). Rebuild
            # đọc lại nó TẤT ĐỊNH (khớp flow ocr→exVan) — nhờ vậy raw/ của tài liệu scan
            # vẫn dựng lại được sau `run_all` mà KHÔNG phải OCR lại (chậm/không tất định).
            cached = ROOT / "ocr" / f"{doc_id}.ocr.txt"
            sidecar = ROOT / "ocr" / f"{doc_id}.ocr.json"
            if cached.exists():
                body = cached.read_text(encoding="utf-8")
                meta = {"extractor": "OCR đã lưu (ocr/)",
                        "pages": len(re.findall(r"\[\[page \d+\]\]", body)), "ocr": True}
                # Cảnh báo lệch hai lượt phải sống sót qua rebuild: nó là lý do người
                # phải đối chiếu bản gốc, và mất nó thì raw/ trông sạch hơn sự thật.
                if sidecar.exists():
                    meta.update(json.loads(sidecar.read_text(encoding="utf-8")))
            elif "--ocr-vision" in argv:
                print(f"{D}  {doc_id}: đọc {path.name} bằng thị giác, 2 lượt "
                      f"({e.args[0].split(',')[0]})…{OFF}")
                body, meta = ocr_pdf_vision(path)
                cached.parent.mkdir(exist_ok=True)
                cached.write_text(body, encoding="utf-8")
                sidecar.write_text(json.dumps(
                    {"extractor": meta["extractor"],
                     "vision_divergent_pages": meta.get("vision_divergent_pages", [])},
                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if meta.get("vision_divergent_pages"):
                    print(f"{Y}  ⚠ hai lượt đọc lệch chữ số ở trang "
                          f"{meta['vision_divergent_pages']} — cần người đối chiếu{OFF}")
            elif "--ocr" in argv:
                print(f"{D}  {doc_id}: OCR {path.name} ({e.args[0].split(',')[0]})…{OFF}")
                body, meta = ocr_pdf(path)
                cached.parent.mkdir(exist_ok=True)
                cached.write_text(body, encoding="utf-8")
            else:
                print(f"{Y}⚠ {doc_id:20s} SCAN, chưa có OCR lưu → cần OCR: {e}{OFF}")
                print(f"{D}   (chạy `extract_van.py --ocr` MỘT LẦN → lưu ocr/, rồi rebuild tự đọc lại){OFF}")
                halted += 1
                continue
        out = write_raw(doc_id, d, body, meta, registry)
        info = " · ".join(f"{k}={meta[k]}" for k in ("pages", "paragraphs", "tables") if k in meta)
        print(f"{G}✓ {doc_id:20s}{OFF} {meta['extractor']:12s} {info:24s} → {out.relative_to(ROOT).as_posix()} "
              f"({len(body)} ký tự)")
        made += 1

    print(f"\n{made} tài liệu VĂN → raw/ · {halted} bỏ qua (thiếu file / cần OCR)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Halt as e:
        print(f"\n{R}✗ HALT — {e}{OFF}", file=sys.stderr)
        sys.exit(1)
