"""MCP server bridging a PM's Google Sheet project tracker (the "Handy-style"
sprint-tracker template used across MOR projects) via a Google Service
Account.

Unlike a hardcoded-column integration, this server DETECTS each sprint tab's
column layout at runtime (by reading its header rows + merged cells), and
DETECTS the Status enum from that spreadsheet's own "Config" tab. This is
required because different projects copy the same template with slightly
different column order / tab naming (verified against two real projects —
see PLAN-slack-pm-tracker.md). Scope is intentionally limited to per-sprint
task tabs (tab name ending in "Sprint N") + each tab's own rollup/aggregate
row for progress reporting — no dependency on a dedicated summary tab.

Config (env vars):
  GSHEET_SPREADSHEET_ID   - the sheet's ID (from its URL)
  GSHEET_SERVICE_ACCOUNT  - path to the service-account JSON key
                            (default: service-account.json next to this file)
"""

import os
import re
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SPREADSHEET_ID = os.environ["GSHEET_SPREADSHEET_ID"]
KEY_PATH = os.environ.get(
    "GSHEET_SERVICE_ACCOUNT",
    os.path.join(os.path.dirname(__file__), "service-account.json"),
)

CONFIG_TAB = "Config"
HEADER_SCAN_ROWS = 15  # how far down to look for the "No." header anchor
HEADER_BLOCK_ROWS = 3  # group row + subheader row + unit row
MAX_COLS = 26  # A..Z is enough for every template seen so far

# canonical field -> is it writable by the bot (progress/remaining are
# spreadsheet formulas and must never be written directly)
NO_KEY = "no"
READONLY_KEYS = {NO_KEY, "progress", "remaining_h"}

mcp = FastMCP("gsheet-pm-tracker")

_creds = service_account.Credentials.from_service_account_file(
    KEY_PATH, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
_svc = build("sheets", "v4", credentials=_creds)

_sheet_meta_cache: dict | None = None
_column_map_cache: dict[str, dict] = {}
_status_enum_cache: list[str] | None = None


def _col_letter(idx: int) -> str:
    """0-indexed column number -> spreadsheet letter(s)."""
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_meta() -> dict:
    global _sheet_meta_cache
    if _sheet_meta_cache is None:
        _sheet_meta_cache = (
            _svc.spreadsheets()
            .get(spreadsheetId=SPREADSHEET_ID, fields="sheets(properties(sheetId,title),merges)")
            .execute()
        )
    return _sheet_meta_cache


def _get_sheet_id(tab: str) -> int:
    for sheet in _sheet_meta()["sheets"]:
        if sheet["properties"]["title"] == tab:
            return sheet["properties"]["sheetId"]
    raise ValueError(f"Tab not found: {tab!r}")


def _get_merges(tab: str) -> list:
    for sheet in _sheet_meta()["sheets"]:
        if sheet["properties"]["title"] == tab:
            return sheet.get("merges", [])
    return []


def _values_get(range_: str, render="FORMATTED_VALUE"):
    return (
        _svc.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=range_, valueRenderOption=render)
        .execute()
        .get("values", [])
    )


def _values_update(range_: str, values: list):
    _svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_,
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def _copy_row(tab: str, src_row: int, dst_row: int, start_col: int, end_col: int, paste_type: str):
    """Copy formatting/formulas from one row to another (both 1-indexed),
    columns [start_col, end_col) 0-indexed. Used so newly appended rows
    inherit the borders/fill/formulas of the row above them."""
    sheet_id = _get_sheet_id(tab)
    grid_range = lambda row: {
        "sheetId": sheet_id,
        "startRowIndex": row - 1,
        "endRowIndex": row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }
    _svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "requests": [
                {
                    "copyPaste": {
                        "source": grid_range(src_row),
                        "destination": grid_range(dst_row),
                        "pasteType": paste_type,
                    }
                }
            ]
        },
    ).execute()


def _classify_column(label: str) -> str | None:
    """Map a combined (possibly multi-row) header label to a canonical
    field key, or None if this column isn't one we care about."""
    n = re.sub(r"\s+", " ", label.replace("\n", " ")).strip().lower()
    if n in ("no.", "no"):
        return NO_KEY
    if "sub-task" in n or "subtask" in n:
        return "subtask_vietnamese"
    if "category" in n:
        return "category_milestone"
    if n == "task":
        return "task"
    if n == "type":
        return "type"
    if n == "sprint":
        return "sprint"
    if n == "assignee":
        return "assignee"
    if "re-estimate" in n or "reestimate" in n:
        return "reestimate_h"
    if "actual effort" in n:
        return "actual_effort_h"
    if "actual" in n and "start date" in n:
        return "actual_start_date"
    if "actual" in n and "end date" in n:
        return "actual_end_date"
    if "start date" in n:
        return "plan_start_date"
    if "end date" in n:
        return "plan_end_date"
    if "estimate" in n:
        return "estimate_h"
    if "progress" in n:
        return "progress"
    if "remaining" in n:
        return "remaining_h"
    if n == "status":
        return "status"
    if n == "note":
        return "note"
    return None


