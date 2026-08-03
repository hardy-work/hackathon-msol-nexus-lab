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
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402
import numeric_guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
STRUCTURED = ROOT / "structured"

PROMPT = """Bạn thực hiện Stage 3 STRUCTURE của LLM Wiki.
Chỉ tổ chức lại văn bản raw dưới đây thành Markdown mạch lạc.

LUẬT CỨNG:
- Không thêm thông tin, không suy luận, không tóm tắt làm mất điều kiện.
- Giữ nguyên mọi số, ngày, đơn vị và số hiệu; không làm tròn hoặc đổi đơn vị.
- Giữ marker nguồn như [[page N]] và tiêu đề/bảng khi có.
- Chỉ trả Markdown nội dung, không frontmatter, không lời dẫn, không code fence.

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
        if fm.get("kind") == "van":
            docs[str(fm.get("doc_id") or path.stem)] = path
    return docs


def structure_one(doc_id: str, raw_path: Path, timeout: int = 600) -> tuple[str | None, list[str], list[str]]:
    raw_text = raw_path.read_text(encoding="utf-8")
    fm, body = frontmatter(raw_text)
    proc = subprocess.run(
        [models.CLAUDE, "-p", "--model", models.LIGHT, "--allowedTools", ""],
        input=PROMPT.format(body=body), capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, cwd=ROOT,
    )
    if proc.returncode != 0:
        return None, [f"Claude lỗi: {(proc.stderr or '').strip()[:240]}"], []
    output = re.sub(r"^```(?:markdown)?\n|\n```$", "", (proc.stdout or "").strip()).strip()
    errors, warnings = numeric_guard.check_transform(body, output)
    if errors:
        return None, errors, warnings
    header = {
        "doc_id": doc_id,
        "version": fm.get("version", 1),
        "raw_path": raw_path.relative_to(ROOT).as_posix(),
        "source_sha256": fm.get("sha256"),
        "generated_by": "scripts/structure.py",
    }
    return "---\n" + yaml.safe_dump(header, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + output + "\n", [], warnings


def verify_one(doc_id: str, raw_path: Path, structured_path: Path) -> tuple[list[str], list[str]]:
    _, raw_body = frontmatter(raw_path.read_text(encoding="utf-8"))
    _, structured_body = frontmatter(structured_path.read_text(encoding="utf-8"))
    return numeric_guard.check_transform(raw_body, structured_body)


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
