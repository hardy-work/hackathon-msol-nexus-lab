#!/usr/bin/env python3
"""STAGE 4 — WIKI-INGEST bằng LLM, theo hợp đồng CLAUDE.md.

  raw/*.md + CLAUDE.md + schema.yml  --[ claude -p ]-->  wiki/entities/<slug>.md

LLM KHÔNG được cấp quyền ghi file. Nó trả nội dung ra stdout, script này mới ghi.
Một cửa duy nhất, nên LLM không thể lỡ tay sửa `originals/` hay `raw/` — hai tầng
mà hợp đồng cấm chạm. Đây là chỗ v1 làm khác sơ đồ (sơ đồ ghi `--allowedTools Write`),
và làm khác theo hướng chặt hơn.

  python3 scripts/ingest.py --entity qc-lan
  python3 scripts/ingest.py --all
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
import build_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
G, R, D, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"

PROMPT = """Bạn đang thực hiện STAGE 4 (WIKI-INGEST) của hệ thống LLM-wiki.
Nhiệm vụ: viết trang `wiki/entities/{slug}.md` cho một thành viên dự án.

===== HỢP ĐỒNG (CLAUDE.md) =====
{contract}

===== SCHEMA MÁY ĐỌC (schema.yml) =====
{schema}

===== DỮ LIỆU TẦNG 2 (raw/) =====
Đây là toàn bộ dữ liệu bạn được dùng. Không dùng gì ngoài đây.

{raw}

===== NGƯỜI CẦN VIẾT TRANG =====
slug (giá trị DIMENSION `assignee`): {slug}
nhãn gốc trong file: {label}
các nguồn raw/ đã sinh ra người này: {raw_paths}

