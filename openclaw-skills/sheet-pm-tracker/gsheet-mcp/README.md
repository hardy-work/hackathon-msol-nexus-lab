# gsheet-mcp

MCP server bridging a PM's Google Sheet sprint tracker (the "Handy-style"
template used across MOR projects) via a Google Service Account.

Unlike a hardcoded-column integration, this server **detects each sprint
tab's column layout at runtime** (from its header rows + merged cells) and
**detects the Status enum from that spreadsheet's own `Config` tab** — so the
same server works across projects whose sheets copy the same template with
slightly different column order or tab naming. Verified against two real
project sheets, including one where `Type` and `Task` are swapped between
two sprint tabs of the *same* spreadsheet. See
`../../../PLAN-slack-pm-tracker.md` for the full design.

Scope is intentionally limited to tabs whose name ends in `Sprint <n>` (e.g.
`Sprint 1` or `2.2.Sprint 1`), plus read-only use of each sprint tab's own
aggregate/rollup row for progress reporting — there is no dependency on a
dedicated summary tab (`1.Summary Project` and similar are out of scope, see
the plan doc for the full list of excluded tabs).

## Setup

```bash
cd openclaw-skills/sheet-pm-tracker/gsheet-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Place your Google service-account key at `service-account.json` in this
folder (gitignored — never commit it). Share the target Google Sheet with
the service account's `client_email` as **Editor**.

Env vars:
- `GSHEET_SPREADSHEET_ID` — **required**, the target project's sheet ID. One
  server instance = one project's sheet; point a different deployment (or a
  copy of this skill folder) at a different sheet for another project.
- `GSHEET_SERVICE_ACCOUNT` — optional, defaults to `service-account.json`
  next to `server.py`.

## Tools

- `list_task_tabs()` — discover sprint tabs by name (matches any tab ending in `Sprint <n>`).
- `get_current_sprint()` — find the sprint whose own aggregate row brackets today's real date; returns `nearest_past` or `nearest_upcoming` (not a guess) if none match.
- `get_status_enum()` — the valid Status values for *this* spreadsheet's `Config` tab (differs per project — never assume a fixed list).
- `get_sprint_tasks(sprint_tab, status?, assignee?)`
- `find_task(keyword_or_no, sprint_tab?)`
- `append_task(sprint_tab, fields)`
- `update_task(sprint_tab, row, fields)`
- `get_progress_summary(scope)` — `"project"` (summed across every sprint tab) or a sprint name like `"Sprint 1"`.

`fields` for `append_task`/`update_task` must be a subset of that tab's
detected writable columns — canonical keys: `category_milestone`, `type`,
`sprint`, `task`, `subtask_vietnamese`, `assignee`, `estimate_h`,
`plan_start_date`, `plan_end_date`, `reestimate_h`, `actual_start_date`,
`actual_end_date`, `actual_effort_h`, `status`, `note`. Only the ones that
actually exist as columns in that tab are accepted. `progress` and
`remaining_h` are spreadsheet formulas and can never be written directly.

## Caveats

- Column detection relies on a `"No."` header cell to anchor the header
  block, and on the sheet's real merged-cell ranges to resolve grouped
  headers like `PLAN`/`Actual` spanning several columns — a sheet that
  doesn't follow this shape at all won't be detected correctly.
- The `No.` column's meaning isn't guaranteed consistent across templates —
  some number every task sequentially, others only number the first row of
  each category block. `append_task` always assigns
  `max(existing numeric No.) + 1`, which is reasonable but may not match a
  template's own numbering convention exactly.
