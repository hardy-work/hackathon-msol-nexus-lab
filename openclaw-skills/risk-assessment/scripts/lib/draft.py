"""Dựng nội dung draft (report tường thuật + JSON block) từ kết quả run_rules()
và các dòng "rủi ro chủ động" (Status=Pending) đọc từ Risk/Issue management
thật. Thuần string building — không gọi API, không LLM (mọi câu chữ đều dựng
từ template + số liệu thật, không tự "viết văn" tự do — để deterministic,
test được).
"""

from __future__ import annotations

import json
import re

LAYER_ORDER = ["Person", "Task", "Sprint", "Module"]
# Nhãn hiển thị cho PM — "Module" (tên nội bộ, khớp rule M1/M2) hiện ra thành
# "Category" vì đó là tên cột thật trên sheet (Category Milestone), PM không
# gọi là "module".
LAYER_LABEL_VN = {"Person": "Người", "Task": "Task", "Sprint": "Sprint", "Module": "Category"}

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


def _is_urgent(item: dict, high_score_threshold: float) -> bool:
    return item.get("score", 0) >= high_score_threshold or item.get("trend") == "Increasing"


def _next_action_suffix(item: dict) -> str:
    options = item.get("nextActionOptions") or ([item["nextAction"]] if item.get("nextAction") else [])
    if not options:
        return ""
    return " — " + " / ".join(options) + "."


def _format_single_line(item: dict) -> str:
    urgent_mark = "⚠️ " if item.get("_urgent") else ""
    return f"{urgent_mark}{item['description']}{_next_action_suffix(item)}"


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
    return f"{urgent_mark}{len(items)} {opener}: {refs}.{suffix}"


def _format_layer_items(layer_items: list[dict]) -> list[str]:
    by_rule: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in layer_items:
        if item["rule"] not in by_rule:
            order.append(item["rule"])
        by_rule.setdefault(item["rule"], []).append(item)

    lines = []
    for rule in order:
        group = by_rule[rule]
        if rule in _GROUPABLE_RULES and len(group) >= 2:
            lines.append(f"  {_format_group_line(rule, group)}")
        else:
            for item in group:
                lines.append(f"  {_format_single_line(item)}")
    return lines


def _opening_summary(all_passive: list[dict], high_score_threshold: float) -> str:
    if not all_passive:
        return "Không phát hiện rủi ro/issue bị động nào hôm nay."
    urgent_count = sum(1 for i in all_passive if _is_urgent(i, high_score_threshold))
    layer_counts: dict[str, int] = {}
    for item in all_passive:
        layer_counts[item["layer"]] = layer_counts.get(item["layer"], 0) + 1
    top_layers = sorted(layer_counts.items(), key=lambda kv: -kv[1])[:2]
    top_desc = ", ".join(f"{LAYER_LABEL_VN[layer]} ({count})" for layer, count in top_layers)
    urgent_clause = f", {urgent_count} mục cần chú ý ngay (⚠️)" if urgent_count else ""
    return f"Phát hiện {len(all_passive)} rủi ro/issue hôm nay{urgent_clause} — tập trung nhiều nhất ở {top_desc}."


def build_draft(
    *,
    today: str,
    project_title: str,
    active_risks: list[dict],
    passive_risks: list[dict],
    passive_issues: list[dict],
    stale_in_progress: list[dict],
    resolved_risks: list[str],
    previous_snapshot_date: str | None,
    thresholds: dict,
) -> str:
    lines = [f"📋 **{project_title}** — {today}", ""]

    all_passive = passive_risks + passive_issues
    for item in all_passive:
        item["_urgent"] = _is_urgent(item, thresholds["highScoreThreshold"])

    lines.append(_opening_summary(all_passive, thresholds["highScoreThreshold"]))
    lines.append("")

    # --- Rủi ro chủ động — LUÔN hiện mục này, kể cả rỗng ---
    # (kỹ thuật: đây là dòng Status=Pending, nhưng không cần lộ chi tiết kỹ
    # thuật đó ra ngoài — PM chỉ cần biết đây là rủi ro do dev tự báo.)
    lines.append("🟡 *Rủi ro chủ động*:")
    if active_risks:
        for item in active_risks:
            missing_next_action = " ⚠️ chưa có Next Action, cần PM bổ sung" if not item.get("nextAction") else ""
            lines.append(f'- [{item.get("id", "?")}] {item["description"]}{missing_next_action}')
    else:
        lines.append("Hiện không có.")
    lines.append("")

    # --- Risk/Issue đã ghi nhưng chưa xử lý xong (Status vẫn "In progress"
    # quá lâu, xem find_stale_in_progress() trong scan.py) — nhắc PM follow-up,
    # tránh bị bỏ quên. LUÔN hiện mục này. ---
    lines.append("🔁 *Rủi ro chưa được xử lý*:")
    if stale_in_progress:
        for item in stale_in_progress:
            lines.append(f'- [{item.get("id", "?")}] {item["description"]} (đã {item["idleDays"]} ngày)')
    else:
        lines.append("Hiện không có.")
    lines.append("")

    # --- Rủi ro bị động — LUÔN hiện mục này, chia thẳng theo layer
    # Người → Task → Sprint → Category. Trong mỗi layer, item cùng rule (nếu
    # >=2) được gộp lại 1 dòng cho gọn — xem _format_layer_items(). ---
    lines.append("🔍 *Rủi ro bị động*:")
    if all_passive:
        for layer in LAYER_ORDER:
            layer_items = [i for i in all_passive if i["layer"] == layer]
            if not layer_items:
                continue
            lines.append(f"**[{LAYER_LABEL_VN[layer]}]**")
            lines.extend(_format_layer_items(layer_items))
    else:
        lines.append("Hiện không có rủi ro bị động nào.")
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

    if previous_snapshot_date:
        lines.append(
            f"Tổng: **{len(passive_risks)} risk + {len(passive_issues)} issue** phát hiện hôm nay, "
            f"**{len(resolved_risks)}** đã hết so với báo cáo ngày {previous_snapshot_date}."
        )
    else:
        lines.append(f"Tổng: **{len(passive_risks)} risk + {len(passive_issues)} issue** phát hiện hôm nay.")
    lines.append("")

    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "activeRisks": active_risks,
                "passiveRisks": passive_risks,
                "passiveIssues": passive_issues,
                "staleInProgress": stale_in_progress,
                "resolvedRisks": resolved_risks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")

    return "\n".join(lines)
