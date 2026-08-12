"""Google Sheets API v4 client — đọc bằng API key (read-only), chỉ dùng
`urllib` chuẩn thư viện. Không mint OAuth/Service Account token ở bản v1 vì
skill này chỉ đọc, không ghi — giống pattern `gg-sheet-daily-report`, khác
`risk-assessment` (skill đó cần Service Account vì có ghi/đọc phạm vi rộng
hơn 3 tab cố định).
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


def get_values(file_id: str, range_a1: str, api_key: str) -> list[list]:
    enc_range = urllib.parse.quote(range_a1, safe="")
    url = f"{BASE_URL}/{file_id}/values/{enc_range}?key={urllib.parse.quote(api_key, safe='')}"
    try:
        with urllib.request.urlopen(url) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8")
        try:
            message = json.loads(payload).get("error", {}).get("message", payload)
        except json.JSONDecodeError:
            message = payload
        raise SheetsApiError(e.code, message) from e
    return result.get("values", [])
