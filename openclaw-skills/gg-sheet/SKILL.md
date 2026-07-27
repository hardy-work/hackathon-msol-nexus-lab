---
name: gg-sheet
description: Thêm, sửa, xóa task trong file Google Sheet lịch trình dự án theo đúng tab/gid, cho PM. File/tab đang dùng được lưu trong config.json (hỏi PM link Google Sheet nếu chưa cấu hình, tự đổi sang schedule khác nếu PM đưa link mới), không hardcode 1 project cụ thể trong skill. Gọi thẳng Google Sheets API v4 (Service Account) để ghi, luôn preview và yêu cầu xác nhận trước khi ghi. KHÔNG dùng để tổng hợp/báo cáo tiến độ.
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
- Skill chỉ phục vụ **1 schedule tại 1 thời điểm**. Nếu `config.json` chưa có/rỗng → hỏi PM xin link trước khi làm gì khác. Khi PM đưa link 1 Google Sheet khác với `fileId` đang ghi trong `config.json` → coi là chuyển hẳn sang schedule mới, ghi đè `config.json` (xem Bước 0), KHÔNG sửa vào SKILL.md
- KHÔNG đọc gộp toàn bộ file qua `mcp__claude_ai_Google_Drive__read_file_content` để tìm dòng cần sửa/xóa → tool này gộp hết các tab thành 1 khối text không nhãn, dễ chọn nhầm dòng
- Nếu có lỗi API → thông báo rõ ràng, không tự ý retry hoặc đoán dữ liệu thay thế
- **Mọi thao tác Thêm/Sửa/Xóa ảnh hưởng đến 1 task đã có Assignee** → PHẢI tính toán lại tổng thời gian (Estimate/Re-estimate) và lịch (Plan Start/End) của Assignee đó trong cùng chuỗi ngày, xem có tạo khoảng trống hoặc chồng lịch không (chi tiết xem Bước tính lại thời gian Assignee, dùng chung cho cả 3 Action). Task **không có Assignee** → KHÔNG tự tính toán/giả định, hỏi lại PM muốn xử lý thế nào
- **Không dừng lại ở việc chỉ nêu/hỏi khoảng trống** — sau khi PM chọn hướng xử lý (hoặc PM chưa chọn buffer rõ ràng), PHẢI thực sự tính và ghi đủ để tổng thời gian của Assignee khớp chuẩn (vd đủ 8h/ngày, đủ 40h/tuần theo số ngày làm việc đang có), rồi nêu rõ tổng cuối cùng trong preview/phản hồi để PM tự verify — không được để lại khoảng trống chưa xử lý mà không nói rõ đó là chủ đích (buffer) hay còn thiếu bước

---

## Config

**Toàn bộ dữ liệu cấu hình (fileId, link, danh sách tab/gid, cấu trúc cột từng tab) nằm trong file `config.json`** (cùng thư mục skill, KHÔNG commit lên git — xem `config.example.json` làm mẫu rỗng). SKILL.md này chỉ chứa **quy trình/logic dùng chung**, không hardcode dữ liệu của 1 project cụ thể — nhờ vậy dùng lại được skill cho dự án khác chỉ bằng cách thay `config.json` (hoặc xoá đi để reset), không cần sửa file này.

Đọc config hiện tại:

```bash
cat openclaw-skills/gg-sheet/config.json
```

Cấu trúc `config.json`:

```json
{
  "fileId": "...",           // fileId của Google Sheet đang dùng, null nếu chưa cấu hình
  "link": "...",              // link đầy đủ, để hiển thị lại cho PM khi cần
  "title": "...",             // tên file (properties.title từ API)
  "tabs": [
    {
      "gid": "...",           // sheetId (gid) của tab
      "name": "...",          // tên tab, dùng cho API values.get/A1 notation
      "note": "...",          // ghi chú riêng của tab (schema khác, cảnh báo lệch cột giữa các tab...)
      "columns": { "A": "No.", "B": "...", ... } // map cột→field, null nếu tab không phải dạng task list
    }
  ],
  "numberFormat": "...",      // ghi chú định dạng số nếu khác chuẩn (vd dùng dấu phẩy thập phân)
  "notes": ["..."]            // các lưu ý chung khác của schedule này (merge cell, thiếu cột nào đó...)
}
```

