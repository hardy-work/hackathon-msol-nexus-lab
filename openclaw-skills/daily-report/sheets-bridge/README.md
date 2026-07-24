# sheets-bridge

MCP server bridging Google Sheets via a service account, so an agent
(OpenClaw / Claude Code) can append daily-report rows and read back existing
ones (e.g. to check who already reported today).

## Setup

```bash
cd sheets-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

1. Create a Google Cloud service account, enable the Sheets API, and download
   its JSON key.
2. Share the target spreadsheet with the service account's email (Editor
   access) — service accounts don't inherit your own Sheets access.
3. Copy `.env.example` to `.env` and fill in `GOOGLE_SHEETS_CREDENTIALS_JSON`
   (path to the key file) and `GOOGLE_SHEETS_SPREADSHEET_ID` (from the sheet's
   URL: `.../spreadsheets/d/<THIS_PART>/edit`).

## Register with Claude Code / OpenClaw

Add to `.mcp.json` (or OpenClaw's MCP config):

```json
{
  "mcpServers": {
    "sheets-bridge": {
      "command": "<ABSOLUTE_PATH_TO_REPO>/openclaw-skills/daily-report/sheets-bridge/.venv/bin/python",
      "args": ["<ABSOLUTE_PATH_TO_REPO>/openclaw-skills/daily-report/sheets-bridge/server.py"],
      "env": {
        "GOOGLE_SHEETS_CREDENTIALS_JSON": "/absolute/path/to/service-account.json",
        "GOOGLE_SHEETS_SPREADSHEET_ID": "your_spreadsheet_id_here"
      }
    }
  }
}
```

## Tools

- `append_report_row(values, sheet_name="Sheet1")` — appends one row (e.g.
  `[date, reporter, task, status, blockers]`) to the end of the sheet
- `get_sheet_rows(sheet_name="Sheet1", range_suffix="A:Z")` — reads all rows
  currently in the given sheet/range

## Not yet wired up

- No column-header validation — the caller (the `daily-report` skill) is
  responsible for keeping `values` in the order the target sheet expects.
