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
"""
import re
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


def load_docs():
    spec_path = ROOT / "extract/van-docs.yml"
    if not spec_path.exists():
        return {}
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return {d["doc_id"]: d for d in spec["docs"]}


def ingest_one(doc_id, d, contract, schema, timeout=600):
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
            "   (d) TUYỆT ĐỐI không tự tính/suy ra số mới. Không có số đo đáng khai thì bỏ trống mục này.") \
            .format(doc_id=doc_id, raw_path=raw_path.relative_to(ROOT).as_posix())
    prompt = PROMPT.format(
        doc_id=doc_id, title=d.get("title", doc_id), domain=d["domain"],
        version=int(registry["version"]), visibility=registry.get("visibility", "internal"),
        contract=contract, schema=schema, raw=structured, ocr_note=ocr_note,
        ocr_rule=ocr_rule, facts_rule=facts_rule,
        raw_path=raw_path.relative_to(ROOT).as_posix())

    t0 = time.time()
    out = subprocess.run(
        [models.CLAUDE, "-p", "--model", models.HEAVY, "--allowedTools", ""],
        input=prompt, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, cwd=ROOT)
    dt = time.time() - t0
    if out.returncode != 0:
        return None, dt, (out.stderr or "").strip()[:200]
    text = (out.stdout or "").strip()
    text = re.sub(r"^```(?:markdown|yaml)?\n|\n```$", "", text).strip()
    # Output LLM không tất định: đôi khi thêm lời dẫn trước frontmatter. Cắt từ dòng
    # '---' đầu tiên. Không có '---' nào = thật sự hỏng.
    if not text.startswith("---"):
        m = re.search(r"(?m)^---\s*$", text)
        if not m:
            return None, dt, "không tìm thấy frontmatter (---)"
        text = text[m.start():]
    number_errors, _ = numeric_guard.check_transform(structured, text, allow_loss=True)
    if number_errors:
        return None, dt, "GATE 2/WIKI chặn: " + "; ".join(number_errors)
    return text + "\n", dt, None


def main():
    contract = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    schema = (ROOT / "schema.yml").read_text(encoding="utf-8")
    docs = load_docs()

    if "--all" in sys.argv:
        targets = [k for k, d in docs.items() if d.get("page_type") == "source"]
    elif "--doc" in sys.argv:
        targets = [sys.argv[sys.argv.index("--doc") + 1]]
    else:
        sys.exit(__doc__)

    (ROOT / "wiki/sources").mkdir(parents=True, exist_ok=True)
    tot = 0.0
    done = []
    for doc_id in targets:
        if doc_id not in docs:
            print(f"{R}✗{OFF} {doc_id}: không có trong extract/van-docs.yml")
            continue
        text, dt, err = ingest_one(doc_id, docs[doc_id], contract, schema)
        tot += dt
        if err:
            print(f"{R}✗{OFF} {doc_id:20s} {dt:5.1f}s  {err}")
            continue
        (ROOT / "wiki/sources" / f"{doc_id}.md").write_text(text, encoding="utf-8")
        done.append(doc_id)
        print(f"{G}✓{OFF} {doc_id:20s} {dt:5.1f}s  {len(text):5d} ký tự → wiki/sources/{doc_id}.md")

    # Stage 4 (phần cuối, CLAUDE.md §4): đồng bộ index.md + append log.md — bằng MÁY.
    if done:
        build_index.build()
        build_index.append_log(done, "Stage 4 WIKI-INGEST (source VĂN)")
        print(f"{D}→ cập nhật wiki/index.md + wiki/log.md ({len(done)} trang){OFF}")
    print(f"\n{len(targets)} trang · {tot:.0f}s")
    print(f"{D}-> chạy `python3 scripts/lint.py` (Gate 3a) trước khi tin.{OFF}")


if __name__ == "__main__":
    main()
