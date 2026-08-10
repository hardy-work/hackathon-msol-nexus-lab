"""Dựng nội dung draft (report cho PM) — thuần string building, không gọi
API, không LLM (mọi câu chữ đều dựng từ template + số liệu thật).

Skill này CHỈ ĐỌC + ĐÁNH GIÁ, không ghi gì vào Sheet — nên report không còn
liệt kê từng risk/issue mới phát hiện (11 rule vẫn chạy đủ, layer vẫn là
cách phân tích nội bộ), mà nén lại thành 1 mục "Đánh giá" (sprint/người/
category có nguy cơ không kịp hay không, kèm đề xuất) + tally gọn của phần
đã có sẵn trên Sheet. Chi tiết từng risk/issue vẫn nằm đủ trong JSON block
để agent tham khảo khi PM hỏi thêm "tại sao lại không kịp" — không cần chạy
lại `scan.py`.
"""

from __future__ import annotations

import json
import re

# 4 rule cho ra thẳng "kịp hay không kịp" ở từng cấp (người/sprint/category)
# — hiện trong mục Đánh giá. Mọi rule còn lại (T1-T4, P1-P3, M1) chỉ là chi
# tiết hỗ trợ, không tính vào đây (PM hỏi thêm mới cần tới).
_ASSESSMENT_RULES = {"P4", "S1", "S2", "M2"}

_DEFICIT_RE = re.compile(r"thiếu ([\d.,]+)h")
_CATEGORY_LAG_RE = re.compile(r"đã trôi qua (\d+)% thời gian nhưng chỉ (\d+)% sub-task hoàn thành")
_GAP_DAYS_RE = re.compile(r"do các ngày sau chưa có effort được allocate: ([\d/,\s]+)\.")


def _short_person_deficit(item: dict) -> str:
    """Rút số giờ thiếu + ngày gap (nếu có) ra từ description (P4) — không
    tính lại, chỉ đọc lại đúng số rule_engine.py đã tính, tránh lệch số
    giữa 2 nơi.
    """
    m = _DEFICIT_RE.search(item["description"])
    deficit = m.group(1) if m else "?"
    who = item.get("relatedAssigneeTask") or item["detectedFrom"]
    gap_m = _GAP_DAYS_RE.search(item["description"])
    if gap_m:
        return f"**{who}** thiếu {deficit}h — do các ngày sau chưa có effort được allocate: {gap_m.group(1)}"
    return f"**{who}** (thiếu {deficit}h)"


def _short_category_lag(item: dict) -> str:
    name = item.get("relatedAssigneeTask") or item["detectedFrom"]
    m = _CATEGORY_LAG_RE.search(item["description"])
    if not m:
        return f"**{name}**"
    elapsed, done = m.groups()
    return f"**{name}** ({elapsed}% thời gian/{done}% xong)"


def _format_existing_item(item: dict) -> str:
    missing_next_action = " ⚠️ chưa có Next Action, cần PM bổ sung" if not item.get("nextAction") else ""
    idle_suffix = f" (đã xử lý được {item['idleDays']} ngày, chưa xong)" if item.get("idleDays") is not None else ""
    return f'- [{item.get("id", "?")}] {item["description"]}{idle_suffix}{missing_next_action}'


