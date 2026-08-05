#!/usr/bin/env python
"""Action 1: Scan — đọc Sprint tab + Resource plan + Risk/Issue management
thật, chạy rule engine, ghi draft + snapshot. KHÔNG BAO GIỜ ghi gì vào Sheet
thật (chỉ đọc + ghi file local `drafts/`, `state/`).

Chạy: `python scripts/scan.py` (script tự resolve mọi file theo vị trí của
chính nó, không phụ thuộc cwd lúc gọi).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts" / "lib"))

from draft import build_draft  # noqa: E402
from google_auth import mint_access_token  # noqa: E402
from load_env import load_env  # noqa: E402
from normalize import normalize_sprint_rows, parse_date  # noqa: E402
from overtime import build_ot_by_assignee_code, parse_overtime  # noqa: E402
from resource_plan import parse_resource_plan  # noqa: E402
from rule_engine import compute_sprint_health, days_between, run_rules  # noqa: E402
from sheets_client import SheetsApiError, get_values  # noqa: E402
from summary_project import find_sprint_end  # noqa: E402

# Status thật trên dropdown Config tab: Open, In progress, Done, Pending,
# Cancel — KHÔNG có "Closed"/"Resolved". Dòng "Cancel" coi như đã đóng, phải
# loại khỏi tập "đang mở" để không bị dedupe chặn tái phát hiện mãi mãi.
CLOSED_STATUSES = ("Done", "Cancel")


def load_config() -> dict | None:
    config_path = SKILL_DIR / "config.json"
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_task_status_log() -> dict:
    log_path = SKILL_DIR / "state" / "task-status-log.json"
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def apply_status_log(tasks: list[dict], today: str) -> list[dict]:
    """Sprint tab KHÔNG có cột lưu ngày status đổi lần cuối, nên phải tự suy
    ra bằng cách so sánh với lần Scan gần nhất — cần cho rule T3 (đứng yên).
    """
    log = load_task_status_log()
    next_log = {}
    for t in tasks:
        prev = log.get(t["detectedFrom"])
        if prev and prev["status"] == t["status"]:
            t["lastUpdated"] = prev["since"]
        else:
            t["lastUpdated"] = today
        next_log[t["detectedFrom"]] = {"status": t["status"], "since": t["lastUpdated"]}

    state_dir = SKILL_DIR / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "task-status-log.json").write_text(
        json.dumps(next_log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return tasks


def load_latest_snapshot(today: str) -> tuple[dict | None, str | None]:
    """Trả `(snapshot, date)` — `date` là ngày của snapshot trước đó tìm được
    (lấy từ tên file `risk-snapshot-YYYY-MM-DD.json`), `None` nếu chưa từng
    Scan lần nào trước đó (dùng để ẩn hẳn mục "Đã hết rủi ro" trong draft,
    thay vì hiện "hiện không có" gây hiểu nhầm là đã so sánh mà không có gì).
    """
    state_dir = SKILL_DIR / "state"
    if not state_dir.exists():
        return None, None
    files = sorted(p for p in state_dir.glob("risk-snapshot-*.json") if p.stem != f"risk-snapshot-{today}")
    if not files:
        return None, None
    latest = files[-1]
    snapshot_date = latest.stem.removeprefix("risk-snapshot-")
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f), snapshot_date


def read_output_tab(file_id: str, tab_name: str, token: str) -> list[dict]:
    """Đọc dòng dữ liệu thật (bỏ header) từ Risk/Issue management — schema cố
    định A-H: ID | Date Detected | Description | Priority | Related
    Assignee/Task | Next Action | Status | Notes.
    """
    rows = get_values(file_id, f"'{tab_name}'!A2:H500", token)
    items = []
    for row in rows:
        if not row or not row[0]:
            continue
        row = list(row) + [""] * (8 - len(row))
        items.append(
            {
                "id": row[0],
                "dateDetected": row[1],
                "description": row[2],
                "priority": row[3],
                "relatedAssigneeTask": row[4],
                "nextAction": row[5],
                "status": row[6],
                "notes": row[7],
            }
        )
    return items


def _detected_from_matches(detected: str, text: str) -> bool:
    """So khớp `detected` như 1 token trọn vẹn trong `text`, không phải
    substring thô — tránh việc TaskID ngắn (vd "AU-1") bị coi là trùng với
    TaskID dài hơn cùng tiền tố (vd "AU-10", "AU-11") chỉ vì "AU-1" là chuỗi
    con của "AU-10".
    """
    if not text:
        return False
    pattern = r"(?<![\w-])" + re.escape(detected) + r"(?![\w-])"
    return re.search(pattern, text) is not None


def dedupe_against_existing(candidates: list[dict], existing_items: list[dict]) -> list[dict]:
    """Loại risk/issue bị động trùng với dòng đã có sẵn trên sheet (đang mở,
    KHÔNG phải Done/Cancel) — match theo `detectedFrom` xuất hiện (dạng token
    trọn vẹn) trong "Related Assignee/Task" hoặc "Description" của dòng đã có.

    Đây là heuristic — sheet schema mới không có cột detectedFrom/rule riêng
    để match chính xác tuyệt đối (đã đơn giản hoá theo template thật, xem
    design.md).
    """
    open_existing = [i for i in existing_items if i["status"] not in CLOSED_STATUSES]
    out = []
    for c in candidates:
        detected = c["detectedFrom"]
        if any(
            _detected_from_matches(detected, i["relatedAssigneeTask"]) or _detected_from_matches(detected, i["description"])
            for i in open_existing
        ):
            continue
        out.append(c)
    return out


def split_existing_by_status(existing_items: list[dict], today: str) -> tuple[list[dict], list[dict]]:
    """Chia dòng đã có sẵn trên Risk/Issue management theo Status — PM cần
    thấy "cái gì đang treo" tách biệt hẳn khỏi "cái gì mới phát hiện hôm nay".

    - "Chưa xử lý": Status="Open" HOẶC "Pending" (dev tự báo qua daily report,
      PM chưa chốt phương án) — với PM cả 2 đều là "chưa ai làm gì cả".
    - "Đang xử lý": Status="In progress", đính kèm `idleDays` (số ngày kể từ
      Date Detected — dùng thẳng cột này làm mốc "từ khi nào bắt đầu 'In
      progress'", vì mọi dòng mới ghi đều khởi tạo Status="In progress" ngay
      từ đầu, xem make_item() trong rule_engine.py).
    - Done/Cancel: loại hẳn (đã đóng, không còn liên quan).
    """
    open_items = [i for i in existing_items if i["status"] in ("Open", "Pending")]
    in_progress_items = []
    for i in existing_items:
        if i["status"] != "In progress":
            continue
        detected_iso = parse_date(i["dateDetected"])
        idle_days = days_between(detected_iso, today) if detected_iso else None
        in_progress_items.append({**i, "idleDays": idle_days})
    return open_items, in_progress_items


def run_scan() -> dict:
    config = load_config()
    if config is None or not config.get("source"):
        return {
            "ok": False,
            "reason": "no_config",
            "askPm": "Dự án này bạn đang theo dõi tiến độ bằng Google Sheet hay Jira? Mình sẽ cấu hình risk-assessment theo đúng nguồn đó.",
        }

    if config["source"] != "gg-sheet":
        return {"ok": False, "reason": "error", "message": "source=jira chưa hỗ trợ ở v2 (chỉ port lại gg-sheet)"}

    env = load_env(SKILL_DIR / ".env")
    key_file = SKILL_DIR / env.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", "service-account.json")

    try:
        token = mint_access_token(str(key_file))

        file_id = config["fileId"]
        current_sprint_name = config["currentSprint"]
        sprint_tab = next(t for t in config["sprintTabs"] if t["name"] == current_sprint_name)

        rows = get_values(file_id, f"'{sprint_tab['name']}'!A{sprint_tab['dataStartRow']}:S500", token)
        tasks = normalize_sprint_rows(
            rows,
            sprint_tab["columns"],
            sprint_tab["name"],
            config["statusDoneValues"],
            sprint_tab["name"],
            start_row=sprint_tab["dataStartRow"],
        )

        today = date.today().isoformat()
        tasks = apply_status_log(tasks, today)

        rp_config = config["resourcePlan"]
        rp_rows = get_values(file_id, f"'{rp_config['tabName']}'!A1:AZ40", token)
        people = parse_resource_plan(rp_rows, rp_config["personCodeMap"], year=rp_config["year"])

        ot_tab_name = config.get("overtimeTab", {}).get("tabName", "Overtime")
        ot_rows = get_values(file_id, f"'{ot_tab_name}'!A1:AZ40", token)
        overtime_people = parse_overtime(ot_rows, year=rp_config["year"])
        ot_by_person = build_ot_by_assignee_code(overtime_people, people)

        summary_tab_name = config.get("summaryProjectTab", {}).get("tabName", "Summary project")
        summary_rows = get_values(file_id, f"'{summary_tab_name}'!A1:N30", token)
        sprint_end = find_sprint_end(summary_rows, current_sprint_name)
        if not sprint_end:
            plan_ends = [t["planEnd"] for t in tasks if t.get("planEnd")]
            sprint_end = max(plan_ends) if plan_ends else today

        snapshot, previous_snapshot_date = load_latest_snapshot(today)

        result = run_rules(
            tasks=tasks,
            resource_plan_people=people,
            sprint_end=sprint_end,
            sprint_name=current_sprint_name,
            snapshot=snapshot,
            thresholds=config["thresholds"],
            today=today,
            ot_by_person=ot_by_person,
        )

        risk_existing = read_output_tab(file_id, config["output"]["riskTab"]["name"], token)
        issue_existing = read_output_tab(file_id, config["output"]["issueTab"]["name"], token)

        existing_open, existing_in_progress = split_existing_by_status(risk_existing + issue_existing, today)
        passive_risks = dedupe_against_existing(result["risks"], risk_existing)
        passive_issues = dedupe_against_existing(result["issues"], issue_existing)
        sprint_health = compute_sprint_health(tasks, people, today, sprint_end, current_sprint_name, ot_by_person)

        draft_text = build_draft(
            today=today,
            project_title=config.get("projectTitle", "dự án"),
            existing_open=existing_open,
            existing_in_progress=existing_in_progress,
            passive_risks=passive_risks,
            passive_issues=passive_issues,
            resolved_risks=result["resolvedRisks"],
            previous_snapshot_date=previous_snapshot_date,
            sprint_health=sprint_health,
            thresholds=config["thresholds"],
        )

        drafts_dir = SKILL_DIR / "drafts"
        drafts_dir.mkdir(exist_ok=True)
        draft_path = drafts_dir / f"draft-{today}.md"
        draft_path.write_text(draft_text, encoding="utf-8")

        state_dir = SKILL_DIR / "state"
        state_dir.mkdir(exist_ok=True)
        (state_dir / f"risk-snapshot-{today}.json").write_text(
            json.dumps({"risks": passive_risks, "issues": passive_issues}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "ok": True,
            "draftPath": str(draft_path),
            "narrative": draft_text,
            "summary": {
                "existingOpen": len(existing_open),
                "existingInProgress": len(existing_in_progress),
                "passiveRisks": len(passive_risks),
                "passiveIssues": len(passive_issues),
                "resolvedRisks": len(result["resolvedRisks"]),
                "sprintOnTrack": sprint_health["onTrack"] if sprint_health else None,
            },
        }
    except SheetsApiError as e:
        return {"ok": False, "reason": "read_error", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — báo lỗi verbatim cho PM, không tự retry
        return {"ok": False, "reason": "error", "message": str(e)}


def main():
    print(json.dumps(run_scan(), ensure_ascii=False))


if __name__ == "__main__":
    main()
