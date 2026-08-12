"""Đếm Risk/Issue theo Status — thuần logic, không gọi mạng."""

from __future__ import annotations

_OPEN_STATUSES = {"Open", "Pending"}
_IN_PROGRESS_STATUS = "In progress"
_CLOSED_STATUSES = {"Done", "Cancel"}


def tally_by_status(items: list[dict]) -> dict:
    """Cùng quy ước với skill `risk-assessment`: Open/Pending = chưa xử lý,
    In progress = đang xử lý, Done/Cancel = bỏ qua (đã đóng).
    """
    return {
        "open": sum(1 for i in items if i.get("status") in _OPEN_STATUSES),
        "inProgress": sum(1 for i in items if i.get("status") == _IN_PROGRESS_STATUS),
        "closed": sum(1 for i in items if i.get("status") in _CLOSED_STATUSES),
    }


def top_high_priority_open(items: list[dict], limit: int = 5) -> list[dict]:
    """Risk/issue Priority=High còn đang mở (không phải Done/Cancel), giữ
    nguyên thứ tự xuất hiện trên Sheet.
    """
    result = [
        i
        for i in items
        if str(i.get("priority", "")).strip().lower() == "high" and i.get("status") not in _CLOSED_STATUSES
    ]
    return result[:limit]
