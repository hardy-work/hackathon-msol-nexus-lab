#!/usr/bin/env python3
"""STAGE 3 · STRUCTURE for prose documents.

The LLM receives one immutable raw document and returns coherent Markdown. It
has no tools and cannot write files. Before the script writes `structured/`, an
asymmetric numeric gate rejects new/rounded/unit-changed numbers and rejects
loss of a number that had a recognized unit in the source.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
import numeric_guard  # noqa: E402
from artifact_paths import frontmatter_is_current  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
STRUCTURED = ROOT / "structured"

PROMPT = """Bạn thực hiện Stage 3 STRUCTURE của LLM Wiki.
Chỉ tổ chức lại văn bản raw dưới đây thành Markdown mạch lạc.

LUẬT CỨNG:
- Không thêm thông tin, không suy luận, không tóm tắt làm mất điều kiện.
- Giữ nguyên mọi số, ngày, đơn vị và số hiệu; không làm tròn hoặc đổi đơn vị.
- KHÔNG SỬA LỖI NGUỒN. Văn bản raw có thể là kết quả OCR và chứa lỗi thấy rõ: sai
  dấu tiếng Việt, dính số thứ tự khoản, và sai cả chữ số. Chép NGUYÊN XI, kể cả khi
  bạn biết chắc giá trị đúng phải là gì. Sửa lỗi nguồn là việc của người đối chiếu
  bản gốc: cổng số phía sau không phân biệt được "sửa đúng" với "bịa", nên nó chặn cả
  hai như nhau, và một lần bạn sửa đúng sẽ làm hỏng cả tài liệu.
- Giữ marker nguồn như [[page N]] và tiêu đề/bảng khi có. Giữ ĐỦ mọi marker, kể cả
  marker ở ngay dòng đầu — đoạn dưới đây là một PHẦN của tài liệu dài, không phải
  toàn bộ, nên nó thường mở đầu bằng một marker và marker đó phải là dòng đầu tiên
  bạn xuất ra.
- TRANG BÌA, BẢNG KIỂM SOÁT TÀI LIỆU, LỊCH SỬ THAY ĐỔI, MỤC LỤC, chữ ký phê duyệt,
  header/footer đều là NỘI DUNG và phải chép đủ. Chúng trông như phần phụ nhưng lại
  giữ ngày hiệu lực, phiên bản, người phê duyệt và danh mục điều khoản — tức là toàn
  bộ phần truy nguồn của tài liệu. Không được bỏ vì "không phải văn bản chính".
- Đoạn này bị cắt ra giữa chừng nên có thể mở đầu hoặc kết thúc dở một chương/điều.
  Cứ để dở. KHÔNG viết thêm tiêu đề nối kiểu "(tiếp theo)", không lặp lại tiêu đề
  chương của đoạn trước, không thêm phần mở đầu hay kết thúc cho tròn ý.
- Chỉ trả Markdown nội dung, không frontmatter, không lời dẫn, không code fence.
- TUYỆT ĐỐI không viết nhận xét về công việc của chính bạn: không mở đầu, không kết
  luận, không thống kê số dòng, không liệt kê lỗi OCR bạn đã thấy. Ký tự cuối cùng
  bạn xuất ra phải là ký tự cuối cùng của tài liệu. Mọi con số bạn viết thêm ngoài
  tài liệu đều bị cổng ghi nhận là số bịa và cả khúc này sẽ bị vứt.

