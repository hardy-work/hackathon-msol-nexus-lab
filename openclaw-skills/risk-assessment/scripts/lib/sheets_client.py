"""Google Sheets API v4 client — chỉ dùng thư viện chuẩn Python (`urllib`)."""

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
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8")
        try:
            message = json.loads(payload).get("error", {}).get("message", payload)
        except json.JSONDecodeError:
            message = payload
        raise SheetsApiError(e.code, message) from e


def get_spreadsheet_meta(file_id: str, token: str, fields: str = "properties.title,sheets.properties") -> dict:
    url = f"{BASE_URL}/{file_id}?fields={urllib.parse.quote(fields)}"
    return _request("GET", url, token)


def get_values(file_id: str, range_a1: str, token: str) -> list[list]:
    enc_range = urllib.parse.quote(range_a1, safe="")
    url = f"{BASE_URL}/{file_id}/values/{enc_range}"
    result = _request("GET", url, token)
    return result.get("values", [])
