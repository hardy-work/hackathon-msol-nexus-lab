"""Dựng nội dung draft (report tường thuật + JSON block) cho PM. Thuần string
building — không gọi API, không LLM (mọi câu chữ đều dựng từ template + số
liệu thật, không tự "viết văn" tự do — để deterministic, test được).

Cấu trúc report KHÔNG chia theo layer (Người/Task/Sprint/Category) nữa — đó
chỉ là cách nội bộ rule_engine.py phân tích (vẫn giữ nguyên field `layer`
trong JSON block để debug), còn phần đọc được ưu tiên theo thứ tự PM cần:
  1. Sức khỏe Sprint (kịp hay không, đề xuất ngay)
  2. Rủi ro đã có trên Sheet, theo Status (Open = chưa xử lý, In progress =
     đang xử lý) — không phải rủi ro mới, PM cần biết cái nào đang bị treo
  3. Rủi ro mới phát hiện, chia theo mức khẩn cấp (cần chú ý ngay / còn lại)
     — không theo layer, vì layer không phải thứ PM quan tâm khi đọc nhanh
  4. Đã hết rủi ro (so với hôm qua, nếu có)
"""

from __future__ import annotations

import json
import re

# Rule nào hay có NHIỀU item cùng lúc trong 1 lần scan thì gộp lại 1 dòng cho
# gọn (thay vì mỗi item 1 dòng riêng) — chỉ áp dụng khi thật sự có >=2 item
# cùng rule, còn 1 item thì vẫn hiện như bình thường.
_GROUPABLE_RULES = {"T1", "T4", "P4"}
_GROUP_OPENERS = {
    "T1": "sub-task đã trễ Plan End",
    "T4": "sub-task đã quá Plan Start mà chưa ai log effort — nhiều khả năng đang bị block",
    "P4": "người đều đang vượt capacity còn lại tới hết sprint",
}
_DEFICIT_RE = re.compile(r"thiếu ([\d.,]+)h")

# Thứ tự cố định khi liệt kê rủi ro mới phát hiện — không phụ thuộc thứ tự
# rule_engine.py sinh ra (chi tiết implementation), để PM đọc nhất quán mỗi
# lần chạy.
_RULE_ORDER = ["P1", "P2", "P3", "P4", "T1", "T2", "T3", "T4", "S1", "S2", "M1", "M2"]


def _is_urgent(item: dict, high_score_threshold: float) -> bool:
    return item.get("score", 0) >= high_score_threshold or item.get("trend") == "Increasing"


def _next_action_suffix(item: dict) -> str:
    options = item.get("nextActionOptions") or ([item["nextAction"]] if item.get("nextAction") else [])
    if not options:
        return ""
    return " — " + " / ".join(options) + "."


def _format_single_line(item: dict) -> str:
    urgent_mark = "⚠️ " if item.get("_urgent") else ""
    return f"- {urgent_mark}{item['description']}{_next_action_suffix(item)}"


def _short_task_ref(item: dict) -> str:
    """"KiênĐT / PCS-5" -> "`PCS-5`·KiênĐT" (rút gọn cho dòng gộp nhóm)."""
    related = item.get("relatedAssigneeTask") or ""
    if " / " in related:
        who, task_id = related.split(" / ", 1)
        return f"`{task_id}`·{who}"
    return f"`{item['detectedFrom']}`"


def _short_person_deficit(item: dict) -> str:
    """Rút số giờ thiếu ra từ description (P4) — không tính lại, chỉ đọc lại
    đúng số rule_engine.py đã tính, tránh lệch số giữa 2 nơi.
    """
    m = _DEFICIT_RE.search(item["description"])
    deficit = m.group(1) if m else "?"
    who = item.get("relatedAssigneeTask") or item["detectedFrom"]
    return f"**{who}** thiếu **{deficit}h**"


def _group_next_action_suffix(items: list[dict]) -> str:
    """Next action của item đầu tiên trong nhóm — nhưng nếu option có nhắc
    thẳng tên người phụ trách CỦA RIÊNG item đó (vd T4: "Hỏi {assignee} lý
    do..."), thay tên đó bằng "từng người" — vì đang gộp NHIỀU người vào 1
    dòng, nêu đích danh 1 người làm ví dụ đại diện cho cả nhóm dễ gây hiểu
    lầm là chỉ áp dụng cho người đó.
    """
    first = items[0]
    options = list(first.get("nextActionOptions") or [])
    related = first.get("relatedAssigneeTask") or ""
    assignee = related.split(" / ", 1)[0] if " / " in related else None
    if assignee:
        options = [opt.replace(assignee, "từng người") for opt in options]
    if not options:
        return ""
    return " — " + " / ".join(options) + "."


def _format_group_line(rule: str, items: list[dict]) -> str:
    urgent_mark = "⚠️ " if any(i.get("_urgent") for i in items) else ""
    opener = _GROUP_OPENERS[rule]
    suffix = _group_next_action_suffix(items)
    if rule == "P4":
        refs = ", ".join(_short_person_deficit(i) for i in items)
    else:
        refs = ", ".join(_short_task_ref(i) for i in items)
    return f"- {urgent_mark}{len(items)} {opener}: {refs}.{suffix}"