**Bước kiểm tra đầu tiên (trước MỌI Action)** — Nếu `config.json` không tồn tại, hoặc `fileId` là `null`/rỗng → skill **chưa được cấu hình cho project này**. KHÔNG tự đoán hay dùng schedule mặc định nào — hỏi ngay PM:

> "Bạn cho mình link Google Sheet lịch trình dự án bạn muốn dùng nhé, mình sẽ cấu hình rồi thêm task cho bạn."

Sau khi có link, chạy đúng quy trình Bước 0 (xem "Xác định tab/gid" bên dưới) để tạo mới `config.json` từ đầu, rồi mới tiếp tục Action PM yêu cầu.

> ⚠️ `config.json` là dữ liệu **theo từng project/máy**, không phải logic của skill — khi copy skill này sang dùng cho dự án khác, chỉ cần xoá `config.json` (giữ lại `config.example.json`) để quay về trạng thái "chưa cấu hình" ở trên.

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

| Field                                                       | Bắt buộc | Ghi chú                                     |
| ----------------------------------------------------------- | -------- | ------------------------------------------- |
| Task                                                        | Có       | Hỏi nếu thiếu                               |
| Category Milestone                                          | Không    |                                             |
| Type                                                        | Không    | vd: BE / FE / QC / Common                   |
| Sprint                                                      | Không    | Mặc định = tên tab nếu tab là dạng Sprint N |
| Sub-task (VN)                                               | Không    |                                             |
| Assignee                                                    | Không    |                                             |
| Estimate(h)                                                 | Không    |                                             |
| Plan Start / Plan End (hoặc Start/End Date với tab Backlog) | Không    |                                             |
| Status                                                      | Không    | Mặc định "Open" nếu không nói gì            |

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
  -d '{ "values": [ [<đúng thứ tự cột theo `columns` của tab này trong config.json>] ] }'
