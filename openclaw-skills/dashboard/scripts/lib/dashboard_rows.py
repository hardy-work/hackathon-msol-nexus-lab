"""Build mảng 2 chiều (list[list]) để ghi vào tab "Dashboard" — thuần logic,
không gọi mạng, để test được không cần Sheets API thật.
"""

from __future__ import annotations


def build_dashboard_rows(
    sprint: dict | None,
    risk_tally: dict,
    issue_tally: dict,
    top_risks: list[dict],
    generated_at: str,
) -> list[list]:
    rows: list[list] = [
        ["NexusBot Dashboard"],
        [f"Cập nhật lúc: {generated_at}"],
        [],
        ["Mục", "Giá trị"],
    ]

    if sprint:
        rows += [
            ["Sprint hiện tại", sprint.get("sprint") or ""],
            ["Tiến độ (%)", sprint.get("progressPct") if sprint.get("progressPct") is not None else ""],
            ["Còn lại (giờ)", sprint.get("remainingHours") if sprint.get("remainingHours") is not None else ""],
            ["Trạng thái sprint", sprint.get("status") or ""],
        ]
    else:
        rows.append(["Sprint hiện tại", "Không có sprint nào đang In progress"])

    rows += [
        ["Risk chưa xử lý", risk_tally.get("open", 0)],
        ["Risk đang xử lý", risk_tally.get("inProgress", 0)],
        ["Issue chưa xử lý", issue_tally.get("open", 0)],
        ["Issue đang xử lý", issue_tally.get("inProgress", 0)],
        [],
        ["Risk ưu tiên cao đang mở"],
        ["ID", "Liên quan", "Mô tả"],
    ]

    if top_risks:
        for r in top_risks:
            rows.append([r.get("id", ""), r.get("relatedAssigneeTask", ""), r.get("description", "")])
    else:
        rows.append(["(không có)", "", ""])

    return rows
