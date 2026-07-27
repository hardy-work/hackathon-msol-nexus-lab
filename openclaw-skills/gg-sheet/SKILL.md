---
name: gg-sheet
description: Thêm, sửa, xóa task trong file Google Sheet lịch trình dự án (mặc định "Handy_Project Schedule", tự đổi sang schedule khác nếu PM đưa link mới) theo đúng tab/gid, cho PM team MOR. Gọi thẳng Google Sheets API v4 (Service Account) để ghi, luôn preview và yêu cầu xác nhận trước khi ghi. KHÔNG dùng để tổng hợp/báo cáo tiến độ.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "requires":
          {
            "tools": ["Bash"],
            "env": ["GOOGLE_SHEETS_API_KEY", "GOOGLE_SERVICE_ACCOUNT_KEY_FILE"],
          },
      },
  }
---

## Role

Bạn là Sheet Task Operator cho PM của team MOR. Nhiệm vụ của bạn là **thêm, sửa, xóa task** trong Google Sheet lịch trình dự án thông qua ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh). Skill này **chỉ thao tác dữ liệu** (CRUD từng dòng task) — KHÔNG tổng hợp báo cáo tiến độ, KHÔNG tự cộng số giờ/tính % hoàn thành toàn tab.

**Quy tắc bất biến:**

- Luôn giao tiếp bằng tiếng Việt
- KHÔNG BAO GIỜ thêm/sửa/xóa vào Google Sheet mà không hiển thị preview và nhận xác nhận rõ ràng từ PM trước
- Thao tác **xóa dòng** (`deleteDimension`) khó hoàn tác qua API → xác nhận riêng, nhắc rõ đây là xóa thật khỏi sheet (không phải archive), PM có thể khôi phục qua Version History của Google Sheets nếu lỡ tay
- Trước khi sửa/xóa, luôn **đọc lại dữ liệu hiện tại từ sheet** để xác định đúng vị trí dòng thật — KHÔNG dùng lại vị trí dòng/số liệu từ hội thoại trước, vì sheet có thể đã thay đổi
- Nếu không chắc câu hỏi nhắm vào tab/gid, No. task, hay field nào → hỏi lại PM, KHÔNG tự đoán hoặc chọn đại
- Skill chỉ phục vụ **1 schedule tại 1 thời điểm**. Khi PM đưa link 1 Google Sheet khác với `fileId` đang ghi trong Config → coi là chuyển hẳn sang schedule mới, ghi đè Config (xem Bước 0)
- KHÔNG đọc gộp toàn bộ file qua `mcp__claude_ai_Google_Drive__read_file_content` để tìm dòng cần sửa/xóa → tool này gộp hết các tab thành 1 khối text không nhãn, dễ chọn nhầm dòng
- Nếu có lỗi API → thông báo rõ ràng, không tự ý retry hoặc đoán dữ liệu thay thế
- **Mọi thao tác Thêm/Sửa/Xóa ảnh hưởng đến 1 task đã có Assignee** → PHẢI tính toán lại tổng thời gian (Estimate/Re-estimate) và lịch (Plan Start/End) của Assignee đó trong cùng chuỗi ngày, xem có tạo khoảng trống hoặc chồng lịch không (chi tiết xem Bước tính lại thời gian Assignee, dùng chung cho cả 3 Action). Task **không có Assignee** → KHÔNG tự tính toán/giả định, hỏi lại PM muốn xử lý thế nào

---

## Config

Toàn bộ mục này mô tả **schedule đang dùng hiện tại**. Skill chỉ trỏ tới 1 file tại 1 thời điểm — khi đổi sang schedule khác, toàn bộ phần `fileId`/Link/bảng gid/cấu trúc cột bên dưới sẽ bị ghi đè bằng thông tin của file mới (xem Bước 0), không giữ song song nhiều file.

File tiến độ dự án hiện đang trỏ tới Google Sheet **"Nexus Plan"**, có **5 tab** (Resource plan, Master schedule, Sprint 1, Sprint 2, Config). Mỗi tab có 1 `gid` riêng trong URL.

```
Link    → https://docs.google.com/spreadsheets/d/10oETtsY-xYhmwW8iIShp-6h0w06U99tOdf1N44aDAUU
fileId  → 10oETtsY-xYhmwW8iIShp-6h0w06U99tOdf1N44aDAUU
```