===== RAW =====
{body}
"""


def frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        return {}, text
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def raw_documents() -> dict[str, Path]:
    docs = {}
    for path in sorted(RAW.glob("*.md")):
        fm, _ = frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("kind") == "van" and frontmatter_is_current(fm, ROOT):
            docs[str(fm.get("doc_id") or path.stem)] = path
    return docs


# Stage 3 chép lại NGUYÊN VĂN cả tài liệu, nên thời gian chạy tỉ lệ với độ dài đầu
# vào chứ không phải một hằng số. Mốc 600s cố định vừa đủ cho vài trang và hết giờ
# ở một bản nội quy 38 trang (94k ký tự) — mà lại hết giờ bằng traceback, sau mười
# phút, không nói gì về nguyên nhân. Cho ngân sách co theo cỡ tài liệu, có sàn và trần.
SECONDS_PER_KCHAR = 12
TIMEOUT_MIN, TIMEOUT_MAX = 600, 3600


def structure_timeout(body: str) -> int:
    return max(TIMEOUT_MIN, min(TIMEOUT_MAX, len(body) // 1000 * SECONDS_PER_KCHAR))


# Stage 3 phải TRẢ LẠI cả tài liệu, nên độ dài đầu ra bằng độ dài đầu vào. Một bản nội
# quy 38 trang (94k ký tự) vượt sức một lượt sinh: model không báo lỗi, nó lặng lẽ rút
# gọn — lượt chạy thật rơi 37 lần số `1`, 17 lần `38` và một loạt số Điều lẻ, tức là mất
# hẳn nhiều điều khoản. Cắt khúc là bắt buộc, không phải tối ưu.
#
# Cắt theo ranh giới trang `[[page N]]` vì đó là ranh giới CÓ THẬT trong nguồn: không
# cắt giữa câu, và marker trang vẫn nằm đúng chỗ sau khi nối lại. Mỗi khúc được soi
# cổng RIÊNG với đúng khúc nguồn của nó — chặt hơn soi cả tài liệu (số rơi ở khúc này
# không thể được bù bằng số trùng giá trị ở khúc khác) và báo lỗi đúng vị trí.
CHUNK_CHARS = 12000
PAGE_MARKER = re.compile(r"^\s*\[\[page \d+\]\]\s*$")


def split_chunks(body: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Cắt body thành khúc <= limit, chỉ cắt ở ranh giới trang (hoặc dòng trống)."""
    lines = body.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        boundary = PAGE_MARKER.match(line) or not line.strip()
        if current and boundary and size >= limit:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    # Không có ranh giới nào để cắt (tài liệu một khối) — trả nguyên, cổng sẽ báo nếu hụt.
    return chunks or [body]


PAGE_REF = re.compile(r"\[\[page (\d+)\]\]")

# Stage 3 dàn lại chứ không tóm tắt, nên độ dài đầu ra phải xấp xỉ đầu vào. Cổng số
# bắt được việc rút gọn ở khúc nhiều số, nhưng một khúc toàn văn xuôi — nghĩa vụ,
# quy tắc ứng xử — có thể mất nửa nội dung mà không rơi con số nào. Ngưỡng đặt rộng
# để không cản việc bỏ header/footer lặp và gộp dòng gãy của OCR.
MIN_LENGTH_RATIO = 0.6


def too_short(before: str, after: str) -> list[str]:
    ratio = len(after) / len(before) if before else 1.0
    if ratio >= MIN_LENGTH_RATIO:
        return []
    return [f"rút gọn còn {ratio:.0%} độ dài nguồn "
            f"({len(after):,}/{len(before):,} ký tự) — Stage 3 dàn lại, không tóm tắt"]


def missing_page_markers(before: str, after: str) -> list[str]:
    """Marker trang là PROVENANCE, không phải số đo — mất là lỗi, nhưng lỗi của nó.

    `numeric_guard` che `[[page N]]` vì số trang không phải số đo (không che thì mỗi
    lần dàn lại trang lại báo "rơi 38"). Che rồi thì không còn ai canh chúng, mà `src`
    của Gate 3a lại trỏ vào đúng những marker này để định vị mục trong raw. Nên canh
    riêng, và báo bằng đúng tên: mất dấu vết nguồn, không phải sai số liệu."""
    lost = sorted(set(PAGE_REF.findall(before)) - set(PAGE_REF.findall(after)), key=int)
    return [f"mất marker trang: {', '.join('[[page ' + n + ']]' for n in lost)}"] if lost else []