def _format_assessment(sprint_health: dict | None, passive_risks: list[dict]) -> list[str]:
    """Thứ tự trình bày: Vấn đề (cụ thể ai/category nào đang gặp gì, kèm
    root cause nếu có) -> Phân tích (số liệu effort/khối lượng cả team) ->
    Kết luận (kịp hay không + đề xuất) — bối cảnh cụ thể trước, số liệu tổng
    quan sau, kết luận cuối cùng.
    """
    p4_items = [i for i in passive_risks if i["rule"] == "P4"]
    s1_items = [i for i in passive_risks if i["rule"] == "S1"]
    m2_items = [i for i in passive_risks if i["rule"] == "M2"]

    problem_lines = []
    for i in p4_items:
        problem_lines.append(f"- {_short_person_deficit(i)}.")
    for i in s1_items:
        problem_lines.append(f"- {i['description']}")
    for i in m2_items:
        problem_lines.append(f"- Category {_short_category_lag(i)} có nguy cơ không kịp deadline riêng.")

    lines = ["📊 *Đánh giá*"]

    if not sprint_health and not problem_lines:
        lines.append("Chưa phát hiện dấu hiệu nào cho thấy sprint/người/category có nguy cơ không kịp.")
        return lines

    if problem_lines:
        lines.append("⚠️ *Vấn đề:*")
        lines.extend(problem_lines)

    if sprint_health:
        name = sprint_health["sprintName"]
        backlog = sprint_health["totalBacklog"]
        capacity = sprint_health["totalCapacity"]
        if sprint_health["onTrack"]:
            surplus = capacity - backlog
            lines.append(
                f"📈 *Phân tích:* {name} còn tồn đọng {backlog:.1f}h công việc, "
                f"cả team còn {capacity:.1f}h khả dụng đến hết sprint (dư {surplus:.1f}h)."
            )
            lines.append(
                f"✅ *Kết luận:* {name} **đang bám sát kế hoạch**. "
                "Duy trì nhịp độ hiện tại, không cần can thiệp gấp."
            )
        else:
            deficit = backlog - capacity
            lines.append(
                f"📈 *Phân tích:* {name} còn tồn đọng {backlog:.1f}h công việc, "
                f"cả team chỉ còn {capacity:.1f}h khả dụng đến hết sprint (thiếu {deficit:.1f}h)."
            )
            lines.append(
                f"✅ *Kết luận:* {name} có nguy cơ **KHÔNG kịp tiến độ**. "
                "Đề xuất: rà soát scope, bổ sung người/OT, hoặc dời deadline với stakeholder."
            )
    elif problem_lines:
        lines.append(
            "✅ *Kết luận:* Cần PM xem xét các vấn đề trên — chưa đủ dữ liệu Resource plan/Summary "
            "project để đánh giá tổng thể toàn sprint."
        )

    return lines


def _detail_note(passive_risks: list[dict], passive_issues: list[dict]) -> str | None:
    detail_risks = [i for i in passive_risks if i["rule"] not in _ASSESSMENT_RULES]
    total = len(detail_risks) + len(passive_issues)
    if total == 0:
        return None
    return (
        f"Ngoài ra còn {len(detail_risks)} risk + {len(passive_issues)} issue khác được phát hiện "
        "(task trễ hạn, chưa bắt đầu, nghỉ phép...) — hỏi mình nếu muốn biết chi tiết cụ thể."
    )


def build_draft(
    *,
    today: str,
    project_title: str,
    existing_open: list[dict],
    existing_in_progress: list[dict],
    passive_risks: list[dict],
    passive_issues: list[dict],
    sprint_health: dict | None,
) -> str:
    lines = [f"📋 **{project_title}** — {today}", ""]

    lines.append("🔴 *Chưa xử lý* (trên Sheet):")
    if existing_open:
        for item in existing_open:
            lines.append(_format_existing_item(item))
    else:
        lines.append("Hiện không có.")
    lines.append("")

    lines.append("🟡 *Đang xử lý* (trên Sheet):")
    if existing_in_progress:
        for item in existing_in_progress:
            lines.append(_format_existing_item(item))
    else:
        lines.append("Hiện không có.")
    lines.append("")

    note = _detail_note(passive_risks, passive_issues)
    if note:
        lines.append(note)
        lines.append("")

    # Kết luận/đánh giá đặt CUỐI CÙNG (trước JSON block) — theo cấu trúc báo
    # cáo cổ điển: bối cảnh/số liệu trước, kết luận sau.
    lines.extend(_format_assessment(sprint_health, passive_risks))
    lines.append("")

    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "existingOpen": existing_open,
                "existingInProgress": existing_in_progress,
                "passiveRisks": passive_risks,
                "passiveIssues": passive_issues,
                "sprintHealth": sprint_health,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")

    return "\n".join(lines)