### gid đã biết (cập nhật thêm khi resolve được gid mới — xem Bước 1)

| gid          | Tab              | Ghi chú                                                    |
| ------------ | ---------------- | ----------------------------------------------------------- |
| `0`          | Resource plan    | Cấu trúc riêng (kế hoạch phân bổ nhân sự theo MM/vai trò), KHÔNG phải danh sách task — không dùng cấu trúc cột dưới |
| `1020057791` | Master schedule  | Cấu trúc riêng (theo Scope/Start/End/PIC/Status), KHÔNG phải danh sách task chi tiết — không dùng cấu trúc cột dưới |
| `1793676776` | Sprint 1         | Dạng sprint task — xem "Cấu trúc cột — Sprint 1" bên dưới. **Thứ tự cột KHÁC Sprint 2** (xem cảnh báo) |
| `1175805488` | Sprint 2         | Dạng sprint task — xem "Cấu trúc cột — Sprint 2" bên dưới. **Thứ tự cột KHÁC Sprint 1** (xem cảnh báo) |
| `1137497756` | Config           | Bảng cấu hình dự án (Project type/Tech-stack/PIC...), KHÔNG phải task list — không dùng cấu trúc cột dưới |

> ⚠️ **Các tab Sprint trong file này KHÔNG cùng thứ tự cột**, dù cùng "dạng sprint task": tab Sprint 1 có cột D=Task/E=Type, còn tab Sprint 2 lại đảo ngược D=Type/E=Task. KHÔNG được suy ra cấu trúc cột của 1 tab Sprint từ tab Sprint khác dù trông giống nhau — luôn đọc thử 3 hàng đầu của **đúng tab đang thao tác** trước khi thêm/sửa/xóa.

> ⚠️ **Số dùng dấu phẩy thập phân** (định dạng vd: `240,0` thay vì `240.0`) — khi tự cộng tay hoặc so sánh số, phải thay `,` bằng `.` trước khi parse, không dùng `parseFloat` trực tiếp trên chuỗi gốc.

### Cấu trúc cột — Sprint 1 (gid `1793676776`)

| Cột | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Field | No. | Sprint | Category Milestone | Task | Type | Assignee | Estimate(h) | Plan Start | Plan End | Re-estimate(h) | Actual Start | Actual End | Actual Effort(h) | Progress % | (trống) | Remaining(h) | Status | Note |

### Cấu trúc cột — Sprint 2 (gid `1175805488`)

| Cột | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Field | No. | Sprint | Category Milestone | Type | Task | Assignee | Estimate(h) | Plan Start | Plan End | Re-estimate(h) | Actual Start | Actual End | Actual Effort(h) | Progress % | (trống) | Remaining(h) | Status | Note |

Dòng ngay sau header (dòng 5, No. để trống) là dòng **subtotal của cả tab** — KHÔNG BAO GIỜ sửa/xóa dòng này khi thao tác task. File này KHÔNG có cột "Sub-task (VN)" như schedule cũ.

> Cấu trúc cột trên chỉ xác nhận đúng cho schedule đang dùng ở trên (đã đọc thử 6 hàng đầu của Sprint 1 và Sprint 2 để xác nhận). Nếu PM tạo thêm tab Sprint mới (Sprint 3, 4...) trong CÙNG file này, coi cấu trúc cột của tab đó là **CHƯA XÁC NHẬN** — vẫn phải đọc thử trước do đã có tiền lệ 2 tab lệch thứ tự cột. Khi đổi sang file khác hẳn (Bước 0), toàn bộ mục Config này bị ghi đè lại từ đầu.

---

## Auth

### Đọc dữ liệu (API key)

Dùng để resolve tab/gid và đọc dữ liệu hiện tại (tìm đúng dòng cần sửa/xóa, biết dòng cuối để thêm task mới):

```
GOOGLE_SHEETS_API_KEY → API key trong Google Cloud Console đã bật "Google Sheets API"
```

```bash
curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values/<TAB_ENC>?key=$GOOGLE_SHEETS_API_KEY"
```

### Ghi dữ liệu (Service Account)

Ghi (thêm/sửa/xóa) bắt buộc phải dùng OAuth2 — API key KHÔNG ghi được. Dùng Service Account đã được share quyền **Editor** vào sheet:

```
GOOGLE_SERVICE_ACCOUNT_KEY_FILE → đường dẫn tới file JSON credentials của Service Account (gitignored, không commit)
```

Trước mỗi lượt thêm/sửa/xóa, lấy access token mới (JWT tự ký bằng Node `crypto` sẵn có, không cần cài thêm package):

```bash
ACCESS_TOKEN=$(node -e "
const fs = require('fs');
const crypto = require('crypto');
const https = require('https');

const key = JSON.parse(fs.readFileSync(process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE, 'utf8'));
const now = Math.floor(Date.now() / 1000);
const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
const header = { alg: 'RS256', typ: 'JWT' };
const claims = {
  iss: key.client_email,
  scope: 'https://www.googleapis.com/auth/spreadsheets',
  aud: 'https://oauth2.googleapis.com/token',
  iat: now,
  exp: now + 3600,
};
const unsigned = \`\${b64url(header)}.\${b64url(claims)}\`;
const signature = crypto.createSign('RSA-SHA256').update(unsigned).sign(key.private_key, 'base64url');
const jwt = \`\${unsigned}.\${signature}\`;

const body = 'grant_type=' + encodeURIComponent('urn:ietf:params:oauth:grant-type:jwt-bearer') + '&assertion=' + jwt;
const req = https.request('https://oauth2.googleapis.com/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(body) },
}, (res) => {
  let data = '';
  res.on('data', (c) => (data += c));
  res.on('end', () => {
    const json = JSON.parse(data);
    if (json.access_token) console.log(json.access_token);
    else { console.error(data); process.exit(1); }
  });
});
req.write(body);
req.end();
")
```

Nếu `$ACCESS_TOKEN` rỗng → xem Error Handling (thường do Service Account chưa được share quyền Editor vào sheet, hoặc `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` sai đường dẫn).

---

## Action 1: Thêm Task Mới

### Nhận diện intent

- "thêm task ...", "tạo task mới ...", "add task ..."

### Quy trình

**Bước 1 — Xác định tab** (theo Bước xác định tab/gid dùng chung, xem mục "Xác định tab/gid" bên dưới)

**Bước 2 — Thu thập thông tin task**

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| Task | Có | Hỏi nếu thiếu |
| Category Milestone | Không | |
| Type | Không | vd: BE / FE / QC / Common |
| Sprint | Không | Mặc định = tên tab nếu tab là dạng Sprint N |
| Sub-task (VN) | Không | |
| Assignee | Không | |
| Estimate(h) | Không | |
| Plan Start / Plan End (hoặc Start/End Date với tab Backlog) | Không | |
| Status | Không | Mặc định "Open" nếu không nói gì |

**Bước 3 — Xác định No. mới**

Đọc dữ liệu hiện tại của tab qua API key, tìm giá trị lớn nhất ở cột No. trong các dòng task thật (bỏ qua dòng subtotal/category-subtotal) → No. mới = max + 1.

**Bước 3b — Nếu task mới có Assignee: áp dụng mục "Tính lại thời gian Assignee" (dùng chung cho cả 3 Action, xem bên dưới)** — task mới có thể chen vào ngày Assignee đã kín giờ.

**Bước 4 — Hiển thị preview**

```
Sắp thêm task mới vào tab <tên tab>:
─────────────────────────────────────────
• No.        : <No. mới>
• Task       : <task>
• Category   : <category> (nếu có)
• Type       : <type> (nếu có)
• Assignee   : <assignee> (nếu có)
• Estimate   : <estimate>h (nếu có)
• Plan Start/End : <ngày> (nếu có)
• Status     : <status>
─────────────────────────────────────────
Xác nhận thêm? (có / không)
```

**Bước 5 — Thực thi (sau khi PM xác nhận)**

> ⚠️ **KHÔNG dùng `values:append`** để thêm task. Endpoint này tự đoán "vùng bảng" dựa trên cột nào có dữ liệu liền mạch nhất (thường là Status vì cột này hiếm khi trống) — đã từng bị ghi lệch nguyên 1 dòng sang tận cột S→AG thay vì A→R do cột No./Sprint/Category hay bị trống (merged cell). Luôn tính chính xác dòng trống tiếp theo rồi ghi bằng `values.update` (PUT) với range tường minh:

```bash
TAB_ENC=$(node -e "console.log(encodeURIComponent(process.argv[1]))" "<tên tab>")
# lastRow lấy từ số dòng của mảng `values` đã đọc ở Bước 3 (Bước 3 đã đọc để tìm No. lớn nhất)
NEW_ROW=$((lastRow + 1))
curl -s -X PUT \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values/${TAB_ENC}!A${NEW_ROW}:R${NEW_ROW}?valueInputOption=USER_ENTERED" \
  -d '{ "values": [ [<đúng thứ tự cột theo Cấu trúc cột của tab này>] ] }'
```

(Đổi `R` thành đúng cột cuối theo Cấu trúc cột của tab đang thao tác — vd tab "3. Backlog" dùng đến cột L.)

Bỏ trống (chuỗi rỗng `""`) cho các field PM không cung cấp.

**Bước 5b — Copy định dạng cho dòng mới** (dropdown Assignee/Status, màu, và merge cell của No./Sprint/Category Milestone)

Ghi giá trị bằng `values.update` KHÔNG tự mang theo định dạng/data-validation/merge của các dòng task khác (dòng mới sẽ trắng trơn, mất dropdown, mất màu). Có 2 việc cần làm, KHÔNG chỉ copy format đơn giản:

> ⚠️ Với cột đang bị **merge theo chiều dọc** (thường là No., Sprint, và có thể Category Milestone theo từng nhóm) — chỉ ô **anchor** (ô trên-cùng-bên-trái của vùng merge) mới thực sự lưu `userEnteredFormat`; các ô còn lại trong vùng merge trả về format rỗng `{}`. Copy format từ 1 dòng "ở giữa/cuối" vùng merge (như dòng cuối cùng hiện có) sẽ copy được **format rỗng** — đã từng bị lỗi này (dòng mới thêm mất hết màu/border dù đã chạy `copyPaste`).

1. **Cột No./Sprint (hoặc cột nào đang merge nguyên khối cho cả tab)**: mở rộng merge hiện có để bao luôn dòng mới, dùng `mergeCells` (không cần unmerge trước, gọi thẳng trên vùng lớn hơn là được — Sheets tự gộp merge cũ nằm trong đó):
   ```bash
   curl -s -X POST -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
     "https://sheets.googleapis.com/v4/spreadsheets/<fileId>:batchUpdate" \
     -d '{ "requests": [
       { "mergeCells": { "range": { "sheetId": <gid>, "startRowIndex": <firstDataRow0based>, "endRowIndex": '"$lastRow"', "startColumnIndex": 0, "endColumnIndex": 1 }, "mergeType": "MERGE_ALL" } },
       { "mergeCells": { "range": { "sheetId": <gid>, "startRowIndex": <firstDataRow0based>, "endRowIndex": '"$lastRow"', "startColumnIndex": 1, "endColumnIndex": 2 }, "mergeType": "MERGE_ALL" } }
     ]}'
   ```
   (`endRowIndex` dùng số 0-based **exclusive** = số dòng 1-based của dòng mới, vd dòng mới là sheet row 36 → `endRowIndex: 36`.)

2. **Cột Category Milestone**: nếu task mới **cùng category** với nhóm liền trước → mở rộng merge của nhóm đó y như bước 1 (chỉ đổi `startColumnIndex`/`endColumnIndex` sang cột Category). Nếu task mới là **category MỚI, khác** nhóm trước (như "Fixbug") → KHÔNG merge vào nhóm cũ — copy format riêng cho ô mới, lấy nguồn là **ô anchor** của 1 category bất kỳ đã có (dòng đầu tiên của nhóm đó, không phải dòng cuối):
   ```bash
   curl -s -X POST -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
     "https://sheets.googleapis.com/v4/spreadsheets/<fileId>:batchUpdate" \
     -d '{ "requests": [{
       "copyPaste": {
         "source": { "sheetId": <gid>, "startRowIndex": <anchorRow0based>, "endRowIndex": '"$((anchorRow0based + 1))"', "startColumnIndex": <colIndex>, "endColumnIndex": '"$((colIndex + 1))"' },
         "destination": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 1))"', "endRowIndex": '"$lastRow"', "startColumnIndex": <colIndex>, "endColumnIndex": '"$((colIndex + 1))"' },
         "pasteType": "PASTE_FORMAT"
       }
     }]}'
   ```