# Một tài liệu dài là NHIỀU lượt gọi nối tiếp, nên xác suất vấp một lỗi tạm thời cộng
# dồn theo số khúc. Không thử lại thì một lần CLI trả mã lỗi với stderr rỗng — hoặc trả
# đúng chuỗi rỗng — vứt sạch công của mọi khúc đã chạy xong trước đó. Thử lại chỉ áp
# dụng cho lỗi HẠ TẦNG (gọi hỏng, đầu ra rỗng); cổng số chặn thì KHÔNG thử lại, vì đó
# là kết luận về nội dung chứ không phải sự cố.
RETRIES = 3
RETRY_BACKOFF = 15
NON_RETRYABLE_CLI = (
    "monthly spend limit", "not logged in", "authentication", "unauthorized",
    "invalid api key", "invalid api_key", "permission denied", "credit balance",
)


def _retryable_failure(message: str) -> bool:
    """Retry transient Claude failures, never quota/auth failures."""
    lowered = (message or "").lower()
    return not any(marker in lowered for marker in NON_RETRYABLE_CLI)


def call_with_retry(chunk: str, budget: int, tag: str) -> tuple[str | None, str]:
    last = "không rõ"
    for attempt in range(1, RETRIES + 1):
        try:
            proc = subprocess.run(
                [models.CLAUDE, "-p", "--no-session-persistence", "--model", models.LIGHT, "--tools="],
                input=PROMPT.format(body=chunk), capture_output=True, text=True,
                encoding="utf-8", timeout=budget, cwd=ROOT,
            )
        except subprocess.TimeoutExpired:
            last = f"quá {budget}s cho {len(chunk):,} ký tự"
        else:
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or '').strip()[:200] or 'stderr rỗng'
                last = f"mã lỗi {proc.returncode}: {detail}"
            else:
                piece = re.sub(r"^```(?:markdown)?\n|\n```$", "",
                               (proc.stdout or "").strip()).strip()
                if piece:
                    return piece, ""
                last = "đầu ra rỗng"
        if attempt < RETRIES and _retryable_failure(last):
            print(f"⟳ {tag or 'tài liệu'}: {last} — thử lại {attempt}/{RETRIES - 1}",
                  file=sys.stderr)
            time.sleep(RETRY_BACKOFF * attempt)
        elif attempt < RETRIES:
            break
    return None, f"{tag}: Claude hỏng sau {RETRIES} lần thử — {last}"


