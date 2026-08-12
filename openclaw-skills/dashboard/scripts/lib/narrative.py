"""Build text tổng hợp — theo OUTPUT-STYLE.md: bôi đậm 2 dấu sao cho giá trị
(task ID, tên người, %, giờ, status), không dùng emoji.
"""

from __future__ import annotations


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "chưa rõ"
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def _fmt_hours(value: float | None) -> str:
    if value is None:
        return "chưa rõ"
    return f"{value:g}h"


def build_narrative(sprint: dict | None, risk_tally: dict, issue_tally: dict, top_risks: list[dict]) -> str:
    lines = ["Tổng quan dự án"]

    if sprint:
        lines.append(
            f"Sprint hiện tại: **{sprint['sprint']}**, tiến độ **{_fmt_pct(sprint['progressPct'])}**, "
            f"còn lại **{_fmt_hours(sprint['remainingHours'])}**, trạng thái **{sprint['status']}**."
        )
    else:
        lines.append("Không tìm thấy sprint nào đang **In progress** trên tab Summary project.")

    lines.append(f"Risk: **{risk_tally['open']}** chưa xử lý, **{risk_tally['inProgress']}** đang xử lý.")
    lines.append(f"Issue: **{issue_tally['open']}** chưa xử lý, **{issue_tally['inProgress']}** đang xử lý.")

    if top_risks:
        lines.append("Risk ưu tiên cao đang mở:")
        for r in top_risks:
            who = r.get("relatedAssigneeTask") or "chưa rõ"
            lines.append(f"- **{r['id']}** ({who}): {r.get('description', '')}")
    else:
        lines.append("Không có risk ưu tiên cao nào đang mở.")

    return "\n".join(lines)