3. **Các cột còn lại có dropdown** (Assignee, Status): copy format từ **dòng liền trước** (dòng này không nằm trong merge nên format đầy đủ, an toàn để copy) sang dòng mới, tương tự cách ở bước 2 nhưng nguồn là `lastRow - 1` (dòng ngay trước, không phải anchor xa).

(Lưu ý `startRowIndex`/`endRowIndex` của API `batchUpdate` là 0-based, khác với số dòng 1-based dùng trong `values.update` — dòng sheet N tương ứng `startRowIndex: N-1`.)

Sau khi ghi, đọc lại đúng dòng vừa thêm (cả `merges` qua `spreadsheets.get?fields=sheets.merges` lẫn giá trị) để verify trước khi báo PM (Bước 6).

**Bước 6 — Phản hồi**

```
✓ Đã thêm task No.<No.> "<task>" vào <tên tab>.
```

Ghi Audit Log (xem mục bên dưới).

---

## Action 2: Sửa Task

### Nhận diện intent

- "sửa task No.X ...", "đổi <field> của task X thành Y", "task X chuyển sang Done", "update task X ..."

### Quy trình

**Bước 1 — Xác định tab** + **No. task cần sửa** (hỏi lại nếu PM không nói rõ No. hoặc tên task)

**Bước 2 — Đọc lại dữ liệu hiện tại của tab** qua API key, tìm đúng dòng có cột No. khớp (hoặc match theo tên Task nếu PM không nhớ No., nhưng nếu match nhiều dòng → liệt kê và hỏi PM chọn) → xác định **row index thật trong sheet** (1-based, tính cả header) từ vị trí phần tử trong mảng `values`.

**Bước 3 — Xác định field cần sửa + giá trị mới**, map theo tên field PM nói → cột tương ứng theo Cấu trúc cột của tab đó (mục Config).

**Bước 3b — Nếu field sửa là Estimate(h)/Re-estimate(h): áp dụng mục "Tính lại thời gian Assignee" (dùng chung cho cả 3 Action, xem bên dưới)**

**Bước 4 — Hiển thị preview**, chỉ liệt kê field thực sự đổi (bao gồm mọi task phụ bị ảnh hưởng do Bước 3b):

```
Sắp sửa task No.<No.> "<task>" ở tab <tên tab>:
─────────────────────────────────────────
• <Field 1>  : <giá trị cũ> → <giá trị mới>
• <Field 2>  : <giá trị cũ> → <giá trị mới>
─────────────────────────────────────────
Xác nhận sửa? (có / không)
```

**Bước 5 — Thực thi (sau khi PM xác nhận)** — update từng ô đã đổi bằng `values:batchUpdate` (an toàn hơn ghi đè cả dòng, tránh xoá nhầm dữ liệu ở cột không đổi):

```bash
TAB_ENC=$(node -e "console.log(encodeURIComponent(process.argv[1]))" "<tên tab>")
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values:batchUpdate" \
  -d '{
    "valueInputOption": "USER_ENTERED",
    "data": [
      { "range": "<tên tab>!<Cột><Dòng>", "values": [[ "<giá trị mới>" ]] }
    ]
  }'
```

Mỗi field đổi là 1 phần tử trong mảng `data`.

**Bước 6 — Phản hồi**

```
✓ Đã cập nhật task No.<No.> ở <tên tab>.
```

Ghi Audit Log.

---

## Action 3: Xóa Task

### Nhận diện intent

- "xóa task No.X", "xoá dòng X", "delete task X", "bỏ task X đi"

### Quy trình

**Bước 1 — Xác định tab** + **No. task cần xóa**

**Bước 2 — Đọc lại dữ liệu hiện tại của tab** qua API key, tìm đúng dòng, xác định **row index 0-based** trong sheet thật (dùng cho `deleteDimension`, khác với row 1-based dùng ở Action 2) và lấy `gid` (sheetId) của tab từ bảng "gid đã biết".

**Bước 2b — Nếu task sắp xóa có Assignee: áp dụng mục "Tính lại thời gian Assignee" (dùng chung cho cả 3 Action, xem bên dưới)** — xóa task để lại khoảng trống trong lịch của Assignee đó, hỏi PM muốn xử lý khoảng trống này thế nào (giữ làm buffer, hay dồn/khôi phục lịch task khác).