def _detect_columns(tab: str) -> dict:
    """Return {"header_row": int, "cols": {field: col_index}} for a sprint
    tab, by locating the "No." header cell and reading the (up to 3) header
    rows below/around it, resolving merged group headers (e.g. "PLAN" /
    "Actual" spanning several columns) via the sheet's actual merge ranges."""
    if tab in _column_map_cache:
        return _column_map_cache[tab]

    col_a = _values_get(f"'{tab}'!A1:A{HEADER_SCAN_ROWS}")
    header_row = None
    for i, row in enumerate(col_a, start=1):
        if row and row[0].strip().rstrip(".").lower() == "no":
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"Could not find header row ('No.') in tab {tab!r}")

    last_col_letter = _col_letter(MAX_COLS - 1)
    raw_rows = _values_get(
        f"'{tab}'!A{header_row}:{last_col_letter}{header_row + HEADER_BLOCK_ROWS - 1}"
    )
    rows = [r + [""] * (MAX_COLS - len(r)) for r in raw_rows]
    while len(rows) < HEADER_BLOCK_ROWS:
        rows.append([""] * MAX_COLS)

    # Resolve merges that fall on the group (first) header row so a group
    # label like "PLAN" is applied to every column it visually spans.
    group_row = list(rows[0])
    for m in _get_merges(tab):
        if m["startRowIndex"] <= header_row - 1 < m["endRowIndex"]:
            top_left = group_row[m["startColumnIndex"]]
            for c in range(m["startColumnIndex"], min(m["endColumnIndex"], MAX_COLS)):
                group_row[c] = top_left

    cols = {}
    for c in range(MAX_COLS):
        combined = " ".join(part[c] for part in [group_row] + rows[1:] if part[c])
        field = _classify_column(combined)
        if field and field not in cols:  # first match wins (PLAN before Actual)
            cols[field] = c

    result = {"header_row": header_row, "cols": cols}
    _column_map_cache[tab] = result
    return result


def _writable_fields(tab: str) -> dict:
    return {k: v for k, v in _detect_columns(tab)["cols"].items() if k not in READONLY_KEYS}


