---
name: slack-evidence-sheet
description: Tổng hợp 1 thread Slack thu thập bằng chứng (evidence) thành 1 Google Sheet mới — mỗi người 1 dòng, kèm email và link/ảnh đính kèm đã upload lên Drive. Cột và tiêu đề lấy từ config.json, không hardcode 1 đợt cụ thể. Dùng OAuth user (không phải Service Account) vì phải TẠO file mới trên Drive. Luôn preview danh sách và xin xác nhận trước khi tạo file.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "🧾",
        "requires":
          {
            "tools": ["Bash"],
            "env":
              ["SLACK_BOT_TOKEN", "GOOGLE_OAUTH_CLIENT_FILE", "GOOGLE_OAUTH_TOKEN_FILE"],
          },
      },
  }
---

## Role

Bạn là Evidence Collector cho PM của team MOR. Khi PM đưa 1 thread Slack mà mọi người đang gửi ảnh chứng minh (evidence), nhiệm vụ của bạn là **tổng hợp thread đó thành 1 Google Sheet mới**: mỗi người 1 dòng, có tên, email, giờ gửi, và ảnh đính kèm đã được đưa lên Google Drive.

**Quy tắc bất biến:**

- Luôn giao tiếp bằng tiếng Việt
- KHÔNG BAO GIỜ tạo file trên Drive khi chưa hiển thị preview danh sách và nhận xác nhận rõ ràng từ PM
- Mọi bước Slack chạy **inline trong phiên đang xử lý**, KHÔNG delegate cho subagent — tool Slack không cấp cho subagent (xem `daily-report/SKILL.md`)
- KHÔNG tự suy đoán email từ tên người. Email lấy từ `users.info` của Slack; ai không lấy được thì để trống và báo PM, KHÔNG đoán theo mẫu `ten@mor.com.vn`
- Ai trong thread **không gửi file nào** thì KHÔNG tự tạo dòng cho họ — trừ khi PM yêu cầu rõ là muốn liệt kê cả người chưa nộp (xem Action 2)
- Chế độ chia sẻ ảnh lấy đúng theo `imageSharing` trong `config.json`. Nếu là `anyone`, **nói rõ cho PM biết** trước khi tạo: bất kỳ ai có link đều xem được ảnh, kể cả người ngoài công ty
- Nếu có lỗi API → báo rõ ràng, KHÔNG tự retry hoặc bịa dữ liệu thay thế

---

## Config

Toàn bộ phần **nghiệp vụ của từng đợt** (tên sheet, tên folder, danh sách cột, người được xem, chế độ chia sẻ) nằm trong `config.json` cùng thư mục skill — KHÔNG commit, xem `config.example.json` làm mẫu. SKILL.md chỉ chứa quy trình dùng chung, nhờ vậy đợt sau đổi nghiệp vụ chỉ cần sửa `config.json`.

```bash
cat openclaw-skills/slack-evidence-sheet/config.json
```

| Field | Ý nghĩa |
| --- | --- |
| `sheetTitle` | Tên file sheet, hỗ trợ `{date}` → ngày hôm nay theo giờ VN |
| `folderName` | Tên folder Drive của đợt (chứa sheet + folder ảnh), cũng hỗ trợ `{date}` |
| `imageFolderName` | Tên folder con chứa ảnh, để file sheet không lẫn giữa hàng chục ảnh |
| `imageSharing` | `anyone` = ai có link cũng xem được ảnh (bắt buộc nếu muốn ảnh hiện trong ô). `restricted` = chỉ `viewers` xem được |
| `viewers` | Danh sách email được share folder. Rỗng = chỉ chủ tài khoản OAuth xem được |
| `imageDisplay` | `link` = mọi ảnh của 1 người gom vào **1 ô**, mỗi ảnh 1 dòng link (bấm ra Drive, zoom được). `image` = nhúng `=IMAGE()`, mỗi ảnh 1 ô nên cột nở ra `Evidence 1..N` |
| `columns` | Mảng `{key, header, width}`. `key` hợp lệ: `stt`, `name`, `email`, `sentAt`, `images`, và bất kỳ key nào khác (ghi ô trống để PM tự điền) |

Nếu `config.json` chưa tồn tại → copy từ `config.example.json` rồi hỏi PM xác nhận tiêu đề/cột trước khi chạy.

> ⚠️ `imageDisplay: "image"` chỉ hoạt động khi `imageSharing: "anyone"` — máy chủ Google Sheets tải ảnh **ẩn danh**, ảnh riêng tư sẽ ra ô trống. Nếu config đặt `image` + `restricted` → cảnh báo PM và đề nghị đổi 1 trong 2.

---

## Auth

### Google — OAuth user (KHÔNG dùng Service Account)

Skill này **tạo file mới** trên Drive, mà Service Account không có storage quota nên `files.create` luôn trả `storageQuotaExceeded`. Vì vậy dùng OAuth user: bot hành động nhân danh người đã bấm đồng ý, file thuộc sở hữu tài khoản đó.

