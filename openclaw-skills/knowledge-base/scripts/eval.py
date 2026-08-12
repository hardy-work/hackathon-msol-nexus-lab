#!/usr/bin/env python3
"""Chấm questions.json. Chấm HÀNH VI, không chấm chuỗi ký tự.

Điểm mấu chốt: nhóm `not_in_kb` chấm ĐÚNG khi hệ thống nói "không tìm thấy" và
chấm TRƯỢT khi nói "chắc chắn không". Hai câu đó nghe giống nhau nhưng khác nhau
về bản chất — và đó là luận điểm của cả dự án.

  python3 scripts/eval.py [--verbose]
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from answer import CO, NF, NO, KB, ask  # noqa: E402
from response_style import check_style  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
G, R, Y, D, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

WANT = {"in_kb": CO, "not_in_kb": NF, "confident_no": NO, "numeric": CO}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def nums(text):
    return {float(x.replace(",", "")) for x in re.findall(r"\d+(?:\.\d+)?", text)}


def check(q, res):
    """-> (đậu?, ghi chú)"""
    want = WANT[q["group"]]
    if res.outcome != want:
        return False, f"kỳ vọng {want}, nhận {res.outcome}"

    exp = q["expect"]
    got = norm(res.answer)

    if "value" in exp:
        v = float(exp["value"])
        if v not in nums(res.answer):
            return False, f"thiếu giá trị {v} (trả về: {res.answer.strip()[:60]})"
    if "values" in exp:
        for k, v in exp["values"].items():
            if float(v) not in nums(res.answer):
                return False, f"thiếu {k}={v}"
    if "answer" in exp and q["group"] != "confident_no":
        if norm(exp["answer"]) not in got:
            return False, f"không thấy '{exp['answer']}'"
    if "answer_set" in exp:
        miss = [a for a in exp["answer_set"] if norm(a) not in got]
        if miss:
            return False, f"thiếu {miss}"
    if "must_cite" in exp:
        cites = norm(" ".join(res.cites))
        miss = [c for c in exp["must_cite"] if norm(c) not in cites]
        if miss:
            return False, f"thiếu nguồn {miss}"
    if not res.cites and q["group"] in ("in_kb", "numeric"):
        return False, "trả lời có nội dung nhưng KHÔNG dẫn nguồn"
    status = {CO: "in_kb", NO: "confident_no", NF: "not_in_kb"}[res.outcome]
    style = check_style(status, res.answer, res.cites)
    if style:
        return False, "văn phong: " + "; ".join(style)
    return True, ""


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    spec = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
    # This suite evaluates the signed Nexus demo snapshot.  Keep the approval
    # authority local to the test harness, matching the other eval entrypoints
    # and run_all.sh; production callers must still inject trusted grants.
    os.environ.setdefault(
        "KNOWLEDGE_BASE_COVERAGE_GRANTS",
        '{"Đô":["knowledge_base:approve_coverage"]}',
    )
    os.environ.setdefault(
        "KNOWLEDGE_BASE_APPROVAL_IDS",
        "nexus-demo-person-role-20260803,nexus-demo-person-task-20260803",
    )
    kb = KB()

    use_llm = "--llm" in sys.argv
    per_group, rows, skipped = {}, [], 0
    for q in spec["questions"]:
        # Câu corpus VĂN cần bậc 3 (LLM đọc trang source) — không trả lời được ở chế độ
        # tất định. Chỉ chạy khi --llm; mặc định bỏ qua để 27/27 handy vẫn tất định/nhanh.
        if q.get("needs_llm") and not use_llm:
            skipped += 1
            continue
        res = ask(kb, q["q"], llm=use_llm)
        ok, note = check(q, res)
        rows.append((q, res, ok, note))
        s = per_group.setdefault(q["group"], [0, 0])
        s[0] += ok
        s[1] += 1

    for q, res, ok, note in rows:
        mark = f"{G}✓{OFF}" if ok else f"{R}✗{OFF}"
        print(f"{mark} {q['id']} {D}[{q['group']:12s} b{res.tier}]{OFF} {q['q'][:56]}")
        print(f"    {D}→{OFF} {res.outcome}{'' if ok else f'   {R}{note}{OFF}'}")
        if verbose:
            print(f"    {D}{res.answer.replace(chr(10),' ')[:150]}{OFF}")
            if res.reason:
                print(f"    {D}vì: {res.reason[:150]}{OFF}")

    tot = sum(s[0] for s in per_group.values())
    n = sum(s[1] for s in per_group.values())
    print(f"\n{'nhóm':14s} đậu/tổng")
    for g in ("in_kb", "not_in_kb", "confident_no", "numeric"):
        p, t = per_group.get(g, (0, 0))
        col = G if p == t else R
        print(f"{g:14s} {col}{p}/{t}{OFF}   {D}{spec['groups'][g]}{OFF}")
    col = G if tot == n else R
    print(f"\n{'TỔNG':14s} {col}{tot}/{n}{OFF}")
    if skipped:
        print(f"{D}({skipped} câu cần bậc 3 đã bỏ qua — chạy `eval.py --llm` để chấm cả corpus VĂN){OFF}")
    return 0 if tot == n else 1


if __name__ == "__main__":
    sys.exit(main())