```

(Đổi `R` thành đúng cột cuối theo `columns` của tab đang thao tác trong `config.json` — có tab ít cột hơn, không phải lúc nào cũng tới R.)

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

3. **Toàn bộ các cột còn lại KHÔNG merge** (từ cột Task cho tới cột cuối, vd D→R — tức MỌI cột không thuộc bước 1/2, kể cả cột Task/Type mà không phải dropdown): copy nguyên khối `startColumnIndex` từ cột đầu tiên không-merge (vd D, Task) đến hết cột cuối (vd R+1) từ **dòng liền trước** (`lastRow - 1`, dòng này không nằm trong merge nên đầy đủ dữ liệu, an toàn để copy) sang dòng mới, dùng **`pasteType: PASTE_NORMAL`** (không phải `PASTE_FORMAT`):
   ```bash
   curl -s -X POST -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
     "https://sheets.googleapis.com/v4/spreadsheets/<fileId>:batchUpdate" \
     -d '{ "requests": [{
       "copyPaste": {
         "source": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 2))"', "endRowIndex": '"$((lastRow - 1))"', "startColumnIndex": <cột Task, vd 3 cho D>, "endColumnIndex": <cột cuối + 1, vd 18 cho R> },
         "destination": { "sheetId": <gid>, "startRowIndex": '"$((lastRow - 1))"', "endRowIndex": '"$lastRow"', "startColumnIndex": <cột Task>, "endColumnIndex": <cột cuối + 1> },
         "pasteType": "PASTE_NORMAL"
       }
     }]}'
   ```
   > ⚠️ Đã thử `PASTE_FORMAT` (chỉ copy format) + `setDataValidation` riêng (copy đúng rule `dataValidation`, đã verify qua API khớp 100% với dòng nguồn) nhưng **màu chip của dropdown (Assignee/Status) trong Google Sheets hiện đại vẫn KHÔNG lên màu** dù dữ liệu API báo khớp — đây là 1 thuộc tính render nội bộ của Sheets mà API v4 không expose đầy đủ để set riêng lẻ. `PASTE_NORMAL` (copy nguyên khối, kể cả các thuộc tính ẩn không thấy qua API) là cách duy nhất xác nhận hoạt động đúng.
   > ⚠️ Cũng đã từng bỏ sót cột Task (D) khi chỉ copy từ E→R (nghĩ D chỉ cần ghi value) → dòng mới bị thiếu border ở đúng cột Task dù các cột khác đã đúng. Luôn copy **từ cột đầu tiên không-merge** (không chỉ từ cột có dropdown) tới hết cột cuối.

4. **Ghi đè lại giá trị thật của dòng mới** (vì bước 3 vừa copy `PASTE_NORMAL` sẽ ghi đè value của dòng liền trước lên dòng mới) — dùng `values.update` ghi lại đúng field PM cung cấp (Task, Type, Assignee, Estimate, ngày, Status...) đè lên đúng những ô cần khác với dòng nguồn, giữ nguyên các ô blank khác:
   ```bash
   curl -s -X PUT -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
     "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values/<tên tab>!D${lastRow}:I${lastRow}?valueInputOption=USER_ENTERED" \
     -d '{ "values": [ [<Task>, <Type>, <Assignee>, <Estimate>, <Plan Start>, <Plan End>] ] }'
   ```
   (Thứ tự làm: bước 3 copy trước để có đủ format/validation/border, rồi bước 4 ghi value đúng đè lên sau — không đổi thứ tự.)

(Lưu ý `startRowIndex`/`endRowIndex` của API `batchUpdate` là 0-based, khác với số dòng 1-based dùng trong `values.update` — dòng sheet N tương ứng `startRowIndex: N-1`.)

Sau khi ghi, đọc lại đúng dòng vừa thêm (`merges` + `dataValidation` qua `spreadsheets.get` lẫn giá trị qua `values.get`) để verify trước khi báo PM (Bước 6).

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

**Bước 3 — Xác định field cần sửa + giá trị mới**, map theo tên field PM nói → cột tương ứng theo `columns` của tab đó trong `config.json`.

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
- **Riêng Action Thêm**: nếu PM không cho ngày cụ thể và Assignee đã **kín lịch hết chuỗi ngày hiện có** (không còn giờ trống) → KHÔNG tự chọn đại 1 ngày. Đề xuất PM chọn 1 trong các hướng:
  1. **Ngày gần nhất còn trống**: ngày làm việc kế tiếp sau chuỗi lịch hiện tại của Assignee (bỏ qua Thứ 7/Chủ nhật).
  2. **Bù giờ từ 1 task khác trong chuỗi ngày hiện tại**: giảm bớt task nào đó để nhường giờ cho task mới, giữ trong cùng khung ngày cũ.
  3. **Không gán ngày**: thêm task nhưng để trống Plan Start/End, PM tự xếp lịch sau.
- Tóm lại — bất cứ khi nào phát hiện Assignee **đã kín lịch** (dù đang Thêm/Sửa/Xóa) → luôn dừng lại và đề xuất phương án cho PM chọn, không tự quyết định thay.
- Nếu task **KHÔNG có Assignee** → KHÔNG tự tính toán/giả định gì thêm, hỏi lại PM muốn xử lý thời gian thế nào (theo Quy tắc bất biến).
- Luôn hỏi PM chọn hướng nào trước khi đưa preview cuối cùng của action đang thực hiện — không tự quyết định thay PM.
- Nếu PM chưa trả lời câu hỏi về khoảng trống/lệch giờ (vd chỉ xác nhận "có" cho phần khác của action) → PHẢI hỏi lại cho tới khi có câu trả lời rõ ràng, KHÔNG coi im lặng là chọn phương án "giữ nguyên/buffer". Sau khi có câu trả lời, thực sự ghi thay đổi để tổng giờ khớp chuẩn (đủ giờ/ngày, đủ giờ/tuần) rồi nêu rõ tổng cuối cùng — không dừng ở mức đề xuất/hỏi mà không hoàn tất.

---

## Xác định tab/gid (dùng chung cho cả 3 Action)

**Bước -1 — Kiểm tra config đã tồn tại chưa** (xem mục Config phía trên) — nếu chưa có `config.json`/`fileId` rỗng → hỏi PM xin link Google Sheet trước, rồi coi như đang chạy Bước 0 với link đó.

**Bước 0 — Kiểm tra xem PM có đang chuyển sang schedule khác không**

- Nếu PM gửi 1 **link Google Sheet mới** mà `fileId` khác với `fileId` đang ghi trong `config.json` (hoặc `config.json` chưa có) → đây là cấu hình lần đầu/đổi sang schedule khác:
  1. Lấy danh sách tab + gid của file mới:
     ```bash
     curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId_mới>?fields=properties.title,sheets.properties&key=$GOOGLE_SHEETS_API_KEY"
     ```
  2. Nếu API lỗi (file không tồn tại/không có quyền) → xem Error Handling, KHÔNG ghi `config.json`.
  3. Nếu thành công → ghi đè toàn bộ `openclaw-skills/gg-sheet/config.json` bằng thông tin file mới: `fileId`, `link`, `title`, và `tabs` (mỗi sheet trong `sheets.properties` → 1 phần tử `{gid, name, note: "", columns: null}` — `columns` để `null` vì cấu trúc cột CHƯA XÁC NHẬN cho tab nào cả ở bước này).
  4. Nhắc PM: Service Account hiện tại đã được share quyền Editor vào file **mới** này chưa — nếu chưa, các Action ghi sẽ lỗi 403.
  5. Báo ngắn gọn cho PM đã chuyển schedule, tìm thấy N tab.
- Nếu không → dùng schedule hiện tại trong `config.json`, tiếp tục Bước 1.

**Bước 1 — Xác định gid/tab**

- PM nói rõ tên tab → dùng thẳng.
- PM gửi link/gid có trong `tabs` của `config.json` → lấy `name` tương ứng.
- PM gửi gid **chưa có** trong `tabs` → tự resolve qua API (không hỏi lại PM tên tab):
  ```bash
  curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId>?fields=sheets.properties&key=$GOOGLE_SHEETS_API_KEY" \
    | node -e "
        const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
        const gid = process.argv[1];
        const match = data.sheets.find(s => String(s.properties.sheetId) === gid);
        console.log(match ? match.properties.title : 'NOT_FOUND');
      " "<gid>"
  ```
  Sau khi resolve → thêm 1 phần tử mới vào mảng `tabs` trong `config.json` (`{gid, name, note: "", columns: null}`).
- Trước khi thao tác 1 tab lần đầu (hoặc tab có `columns: null`) → đọc thử 2-3 hàng đầu của tab đó để xác định cấu trúc cột thật, rồi cập nhật lại `columns` (và `note` nếu có gì đặc biệt, vd lệch cột so với tab khác) vào đúng phần tử trong `config.json`.
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

| Lỗi                                                              | Phản hồi                                                                                                                                                 |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Link Google Sheet mới nhưng API `spreadsheets.get` lỗi (403/404) | File không tồn tại hoặc chưa share quyền → báo PM kiểm tra lại quyền chia sẻ, KHÔNG ghi `config.json`                                                    |
| Không rõ PM muốn thao tác tab/No. task nào                       | Hỏi lại rõ ràng, không tự đoán                                                                                                                           |
| gid chưa có trong `tabs` của `config.json`                       | Tự resolve qua API `spreadsheets.get`, không hỏi lại PM tên tab                                                                                          |
| API resolve gid trả về `NOT_FOUND`                               | gid không tồn tại trong file → hỏi lại PM kiểm tra lại link/gid                                                                                          |
| Không tìm thấy No. task cần sửa/xóa                              | Báo PM: "Không tìm thấy task No.X trong tab Y, bạn kiểm tra lại số/tên task nhé."                                                                        |
| `$ACCESS_TOKEN` rỗng / lỗi mint token                            | Kiểm tra `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` đúng đường dẫn, và Service Account (`client_email` trong file JSON) đã được share quyền Editor vào sheet chưa |
| API ghi trả lỗi `403 PERMISSION_DENIED`                          | "Service Account chưa có quyền Editor trên file này, bạn share quyền giúp mình nhé (email trong file credentials)."                                      |
| API trả lỗi `400 INVALID_ARGUMENT`                               | Kiểm tra lại tên tab/range dùng trong request có đúng chính tả/khoảng trắng, hoặc giá trị gửi lên không đúng kiểu dữ liệu cột                            |
| API trả lỗi `404` (không tìm thấy range)                         | Tên tab sai hoặc tab đã bị đổi tên/xoá → hỏi lại PM tên tab hiện tại                                                                                     |
| PM trả lời "không" ở bước xác nhận                               | "Đã huỷ, không có thay đổi nào trên sheet."                                                                                                              |
| JSON thiếu `values` hoặc parse lỗi                               | Báo PM: "Không đọc được dữ liệu tab này để xác định vị trí dòng, cấu trúc cột có thể đã thay đổi."                                                       |
