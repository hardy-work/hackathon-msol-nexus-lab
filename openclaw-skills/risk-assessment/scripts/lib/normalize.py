"""Source Adapter — parse Sprint tab thô (Google Sheets values) thành mảng
task item chuẩn hoá cho rule_engine.

Cấu trúc cột đọc theo `columns` (map field -> chữ cột) trong config.json của
từng Sprint tab — KHÔNG hardcode chữ cột, vì đã từng đổi (thêm TaskID/
Priority/Role/Sub-task, tách Task/Sub-task) — xem note trong SKILL.md.
"""

from __future__ import annotations

import re

_DATE_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")


def col_to_index(letter: str) -> int:
    return ord(letter.upper()) - ord("A")


def cell(row: list, letter: str | None):
    if not letter:
        return None
    idx = col_to_index(letter)
    if idx >= len(row):
        return None
    value = row[idx]
    return None if value == "" else value


def parse_date(value) -> str | None:
    """"D-M-YYYY"/"DD-M-YYYY" (không zero-pad tháng/ngày) -> "YYYY-MM-DD".

    KHÔNG dùng parser ngày mặc định của ngôn ngữ nào (dễ hiểu nhầm sang
    MM-DD-YYYY kiểu Mỹ) — luôn tự parse bằng regex.
    """
    if not value:
        return None
    m = _DATE_RE.match(str(value).strip())
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def parse_hours(value) -> float | None:
    """Số giờ có thể dùng dấu phẩy thập phân ("480,0") hoặc có hậu tố % (Progress)."""
    if value is None or value == "":
        return None
    s = str(value).strip().replace(",", ".").rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_sprint_rows(
    rows: list[list],
    columns: dict,
    sprint_name: str,
    status_done_values: list[str],
    tab_name: str,
    start_row: int = 1,
) -> list[dict]:
    """rows[0] tương ứng sheet row số `start_row` (1-based) — caller truyền
    đúng offset thật để fallback detectedFrom (khi tab không có cột TaskID)
    trỏ đúng dòng trên sheet.
    """
    tasks = []
    last_category = None
    for i, row in enumerate(rows):
        row_number = start_row + i
        title = cell(row, columns.get("Sub-task")) or cell(row, columns.get("Task"))
        task_id = cell(row, columns.get("TaskID"))
        if not title and not task_id:
            continue  # dòng trống hoặc subtotal (không có Sub-task/Task lẫn TaskID)

        category = cell(row, columns.get("Category Milestone"))
        if category:
            last_category = str(category).strip()

        status = cell(row, columns.get("Status")) or "Open"
        estimate = parse_hours(cell(row, columns.get("Re-estimate(h)")))
        if estimate is None:
            estimate = parse_hours(cell(row, columns.get("Estimate(h)")))
        detected_from = task_id or f"{tab_name}, row {row_number}"

        tasks.append(
            {
                "id": detected_from,
                "title": title,
                "taskName": cell(row, columns.get("Task")),
                "category": last_category,
                "role": cell(row, columns.get("Role")),
                "assignee": cell(row, columns.get("Assignee")),
                "priority": cell(row, columns.get("Priority")),
                "status": status,
                "isDone": status in status_done_values,
                "planStart": parse_date(cell(row, columns.get("Plan Start"))),
                "planEnd": parse_date(cell(row, columns.get("Plan End"))),
                "estimateHours": estimate,
                "actualHours": parse_hours(cell(row, columns.get("Actual Effort(h)"))),
                "remainingHours": parse_hours(cell(row, columns.get("Remaining(h)"))),
                "sprint": sprint_name,
                "lastUpdated": None,
                "detectedFrom": detected_from,
            }
        )
    return tasks
