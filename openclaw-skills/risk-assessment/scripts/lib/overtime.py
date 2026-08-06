"""Parse tab "Overtime" (bảng OT theo ngày mỗi người) — cấu trúc lưới ngày
giống Resource plan (header 2 tầng: tháng rồi số ngày) nhưng đơn giản hơn:
không có cột Name/Email phía sau, cột ngày nằm ngay sau Role tới hết dòng.

Join sang Sprint tab/Resource plan qua Slack ID (ổn định hơn so tên đầy đủ,
tránh trùng/lệch dấu) thay vì thêm 1 map cấu hình tay mới — xem
`build_ot_by_assignee_code()`.
"""

from __future__ import annotations

from normalize import parse_hours

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _find_header_row(rows: list[list]) -> int:
    for i, row in enumerate(rows):
        if any(str(c).strip() == "Member" for c in row):
            return i
    raise ValueError('Không tìm thấy header "Member" trong tab Overtime')


def _find_col(row: list, target: str) -> int:
    for i, c in enumerate(row):
        if str(c).strip() == target:
            return i
    raise ValueError(f'Không tìm thấy cột "{target}"')


def parse_overtime(rows: list[list], year: int) -> list[dict]:
    header_idx = _find_header_row(rows)
    header_row = rows[header_idx]
    day_row = rows[header_idx + 1]

    role_idx = _find_col(header_row, "Role")
    slack_id_idx = _find_col(header_row, "Slack ID")
    member_idx = _find_col(header_row, "Member")

    # Cột ngày nằm ngay sau Role tới hết dòng (KHÔNG có cột nào theo sau như
    # Resource plan) -- dùng độ dài day_row làm biên phải vì header_row có
    # thể ngắn hơn (chỉ ghi tên tháng 1 lần, không lặp lại mỗi cột).
    date_col_month: dict[int, int] = {}
    current_month = None
    for col in range(role_idx + 1, len(day_row)):
        cell = str(header_row[col]).strip().lower() if col < len(header_row) else ""
        if cell in _MONTH_NAMES:
            current_month = _MONTH_NAMES[cell]
        if current_month is not None:
            date_col_month[col] = current_month

    date_col_iso: dict[int, str] = {}
    for col, month in date_col_month.items():
        raw_day = day_row[col] if col < len(day_row) else ""
        if not str(raw_day).strip():
            continue
        try:
            day = int(str(raw_day).strip())
        except ValueError:
            continue
        date_col_iso[col] = f"{year:04d}-{month:02d}-{day:02d}"

    people = []
    row_idx = header_idx + 2
    while row_idx < len(rows):
        row = rows[row_idx]
        member = row[member_idx].strip() if member_idx < len(row) and row[member_idx] else ""
        if not member:
            break
        slack_id = row[slack_id_idx].strip() if slack_id_idx < len(row) and row[slack_id_idx] else None

        daily_hours = {}
        for col, iso_date in date_col_iso.items():
            raw = row[col] if col < len(row) else ""
            daily_hours[iso_date] = parse_hours(raw)

        people.append({"member": member, "slackId": slack_id, "dailyHours": daily_hours})
        row_idx += 1

    return people


def build_ot_by_assignee_code(overtime_people: list[dict], resource_plan_people: list[dict]) -> dict[str, dict]:
    """Nối OT (keyed theo Slack ID) sang đúng `assigneeCode` (keyed theo
    Resource plan, đã map qua personCodeMap) — join qua Slack ID vì Overtime
    tab dùng tên đầy đủ, không phải code ngắn như Resource plan.
    """
    slack_to_code = {p["slackId"]: p["assigneeCode"] for p in resource_plan_people if p.get("slackId")}
    result = {}
    for person in overtime_people:
        code = slack_to_code.get(person.get("slackId"))
        if not code:
            continue
        result[code] = person["dailyHours"]
    return result
