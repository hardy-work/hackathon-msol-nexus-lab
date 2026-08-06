"""Đọc ngày kết thúc sprint hiện tại từ tab "Summary project" (cột "End date"),
thay vì suy đoán bằng Plan End xa nhất trong Sprint tab (không chính xác vì
Plan End của từng sub-task không nhất thiết trùng ngày sprint thật sự đóng).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})")


def _parse_end_date(cell: str) -> str | None:
    """Cell thật dạng "2026/08/07（Thứ 6）". Nếu ngày rơi vào Chủ nhật thì lùi
    về Thứ 6 gần nhất — tuần làm việc không tính Thứ 7/Chủ nhật.
    """
    if not cell:
        return None
    m = _DATE_RE.search(cell)
    if not m:
        return None
    parsed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if parsed.weekday() == 6:  # Chủ nhật
        parsed -= timedelta(days=2)
    return parsed.isoformat()


def find_sprint_end(rows: list[list], sprint_name: str) -> str | None:
    """Tự dò header "Sprint"/"End date" trong `rows` (không hardcode vị trí —
    tab này từng đổi cấu trúc như mọi tab khác), rồi tìm dòng có cột "Sprint"
    khớp `sprint_name` và trả về "End date" đã parse. `None` nếu không tìm
    thấy (caller tự fallback).
    """
    header_row_idx = col_sprint = col_end = None
    for i, row in enumerate(rows):
        if "Sprint" in row and "End date" in row:
            header_row_idx = i
            col_sprint = row.index("Sprint")
            col_end = row.index("End date")
            break
    if header_row_idx is None:
        return None

    for row in rows[header_row_idx + 1 :]:
        if len(row) <= max(col_sprint, col_end):
            continue
        if row[col_sprint].strip() == sprint_name:
            return _parse_end_date(row[col_end])
    return None