def _format_rule_grouped(items: list[dict]) -> list[str]:
    """Gom item theo `rule` (KHÔNG theo layer) — nếu >=2 item cùng 1 rule
    groupable thì gộp 1 dòng, còn lại hiện riêng từng dòng. Duyệt theo
    `_RULE_ORDER` cố định, không theo thứ tự xuất hiện trong list đầu vào.
    """
    by_rule: dict[str, list[dict]] = {}
    for item in items:
        by_rule.setdefault(item["rule"], []).append(item)

    lines = []
    for rule in _RULE_ORDER:
        if rule not in by_rule:
            continue
        group = by_rule[rule]
        if rule in _GROUPABLE_RULES and len(group) >= 2:
            lines.append(_format_group_line(rule, group))
        else:
            for item in group:
                lines.append(_format_single_line(item))
    return lines


def _format_existing_item(item: dict) -> str:
    missing_next_action = " ⚠️ chưa có Next Action, cần PM bổ sung" if not item.get("nextAction") else ""
    idle_suffix = f" (đã xử lý được {item['idleDays']} ngày, chưa xong)" if item.get("idleDays") is not None else ""
    return f'- [{item.get("id", "?")}] {item["description"]}{idle_suffix}{missing_next_action}'


def _format_sprint_health(health: dict) -> list[str]:
    name = health["sprintName"]
    backlog = health["totalBacklog"]
    capacity = health["totalCapacity"]
    lines = [f"📊 *Sức khỏe {name}*"]
    if health["onTrack"]:
        surplus = capacity - backlog
        lines.append(
            f"Tiến độ: **Đang bám sát kế hoạch** — công việc còn lại cần khoảng {backlog:.1f}h, "
            f"cả team còn {capacity:.1f}h có thể làm tới hết sprint (dư {surplus:.1f}h)."
        )
        lines.append("Đề xuất: Duy trì nhịp độ hiện tại, không cần can thiệp gấp — vẫn nên theo dõi tiếp các ngày tới.")
    else:
        deficit = backlog - capacity
        lines.append(
            f"Tiến độ: **KHÔNG kịp tiến độ** — công việc còn lại cần khoảng {backlog:.1f}h, "
            f"nhưng cả team chỉ còn {capacity:.1f}h có thể làm tới hết sprint (thiếu {deficit:.1f}h)."
        )
        lines.append(
            "Đề xuất: Rà soát scope sprint, cắt bớt task ưu tiên thấp / Bổ sung người/OT cả team / "
            "Xin dời deadline sprint với stakeholder."
        )
    return lines


def build_draft(
    *,
    today: str,
    project_title: str,
    existing_open: list[dict],
    existing_in_progress: list[dict],
    passive_risks: list[dict],
    passive_issues: list[dict],
    resolved_risks: list[str],
    previous_snapshot_date: str | None,
    sprint_health: dict | None,
    thresholds: dict,
) -> str:
    lines = [f"📋 **{project_title}** — {today}", ""]

    # --- Sức khỏe Sprint — LUÔN đặt đầu tiên (PM cần "so what" trước tiên) ---
    # Chỉ vắng mặt khi thiếu dữ liệu Resource plan/sprint_end (xem scan.py).
    if sprint_health:
        lines.extend(_format_sprint_health(sprint_health))
        lines.append("")

    # --- Rủi ro đã có trên Sheet — chia theo Status, KHÔNG phải rủi ro mới
    # phát hiện hôm nay. "Chưa xử lý" gồm cả Open lẫn Pending (dev tự báo,
    # PM chưa chốt phương án) — với PM cả 2 đều là "chưa ai làm gì". ---
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

    # --- Rủi ro mới phát hiện — chia theo mức khẩn cấp, KHÔNG theo layer. ---
    all_passive = passive_risks + passive_issues
    for item in all_passive:
        item["_urgent"] = _is_urgent(item, thresholds["highScoreThreshold"])

    urgent_items = [i for i in all_passive if i["_urgent"]]
    other_items = [i for i in all_passive if not i["_urgent"]]

    lines.append(f"🔍 *Rủi ro mới phát hiện* ({len(passive_risks)} risk + {len(passive_issues)} issue):")
    if all_passive:
        if urgent_items:
            lines.append("*Cần chú ý ngay:*")
            lines.extend(_format_rule_grouped(urgent_items))
        if other_items:
            lines.append("*Còn lại:*")
            lines.extend(_format_rule_grouped(other_items))
    else:
        lines.append("Hiện không có rủi ro/issue mới nào.")
    lines.append("")

    for item in all_passive:
        del item["_urgent"]

    # Chỉ hiện mục này khi THẬT SỰ có báo cáo hôm trước để so — không có thì
    # ẩn hẳn, tránh gây hiểu nhầm là "đã so sánh mà không thấy gì".
    if previous_snapshot_date:
        lines.append(f"✅ *Đã hết rủi ro* (so với báo cáo ngày {previous_snapshot_date}):")
        if resolved_risks:
            for d in resolved_risks:
                lines.append(f"- {d}")
        else:
            lines.append(f"Không có rủi ro nào vừa hết so với báo cáo ngày {previous_snapshot_date}.")
        lines.append("")

    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "existingOpen": existing_open,
                "existingInProgress": existing_in_progress,
                "passiveRisks": passive_risks,
                "passiveIssues": passive_issues,
                "resolvedRisks": resolved_risks,
                "sprintHealth": sprint_health,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")

    return "\n".join(lines)
