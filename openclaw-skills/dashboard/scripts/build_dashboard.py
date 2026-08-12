#!/usr/bin/env python
"""Dashboard — đọc "Summary project" + "Risk management" + "Isssue
management" (Google Sheet đang dùng chung), tổng hợp thành 1 bản tóm tắt sức
khỏe dự án, và ghi lại vào tab "Dashboard" (tự tạo nếu chưa có, xoá sạch rồi
ghi lại — CHỈ đụng đúng tab này, không đụng tab nào khác).

Ghi chỉ chạy khi có `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` trong `.env` — nếu
chưa cấu hình Service Account, script vẫn chạy được, chỉ bỏ qua bước ghi
(`written: false`) và trả về narrative để xem trong chat như bình thường.

Chạy: `python3 scripts/build_dashboard.py` (script tự resolve mọi file theo
vị trí của chính nó, không phụ thuộc cwd lúc gọi).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts" / "lib"))

from dashboard_rows import build_dashboard_rows  # noqa: E402
from google_auth import mint_access_token  # noqa: E402
from load_env import load_env  # noqa: E402
from narrative import build_narrative  # noqa: E402
from parse import find_current_sprint_row, read_status_tab  # noqa: E402
from sheets_client import SheetsApiError, get_values  # noqa: E402
from sheets_write import SheetsApiError as WriteApiError  # noqa: E402
from sheets_write import publish_dashboard  # noqa: E402
from tally import tally_by_status, top_high_priority_open  # noqa: E402


def load_config() -> dict | None:
    config_path = SKILL_DIR / "config.json"
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run() -> dict:
    config = load_config()
    if config is None or not config.get("fileId"):
        return {
            "ok": False,
            "reason": "no_config",
            "askPm": "Cho mình xin link Google Sheet đang dùng để theo dõi tiến độ, và tên 3 tab: Summary project, Risk management, Isssue management (nếu khác tên mặc định).",
        }

    env = load_env(SKILL_DIR / ".env")
    api_key = env.get("GOOGLE_SHEETS_API_KEY")
    if not api_key:
        return {"ok": False, "reason": "no_config", "message": "Thiếu GOOGLE_SHEETS_API_KEY trong .env"}

    file_id = config["fileId"]
    tabs = config["sourceTabs"]

    try:
        summary_rows = get_values(file_id, f"'{tabs['summaryProject']['name']}'!A1:K30", api_key)
        risk_rows = get_values(file_id, f"'{tabs['riskManagement']['name']}'!A1:K500", api_key)
        issue_rows = get_values(file_id, f"'{tabs['issueManagement']['name']}'!A1:K500", api_key)
    except SheetsApiError as e:
        return {"ok": False, "reason": "read_error", "message": str(e)}

    sprint = find_current_sprint_row(summary_rows)
    risks = read_status_tab(risk_rows)
    issues = read_status_tab(issue_rows)

    risk_tally = tally_by_status(risks)
    issue_tally = tally_by_status(issues)
    top_risks = top_high_priority_open(risks)

    narrative = build_narrative(sprint, risk_tally, issue_tally, top_risks)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    result = {
        "ok": True,
        "narrative": narrative,
        "summary": {
            "sprint": sprint,
            "risk": risk_tally,
            "issue": issue_tally,
            "topHighPriorityRisks": top_risks,
        },
        "written": False,
    }

    key_file_rel = env.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_file_rel:
        return result

    output_tab_name = config.get("outputTab", {}).get("name", "Dashboard")
    key_file = SKILL_DIR / key_file_rel
    try:
        token = mint_access_token(str(key_file))
        rows = build_dashboard_rows(sprint, risk_tally, issue_tally, top_risks, generated_at)
        sheet_id = publish_dashboard(file_id, output_tab_name, rows, token)
    except (WriteApiError, OSError, KeyError, ValueError) as e:
        result["writeError"] = str(e)
        return result

    result["written"] = True
    result["dashboardTabUrl"] = f"https://docs.google.com/spreadsheets/d/{file_id}/edit#gid={sheet_id}"
    return result


def main():
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