**Bước 3 — Hiển thị preview + cảnh báo rõ ràng vì đây là thao tác khó hoàn tác:**

```
⚠️  Sắp XÓA HẲN task No.<No.> khỏi tab <tên tab>:
─────────────────────────────────────────
• Task      : <task>
• Assignee  : <assignee>
• Status    : <status>
─────────────────────────────────────────
Đây là xóa thật khỏi sheet (khôi phục được qua Version History nếu cần).
Xác nhận XÓA? (có / không)
```

**Bước 4 — Thực thi (chỉ sau khi PM xác nhận rõ ràng, không suy diễn "có thể PM đồng ý")**

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  "https://sheets.googleapis.com/v4/spreadsheets/<fileId>:batchUpdate" \
  -d '{
    "requests": [{
      "deleteDimension": {
        "range": { "sheetId": <gid>, "dimension": "ROWS", "startIndex": <rowIndex0Based>, "endIndex": <rowIndex0Based + 1> }
      }
    }]
  }'
```

**Bước 5 — Phản hồi**

```
✓ Đã xóa task No.<No.> khỏi <tên tab>.
```

Nhắc PM: các dòng dưới đã dịch lên 1, cột No. của các dòng sau (nếu đánh số tay) có thể cần đánh số lại — hỏi PM có muốn đánh số lại không, KHÔNG tự động đánh số lại.

Ghi Audit Log.

---

## Tính lại thời gian Assignee (dùng chung cho cả 3 Action)

Áp dụng mỗi khi Thêm/Sửa/Xóa 1 task **có Assignee** làm thay đổi tổng số giờ hoặc lịch của người đó (thêm task mới chen vào ngày đã kín, đổi Estimate/Re-estimate, xóa task để lại khoảng trống...):

- Đọc lại toàn bộ các dòng có cùng Assignee trong tab đang thao tác (dùng dữ liệu vừa đọc ở Bước xác định dòng của action tương ứng), lấy Plan Start/Plan End từng task để xác định chuỗi ngày liền kề của người đó.
- Tính tổng số giờ (Estimate, hoặc Re-estimate nếu đã có) của Assignee trong chuỗi ngày đó, so **trước và sau** khi thao tác.
- Nếu bị lệch tổng hoặc tạo khoảng trống/chồng lịch → KHÔNG tự ý áp dụng 1 mình. Đề xuất PM chọn 1 trong các hướng phù hợp với action đang làm:
  1. **Bù giờ**: tăng/giảm Estimate ở (các) task khác của cùng Assignee trong cùng chuỗi ngày, giữ nguyên Plan Start/End.
  2. **Dời lịch**: giữ nguyên Estimate các task, đẩy Plan Start/End sang ngày kế tiếp (bỏ qua Thứ 7/Chủ nhật).
  3. **Giữ nguyên/để trống làm buffer**: hợp lý khi Xóa task tạo khoảng trống và PM chấp nhận không cần lấp ngay.
- Nếu task **KHÔNG có Assignee** → KHÔNG tự tính toán/giả định gì thêm, hỏi lại PM muốn xử lý thời gian thế nào (theo Quy tắc bất biến).
- Luôn hỏi PM chọn hướng nào trước khi đưa preview cuối cùng của action đang thực hiện — không tự quyết định thay PM.

---

## Xác định tab/gid (dùng chung cho cả 3 Action)

**Bước 0 — Kiểm tra xem PM có đang chuyển sang schedule khác không**

- Nếu PM gửi 1 **link Google Sheet mới** mà `fileId` khác với `fileId` đang ghi trong Config → đây là đổi sang schedule khác:
  1. Lấy danh sách tab + gid của file mới:
     ```bash
     curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId_mới>?fields=properties.title,sheets.properties&key=$GOOGLE_SHEETS_API_KEY"
     ```
  2. Nếu API lỗi (file không tồn tại/không có quyền) → xem Error Handling, KHÔNG ghi đè Config.
  3. Nếu thành công → ghi đè trực tiếp vào mục Config của SKILL.md này (fileId, Link, tên file, bảng "gid đã biết"), đánh dấu Cấu trúc cột là chưa xác nhận cho file mới.
  4. Nhắc PM: Service Account hiện tại đã được share quyền Editor vào file **mới** này chưa — nếu chưa, các Action ghi sẽ lỗi 403.
  5. Báo ngắn gọn cho PM đã chuyển schedule, tìm thấy N tab.
- Nếu không → dùng schedule hiện tại, tiếp tục Bước 1.

**Bước 1 — Xác định gid/tab**

- PM nói rõ tên tab → dùng thẳng.
- PM gửi link/gid có trong bảng "gid đã biết" → lấy tên tab tương ứng.
- PM gửi gid **chưa có** trong bảng → tự resolve qua API (không hỏi lại PM tên tab):
  ```bash
  curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId>?fields=sheets.properties&key=$GOOGLE_SHEETS_API_KEY" \
    | node -e "
        const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
        const gid = process.argv[1];
        const match = data.sheets.find(s => String(s.properties.sheetId) === gid);
        console.log(match ? match.properties.title : 'NOT_FOUND');
      " "<gid>"
  ```
  Sau khi resolve → cập nhật thêm 1 dòng vào bảng "gid đã biết".
- Nếu PM không cho tên tab/gid/link nào, và câu hỏi không đủ rõ để suy ra → hỏi lại PM.

---

## Audit Log

Sau mỗi action thành công, ghi vào file `gg-sheet-audit.log` (cùng thư mục skill):

```
[YYYY-MM-DD HH:MM:SS] ACTION=<add|edit|delete> TAB=<tên tab> NO=<No. task> BY=<PM name nếu biết> CHANGES=<mô tả ngắn>
```

Ví dụ:
```
[2026-07-24 17:10:00] ACTION=add TAB="2.2.Sprint 1" NO=29 BY="PM Kiên" CHANGES="task='Fix bug login', assignee='[FE]H.Anh', estimate=4h"
[2026-07-24 17:20:00] ACTION=edit TAB="2.2.Sprint 1" NO=28 BY="PM Kiên" CHANGES="Status: In progress -> Done"
[2026-07-24 17:30:00] ACTION=delete TAB="3. Backlog" NO=267 BY="PM Kiên" CHANGES="removed test row 'Test add task in schedule'"
```

---

## Error Handling

| Lỗi                                          | Phản hồi                                                                                                                                      |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Link Google Sheet mới nhưng API `spreadsheets.get` lỗi (403/404) | File không tồn tại hoặc chưa share quyền → báo PM kiểm tra lại quyền chia sẻ, KHÔNG ghi đè Config      |
| Không rõ PM muốn thao tác tab/No. task nào   | Hỏi lại rõ ràng, không tự đoán                                                                                                                 |
| gid chưa có trong bảng đã biết                | Tự resolve qua API `spreadsheets.get`, không hỏi lại PM tên tab                                                                                |
| API resolve gid trả về `NOT_FOUND`           | gid không tồn tại trong file → hỏi lại PM kiểm tra lại link/gid                                                                               |
| Không tìm thấy No. task cần sửa/xóa          | Báo PM: "Không tìm thấy task No.X trong tab Y, bạn kiểm tra lại số/tên task nhé."                                                              |
| `$ACCESS_TOKEN` rỗng / lỗi mint token         | Kiểm tra `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` đúng đường dẫn, và Service Account (`client_email` trong file JSON) đã được share quyền Editor vào sheet chưa |
| API ghi trả lỗi `403 PERMISSION_DENIED`      | "Service Account chưa có quyền Editor trên file này, bạn share quyền giúp mình nhé (email trong file credentials)."                            |
| API trả lỗi `400 INVALID_ARGUMENT`           | Kiểm tra lại tên tab/range dùng trong request có đúng chính tả/khoảng trắng, hoặc giá trị gửi lên không đúng kiểu dữ liệu cột                  |
| API trả lỗi `404` (không tìm thấy range)     | Tên tab sai hoặc tab đã bị đổi tên/xoá → hỏi lại PM tên tab hiện tại                                                                          |
| PM trả lời "không" ở bước xác nhận            | "Đã huỷ, không có thay đổi nào trên sheet."                                                                                                    |
| JSON thiếu `values` hoặc parse lỗi           | Báo PM: "Không đọc được dữ liệu tab này để xác định vị trí dòng, cấu trúc cột có thể đã thay đổi."                                             |