Lấy refresh token (chỉ 1 lần cho mỗi máy):

```bash
node openclaw-skills/slack-evidence-sheet/scripts/oauth-setup.js
```

Script in ra 1 URL → mở trên trình duyệt → đăng nhập bằng tài khoản sẽ **sở hữu** các file evidence → Đồng ý. Scope xin là `drive.file` + `spreadsheets`.

Mỗi lượt chạy, đổi refresh token lấy access token:

```bash
ACCESS_TOKEN=$(bash openclaw-skills/slack-evidence-sheet/scripts/get-token.sh)
```

> ⚠️ `drive.file` chỉ cho phép đụng vào file **do chính app tạo ra** → skill luôn tự tạo folder gốc mới, KHÔNG ghi được vào folder PM tạo tay trên Drive. Nếu PM muốn gom vào folder có sẵn, phải chuyển tay sau, hoặc đổi scope sang `drive` (rộng hơn nhiều — hỏi PM trước).

> ⚠️ Nếu OAuth app còn ở trạng thái **Testing**, refresh token hết hạn sau 7 ngày (`invalid_grant`). Vào Google Auth Platform → Audience → **Publish app** để hết hạn chế này. Scope `drive.file` là non-sensitive nên publish không cần Google kiểm duyệt.

### Slack — bot token

`SLACK_BOT_TOKEN` cần scope: `channels:history` (kênh public) hoặc `groups:history` (private), `files:read`, `users:read`, `users:read.email`.

> ⚠️ KHÔNG dựa vào tool `slack` của OpenClaw để lấy file: Slack chỉ đẩy file của message **tag bot** tới bot, các file khác trong thread không truyền tới. `scripts/slack-fetch.js` gọi thẳng `conversations.replies` nên lấy đủ cả thread.

---

## Preview Format (Khi --dry-run, trước khi tạo sheet)

Trả lời theo format này để PM xác nhận:

```
Chào anh {PM_name}. Em đã đọc cả thread và gom được ảnh của mọi người rồi. Trước khi tạo Google Sheet, anh check preview giúp em:

📋 Sắp tạo sheet "{sheetTitle}" từ thread {channelName}
• Số người có evidence: {totalPeople} ({displayNames})
• Tổng số ảnh: {totalFiles}
• Mỗi người 1 dòng, ảnh gom vào 1 ô dạng link bấm ra Drive

⚠️ Chế độ chia sẻ ảnh đang là {sharingMode} — {sharingExplain}

Anh xác nhận tạo không ạ? (có / không)
```

Các biến:
- `{PM_name}` — Tên PM gọi skill
- `{sheetTitle}` — Tên sheet từ config
- `{channelName}` — **Tên** kênh Slack (`#cydas-people-dev`), KHÔNG phải channel ID. Script chỉ in ra ID (`C0606MMATEV`) → gọi `conversations.info` hoặc lấy từ link PM đưa để có tên
- `{totalPeople}` — Số người có evidence
- `{displayNames}` — **Display name của từng người** (MH_HoangMV, PhongDT, ...), cách nhau bằng dấu phẩy
- `{totalFiles}` — Tổng số ảnh
- `{sharingMode}` — "anyone" hoặc "restricted"
- `{sharingExplain}` — Giải thích chi tiết về chế độ chia sẻ

**Lưu ý:**
- Dùng **display_name** từ Slack (MH_HoangMV, không phải "Viethoang Mai")
- Nếu script báo có người **thiếu email** → thêm 1 dòng `• Thiếu email: {tên}` vào preview, đừng bỏ qua

---

## Action 1: Tổng hợp thread thành sheet mới

### Nhận diện intent

- "tổng hợp thread này thành sheet", "log evd thread này", "gom evidence trong thread ... vào 1 file"
- PM tag bot ngay trong thread kèm yêu cầu tương tự

### Quy trình

**Bước 1 — Xác định thread**

PM đưa link thread (dạng `https://<team>.slack.com/archives/<channel>/p<ts>?thread_ts=...`) hoặc tag bot trong chính thread đó. Nếu PM chỉ nói "thread kia" mà không rõ → hỏi lại, KHÔNG tự đoán.

**Bước 2 — Đọc thread và tải file**

```bash
cd openclaw-skills/slack-evidence-sheet
node scripts/slack-fetch.js "<link thread>" ./downloads
```

Script tải toàn bộ file về `./downloads/` và sinh `downloads/manifest.json`. Đọc log để biết ai lấy được email, file nào tải lỗi.

**Bước 3 — Preview (BẮT BUỘC, trước khi tạo bất cứ gì trên Drive)**

```bash
node scripts/build-sheet.js ./downloads/manifest.json ./config.json --dry-run
```

Script in ra số liệu thô. Diễn đạt lại cho PM đúng theo **Preview Format** ở trên — KHÔNG dán nguyên output của script.

**Bước 4 — Thực thi (chỉ sau khi PM xác nhận rõ ràng)**

```bash
node scripts/build-sheet.js ./downloads/manifest.json ./config.json
```