def structure_one(doc_id: str, raw_path: Path, timeout: int | None = None) -> tuple[str | None, list[str], list[str]]:
    raw_text = raw_path.read_text(encoding="utf-8")
    fm, body = frontmatter(raw_text)
    chunks = split_chunks(body)
    pieces, errors, warnings = [], [], []
    for index, chunk in enumerate(chunks, start=1):
        tag = f"khúc {index}/{len(chunks)}" if len(chunks) > 1 else ""
        budget = timeout if timeout is not None else structure_timeout(chunk)
        piece, failure = call_with_retry(chunk, budget, tag)
        if piece is None:
            return None, [failure], warnings
        piece_errors, piece_warnings = numeric_guard.check_transform(chunk, piece)
        piece_errors += missing_page_markers(chunk, piece) + too_short(chunk, piece)
        errors += [f"{tag}: {message}" if tag else message for message in piece_errors]
        warnings += [f"{tag}: {message}" if tag else message for message in piece_warnings]
        pieces.append(piece)
    if errors:
        # Cổng chặn thì KHÔNG ghi structured/ — nhưng bản bị từ chối phải xem được, nếu
        # không thì chẩn đoán một danh sách "rơi 5× `1` day" là đoán mò, và cách duy nhất
        # để nhìn là chạy lại cả tài liệu. Ghi vào derived/ vì đây là trạng thái vận hành
        # tái tạo được, không phải artifact của corpus.
        reject_dir = ROOT / "derived/stage3-rejected"
        reject_dir.mkdir(parents=True, exist_ok=True)
        (reject_dir / f"{doc_id}.md").write_text("\n\n".join(pieces), encoding="utf-8")
        errors.append(f"bản bị từ chối: derived/stage3-rejected/{doc_id}.md")
        return None, errors, warnings
    output = "\n\n".join(pieces)
    header = {
        "doc_id": doc_id,
        "version": fm.get("version", 1),
        "raw_path": raw_path.relative_to(ROOT).as_posix(),
        "source_sha256": fm.get("sha256"),
        "generated_by": "scripts/structure.py",
    }
    return "---\n" + yaml.safe_dump(header, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + output + "\n", [], warnings


def validate_source_metadata(doc_id: str, raw_path: Path,
                             structured_path: Path) -> list[str]:
    """Reject a structured artifact produced from another raw/version."""
    raw_fm, _ = frontmatter(raw_path.read_text(encoding="utf-8"))
    structured_fm, _ = frontmatter(structured_path.read_text(encoding="utf-8"))
    errors = []
    if structured_fm.get("doc_id") != doc_id:
        errors.append(f"structured doc_id={structured_fm.get('doc_id')!r} lệch {doc_id!r}")
    if raw_fm.get("version") is not None:
        try:
            if int(structured_fm.get("version")) != int(raw_fm["version"]):
                errors.append("structured version lệch raw version")
        except (TypeError, ValueError):
            errors.append("structured thiếu version hợp lệ")
    source_sha = raw_fm.get("sha256")
    if source_sha and structured_fm.get("source_sha256") != source_sha:
        errors.append("structured source_sha256 lệch raw sha256")
    if not structured_fm.get("source_sha256"):
        errors.append("structured thiếu source_sha256")
    try:
        expected_raw = raw_path.relative_to(ROOT).as_posix()
    except ValueError:
        expected_raw = None
    if expected_raw and structured_fm.get("raw_path") != expected_raw:
        errors.append(f"structured raw_path={structured_fm.get('raw_path')!r} lệch {expected_raw!r}")
    return errors


def verify_one(doc_id: str, raw_path: Path, structured_path: Path) -> tuple[list[str], list[str]]:
    _, raw_body = frontmatter(raw_path.read_text(encoding="utf-8"))
    _, structured_body = frontmatter(structured_path.read_text(encoding="utf-8"))
    metadata_errors = validate_source_metadata(doc_id, raw_path, structured_path)
    numeric_errors, warnings = numeric_guard.check_transform(raw_body, structured_body)
    return metadata_errors + numeric_errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm artifact đã có, không gọi LLM")
    args = parser.parse_args()
    docs = raw_documents()
    targets = list(docs) if args.all else ([args.doc] if args.doc else [])
    if not targets:
        parser.error("cần --doc <doc_id> hoặc --all")
    STRUCTURED.mkdir(exist_ok=True)
    failed = 0
    for doc_id in targets:
        raw_path = docs.get(doc_id)
        if raw_path is None:
            print(f"✗ không có raw prose cho {doc_id}", file=sys.stderr)
            failed += 1
            continue
        out_path = STRUCTURED / f"{doc_id}.md"
        if args.check:
            if not out_path.exists():
                print(f"✗ thiếu {out_path.relative_to(ROOT)}", file=sys.stderr)
                failed += 1
                continue
            errors, warnings = verify_one(doc_id, raw_path, out_path)
            text = None
        else:
            text, errors, warnings = structure_one(doc_id, raw_path)
        for warning in warnings:
            print(f"⚠ {doc_id}: {warning}")
        if errors:
            print(f"✗ {doc_id}: GATE 2/STRUCTURE chặn: {'; '.join(errors)}", file=sys.stderr)
            failed += 1
            continue
        if text is not None:
            out_path.write_text(text, encoding="utf-8")
        print(f"✓ {doc_id}: {out_path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
