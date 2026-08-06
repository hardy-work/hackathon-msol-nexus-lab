"""Rule engine cho skill risk-assessment — thuần deterministic, KHÔNG có LLM.
scan.py chỉ gọi run_rules() rồi diễn giải kết quả bằng tiếng Việt.

12 rule chia theo 4 layer (Person/Task/Sprint/Module). Skill này CHỈ ĐỌC +
ĐÁNH GIÁ — không ghi gì vào Sheet (việc ghi risk/issue do skill khác đảm
nhiệm), nên không cần Trend/so sánh lịch sử, mỗi lần chạy là 1 bức ảnh độc
lập tại thời điểm gọi.

Output item (risk hoặc issue): `layer`, `rule`, `description`, `priority`,
`relatedAssigneeTask`, `nextAction`/`nextActionOptions`, `score`,
`detectedFrom` — thuần để hiển thị/phân tích, không tương ứng cột nào trên
Sheet (skill không ghi gì cả).

Phân loại Risk vs Issue theo quy ước PM cổ điển (giữ nguyên từ v1):
  Issue = sự thật đã xảy ra rồi (T1 trễ hạn, T2 effort đã vượt xa ước tính)
  Risk  = mọi rule còn lại — cảnh báo sớm, chưa chắc thành vấn đề
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

DEFAULT_THRESHOLDS = {
    "overdueGraceDays": 0,
    "stalledDays": 3,
    "estimateVarianceRatio": 1.5,
    "workHoursPerDay": 8,
    "highScoreThreshold": 6,
    "unassignedNearDeadlineDays": 2,
    "velocityDropMarginPct": 15,
    "notStartedGraceDays": 0,
    "cutoffHour": 18,
}


def days_between(from_iso: str, to_iso: str) -> int:
    d1 = datetime.strptime(from_iso, "%Y-%m-%d").date()
    d2 = datetime.strptime(to_iso, "%Y-%m-%d").date()
    return (d2 - d1).days


def priority_from_score(score: float, th: dict) -> str:
    # Vocabulary khớp đúng dropdown "Priority" trong tab Config của sheet thật:
    # Highest / High / Medium / Low.
    if score >= th["highScoreThreshold"]:
        return "Highest"
    if score >= th["highScoreThreshold"] - 2:
        return "High"
    if score >= 2:
        return "Medium"
    return "Low"


def make_item(
    *,
    layer: str,
    rule: str,
    description: str,
    detected_from: str,
    probability: float,
    impact: float,
    next_action_options: list[str],
    today: str,
    th: dict,
    related_assignee_task: str | None = None,
) -> dict:
    score = probability * impact
    return {
        "id": None,
        "layer": layer,
        "rule": rule,
        "dateDetected": today,
        "description": description,
        "priority": priority_from_score(score, th),
        "relatedAssigneeTask": related_assignee_task or detected_from,
        "nextAction": next_action_options[0] if next_action_options else "",
        "nextActionOptions": list(next_action_options or []),
        "score": score,
        "detectedFrom": detected_from,
    }


def _assignee_task_label(task: dict) -> str:
    if task.get("assignee"):
        return f"{task['assignee']} / {task['detectedFrom']}"
    return task["detectedFrom"]


# --- T1: Sub-task trễ hạn, chưa Done -> Issue ---------------------------------
def rule_T1_overdue(tasks: list[dict], today: str, th: dict) -> list[dict]:
    out = []
    for t in tasks:
        if t["isDone"] or not t.get("planEnd"):
            continue
        days_late = days_between(t["planEnd"], today)
        if days_late > th["overdueGraceDays"]:
            impact = 3 if days_late >= 7 else 2 if days_late >= 3 else 1
            out.append(
                make_item(
                    layer="Task",
                    rule="T1",
                    description=f'Sub-task "{t["title"]}" ({t.get("assignee") or "chưa gán người"}) đã trễ {days_late} ngày so với Plan End.',
                    detected_from=t["detectedFrom"],
                    probability=3,
                    impact=impact,
                    next_action_options=[
                        "Xác nhận lại deadline mới với PM/khách hàng",
                        "Bổ sung người hỗ trợ đẩy nhanh tiến độ",
                        "Giảm scope task nếu có thể",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=_assignee_task_label(t),
                )
            )
    return out


# --- T2: Effort vượt xa ước tính -> Issue -------------------------------------
def rule_T2_effort_overrun(tasks: list[dict], today: str, th: dict) -> list[dict]:
    out = []
    for t in tasks:
        if not t.get("estimateHours") or not t.get("actualHours") or t["estimateHours"] <= 0:
            continue
        ratio = t["actualHours"] / t["estimateHours"]
        if ratio > th["estimateVarianceRatio"]:
            out.append(
                make_item(
                    layer="Task",
                    rule="T2",
                    description=f'Sub-task "{t["title"]}" đã tốn {t["actualHours"]}h thực tế so với {t["estimateHours"]}h ước tính (x{ratio:.1f}).',
                    detected_from=t["detectedFrom"],
                    probability=2,
                    impact=3 if ratio > th["estimateVarianceRatio"] * 1.5 else 2,
                    next_action_options=[
                        "Re-estimate lại phần việc còn lại",
                        f'Trao đổi với {t.get("assignee") or "assignee"} về khó khăn phát sinh',
                        "Chia nhỏ task, tách phần khó ra xử lý riêng",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=_assignee_task_label(t),
                )
            )
    return out


# --- T3: Sub-task đứng yên >= N ngày -> Risk ----------------------------------
def rule_T3_stalled(tasks: list[dict], today: str, th: dict) -> list[dict]:
    out = []
    for t in tasks:
        if t["isDone"] or not t.get("lastUpdated"):
            continue
        idle_days = days_between(t["lastUpdated"], today)
        # Ngưỡng không nên cố định cho mọi task: task dự kiến làm nhiều ngày
        # (Plan End - Plan Start dài) đứng ở "In progress" suốt thời gian đó
        # là bình thường, không phải bị đứng yên. Nếu biết được thời lượng dự
        # kiến của task, lấy max(stalledDays, thời lượng đó) làm ngưỡng riêng;
        # task không có đủ Plan Start/End thì dùng lại stalledDays mặc định.
        duration = (
            days_between(t["planStart"], t["planEnd"]) if t.get("planStart") and t.get("planEnd") else None
        )
        threshold = max(duration, th["stalledDays"]) if duration and duration > 0 else th["stalledDays"]
        if idle_days >= threshold:
            out.append(
                make_item(
                    layer="Task",
                    rule="T3",
                    description=f'Sub-task "{t["title"]}" đứng yên (status không đổi) đã {idle_days} ngày.',
                    detected_from=t["detectedFrom"],
                    probability=2,
                    impact=2,
                    next_action_options=[
                        f'Hỏi {t.get("assignee") or "người phụ trách"} về tiến độ',
                        "Xem xét reassign task",
                        "Kiểm tra task có đang bị block bởi task khác không",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=_assignee_task_label(t),
                )
            )
    return out


# --- S1: %Done sprint hiện tại thấp hẳn sprint trước -> Risk ------------------
def _sprint_number(name: str | None) -> int | None:
    m = re.search(r"(\d+)", name or "")
    return int(m.group(1)) if m else None


def rule_S1_velocity_drop(tasks: list[dict], today: str, th: dict) -> list[dict]:
    by_sprint: dict[str, dict] = {}
    for t in tasks:
        if not t.get("sprint"):
            continue
        entry = by_sprint.setdefault(t["sprint"], {"total": 0, "done": 0})
        entry["total"] += 1
        if t["isDone"]:
            entry["done"] += 1

    sprints = sorted((s for s in by_sprint if _sprint_number(s) is not None), key=_sprint_number)
    if len(sprints) < 2:
        return []  # cần >=2 sprint tab có mặt trong cùng lần Scan mới so được

    prev_name, curr_name = sprints[-2], sprints[-1]
    prev, curr = by_sprint[prev_name], by_sprint[curr_name]
    prev_rate = (prev["done"] / prev["total"] * 100) if prev["total"] else 0
    curr_rate = (curr["done"] / curr["total"] * 100) if curr["total"] else 0

    if prev_rate - curr_rate >= th["velocityDropMarginPct"]:
        return [
            make_item(
                layer="Sprint",
                rule="S1",
                description=f"Velocity giảm: {curr_name} hoàn thành {curr_rate:.0f}% so với {prev_name} là {prev_rate:.0f}%.",
                detected_from=curr_name,
                probability=2,
                impact=3,
                next_action_options=[f"Rà soát scope {curr_name}", "Bổ sung người hỗ trợ", "Kiểm tra có task nào bị block hàng loạt không"],
                today=today,
                th=th,
                related_assignee_task=curr_name,
            )
        ]
    return []


# --- S2: Sprint có nguy cơ không kịp (team-wide) -> Risk ----------------------
def rule_S2_sprint_at_risk(
    tasks: list[dict],
    resource_plan_people: list[dict],
    today: str,
    sprint_end: str,
    sprint_name: str,
    th: dict,
    ot_by_person: dict[str, dict] | None = None,
    now_hour: int | None = None,
) -> list[dict]:
    by_person = compute_capacity_backlog_by_person(tasks, resource_plan_people, today, sprint_end, sprint_name, th, ot_by_person, now_hour)
    total_capacity = sum(cb["capacity"] for cb in by_person.values())
    total_backlog = sum(cb["backlog"] for cb in by_person.values())
    if total_backlog > total_capacity:
        return [
            make_item(
                layer="Sprint",
                rule="S2",
                description=f"{sprint_name} có nguy cơ không kịp tiến độ: dự kiến cần {total_backlog:.1f}h, thời gian còn lại {total_capacity:.1f}h.",
                detected_from=sprint_name,
                probability=3,
                impact=3,
                next_action_options=["Rà soát scope sprint, cắt bớt task ưu tiên thấp", "Bổ sung người/OT cả team", "Xin dời deadline sprint với stakeholder"],
                today=today,
                th=th,
                related_assignee_task=sprint_name,
            )
        ]
    return []


# --- M1: Bug trend theo module (đếm "Verify bug") -> Risk ---------------------
_BUG_STATUS_RE = re.compile(r"^verify bug$", re.IGNORECASE)


def rule_M1_bug_trend_by_module(tasks: list[dict], today: str, th: dict) -> list[dict]:
    by_category: dict[str, list[dict]] = {}
    for t in tasks:
        if _BUG_STATUS_RE.match((t.get("status") or "").strip()):
            category = t.get("category") or "Chưa rõ category"
            by_category.setdefault(category, []).append(t)

    out = []
    for category, bug_tasks in by_category.items():
        count = len(bug_tasks)
        refs = ", ".join(t["detectedFrom"] for t in bug_tasks)
        out.append(
            make_item(
                layer="Module",
                rule="M1",
                description=f'Category "{category}" có {count} sub-task đang ở trạng thái "Verify bug": {refs}.',
                detected_from=f"{category} (Verify bug)",
                probability=3,
                impact=3 if count >= 6 else 2 if count >= 3 else 1,
                next_action_options=[
                    "Rà soát lại danh sách bug đang chờ verify",
                    "Ưu tiên fix/verify trước khi nhận task mới",
                    "Phân công riêng 1 người tập trung verify bug",
                ],
                today=today,
                th=th,
                related_assignee_task=category,
            )
        )
    return out


# --- M2: Category tụt hậu so với chính deadline của nó -> Risk ----------------
def rule_M2_category_behind_own_deadline(tasks: list[dict], today: str, th: dict) -> list[dict]:
    by_category: dict[str, dict] = {}
    for t in tasks:
        if not t.get("category"):
            continue
        entry = by_category.setdefault(t["category"], {"starts": [], "ends": [], "total": 0, "done": 0})
        if t.get("planStart"):
            entry["starts"].append(t["planStart"])
        if t.get("planEnd"):
            entry["ends"].append(t["planEnd"])
        entry["total"] += 1
        if t["isDone"]:
            entry["done"] += 1

    out = []
    for category, entry in by_category.items():
        if not entry["starts"] or not entry["ends"] or entry["total"] == 0:
            continue
        min_start, max_end = min(entry["starts"]), max(entry["ends"])
        total_days = days_between(min_start, max_end)
        if total_days <= 0:
            continue
        elapsed_days = max(0, min(days_between(min_start, today), total_days))
        pct_elapsed = elapsed_days / total_days * 100
        pct_done = entry["done"] / entry["total"] * 100

        if pct_elapsed - pct_done >= th["velocityDropMarginPct"]:
            out.append(
                make_item(
                    layer="Module",
                    rule="M2",
                    description=f'Category "{category}" đang tụt hậu tiến độ so với deadline riêng: đã trôi qua {pct_elapsed:.0f}% thời gian nhưng chỉ {pct_done:.0f}% sub-task hoàn thành.',
                    detected_from=category,
                    probability=2,
                    impact=3,
                    next_action_options=[
                        f"Rà soát lại tiến độ category {category}",
                        "Bổ sung người hỗ trợ category này",
                        "Xem xét dời 1 phần scope category này sang sprint sau",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=category,
                )
            )
    return out


# --- P1: Nhân sự nghỉ -> cascade Sub-task/Module bị ảnh hưởng -> Risk ---------
def _group_consecutive_leave_dates(daily_hours: dict) -> list[tuple[str, str]]:
    """Ngày trong tuần có giá trị 0 tường minh = nghỉ (None = cuối tuần/chưa
    tới, KHÔNG phải nghỉ) -- xem ghi chú "chưa verify với dữ liệu thật" ở
    design.md. Gom các ngày nghỉ liên tiếp (theo lịch, không chỉ ngày làm
    việc) thành từng khoảng.
    """
    leave_dates = sorted(d for d, h in daily_hours.items() if h == 0)
    if not leave_dates:
        return []
    periods = []
    start = prev = leave_dates[0]
    for d in leave_dates[1:]:
        if days_between(prev, d) == 1:
            prev = d
        else:
            periods.append((start, prev))
            start = prev = d
    periods.append((start, prev))
    return periods


def rule_P1_leave_cascade(tasks: list[dict], resource_plan_people: list[dict], today: str, th: dict) -> list[dict]:
    tasks_by_assignee: dict[str, list[dict]] = {}
    for t in tasks:
        if t["isDone"] or not t.get("assignee"):
            continue
        tasks_by_assignee.setdefault(t["assignee"], []).append(t)

    out = []
    for person in resource_plan_people:
        code = person["assigneeCode"]
        for leave_start, leave_end in _group_consecutive_leave_dates(person["dailyHours"]):
            affected = [
                t
                for t in tasks_by_assignee.get(code, [])
                if t.get("planStart") and t.get("planEnd") and t["planStart"] <= leave_end and t["planEnd"] >= leave_start
            ]
            if not affected:
                continue
            task_refs = ", ".join(t["detectedFrom"] for t in affected)
            modules = sorted({t["category"] for t in affected if t.get("category")})
            module_label = ", ".join(modules) if modules else "chưa rõ category"
            when = leave_start if leave_start == leave_end else f"{leave_start} → {leave_end}"
            out.append(
                make_item(
                    layer="Person",
                    rule="P1",
                    # Description PHẢI bắt đầu đúng nguyên văn detected_from (kể
                    # cả dấu phẩy) để dedupe (scan.py) so khớp được với dòng đã
                    # ghi thật trên sheet — trước đây thiếu dấu phẩy nên không
                    # bao giờ khớp, risk cứ báo lặp lại dù đã ghi rồi. Nói rõ
                    # "sub-task" ngay trước ID để không ai hiểu nhầm ID là module.
                    description=f"{code}, nghỉ {when} — ảnh hưởng {len(affected)} sub-task {task_refs} thuộc category {module_label}.",
                    detected_from=f"{code}, nghỉ {when}",
                    probability=3,
                    impact=3 if len(affected) >= 3 else 2 if len(affected) >= 2 else 1,
                    next_action_options=[
                        "Reschedule các sub-task bị ảnh hưởng",
                        "Reassign cho người khác trong lúc nghỉ",
                        "Chấp nhận buffer, dời cả timeline category nếu không gấp",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=f"{code} / {task_refs}",
                )
            )
    return out


# --- P2: Quá tải 1 ngày (cùng Plan Start=Plan End, cùng assignee) -> Risk -----
def rule_P2_daily_overload(tasks: list[dict], today: str, th: dict) -> list[dict]:
    by_assignee_day: dict[tuple, dict] = {}
    for t in tasks:
        if (
            t["isDone"]
            or not t.get("assignee")
            or not t.get("planStart")
            or t["planStart"] != t.get("planEnd")
            or not t.get("estimateHours")
        ):
            continue
        key = (t["assignee"], t["planStart"])
        entry = by_assignee_day.setdefault(key, {"assignee": t["assignee"], "day": t["planStart"], "hours": 0.0, "tasks": []})
        entry["hours"] += t["estimateHours"]
        entry["tasks"].append(t["detectedFrom"])

    out = []
    for entry in by_assignee_day.values():
        # >=2 task khác nhau dồn vào cùng ngày mới tính là "bị xếp chồng lịch".
        # 1 task duy nhất mà tự nó estimate/re-estimate >8h (vd phát sinh vấn
        # đề nên phải sửa Re-estimate lên) KHÔNG phải lỗi xếp lịch — đó là
        # chuyện riêng của task đó (P4/S2 đã cover quá tải theo backlog rồi).
        if len(entry["tasks"]) >= 2 and entry["hours"] > th["workHoursPerDay"]:
            out.append(
                make_item(
                    layer="Person",
                    rule="P2",
                    description=f'{entry["assignee"]} bị xếp {entry["hours"]}h task trong ngày {entry["day"]}, vượt quá {th["workHoursPerDay"]}h/ngày.',
                    detected_from=entry["tasks"][0],
                    probability=3,
                    impact=2,
                    next_action_options=[f'OT {entry["assignee"]}', "Dời bớt task sang ngày làm việc kế tiếp", "San bớt 1 task cho người khác cùng role"],
                    today=today,
                    th=th,
                    related_assignee_task=f'{entry["assignee"]} / {", ".join(entry["tasks"])}',
                )
            )
    return out


# --- P3: Sub-task chưa Assignee, Plan End gần -> Risk -------------------------
def rule_P3_unassigned_near_deadline(tasks: list[dict], today: str, th: dict) -> list[dict]:
    out = []
    for t in tasks:
        if t["isDone"] or t.get("assignee") or not t.get("planEnd"):
            continue
        days_left = days_between(today, t["planEnd"])
        if days_left <= th["unassignedNearDeadlineDays"]:
            out.append(
                make_item(
                    layer="Person",
                    rule="P3",
                    description=f'Sub-task "{t["title"]}" còn {days_left} ngày tới hạn nhưng chưa có assignee/người phụ trách.',
                    detected_from=t["detectedFrom"],
                    probability=3,
                    impact=2,
                    next_action_options=["Gán người ngay", "Dời Plan End sang sau", "Giảm scope hoặc bỏ task nếu không còn quan trọng"],
                    today=today,
                    th=th,
                    related_assignee_task=t["detectedFrom"],
                )
            )
    return out


# --- Helper dùng chung cho P4 và S2 (Sprint layer) ----------------------------
def compute_person_capacity(
    daily_hours: dict,
    ot_daily_hours: dict,
    today: str,
    sprint_end: str,
    th: dict,
    now_hour: int | None = None,
) -> float:
    """Capacity = giờ làm bình thường (từ mốc `regular_start` tới hết sprint)
    + giờ OT (từ HÔM NAY tới hết sprint), cộng lại.

    `regular_start` phụ thuộc giờ đồng hồ THẬT lúc gọi, so với
    `th["cutoffHour"]` (mặc định 18h — coi như hết giờ làm việc thông
    thường):
      - Gọi TRƯỚC cutoff (vd buổi sáng/trong giờ làm) -> hôm nay CHƯA dùng
        hết giờ -> `regular_start` = hôm nay (tính đủ cả hôm nay).
      - Gọi SAU cutoff (vd buổi tối) -> hôm nay coi như đã dùng hết ->
        `regular_start` = ngày mai (như cũ).

    `now_hour` cho phép tiêm giờ giả để test (không phụ thuộc đồng hồ máy
    thật) — bỏ trống thì dùng giờ thật (`datetime.now().hour`).

    OT vẫn LUÔN tính từ hôm nay bất kể giờ nào gọi — vì OT là làm thêm ngoài
    giờ hành chính, không phụ thuộc đã hết giờ làm thông thường hay chưa.

    Ngày không có trong `daily_hours`/`ot_daily_hours` (ngoài phạm vi bảng)
    hoặc giá trị None/rỗng (cuối tuần/chưa điền/chưa đăng ký OT) đều tính 0.
    """
    now_hour = datetime.now().hour if now_hour is None else now_hour
    cutoff_hour = th.get("cutoffHour", 18)
    if now_hour < cutoff_hour:
        regular_start = today
    else:
        regular_start = (date.fromisoformat(today) + timedelta(days=1)).isoformat()

    regular = sum(h for d, h in daily_hours.items() if regular_start <= d <= sprint_end and h)
    overtime = sum(h for d, h in (ot_daily_hours or {}).items() if today <= d <= sprint_end and h)
    return regular + overtime


def compute_person_backlog(assignee_code: str, tasks: list[dict], sprint_name: str) -> float:
    return sum(
        t["remainingHours"]
        for t in tasks
        if t.get("assignee") == assignee_code and t.get("sprint") == sprint_name and not t["isDone"] and t.get("remainingHours") is not None
    )


def compute_capacity_backlog_by_person(
    tasks: list[dict],
    resource_plan_people: list[dict],
    today: str,
    sprint_end: str,
    sprint_name: str,
    th: dict,
    ot_by_person: dict[str, dict] | None = None,
    now_hour: int | None = None,
) -> dict[str, dict]:
    ot_by_person = ot_by_person or {}
    result = {}
    for person in resource_plan_people:
        code = person["assigneeCode"]
        result[code] = {
            "capacity": compute_person_capacity(person["dailyHours"], ot_by_person.get(code), today, sprint_end, th, now_hour),
            "backlog": compute_person_backlog(code, tasks, sprint_name),
        }
    return result


def compute_sprint_health(
    tasks: list[dict],
    resource_plan_people: list[dict],
    today: str,
    sprint_end: str,
    sprint_name: str,
    th: dict,
    ot_by_person: dict[str, dict] | None = None,
    now_hour: int | None = None,
) -> dict:
    """Tổng backlog/capacity CẢ TEAM — LUÔN trả về số liệu (khác S2, chỉ sinh
    risk khi vượt ngưỡng) — dùng cho mục "Sức khỏe Sprint" trong draft, PM cần
    thấy con số này mỗi lần chạy, kể cả khi sprint đang ổn.
    """
    by_person = compute_capacity_backlog_by_person(tasks, resource_plan_people, today, sprint_end, sprint_name, th, ot_by_person, now_hour)
    total_capacity = sum(cb["capacity"] for cb in by_person.values())
    total_backlog = sum(cb["backlog"] for cb in by_person.values())
    return {
        "sprintName": sprint_name,
        "totalBacklog": total_backlog,
        "totalCapacity": total_capacity,
        "onTrack": total_backlog <= total_capacity,
    }


# --- P4: Quá tải theo tồn đọng CẢ SPRINT (không chỉ 1 ngày) -> Risk -----------
def rule_P4_sprint_backlog_overload(
    tasks: list[dict],
    resource_plan_people: list[dict],
    today: str,
    sprint_end: str,
    sprint_name: str,
    th: dict,
    ot_by_person: dict[str, dict] | None = None,
    now_hour: int | None = None,
) -> list[dict]:
    out = []
    by_person = compute_capacity_backlog_by_person(tasks, resource_plan_people, today, sprint_end, sprint_name, th, ot_by_person, now_hour)
    for code, cb in by_person.items():
        if cb["backlog"] > cb["capacity"]:
            deficit = cb["backlog"] - cb["capacity"]
            out.append(
                make_item(
                    layer="Person",
                    rule="P4",
                    # Description PHẢI bắt đầu bằng đúng nguyên văn detected_from
                    # để dedupe so khớp được (trước đây detected_from có thêm
                    # ", sprint {sprint_name}" không xuất hiện ở đâu cả trên
                    # sheet thật -> risk cứ báo lặp lại dù đã ghi rồi).
                    description=f'{code}, sprint {sprint_name}: tồn đọng {cb["backlog"]:.1f}h trong khi capacity còn lại tới hết sprint chỉ {cb["capacity"]:.1f}h (thiếu {deficit:.1f}h).',
                    detected_from=f"{code}, sprint {sprint_name}",
                    probability=3,
                    impact=3 if deficit >= 16 else 2,
                    next_action_options=["OT bù giờ", "San bớt task sang người khác", "Xin dời deadline sprint"],
                    today=today,
                    th=th,
                    related_assignee_task=code,
                )
            )
    return out


# --- T4: Chưa bắt đầu dù đã tới Plan Start -> Risk ----------------------------
def rule_T4_not_started(tasks: list[dict], today: str, th: dict) -> list[dict]:
    out = []
    for t in tasks:
        if t["isDone"] or not t.get("planStart"):
            continue
        if t.get("actualHours"):
            continue  # đã ghi nhận effort thực tế -> coi như đã bắt đầu
        days_past_start = days_between(t["planStart"], today)
        if days_past_start > th["notStartedGraceDays"]:
            out.append(
                make_item(
                    layer="Task",
                    rule="T4",
                    description=f'Sub-task "{t["title"]}" ({t.get("assignee") or "chưa gán người"}) đã quá Plan Start {days_past_start} ngày nhưng chưa ghi nhận effort thực tế nào — có thể đang bị block.',
                    detected_from=t["detectedFrom"],
                    probability=3,
                    impact=3 if days_past_start >= 5 else 2 if days_past_start >= 2 else 1,
                    next_action_options=[
                        f'Hỏi {t.get("assignee") or "người phụ trách"} lý do chưa bắt đầu / đang chờ gì',
                        "Kiểm tra task có đang phụ thuộc (blocked by) task khác chưa xong không",
                        "Dời Plan Start sang ngày thực tế có thể bắt đầu",
                    ],
                    today=today,
                    th=th,
                    related_assignee_task=_assignee_task_label(t),
                )
            )
    return out


def run_rules(
    *,
    tasks: list[dict],
    resource_plan_people: list[dict] | None = None,
    sprint_end: str | None = None,
    sprint_name: str | None = None,
    thresholds: dict | None = None,
    today: str | None = None,
    ot_by_person: dict[str, dict] | None = None,
) -> dict:
    """Entrypoint DUY NHẤT scan.py cần gọi — chạy đủ 12 rule theo đúng thứ tự
    layer. `resource_plan_people`/`sprint_end`/`sprint_name` là optional:
    thiếu 1 trong 3 thì bỏ qua P1/P4/S2 (cần dữ liệu Resource plan + biết
    sprint đang phân tích), các rule còn lại vẫn chạy bình thường.
    `ot_by_person` (assigneeCode -> dailyHours OT, optional) cộng thêm vào
    capacity của P4/S2 — xem `compute_person_capacity()`.

    Skill này chỉ ĐỌC + ĐÁNH GIÁ, không ghi gì vào Sheet — nên không cần so
    sánh với lần chạy trước (không có Trend/resolvedRisks, mỗi lần chạy là 1
    bức ảnh độc lập tại thời điểm gọi).
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    today = today or date.today().isoformat()
    resource_plan_people = resource_plan_people or []

    issues = [
        *rule_T1_overdue(tasks, today, th),
        *rule_T2_effort_overrun(tasks, today, th),
    ]

    risks = [
        *rule_T3_stalled(tasks, today, th),
        *rule_T4_not_started(tasks, today, th),
        *rule_P2_daily_overload(tasks, today, th),
        *rule_P3_unassigned_near_deadline(tasks, today, th),
        *rule_S1_velocity_drop(tasks, today, th),
        *rule_M1_bug_trend_by_module(tasks, today, th),
        *rule_M2_category_behind_own_deadline(tasks, today, th),
    ]

    if resource_plan_people and sprint_end and sprint_name:
        risks += rule_P1_leave_cascade(tasks, resource_plan_people, today, th)
        risks += rule_P4_sprint_backlog_overload(tasks, resource_plan_people, today, sprint_end, sprint_name, th, ot_by_person)
        risks += rule_S2_sprint_at_risk(tasks, resource_plan_people, today, sprint_end, sprint_name, th, ot_by_person)

    return {"risks": risks, "issues": issues}
