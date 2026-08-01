# Copy format/merge cho dòng task mới (Action 1 — Bước 5.1)

Chỉ đọc file này khi đang thực thi Action 1 (Thêm Task), sau khi đã xác định `lastRow`, `gid`, cột cuối, và (nếu cần) `anchorRow`/`colCategory`. Không cần đọc cho Action 2 (Sửa)/Action 3 (Xóa).

> ⚠️ Cột đang merge dọc (No., Sprint, Category theo nhóm): chỉ ô **anchor** (trên-cùng-bên-trái) giữ `userEnteredFormat` thật, các ô còn lại trong vùng merge trả về `{}`. Copy format từ dòng cuối (nằm trong merge) sẽ copy được format rỗng — luôn copy Category từ **anchor** (dòng đầu nhóm), không phải dòng cuối.

**Gộp thành 1 lệnh `batchUpdate` duy nhất** (các request độc lập, không đè cột lên nhau nên gộp an toàn):

- Request 1-2: mở rộng merge No./Sprint bao luôn dòng mới (không cần unmerge trước — Sheets tự gộp merge cũ nằm trong đó).
- Request 3: Category — cùng category với nhóm liền trước → mở rộng merge nhóm đó (dùng `mergeCells` thay vì `copyPaste` bên dưới). Category MỚI khác nhóm trước → `copyPaste` `PASTE_FORMAT` từ ô anchor của 1 category có sẵn.
- Request 4: mọi cột không-merge còn lại (Task → cột cuối, vd D→R) — copy nguyên khối bằng `copyPaste` `PASTE_NORMAL` (không phải `PASTE_FORMAT`) từ **dòng liền trước** (`lastRow - 1`, ngoài vùng merge nên đủ dữ liệu) sang dòng mới. Luôn copy từ cột đầu tiên không-merge (Task), không chỉ từ cột có dropdown — bỏ sót cột Task từng gây thiếu border đúng cột đó.

```bash
curl -s -X POST -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/<fileId>:batchUpdate" \
  -d '{ "requests": [
    { "mergeCells": { "range": { "sheetId": <gid>, "startRowIndex": <firstDataRow0based>, "endRowIndex": '"$lastRow"', "startColumnIndex": 0, "endColumnIndex": 1 }, "mergeType": "MERGE_ALL" } },
    { "mergeCells": { "range": { "sheetId": <gid>, "startRowIndex": <firstDataRow0based>, "endRowIndex": '"$lastRow"', "startColumnIndex": 1, "endColumnIndex": 2 }, "mergeType": "MERGE_ALL" } },
    { "copyPaste": {
        "source": { "sheetId": <gid>, "startRowIndex": <anchorRow0based>, "endRowIndex": '"$((anchorRow0based + 1))"', "startColumnIndex": <colCategory>, "endColumnIndex": '"$((colCategory + 1))"' },
        "destination": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 1))"', "endRowIndex": '"$lastRow"', "startColumnIndex": <colCategory>, "endColumnIndex": '"$((colCategory + 1))"' },
        "pasteType": "PASTE_FORMAT"
    }},
    { "copyPaste": {
        "source": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 2))"', "endRowIndex": '"$((lastRow - 1))"', "startColumnIndex": <cột Task, vd 3 cho D>, "endColumnIndex": <cột cuối + 1, vd 18 cho R> },
        "destination": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 1))"', "endRowIndex": '"$lastRow"', "startColumnIndex": <cột Task>, "endColumnIndex": <cột cuối + 1> },
        "pasteType": "PASTE_NORMAL"
    }}
  ]}'
```

(Thay request 3 bằng `mergeCells` mở rộng nếu cùng category nhóm trước. `startRowIndex`/`endRowIndex` 0-based, `endRowIndex` exclusive; dòng sheet N ↔ `startRowIndex: N-1`.)

> ⚠️ Đã thử `PASTE_FORMAT` + `setDataValidation` riêng (rule khớp 100% qua API) nhưng màu chip dropdown Assignee/Status vẫn KHÔNG lên — thuộc tính render nội bộ Sheets mà API không set riêng lẻ được. Chỉ `PASTE_NORMAL` mới xác nhận hoạt động đúng.
