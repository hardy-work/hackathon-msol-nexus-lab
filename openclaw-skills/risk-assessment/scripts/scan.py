#!/usr/bin/env python
"""Scan — đọc Sprint tab + Resource plan + Overtime + Risk/Issue management
thật, chạy rule engine, ghi draft (`drafts/`). Skill này CHỈ ĐỌC + ĐÁNH GIÁ —
KHÔNG BAO GIỜ ghi gì vào Sheet thật (việc ghi risk/issue vào Sheet do skill
khác — "daily report" — đảm nhiệm).

Chạy: `python scripts/scan.py` (script tự resolve mọi file theo vị trí của
chính nó, không phụ thuộc cwd lúc gọi).
"""

from __future__ import annotations

import json
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


def split_existing_by_status(existing_items: list[dict], today: str) -> tuple[list[dict], list[dict]]:
    """Chia dòng đã có sẵn trên Risk/Issue management theo Status — PM cần
    thấy "cái gì đang treo" tách biệt hẳn khỏi phần đánh giá của rule engine.

    - "Chưa xử lý": Status="Open" HOẶC "Pending" (dev tự báo qua daily report,
      PM chưa chốt phương án) — với PM cả 2 đều là "chưa ai làm gì cả".
    - "Đang xử lý": Status="In progress", đính kèm `idleDays` (số ngày kể từ
      Date Detected).
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

        result = run_rules(
            tasks=tasks,
            resource_plan_people=people,
            sprint_end=sprint_end,
            sprint_name=current_sprint_name,
            thresholds=config["thresholds"],
            today=today,
            ot_by_person=ot_by_person,
        )

        risk_existing = read_output_tab(file_id, config["output"]["riskTab"]["name"], token)
        issue_existing = read_output_tab(file_id, config["output"]["issueTab"]["name"], token)

        existing_open, existing_in_progress = split_existing_by_status(risk_existing + issue_existing, today)
        sprint_health = compute_sprint_health(tasks, people, today, sprint_end, current_sprint_name, config["thresholds"], ot_by_person)

        draft_text = build_draft(
            today=today,
            project_title=config.get("projectTitle", "dự án"),
            existing_open=existing_open,
            existing_in_progress=existing_in_progress,
            passive_risks=result["risks"],
            passive_issues=result["issues"],
            sprint_health=sprint_health,
        )

        drafts_dir = SKILL_DIR / "drafts"
        drafts_dir.mkdir(exist_ok=True)
        draft_path = drafts_dir / f"draft-{today}.md"
        draft_path.write_text(draft_text, encoding="utf-8")

        return {
            "ok": True,
            "draftPath": str(draft_path),
            "narrative": draft_text,
            "summary": {
                "existingOpen": len(existing_open),
                "existingInProgress": len(existing_in_progress),
                "passiveRisks": len(result["risks"]),
                "passiveIssues": len(result["issues"]),
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
