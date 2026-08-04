"""Dựng nội dung draft (report tường thuật + JSON block) từ kết quả run_rules()
và các dòng "rủi ro chủ động" (Status=Pending) đọc từ Risk/Issue management
thật. Thuần string building — không gọi API, không LLM.
"""

from __future__ import annotations

import json

LAYER_ORDER = ["Person", "Task", "Sprint", "Module"]
# Nhãn hiển thị cho PM — "Module" (tên nội bộ, khớp rule M1/M2) hiện ra thành
# "Category" vì đó là tên cột thật trên sheet (Category Milestone), PM không
# gọi là "module".
LAYER_LABEL_VN = {"Person": "Người", "Task": "Task", "Sprint": "Sprint", "Module": "Category"}


def _is_urgent(item: dict, high_score_threshold: float) -> bool:
    return item.get("score", 0) >= high_score_threshold or item.get("trend") == "Increasing"


def _format_item_line(item: dict) -> str:
    options = item.get("nextActionOptions") or ([item["nextAction"]] if item.get("nextAction") else [])
    next_action_text = " / ".join(options) if options else "(chưa có đề xuất)"
    urgent_mark = "⚠️ " if item.get("_urgent") else ""
    return f'- {urgent_mark}{item["description"]} (Next Action: {next_action_text})'


def build_draft(
    *,
    today: str,
    project_title: str,
    active_risks: list[dict],
    passive_risks: list[dict],
    passive_issues: list[dict],
    resolved_risks: list[str],
    previous_snapshot_date: str | None,
    thresholds: dict,
) -> str:
    lines = [f"📋 Báo cáo rủi ro {project_title} — {today}", ""]

    # --- Rủi ro chủ động — LUÔN hiện mục này, kể cả rỗng ---
    lines.append("🟡 Rủi ro chủ động (đã ghi tay lúc log task, Status=Pending):")
    if active_risks:
        for item in active_risks:
            missing_next_action = " ⚠️ chưa có Next Action, cần PM bổ sung" if not item.get("nextAction") else ""
            lines.append(f'- [{item.get("id", "?")}] {item["description"]}{missing_next_action}')
    else:
        lines.append("- Hiện không có rủi ro chủ động nào (chưa có dòng Status=Pending).")
    lines.append("")

    # --- Rủi ro bị động — LUÔN hiện mục này, chia thẳng theo layer
    # Người → Task → Sprint → Category (không tách riêng khối "cần chú ý
    # ngay" nữa vì làm vỡ thứ tự layer — mức khẩn cấp giờ đánh dấu ⚠️ ngay
    # tại đúng vị trí layer của item đó). ---
    all_passive = passive_risks + passive_issues
    for item in all_passive:
        item["_urgent"] = _is_urgent(item, thresholds["highScoreThreshold"])

    lines.append("🔍 Rủi ro bị động, theo layer Người → Task → Sprint → Category:")
    if all_passive:
        for layer in LAYER_ORDER:
            layer_items = [i for i in all_passive if i["layer"] == layer]
            if not layer_items:
                continue
            lines.append(f"  [{LAYER_LABEL_VN[layer]}]")
            for item in layer_items:
                lines.append(f"  {_format_item_line(item)}")
    else:
        lines.append("- Hiện không có rủi ro bị động nào.")
    lines.append("")

    for item in all_passive:
        del item["_urgent"]

    # Chỉ hiện mục này khi THẬT SỰ có báo cáo hôm trước để so — không có thì
    # ẩn hẳn, tránh gây hiểu nhầm là "đã so sánh mà không thấy gì".
    if previous_snapshot_date:
        lines.append(f"✅ Đã hết rủi ro (so với báo cáo ngày {previous_snapshot_date}):")
        if resolved_risks:
            for d in resolved_risks:
                lines.append(f"- {d}")
        else:
            lines.append(f"- Không có rủi ro nào vừa hết so với báo cáo ngày {previous_snapshot_date}.")
        lines.append("")

    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "activeRisks": active_risks,
                "passiveRisks": passive_risks,
                "passiveIssues": passive_issues,
                "resolvedRisks": resolved_risks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")

    return "\n".join(lines)
