"""Ghi vào tab "Dashboard" qua Google Sheets API v4 (OAuth2 Service Account,
token mint bằng `google_auth.py`) — network I/O, không test (giống
`sheets_client.py`).

CHỈ ĐỤNG ĐÚNG 1 TAB do `tab_name` chỉ định — tự tạo tab nếu chưa có, xoá sạch
nội dung tab đó trước khi ghi lại (để không sót dòng cũ từ lần chạy trước có
nhiều dữ liệu hơn), KHÔNG BAO GIỜ đụng tab nào khác trên spreadsheet.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Sheets API error {status}: {message}")
        self.status = status
        self.message = message


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8")
        try:
            message = json.loads(payload).get("error", {}).get("message", payload)
        except json.JSONDecodeError:
            message = payload
        raise SheetsApiError(e.code, message) from e


def get_sheet_id(file_id: str, tab_name: str, token: str) -> int | None:
    url = f"{BASE_URL}/{file_id}?fields={urllib.parse.quote('sheets.properties')}"
    result = _request("GET", url, token)
    for sheet in result.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            return props.get("sheetId")
    return None


def ensure_tab_exists(file_id: str, tab_name: str, token: str) -> int:
    """Trả về sheetId của tab `tab_name` — tạo mới nếu chưa tồn tại."""
    sheet_id = get_sheet_id(file_id, tab_name, token)
    if sheet_id is not None:
        return sheet_id
    url = f"{BASE_URL}/{file_id}:batchUpdate"
    body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
    result = _request("POST", url, token, body)
    return result["replies"][0]["addSheet"]["properties"]["sheetId"]


def clear_tab(file_id: str, tab_name: str, token: str) -> None:
    enc_range = urllib.parse.quote(f"'{tab_name}'!A1:Z1000", safe="")
    url = f"{BASE_URL}/{file_id}/values/{enc_range}:clear"
    _request("POST", url, token, {})


def write_rows(file_id: str, tab_name: str, rows: list[list], token: str) -> None:
    enc_range = urllib.parse.quote(f"'{tab_name}'!A1", safe="")
    url = f"{BASE_URL}/{file_id}/values/{enc_range}?valueInputOption=USER_ENTERED"
    _request("PUT", url, token, {"values": rows})


def publish_dashboard(file_id: str, tab_name: str, rows: list[list], token: str) -> int:
    """Tạo tab nếu chưa có, xoá sạch, ghi lại toàn bộ `rows`. Trả về sheetId
    (dùng để build link `...#gid=<sheetId>`).
    """
    sheet_id = ensure_tab_exists(file_id, tab_name, token)
    clear_tab(file_id, tab_name, token)
    write_rows(file_id, tab_name, rows, token)
    return sheet_id
