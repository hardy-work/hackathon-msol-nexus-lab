"""Parse dữ liệu thô (Google Sheets values) thành cấu trúc chuẩn hoá — thuần
logic, không gọi mạng, để test được không cần Sheets API thật.
"""

from __future__ import annotations


def parse_number(value) -> float | None:
    """Số kiểu Việt Nam: dấu phẩy thập phân, có thể có hậu tố "%" (Progress)."""
    if value is None or value == "":
        return None
    s = str(value).strip().replace(",", ".").rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def find_current_sprint_row(rows: list[list], in_progress_marker: str = "In progress") -> dict | None:
    """Tự dò header trong `rows` (không hardcode vị trí — tab "Summary
    project" có thể đổi cấu trúc như các tab khác trong repo), rồi lấy dòng
    sprint đầu tiên có Status chứa `in_progress_marker`. `None` nếu không có
    sprint nào đang chạy hoặc không dò được header.
    """
    header_idx = None
    cols: dict[str, int] = {}
    wanted = ("Sprint", "Start date", "End date", "Remaining Time (h)", "Progress", "Status")
    for i, row in enumerate(rows):
        if "Sprint" in row and "Status" in row:
            header_idx = i
            cols = {name: row.index(name) for name in wanted if name in row}
            break
    if header_idx is None:
        return None

    def cell(row: list, name: str):
        idx = cols.get(name)
        if idx is None or idx >= len(row):
            return None
        return row[idx] or None

    for row in rows[header_idx + 1 :]:
        status = cell(row, "Status")
        if status and in_progress_marker.lower() in str(status).lower():
            return {
                "sprint": cell(row, "Sprint"),
                "startDate": cell(row, "Start date"),
                "endDate": cell(row, "End date"),
                "remainingHours": parse_number(cell(row, "Remaining Time (h)")),
                "progressPct": parse_number(cell(row, "Progress")),
                "status": status,
            }
    return None


def _find_col_index(header: list, name: str) -> int | None:
    for i, c in enumerate(header):
        if str(c).strip() == name:
            return i
    return None


def read_status_tab(rows: list[list]) -> list[dict]:
    """Đọc Risk management / Isssue management — tự dò cột theo TÊN header
    (không hardcode range/vị trí), vì 2 tab lệch cột trên sheet thật: Isssue
    management gộp "Related Assignee/Task" thành 1 cột, Risk management tách
    "Related Assignee" + "Task" riêng — đọc cứng theo vị trí sẽ lệch dữ liệu
    mà không báo lỗi gì.
    """
    if not rows:
        return []
    header = rows[0]
    id_idx = _find_col_index(header, "ID")
    priority_idx = _find_col_index(header, "Priority")
    status_idx = _find_col_index(header, "Status")
    desc_idx = _find_col_index(header, "Description")
    combined_idx = _find_col_index(header, "Related Assignee/Task")
    assignee_idx = _find_col_index(header, "Related Assignee")
    task_idx = _find_col_index(header, "Task")
    if task_idx is None:
        task_idx = _find_col_index(header, "Related Task")

    def cell(row: list, idx: int | None) -> str:
        return row[idx].strip() if idx is not None and idx < len(row) and row[idx] else ""

    items = []
    for row in rows[1:]:
        row_id = cell(row, id_idx)
        if not row_id:
            continue
        if combined_idx is not None:
            related = cell(row, combined_idx)
        else:
            assignee = cell(row, assignee_idx)
            task = cell(row, task_idx)
            related = f"{assignee} / {task}" if assignee and task else (assignee or task)
        items.append(
            {
                "id": row_id,
                "priority": cell(row, priority_idx),
                "status": cell(row, status_idx),
                "description": cell(row, desc_idx),
                "relatedAssigneeTask": related,
            }
        )
    return items
