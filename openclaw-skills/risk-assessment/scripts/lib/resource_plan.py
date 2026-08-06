"""Parse bảng "Thời gian làm việc mỗi ngày" (tab Resource plan, nằm bên phải
tab, header 2 tầng: tháng rồi tới số ngày trong tháng) thành giờ làm việc
mỗi người mỗi ngày — dùng cho rule P1 (nghỉ -> cascade) và P4/S2 (capacity).

Tự định vị bảng bằng cách tìm ô "Member" (không hardcode chữ cột) — layout
bên trái tab có thể đổi mà không ảnh hưởng, miễn "Member"/"Role" và 2 dòng
header ngay dưới nó còn giữ đúng cấu trúc. Cột code ngắn (vd "MH_SonBH") từng
tên "Name" (nằm SAU cụm ngày) rồi đổi thành "Slack name" (nằm TRƯỚC Role,
giống hệt tab Overtime) — thử cả 2 tên, không hardcode vị trí cột đó.
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
    raise ValueError('Không tìm thấy header "Member" trong bảng Resource plan')


def _find_col(row: list, target: str) -> int:
    for i, c in enumerate(row):
        if str(c).strip() == target:
            return i
    raise ValueError(f'Không tìm thấy cột "{target}"')


def _find_col_optional(row: list, target: str) -> int | None:
    for i, c in enumerate(row):
        if str(c).strip() == target:
            return i
    return None


def parse_resource_plan(rows: list[list], person_code_map: dict, year: int) -> list[dict]:
    header_idx = _find_header_row(rows)
    header_row = rows[header_idx]
    day_row = rows[header_idx + 1]

    role_idx = _find_col(header_row, "Role")
    member_idx = _find_col(header_row, "Member")
    # Cột code ngắn (vd "MH_SonBH") từng tên là "Name" (nằm SAU cụm ngày), giờ
    # đổi thành "Slack name" (nằm TRƯỚC Role, cùng cấu trúc tab Overtime) —
    # thử cả 2 tên, không hardcode 1 vị trí cố định.
    name_idx = _find_col_optional(header_row, "Name")
    if name_idx is None:
        name_idx = _find_col_optional(header_row, "Slack name")
    # Tương tự "Id Slack" (cũ) / "Slack ID" (mới) -- optional cả 2, không có
    # thì slackId=None, KHÔNG raise lỗi (tránh vỡ deployment sheet cũ hơn nữa).
    slack_id_idx = _find_col_optional(header_row, "Id Slack")
    if slack_id_idx is None:
        slack_id_idx = _find_col_optional(header_row, "Slack ID")

    # Cột ngày nằm ngay sau Role -- dùng độ dài day_row làm biên phải (KHÔNG
    # dùng vị trí Name/Slack name làm mốc nữa, vì cột đó từng nằm SAU cụm
    # ngày, giờ lại nằm TRƯỚC Role -- không còn đáng tin cậy làm biên).
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
        name_code = row[name_idx].strip() if name_idx is not None and name_idx < len(row) and row[name_idx] else ""
        assignee_code = person_code_map.get(name_code, name_code)
        slack_id = (
            row[slack_id_idx].strip() if slack_id_idx is not None and slack_id_idx < len(row) and row[slack_id_idx] else None
        )

        daily_hours = {}
        for col, iso_date in date_col_iso.items():
            raw = row[col] if col < len(row) else ""
            daily_hours[iso_date] = parse_hours(raw)

        people.append({"member": member, "assigneeCode": assignee_code, "slackId": slack_id, "dailyHours": daily_hours})
        row_idx += 1

    return people
