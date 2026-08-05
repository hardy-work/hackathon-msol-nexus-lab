#!/usr/bin/env python
"""Action 2: Apply — đọc state/pending-apply.json (agent ghi bằng Write tool
sau khi diễn giải phản hồi tự nhiên của PM), ghi thật vào Risk/Issue
management. Item có `id` -> update đúng dòng đó (rủi ro chủ động, thường đổi
Status Pending -> Open + điền Next Action); item không có `id` -> tạo dòng
mới, ID tự tăng (rủi ro bị động).

Chạy: `python scripts/apply.py` (không tham số — mọi input nằm trong
state/pending-apply.json).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts" / "lib"))

from google_auth import mint_access_token  # noqa: E402
from load_env import load_env  # noqa: E402
from sheets_client import SheetsApiError, batch_update_values, get_values, update_values  # noqa: E402

OUTPUT_COLUMNS = ["A", "B", "C", "D", "E", "F", "G", "H"]  # ID..Notes, thứ tự cố định


def _format_date_dmy(iso_date: str) -> str:
    """"YYYY-MM-DD" -> "D-M-YYYY" (không zero-pad) — khớp đúng định dạng ngày
    đã dùng xuyên suốt sheet thật (vd "27-7-2026"). Ghi tường minh thay vì để
    Google Sheets tự parse/format chuỗi ISO — đã thấy 2 tab Risk/Issue hiển
    thị KHÁC NHAU (1 tab giữ nguyên literal ISO, tab kia tự đổi sang D-M-Y)
    tuỳ định dạng cell có sẵn của từng cột, không đáng tin cậy.
    """
    y, m, d = iso_date.split("-")
    return f"{int(d)}-{int(m)}-{y}"


def load_config() -> dict:
    with open(SKILL_DIR / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _next_id_number(existing_rows: list[list], prefix: str) -> int:
    max_n = 0
    for row in existing_rows:
        if row and row[0] and row[0].startswith(prefix + "-"):
            try:
                max_n = max(max_n, int(row[0].split("-")[1]))
            except (ValueError, IndexError):
                continue
    return max_n + 1


def write_items(file_id: str, tab_name: str, id_prefix: str, items: list[dict], token: str) -> list[dict]:
    if not items:
        return []

    rows = get_values(file_id, f"'{tab_name}'!A2:H500", token)
    written = []
    field_to_col = {"status": "G", "nextAction": "F", "notes": "H", "priority": "D"}

    updates = []
    for item in items:
        if not item.get("id"):
            continue
        row_index = next((i + 2 for i, row in enumerate(rows) if row and row[0] == item["id"]), None)
        if row_index is None:
            continue  # id không tồn tại trên sheet -- bỏ qua, KHÔNG tự tạo mới thay
        for field, col in field_to_col.items():
            if field in item:
                updates.append({"range": f"'{tab_name}'!{col}{row_index}", "values": [[item[field]]]})
        written.append({"id": item["id"], "action": "update"})

    if updates:
        batch_update_values(file_id, updates, token)

    new_rows = []
    next_n = _next_id_number(rows, id_prefix)
    for item in items:
        if item.get("id"):
            continue
        new_id = f"{id_prefix}-{next_n:03d}"
        next_n += 1
        new_rows.append(
            [
                new_id,
                _format_date_dmy(item.get("dateDetected") or date.today().isoformat()),
                item["description"],
                item["priority"],
                item["relatedAssigneeTask"],
                item["nextAction"],
                item.get("status", "In progress"),
                item.get("notes", ""),
            ]
        )
        written.append({"id": new_id, "action": "create"})

    if new_rows:
        start_row = len(rows) + 2  # header ở row1, rows[] bắt đầu từ row2
        end_row = start_row + len(new_rows) - 1
        update_values(file_id, f"'{tab_name}'!A{start_row}:H{end_row}", new_rows, token)

    return written


def find_pending_draft() -> Path | None:
    drafts_dir = SKILL_DIR / "drafts"
    if not drafts_dir.exists():
        return None
    candidates = sorted(p for p in drafts_dir.glob("draft-*.md") if not p.name.endswith(".applied.md"))
    return candidates[-1] if candidates else None


def append_audit_log(line: str) -> None:
    with open(SKILL_DIR / "risk-assessment-audit.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_apply() -> dict:
    pending_path = SKILL_DIR / "state" / "pending-apply.json"
    if not pending_path.exists():
        return {
            "ok": False,
            "reason": "no_pending_apply",
            "message": "Chưa có state/pending-apply.json — ghi file này bằng Write tool trước khi chạy apply.py",
        }

    with open(pending_path, "r", encoding="utf-8") as f:
        pending = json.load(f)

    config = load_config()
    env = load_env(SKILL_DIR / ".env")
    key_file = SKILL_DIR / env.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", "service-account.json")

    try:
        token = mint_access_token(str(key_file))
        file_id = config["fileId"]

        written_risks = write_items(file_id, config["output"]["riskTab"]["name"], "R", pending.get("risks", []), token)
        written_issues = write_items(file_id, config["output"]["issueTab"]["name"], "I", pending.get("issues", []), token)

        draft_path = find_pending_draft()
        if draft_path:
            draft_path.rename(draft_path.with_name(draft_path.stem + ".applied.md"))

        new_count = sum(1 for w in written_risks + written_issues if w["action"] == "create")
        updated_count = sum(1 for w in written_risks + written_issues if w["action"] == "update")
        by = pending.get("appliedBy", "PM")
        audit_line = (
            f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] ACTION=apply SOURCE=gg-sheet '
            f'NEW={new_count} UPDATED={updated_count} BY="{by}" '
            f'CHANGES="{len(written_risks)} risk, {len(written_issues)} issue"'
        )
        append_audit_log(audit_line)

        pending_path.unlink()

        return {"ok": True, "written": {"risks": written_risks, "issues": written_issues}, "auditLine": audit_line}
    except SheetsApiError as e:
        return {"ok": False, "reason": "write_error", "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "error", "message": str(e)}


def main():
    print(json.dumps(run_apply(), ensure_ascii=False))


if __name__ == "__main__":
    main()
