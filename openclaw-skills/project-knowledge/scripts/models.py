#!/usr/bin/env python3
"""Chính sách MODEL của dự án — MỘT chỗ khai, mọi script gọi claude dùng chung.

Do chủ dự án quy định:
  - Việc NẶNG  (sinh nội dung, suy luận kỹ theo hợp đồng) -> Opus 4.8
  - Gate 3b REVIEW khi chạy Claude Pro                                  -> Sonnet 5
  - Việc NHẸ   (tổng hợp câu trả lời ngắn, dựng lại văn mạch lạc)        -> Sonnet
  - Việc RẺ    (định tuyến, phân loại nhanh)                            -> Haiku

Đổi chính sách thì sửa ĐÚNG file này. KHÔNG rải model id ra từng script.
"""

# Nặng: Stage 4 WIKI-INGEST (ingest.py). Gate 3b dùng REVIEW để tương thích
# Claude Pro và không ép tài khoản Pro gọi Opus.
HEAVY = "claude-opus-4-8"

# Nhẹ: tổng hợp câu trả lời bậc 3 (answer.py), Stage 3 STRUCTURE (khi dựng luồng VĂN).
LIGHT = "claude-sonnet-5"

# Gate 3b: review nội dung wiki bằng Sonnet 5 khi chạy Claude Code subscription.
REVIEW = "claude-sonnet-5"

# Rẻ: định tuyến / phân loại (chưa dùng ở v1 — để sẵn cho bộ định tuyến bậc RAG).
CHEAP = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Phân giải đường dẫn tới `claude` chạy được.
# Trên Windows, npm đặt shim `claude.CMD`/`.ps1` trên PATH, nhưng Python subprocess
# chỉ tìm `.exe` -> ["claude", ...] báo FileNotFoundError. Binary THẬT nằm trong
# node_modules cạnh shim. Trên POSIX `claude` là binary chạy thẳng được.
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402


def _find_claude():
    exe = shutil.which("claude.exe")
    if exe:
        return exe
    hit = shutil.which("claude")
    if hit and not hit.lower().endswith((".cmd", ".ps1", ".bat")):
        return hit                      # POSIX: 'claude' là binary chạy được
    if hit:                             # Windows shim -> claude.exe thật cạnh nó
        cand = Path(hit).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if cand.exists():
            return str(cand)
    return hit or "claude"              # cùng lắm để subprocess tự thử (báo lỗi rõ)


CLAUDE = _find_claude()