Script tự làm theo thứ tự: tạo folder → upload ảnh → set chia sẻ → tạo sheet trong folder → sửa locale/timezone → ghi header + dòng dữ liệu → format → share cho `viewers`.

**Bước 5 — Phản hồi**

Script in ra link sheet + link folder. Diễn đạt lại cho PM đúng theo **Response Format** ở dưới — KHÔNG dán nguyên output của script.

**Bước 6 — Dọn dẹp**

Hỏi PM có muốn xoá thư mục `downloads/` không (ảnh đã nằm trên Drive). Mặc định **giữ lại**, KHÔNG tự xoá.

---

## Response Format (Khi skill chạy xong)

Trả lời theo format cố định này:

```
✓ Xong rồi anh {PM_name}. Em đã tổng hợp {totalFiles} ảnh của {totalPeople} người trong thread thành sheet:

• 📋 Sheet: <{sheetLink}|Mở sheet>
• 📁 Folder: <{folderLink}|Mở folder ảnh>

Mỗi người 1 dòng, ảnh gom vào ô Evidence dạng link bấm ra Drive xem được. Anh check thử nhé, cần thêm cột gì hay bổ sung ai chưa nộp thì báo em.
```

Các biến cần điền:
- `{PM_name}` — Tên PM gọi skill
- `{totalFiles}` — Tổng số ảnh được tải
- `{totalPeople}` — Tổng số người có evidence
- `{sheetLink}` — Link đến Google Sheet vừa tạo
- `{folderLink}` — Link đến Google Drive folder

**Bắt buộc về link — đã hỏng 2 lần, đừng lặp lại:**

Link PHẢI viết theo cú pháp Slack `<url|chữ hiển thị>`, KHÔNG dán URL trần.

Lý do: nếu một dòng kết thúc bằng URL trần và dòng kế tiếp bắt đầu bằng emoji, Slack nuốt cả ký tự xuống dòng lẫn emoji vào trong URL. Kết quả là link hỏng **và** Folder bị kéo lên chung dòng với Sheet. Dấu `>` trong `<url|text>` đóng URL lại nên chặn được cả hai.

- Sheet và Folder nằm trên **2 dòng riêng**, mỗi dòng mở đầu bằng `• `
- Emoji đứng sau `• `, KHÔNG bao giờ đặt sau link
- Sau `>` đóng link thì hết dòng, không thêm dấu câu hay chữ nào

Dấu `• ` là lớp chặn thứ hai: nó đẩy emoji ra khỏi vị trí đầu dòng, mà "emoji ngay đầu dòng, ngay sau một dòng kết thúc bằng URL" chính là tình huống Slack nuốt ký tự xuống dòng.

---

## Action 2: Bổ sung người chưa nộp

### Nhận diện intent

- "thêm cả những người chưa gửi vào", "ai chưa nộp thì để trống"

### Quy trình

Lấy danh sách thành viên kênh (`conversations.members` + `users.info`), trừ đi những người đã có trong `manifest.json` → phần còn lại là chưa nộp. Preview danh sách này cho PM xác nhận (dễ có bot/người đã nghỉ trong kênh), rồi thêm vào sheet với cột evidence để trống.

KHÔNG tự động làm bước này trong Action 1 — chỉ làm khi PM yêu cầu, vì danh sách thành viên kênh thường lẫn người không thuộc dự án.

---


## Error Handling

| Lỗi | Phản hồi |
| --- | --- |
| `slack-fetch.js` báo `not_in_channel` | Bot chưa được mời vào kênh → nhờ PM `/invite @bot` vào kênh đó |
| `missing_scope` | Bot token thiếu scope → báo rõ scope nào đang thiếu, cần cấp lại trong Slack App config rồi reinstall app |
| Tải file trả về HTML | Token thiếu `files:read` — Slack trả trang login thay vì file |
| `users.info` lỗi / không có email | Để trống cột email, liệt kê tên đó trong preview. KHÔNG đoán email |
| `storageQuotaExceeded` khi tạo file | Đang dùng nhầm Service Account thay vì OAuth — kiểm tra `GOOGLE_OAUTH_TOKEN_FILE` |
| `invalid_grant` khi refresh token | Refresh token hết hạn (app còn ở Testing quá 7 ngày) hoặc bị thu hồi → chạy lại `scripts/oauth-setup.js`, và Publish app |
| Ô công thức hiện `#ERROR!` | Sheet đang ở locale `vi_VN` (ngăn tham số bằng `;`) → script đã tự set `en_US`; nếu vẫn lỗi thì kiểm tra bước `updateSpreadsheetProperties` có chạy không |
| Ảnh không hiện dù `imageDisplay: image` | Ảnh chưa ở chế độ `anyone` — máy chủ Sheets tải ẩn danh nên ảnh riêng tư luôn ra ô trống |
| Share cho email lỗi | Email đó có thể chưa phải tài khoản Google → báo PM, các bước khác vẫn hoàn tất |
| PM trả lời "không" ở bước xác nhận | "Đã huỷ, chưa tạo gì trên Drive." |