===== YÊU CẦU =====
1. Trả về ĐÚNG nội dung file markdown, bắt đầu bằng `---`. Không rào ```, không lời dẫn.
   KHÔNG thêm bất kỳ lời bàn/tự kiểm tra/ghi chú nào SAU nội dung trang (không mục
   "Kiểm tra hợp đồng", không "Lưu ý: ... quyền ghi"). Kết thúc ở mục cuối của trang.
2. Frontmatter bắt buộc: page, name, assignee, project, task_count, estimate_h,
   actual_h, raw_paths. Thêm `role` CHỈ KHI suy được từ tiền tố nhãn PIC
   (ví dụ `[QC] LAN` -> QC). Không có tiền tố thì BỎ TRỐNG `role` — không đoán.
3. Ba trường số PHẢI ở dạng con trỏ, đúng cú pháp:
   task_count:   {{ facts_ref: "raw/handy-sprints.facts.json#{slug}.task_count" }}
   estimate_h:   {{ facts_ref: "raw/handy-sprints.facts.json#{slug}.estimate_h" }}
   actual_h:     {{ facts_ref: "raw/handy-sprints.facts.json#{slug}.actual_h" }}
   TUYỆT ĐỐI không gõ con số vào trang. Cả trong thân bài cũng không.
4. Thân bài phải có liên kết `[[handy-schedule-v2-1]]` (liên kết hai chiều).
5. Thân bài cần một mục "## Ghi chú" nhận xét thật về người này dựa trên raw/,
   và một mục "## Phạm vi" nói rõ trang chỉ phủ Sprint 0–7.
6. Nếu người này 0 task: nói rõ đây KHÔNG phải thiếu dữ liệu, mà là căn cứ để
   bậc 1 trả lời "chắc chắn không". Nếu `role` bỏ trống: nói rõ đó LÀ thiếu dữ liệu.
7. Tiếng Việt, gọn.
"""


def load_people():
    d = json.loads((ROOT / "raw/handy-sprints.facts.json").read_text(encoding="utf-8"))
    return d["facts"]


def sprints_of(slug):
    out = []
    for p in sorted((ROOT / "raw").glob("handy-sprint[0-9].facts.json")):
        if slug in json.loads(p.read_text(encoding="utf-8"))["facts"]:
            out.append(f"raw/{p.name.replace('.facts.json', '.md')}")
    return out


def ingest_one(slug, info, contract, schema, timeout=300):
    raw_paths = ["raw/handy-config.md"] + sprints_of(slug) + ["raw/handy-sprints.md"]
    # Chỉ đưa NHỮNG DÒNG của người này. Đưa cả bảng 283 dòng làm prompt phồng lên
    # ~50 KB và claude -p vượt timeout. Lọc trước cũng đúng về nguyên tắc:
    # trang của một người không cần thấy task của người khác.
    chunks = []
    for rp in raw_paths:
        txt = (ROOT / rp).read_text(encoding="utf-8")
        if re.match(r"raw/handy-sprint\d\.md", rp):
            keep = [ln for ln in txt.splitlines()
                    if ln.startswith("| dòng") or set(ln) <= set("|- ")
                    or info["label"] in ln]
            txt = "\n".join(keep[:60])
        chunks.append(f"--- {rp} ---\n{txt[:4000]}")
    raw_text = "\n\n".join(chunks)
    prompt = PROMPT.format(slug=slug, label=info["label"], contract=contract,
                           schema=schema, raw=raw_text, raw_paths=raw_paths)
    t0 = time.time()
    # prompt qua STDIN, KHÔNG qua argv: Windows giới hạn dòng lệnh ~32KB, prompt kèm
    # raw/ dễ vượt -> WinError 206. stdin không có trần đó. encoding utf-8 cho tiếng Việt.
    out = subprocess.run([models.CLAUDE, "-p", "--model", models.HEAVY,
                          "--allowedTools", ""],
                         input=prompt, capture_output=True, text=True,
                         encoding="utf-8", timeout=timeout, cwd=ROOT)
    dt = time.time() - t0
    if out.returncode != 0:
        return None, dt, out.stderr.strip()[:200]
    text = out.stdout.strip()
    text = re.sub(r"^```(?:markdown|yaml)?\n|\n```$", "", text).strip()
    # Output LLM không tất định: đôi khi thêm lời dẫn trước frontmatter -> cắt từ '---' đầu.
    if not text.startswith("---"):
        m = re.search(r"(?m)^---\s*$", text)
        if not m:
            return None, dt, "không tìm thấy frontmatter (---)"
        text = text[m.start():]
    # raw_paths là MÁY BIẾT (tính ở trên) — KHÔNG tin LLM chép lại: nó hay viết tắt
    # danh sách bằng '…' ("sprint0.md … sprint6.md") -> lint-refs đỏ vì file không tồn tại.
    # Ghi đè bằng danh sách chuẩn. `-[ \t]+` (dash + khoảng trắng) để không nuốt '---'.
    block = "raw_paths:\n" + "".join(f"  - {p}\n" for p in raw_paths)
    text = re.sub(r"raw_paths:\n(?:[ \t]*-[ \t]+\S.*\n)+", block, text, count=1)
    return text + "\n", dt, None


def main():
    contract = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    schema = (ROOT / "schema.yml").read_text(encoding="utf-8")
    people = load_people()

    if "--all" in sys.argv:
        targets = list(people)
    elif "--entity" in sys.argv:
        targets = [sys.argv[sys.argv.index("--entity") + 1]]
    else:
        sys.exit(__doc__)

    tot = 0.0
    done = []
    for slug in targets:
        if slug not in people:
            print(f"{R}✗{OFF} {slug}: không có trong raw/handy-sprints.facts.json")
            continue
        text, dt, err = ingest_one(slug, people[slug], contract, schema)
        tot += dt
        if err:
            print(f"{R}✗{OFF} {slug:10s} {dt:5.1f}s  {err}")
            continue
        (ROOT / "wiki/entities" / f"{slug}.md").write_text(text, encoding="utf-8")
        done.append(slug)
        # chỉ soi số ĐO LƯỜNG. Bỏ v2.1 (phiên bản), §5.3 (mục), Sprint 0-7, ô Excel.
        clean = re.sub(r"facts_ref[^}]*}|v\d[\d.]*|§[\d.]+|[A-Z]+\d+(?::[A-Z]+\d+)?", "", text)
        nums = re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?\s*(?:h|giờ|task|%)", clean)
        flag = f"  {R}⚠ có số gõ tay: {nums}{OFF}" if nums else ""
        print(f"{G}✓{OFF} {slug:10s} {dt:5.1f}s  {len(text):5d} ký tự{flag}")

    # Stage 4 (phần cuối, CLAUDE.md §4): đồng bộ index.md + append log.md — bằng MÁY.
    if done:
        build_index.build()
        build_index.append_log(done, "Stage 4 WIKI-INGEST (entity)")
        print(f"{D}→ cập nhật wiki/index.md + wiki/log.md ({len(done)} trang){OFF}")
    print(f"\n{len(targets)} trang · {tot:.0f}s · {tot / max(len(targets), 1):.0f}s/trang")
    print(f"{D}-> chạy `python3 scripts/lint.py` (Gate 3a) trước khi tin.{OFF}")


if __name__ == "__main__":
    main()