def _parse_date_ddmmyyyy(raw: str) -> date | None:
    """Parse 'D-M-YYYY' / 'DD-MM-YYYY' (also accepts '/')."""
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", raw.strip())
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _parse_number(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(re.sub(r"[^\d.\-]", "", raw) or 0)
    except ValueError:
        return 0.0


def _find_rows(tab: str) -> dict:
    """Locate the aggregate/rollup row (totals, no Task/Assignee) and the
    first real data row for a sprint tab. Both templates seen so far put a
    blank separator row then one aggregate row between the header block and
    the real task rows — detected here instead of assumed at a fixed offset."""
    info = _detect_columns(tab)
    cols = info["cols"]
    header_row = info["header_row"]
    task_col = cols.get("task")
    assignee_col = cols.get("assignee")
    estimate_col = cols.get("estimate_h")

    last_col_letter = _col_letter(MAX_COLS - 1)
    scan = _values_get(f"'{tab}'!A{header_row + HEADER_BLOCK_ROWS}:{last_col_letter}{header_row + HEADER_BLOCK_ROWS + 12}")

    aggregate_row = None
    data_row = None
    for offset, row in enumerate(scan):
        row = row + [""] * (MAX_COLS - len(row))
        row_no = header_row + HEADER_BLOCK_ROWS + offset
        has_task = task_col is not None and row[task_col].strip()
        has_assignee = assignee_col is not None and row[assignee_col].strip()
        has_estimate = estimate_col is not None and row[estimate_col].strip()
        if not has_task and not has_assignee and has_estimate and aggregate_row is None:
            aggregate_row = row_no
        if has_task or has_assignee:
            data_row = row_no
            break
    return {"header_row": header_row, "aggregate_row": aggregate_row, "data_row": data_row}


def _read_row(tab: str, row_no: int, cols: dict) -> dict:
    last_col_letter = _col_letter(MAX_COLS - 1)
    vals = _values_get(f"'{tab}'!A{row_no}:{last_col_letter}{row_no}")
    row = (vals[0] if vals else []) + [""] * MAX_COLS
    out = {"row": row_no}
    for field, idx in cols.items():
        out[field] = row[idx]
    return out


def _read_tasks(tab: str) -> list[dict]:
    info = _detect_columns(tab)
    cols = info["cols"]
    bounds = _find_rows(tab)
    if bounds["data_row"] is None:
        return []
    task_col = cols.get("task")
    assignee_col = cols.get("assignee")

    last_col_letter = _col_letter(MAX_COLS - 1)
    rows = _values_get(f"'{tab}'!A{bounds['data_row']}:{last_col_letter}{bounds['data_row'] + 300}")
    tasks = []
    for offset, row in enumerate(rows):
        row = row + [""] * (MAX_COLS - len(row))
        has_task = task_col is not None and row[task_col].strip()
        has_assignee = assignee_col is not None and row[assignee_col].strip()
        if not has_task and not has_assignee:
            break
        entry = {"row": bounds["data_row"] + offset}
        for field, idx in cols.items():
            entry[field] = row[idx]
        tasks.append(entry)
    return tasks


def _status_col_in_config() -> tuple[str, int] | None:
    """Find the header row + column of "Status" in the Config tab. The
    header isn't always row 1 — some templates have a title row above it."""
    rows = _values_get(f"'{CONFIG_TAB}'!A1:{_col_letter(MAX_COLS-1)}{HEADER_SCAN_ROWS}")
    for r, row in enumerate(rows, start=1):
        for i, cell in enumerate(row):
            if cell.strip().lower() == "status":
                return _col_letter(i), i, r
    return None


def _get_status_enum() -> list[str]:
    global _status_enum_cache
    if _status_enum_cache is not None:
        return _status_enum_cache
    found = _status_col_in_config()
    if not found:
        _status_enum_cache = []
        return _status_enum_cache
    letter, _, header_row = found
    values = _values_get(f"'{CONFIG_TAB}'!{letter}{header_row+1}:{letter}{header_row+200}")
    _status_enum_cache = [v[0] for v in values if v and v[0].strip()]
    return _status_enum_cache


_SPRINT_TAB_RE = re.compile(r"(Sprint \d+)\s*$")


@mcp.tool()
def list_task_tabs() -> dict:
    """List sprint task tabs available, e.g. {"Sprint 1": "2.2.Sprint 1"}
    or {"Sprint 1": "Sprint 1"} depending on this project's naming. Any tab
    whose name ends in "Sprint <n>" is included; other tabs (Config, Master
    schedule, CR, UAT, Backlog, Next Action Plan, ROC, ...) are ignored."""
    mapping = {}
    for sheet in _sheet_meta()["sheets"]:
        title = sheet["properties"]["title"]
        m = _SPRINT_TAB_RE.search(title)
        if m:
            mapping[m.group(1)] = title
    return mapping


@mcp.tool()
def get_current_sprint() -> dict:
    """Find the sprint whose own aggregate-row PLAN Start/End Date brackets
    today's real-world date (read directly from each sprint tab — no
    dependency on a separate summary tab, since not every project has one).

    Returns {"current": "Sprint N", "tab": "..."} if exactly one sprint
    matches. If none match (e.g. every sprint in the sheet is in the past),
    returns {"current": None, "nearest_past": "Sprint N", ...} so the skill
    can ask the PM instead of guessing.
    """
    tabs = list_task_tabs()
    today = date.today()
    sprints = []
    for sprint_name, tab in tabs.items():
        cols = _detect_columns(tab)["cols"]
        bounds = _find_rows(tab)
        if bounds["aggregate_row"] is None:
            continue
        agg = _read_row(tab, bounds["aggregate_row"], cols)
        start = _parse_date_ddmmyyyy(agg.get("plan_start_date", ""))
        end = _parse_date_ddmmyyyy(agg.get("plan_end_date", ""))
        if not start or not end:
            continue
        sprints.append({"sprint": sprint_name, "tab": tab, "start": start, "end": end})

    matches = [s for s in sprints if s["start"] <= today <= s["end"]]
    if len(matches) == 1:
        s = matches[0]
        return {"current": s["sprint"], "tab": s["tab"]}
    if len(matches) > 1:
        return {
            "current": None,
            "ambiguous": [s["sprint"] for s in matches],
            "message": "Nhiều sprint cùng khớp ngày hôm nay, cần PM chỉ định rõ.",
        }

    past = [s for s in sprints if s["end"] < today]
    upcoming = [s for s in sprints if s["start"] > today]
    nearest_past = max(past, key=lambda s: s["end"]) if past else None
    nearest_upcoming = min(upcoming, key=lambda s: s["start"]) if upcoming else None
    return {
        "current": None,
        "nearest_past": nearest_past["sprint"] if nearest_past else None,
        "nearest_past_end_date": str(nearest_past["end"]) if nearest_past else None,
        "nearest_upcoming": nearest_upcoming["sprint"] if nearest_upcoming else None,
        "nearest_upcoming_start_date": str(nearest_upcoming["start"]) if nearest_upcoming else None,
        "message": (
            "Không có sprint nào đang chạy tính đến hôm nay. "
            "Cần hỏi lại PM muốn thao tác trên sprint nào."
        ),
    }


@mcp.tool()
def get_status_enum() -> list[str]:
    """List the valid Status values for this spreadsheet (read from its own
    Config tab). Use this to validate/offer choices instead of assuming a
    fixed list — the enum differs per project."""
    return _get_status_enum()


@mcp.tool()
def get_sprint_tasks(sprint_tab: str, status: str = "", assignee: str = "") -> list[dict]:
    """Read all tasks in a sprint tab (e.g. "Sprint 1" or "2.2.Sprint 1"),
    optionally filtered by exact Status or by Assignee substring match."""
    tasks = _read_tasks(sprint_tab)
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if assignee:
        needle = assignee.lower().replace(" ", "")
        tasks = [t for t in tasks if needle in t.get("assignee", "").lower().replace(" ", "")]
    return tasks


@mcp.tool()
def find_task(keyword_or_no: str, sprint_tab: str = "") -> list[dict]:
    """Find tasks matching a No. (exact) or a case-insensitive substring of
    Task / Sub-task Vietnamese, within one sprint tab if given, else across
    all sprint tabs."""
    tabs = [sprint_tab] if sprint_tab else list(list_task_tabs().values())
    needle = keyword_or_no.strip().lower()
    results = []
    for tab in tabs:
        for t in _read_tasks(tab):
            if (
                t.get("no", "").strip() == keyword_or_no.strip()
                or needle in t.get("task", "").lower()
                or needle in t.get("subtask_vietnamese", "").lower()
            ):
                results.append({**t, "tab": tab})
    return results


@mcp.tool()
def append_task(sprint_tab: str, fields: dict) -> dict:
    """Append a new task row to a sprint tab. `fields` keys must be a subset
    of this tab's writable fields (call list_task_tabs()/get_sprint_tasks()
    first to see the shape, or rely on the canonical keys: category_milestone,
    type, sprint, task, subtask_vietnamese, assignee, estimate_h,
    plan_start_date, plan_end_date, reestimate_h, actual_start_date,
    actual_end_date, actual_effort_h, status, note — only the ones that
    actually exist as columns in this tab will be used).

    Never pass "progress" or "remaining_h" — those are spreadsheet formulas.
    """
    cols = _detect_columns(sprint_tab)["cols"]
    writable = _writable_fields(sprint_tab)
    bad_keys = set(fields) - set(writable)
    if bad_keys:
        raise ValueError(f"Not writable / unknown field(s) for {sprint_tab!r}: {sorted(bad_keys)}")
    enum = _get_status_enum()
    if "status" in fields and enum and fields["status"] not in enum:
        raise ValueError(f"Status must be one of {enum}, got {fields['status']!r}")

    existing = _read_tasks(sprint_tab)
    no_col = cols.get(NO_KEY)
    if no_col is not None:
        next_no = 1 + max(
            (int(t[NO_KEY]) for t in existing if t.get(NO_KEY, "").strip().isdigit()), default=0
        )
    else:
        next_no = len(existing) + 1

    bounds = _find_rows(sprint_tab)
    prev_row = existing[-1]["row"] if existing else bounds["aggregate_row"] or bounds["data_row"] - 1
    next_row = prev_row + 1

    # New row inherits the previous row's formatting (borders, fills, fonts)
    # and any read-only formulas (Progress/Remaining), so it looks and
    # behaves like every other task row instead of a bare, unformatted one.
    _copy_row(sprint_tab, prev_row, next_row, 0, MAX_COLS, "PASTE_FORMAT")
    readonly_cols = sorted(
        idx for field, idx in _detect_columns(sprint_tab)["cols"].items() if field in READONLY_KEYS and field != NO_KEY
    )
    if readonly_cols:
        _copy_row(sprint_tab, prev_row, next_row, readonly_cols[0], readonly_cols[-1] + 1, "PASTE_NORMAL")

    row = [""] * MAX_COLS
    if no_col is not None:
        row[no_col] = str(next_no)
    for key, col in writable.items():
        if key in fields:
            row[col] = str(fields[key])

    # Write field-by-field (skipping read-only columns entirely) so the
    # formulas just copied in above are never immediately blanked out.
    skip_cols = set(idx for field, idx in cols.items() if field in READONLY_KEYS and field != NO_KEY)
    for idx in sorted(set(writable.values()) | ({no_col} if no_col is not None else set())):
        if idx in skip_cols:
            continue
        letter = _col_letter(idx)
        _values_update(f"'{sprint_tab}'!{letter}{next_row}", [[row[idx]]])

    return {"row": next_row, "no": next_no, **fields}


@mcp.tool()
def update_task(sprint_tab: str, row: int, fields: dict) -> dict:
    """Update specific cells of an existing task row (as returned by
    find_task/get_sprint_tasks in the "row" field). Only cells present in
    `fields` are touched — never pass "progress" or "remaining_h", those are
    formulas."""
    writable = _writable_fields(sprint_tab)
    bad_keys = set(fields) - set(writable)
    if bad_keys:
        raise ValueError(f"Not writable / unknown field(s) for {sprint_tab!r}: {sorted(bad_keys)}")
    enum = _get_status_enum()
    if "status" in fields and enum and fields["status"] not in enum:
        raise ValueError(f"Status must be one of {enum}, got {fields['status']!r}")

    for key, value in fields.items():
        letter = _col_letter(writable[key])
        _values_update(f"'{sprint_tab}'!{letter}{row}", [[str(value)]])
    return {"row": row, "updated": fields}


@mcp.tool()
def get_progress_summary(scope: str = "project") -> dict:
    """Progress rollup, read from each sprint tab's own aggregate row (no
    dependency on a separate summary tab). scope="project" sums across every
    sprint tab; scope="<Sprint name>" (e.g. "Sprint 1") reports just that
    sprint's own aggregate row."""
    tabs = list_task_tabs()

    if scope != "project":
        tab = tabs.get(scope)
        if not tab:
            return {"scope": scope, "message": f"Không tìm thấy sprint {scope!r}."}
        cols = _detect_columns(tab)["cols"]
        bounds = _find_rows(tab)
        if bounds["aggregate_row"] is None:
            return {"scope": scope, "message": f"Không tìm thấy dòng tổng hợp của {scope!r}."}
        agg = _read_row(tab, bounds["aggregate_row"], cols)
        return {
            "scope": scope,
            "start_date": agg.get("plan_start_date"),
            "end_date": agg.get("plan_end_date"),
            "estimate_h": agg.get("estimate_h"),
            "re_estimate_h": agg.get("reestimate_h"),
            "actual_effort_h": agg.get("actual_effort_h"),
            "remaining_h": agg.get("remaining_h"),
            "progress": agg.get("progress"),
        }

    total_actual = 0.0
    total_remaining = 0.0
    total_estimate = 0.0
    total_reestimate = 0.0
    counted = 0
    for sprint_name, tab in tabs.items():
        cols = _detect_columns(tab)["cols"]
        bounds = _find_rows(tab)
        if bounds["aggregate_row"] is None:
            continue
        agg = _read_row(tab, bounds["aggregate_row"], cols)
        total_actual += _parse_number(agg.get("actual_effort_h", ""))
        total_remaining += _parse_number(agg.get("remaining_h", ""))
        total_estimate += _parse_number(agg.get("estimate_h", ""))
        total_reestimate += _parse_number(agg.get("reestimate_h", ""))
        counted += 1

    if counted == 0:
        return {"scope": "toàn dự án", "message": "Không tìm thấy dòng tổng hợp ở bất kỳ sprint nào."}

    denom = total_actual + total_remaining
    progress = f"{(total_actual / denom * 100):.2f}%" if denom > 0 else None
    return {
        "scope": "toàn dự án",
        "sprints_counted": counted,
        "estimate_h": total_estimate,
        "re_estimate_h": total_reestimate,
        "actual_effort_h": total_actual,
        "remaining_h": total_remaining,
        "progress": progress,
    }


if __name__ == "__main__":
    mcp.run()
