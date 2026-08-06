#!/usr/bin/env python3
"""Chính sách MODEL của dự án — MỘT chỗ khai, mọi script gọi claude dùng chung.

Do chủ dự án quy định:
  - Việc NẶNG  (sinh nội dung, suy luận kỹ theo hợp đồng) -> Opus 4.8
  - Gate 3b REVIEW khi chạy Claude Pro                                  -> Sonnet 5
  - Việc NHẸ   (tổng hợp câu trả lời ngắn, dựng lại văn mạch lạc)        -> Sonnet
  - Việc RẺ    (định tuyến, phân loại nhanh)                            -> Haiku

Đổi chính sách thì sửa ĐÚNG file này. KHÔNG rải model id ra từng script.
"""

import os
import shutil
from pathlib import Path

# Claude Code supports the short aliases below and resolves them to the
# currently available model family.  Deployments may pin exact IDs through
# environment variables when they need reproducibility.
HEAVY = os.getenv("PROJECT_KNOWLEDGE_HEAVY_MODEL", "opus")

# Nhẹ: tổng hợp câu trả lời bậc 3 (answer.py), Stage 3 STRUCTURE (khi dựng luồng VĂN).
LIGHT = os.getenv("PROJECT_KNOWLEDGE_SONNET_MODEL", "sonnet")

# Gate 3b: review nội dung wiki bằng Sonnet khi chạy Claude Code subscription.
REVIEW = os.getenv("PROJECT_KNOWLEDGE_REVIEW_MODEL", LIGHT)

# Rẻ: định tuyến / phân loại query trước khi chọn retrieval tier.
CHEAP = os.getenv("PROJECT_KNOWLEDGE_HAIKU_MODEL", "haiku")


# ---------------------------------------------------------------------------
# Phân giải đường dẫn tới `claude` chạy được.
# Trên Windows, npm đặt shim `claude.CMD`/`.ps1` trên PATH, nhưng Python subprocess
# chỉ tìm `.exe` -> ["claude", ...] báo FileNotFoundError. Binary THẬT nằm trong
# node_modules cạnh shim. Trên POSIX `claude` là binary chạy thẳng được.
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
