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
  python3 scripts/extract_van.py --ocr                 # OCR luôn PDF scan (chậm, không tất định)
"""
import hashlib
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
            if cached.exists():
                body = cached.read_text(encoding="utf-8")
                meta = {"extractor": "OCR đã lưu (ocr/)",
                        "pages": len(re.findall(r"\[\[page \d+\]\]", body)), "ocr": True}
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
