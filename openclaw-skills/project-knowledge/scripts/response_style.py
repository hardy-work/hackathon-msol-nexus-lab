#!/usr/bin/env python3
"""Cổng văn phong tối thiểu cho output Project Knowledge.

Đây không chấm văn chương. Nó bắt các lỗi làm chatbot demo mất tin cậy: câu trả
lời rỗng, lẫn trace/ANSI, câu ``not_in_kb`` lại khẳng định phủ định, hoặc câu có
dữ liệu nhưng không có citation. LLM tier 3 và output tất định dùng chung cổng.
"""
from __future__ import annotations

import re


NOT_FOUND_MARKERS = (
    "không tìm thấy", "không thấy", "kho không biết", "kho chưa có",
    "không thể", "không phải câu hỏi", "yêu cầu ghi/cập nhật",
)
NEGATIVE_MARKERS = ("không", "chưa", "0 task", "0 công việc")
UNCERTAINTY_MARKERS = ("có thể", "hình như", "có lẽ", "tôi đoán", "probably")


def check_style(status: str, answer: str, citations: list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Trả danh sách lỗi văn phong/contract; rỗng là đạt."""
    text = str(answer or "").strip()
    low = text.lower()
    cites = list(citations or [])
    problems: list[str] = []
    if not text:
        problems.append("answer rỗng")
        return problems
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        problems.append("answer chứa control character")
    if "\x1b[" in text:
        problems.append("answer chứa ANSI escape")
    if re.search(r"\b(?:traceback|todo|undefined|nan)\b", low):
        problems.append("answer chứa dấu vết runtime")
    if len(text.splitlines()) > 8:
        problems.append("answer quá dài cho chat demo")
    if status == "in_kb":
        if not cites:
            problems.append("in_kb thiếu citation")
        if any(marker in low for marker in UNCERTAINTY_MARKERS):
            problems.append("in_kb dùng từ ngập ngừng")
    elif status == "not_in_kb":
        if "chắc chắn không" in low or "không ai" in low:
            problems.append("not_in_kb lấn sang phủ định chắc chắn")
        if not any(marker in low for marker in NOT_FOUND_MARKERS):
            problems.append("not_in_kb thiếu câu báo không tìm thấy/thiếu dữ liệu")
    elif status == "confident_no":
        if not any(marker in low for marker in NEGATIVE_MARKERS):
            problems.append("confident_no thiếu kết luận phủ định")
    return problems


if __name__ == "__main__":
    cases = [
        ("in_kb", "Có: **BE**.", ["raw/nexus-config.md"], []),
        ("not_in_kb", "Không tìm thấy thông tin này trong kho.", [], []),
        ("confident_no", "Không. Người này có 0 task.", ["raw/nexus-people.md"], []),
        ("not_in_kb", "Chắc chắn không có.", [], [
            "not_in_kb lấn sang phủ định chắc chắn",
            "not_in_kb thiếu câu báo không tìm thấy/thiếu dữ liệu",
        ]),
        ("in_kb", "Có thể là BE.", ["raw/nexus-config.md"], ["in_kb dùng từ ngập ngừng"]),
    ]
    failed = 0
    for status, answer, cites, expected in cases:
        got = check_style(status, answer, cites)
        ok = got == expected
        failed += not ok
        print(f"{'✓' if ok else '✗'} {status}: {got or 'OK'}")
    raise SystemExit(failed)
