#!/usr/bin/env python3
"""Cheap query router for the Project Knowledge retrieval pipeline.

Haiku is deliberately used only as a classifier.  It never writes facts and it
never produces the user-facing answer.  A failed/invalid model call returns a
safe ``fallback`` decision so the deterministic + keyword path remains usable
offline.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

import models


ROUTES = {
    "structured",   # facts/DuckDB first
    "document",     # wiki/keyword retrieval
    "semantic",     # BGE-M3 retrieval
    "graph",        # relationship/multi-hop retrieval
    "open",         # retrieval followed by Sonnet synthesis
    "action",       # approval/action skill hand-off
    "unsupported",  # likely outside the committed corpus
}

ROUTER_PROMPT = """Bạn là bộ định tuyến rẻ cho Project Knowledge Nexus.
Chỉ phân loại câu hỏi, KHÔNG trả lời câu hỏi và KHÔNG suy đoán dữ liệu.

Chọn đúng một route:
- structured: hỏi task, người, role, sprint, effort, status, priority, ngày, số liệu
- document: hỏi nội dung một sheet/tài liệu hoặc cần đọc wiki
- semantic: câu hỏi diễn đạt khác từ dữ liệu, cần tìm theo ngữ nghĩa
- graph: hỏi quan hệ nhiều bước giữa task, người, sprint, role, milestone,
  dependency hoặc ảnh hưởng; dùng graph.json trước khi đưa context cho LLM
- open: câu hỏi vì sao, đánh giá, tổng hợp nhiều nguồn; sau đó Sonnet mới trả lời
- action: yêu cầu tạo/sửa/cập nhật/log dữ liệu; phải chuyển sang approval skill
- unsupported: rõ ràng nằm ngoài phạm vi kho Nexus hiện tại

Trả DUY NHẤT JSON hợp lệ, không markdown:
{{"route":"structured|document|semantic|graph|open|action|unsupported","
"confidence":0.0,"reason":"..."}}

CÂU HỎI: {query}
"""


@dataclass(frozen=True)
class Decision:
    route: str
    confidence: float
    reason: str
    source: str = "haiku"
    error: str = ""


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _json_object(text: str) -> dict[str, object] | None:
    """Parse strict JSON, tolerating a short explanatory wrapper from the CLI."""
    text = (text or "").strip()
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_response(text: str) -> Decision | None:
    """Validate a model response before it can influence routing."""
    data = _json_object(text)
    if not data:
        return None
    route = str(data.get("route", "")).strip().lower()
    if route not in ROUTES:
        return None
    return Decision(
        route=route,
        confidence=_clamp_confidence(data.get("confidence")),
        reason=str(data.get("reason", "")).strip()[:300],
    )


def heuristic_route(query: str) -> Decision:
    """Offline safety hint used only when Haiku is unavailable.

    This is intentionally conservative: it never declares ``unsupported`` and
    therefore cannot turn a missing model into a false negative answer.
    """
    q = query.casefold()
    if re.search(r"\b(cập nhật|sửa|ghi|log|tạo|đổi|update|create|delete)\b", q):
        return Decision("action", 0.99, "phát hiện động từ ghi/cập nhật", "heuristic")
    if re.search(r"vì sao|tại sao|nguyên nhân|đánh giá|nhận xét|giải thích", q):
        return Decision("open", 0.75, "câu hỏi diễn giải", "heuristic")
    if re.search(r"tài liệu|sheet|wiki|master schedule|resource plan|summary", q):
        return Decision("document", 0.70, "nhắc tới tài liệu hoặc sheet", "heuristic")
    if re.search(r"ai |task|sprint|effort|giờ|status|trạng thái|bao nhiêu|ngày", q):
        return Decision("structured", 0.65, "có dấu hiệu truy vấn dữ liệu cấu trúc", "heuristic")
    return Decision("document", 0.40, "không đủ tín hiệu; dùng retrieval an toàn", "heuristic")


def classify(query: str, timeout: int | None = None) -> Decision:
    """Call Haiku and return a safe decision on every failure path."""
    if timeout is None:
        timeout = max(1, int(os.getenv("PROJECT_KNOWLEDGE_ROUTER_TIMEOUT_SECONDS", "60")))
    try:
        proc = subprocess.run(
            [models.CLAUDE, "-p", "--model", models.CHEAP, "--tools="],
            input=ROUTER_PROMPT.format(query=query),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        fallback = heuristic_route(query)
        return Decision(fallback.route, fallback.confidence, fallback.reason,
                        "fallback", f"{type(exc).__name__}: {exc}")

    if proc.returncode != 0:
        fallback = heuristic_route(query)
        return Decision(fallback.route, fallback.confidence, fallback.reason,
                        "fallback", proc.stderr.strip()[:300])

    decision = parse_response(proc.stdout)
    if decision is None:
        fallback = heuristic_route(query)
        return Decision(fallback.route, fallback.confidence, fallback.reason,
                        "fallback", "Haiku response không phải JSON route hợp lệ")
    return decision


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Classify a Nexus query with Haiku")
    parser.add_argument("query")
    parser.add_argument("--offline", action="store_true",
                        help="dùng heuristic, không gọi Claude")
    args = parser.parse_args()
    decision = heuristic_route(args.query) if args.offline else classify(args.query)
    print(json.dumps({
        "route": decision.route,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "source": decision.source,
        **({"error": decision.error} if decision.error else {}),
    }, ensure_ascii=False, indent=2))
