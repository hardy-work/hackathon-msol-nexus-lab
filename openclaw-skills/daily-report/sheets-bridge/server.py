"""MCP server bridging Google Sheets (service account auth).

Lets an agent append daily-report rows to a spreadsheet and read back
existing rows (e.g. to check who already reported today).

Config (env vars):
  GOOGLE_SHEETS_CREDENTIALS_JSON - path to a service account key file
  GOOGLE_SHEETS_SPREADSHEET_ID   - target spreadsheet id (from its URL)
"""

import os
import re

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")

mcp = FastMCP("sheets-bridge")

_creds = Credentials.from_service_account_file(CREDENTIALS_JSON, scopes=SCOPES)
_sheets = build("sheets", "v4", credentials=_creds).spreadsheets()


_ROW_RE = re.compile(r"![A-Z]+(\d+)")


@mcp.tool()
def append_report_row(values: list[str], sheet_name: str = "Sheet1") -> dict:
    """Append one row to the end of the sheet.

    `values` is the ordered list of cell values for the new row (e.g.
    [date, reporter, task, status, blockers]). Returns `row` (1-indexed sheet
    row number) so the caller can later call `update_report_row` if this
    report gets edited.
    """
    result = _sheets.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()
    updated_range = result.get("updates", {}).get("updatedRange", "")
    row_match = _ROW_RE.search(updated_range)
    return {
        "updatedRange": updated_range,
        "row": int(row_match.group(1)) if row_match else None,
    }


@mcp.tool()
def update_report_row(row: int, values: list[str], sheet_name: str = "Sheet1") -> dict:
    """Overwrite an existing row in place (1-indexed row number, as returned
    by `append_report_row`). Use this when a report message gets edited after
    it was already pushed, instead of appending a duplicate row.
    """
    result = _sheets.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()
    return {"updatedRange": result.get("updatedRange", "")}


@mcp.tool()
def get_sheet_rows(sheet_name: str = "Sheet1", range_suffix: str = "A:Z") -> list[list[str]]:
    """Read all rows currently in the given sheet/range."""
    result = _sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{range_suffix}",
    ).execute()
    return result.get("values", [])


if __name__ == "__main__":
    mcp.run()
