# slack-evidence-sheet — Cách dùng

Skill gom **1 thread Slack thu thập bằng chứng** thành **1 Google Sheet mới**: mỗi người 1 dòng, có tên, email, giờ gửi và ảnh đính kèm đã upload lên Google Drive. Xem [`SKILL.md`](SKILL.md) cho luồng chi tiết.

Ví dụ câu lệnh: _"tổng hợp thread này thành sheet log evidence"_ kèm link thread.

## Vì sao skill này dùng OAuth chứ không dùng Service Account như `gg-sheet`

`gg-sheet` chỉ **sửa** một sheet có sẵn do người thật sở hữu, nên Service Account đủ dùng. Skill này phải **tạo file mới**, mà Service Account không có storage quota — `files.create` luôn trả `storageQuotaExceeded`, kể cả khi ghi vào folder do người dùng sở hữu, vì owner của file mới vẫn là SA.

Ranh giới chung cho repo: **skill chỉ sửa file có sẵn thì dùng Service Account, skill tạo file mới thì dùng OAuth.**

## Setup

### 1. Google — OAuth client

Trong GCP Console (project nào cũng được, có thể dùng chung project với `gg-sheet`):

1. Bật **Google Drive API** và **Google Sheets API** trong _APIs & Services → Library_.
2. _Google Auth Platform → Get started_: điền app name + email, Audience chọn **Internal** nếu tài khoản thuộc Workspace, không thì **External**.
3. Nếu chọn External → vào **Audience** bấm **Publish app**. Bỏ qua bước này thì refresh token chết sau 7 ngày.
4. _Clients → Create client → Desktop app_ → **Download JSON**, lưu thành `oauth-client.json` trong thư mục skill này.

```bash
cp .env.example .env      # điền SLACK_BOT_TOKEN, trỏ đúng 2 đường dẫn file
node scripts/oauth-setup.js
```

Script in ra 1 URL — mở trên trình duyệt, đăng nhập bằng **tài khoản sẽ sở hữu các file evidence**, bấm Đồng ý. Gặp màn "Google hasn't verified this app" thì bấm Advanced → Go to ... (bình thường với app tự tạo). Xong, `oauth-token.json` được ghi ra.

### 2. Slack — bot token

Bot cần các scope: `channels:history` (kênh public) hoặc `groups:history` (private), `files:read`, `users:read`, `users:read.email`. Cấp trong Slack App config → OAuth & Permissions → reinstall app → copy `xoxb-...` vào `.env`.

Bot cũng phải **là thành viên của kênh** chứa thread, nếu không sẽ lỗi `not_in_channel`.

### 3. Config cho từng đợt

```bash
cp config.example.json config.json
```

Sửa `columns`, `sheetTitle`, `viewers` theo đợt. Hai field cần cân nhắc:

- `imageSharing` — `anyone` nghĩa là **bất kỳ ai có link đều xem được ảnh**, kể cả người ngoài công ty. Đây là điều kiện bắt buộc nếu muốn ảnh hiện trực tiếp trong ô. Cần thì đổi sang `restricted` và liệt kê email vào `viewers`.
- `imageDisplay` — `link` cho ô chứa hyperlink (bấm ra Drive, **zoom được**, hợp với screenshot chữ nhỏ); `image` để nhúng ảnh vào ô (xem nhanh nhưng không zoom).

Đợt sau đổi nghiệp vụ thì sửa `config.json`, không sửa `SKILL.md` — `SKILL.md` được commit và đồng bộ cho cả team, `config.json` thì gitignored, riêng từng máy.

## Chạy tay (không qua agent)

```bash
export SLACK_BOT_TOKEN=xoxb-...
export GOOGLE_OAUTH_TOKEN_FILE=./oauth-token.json

node scripts/slack-fetch.js "<link thread>" ./downloads
node scripts/build-sheet.js ./downloads/manifest.json ./config.json --dry-run   # xem trước
node scripts/build-sheet.js ./downloads/manifest.json ./config.json             # tạo thật
```

## Known limitations

- Scope `drive.file` chỉ cho app đụng vào file **do chính nó tạo** → skill luôn tạo folder gốc mới, không ghi được vào folder có sẵn trên Drive.
- File tạo ra thuộc sở hữu **cá nhân** đã bấm đồng ý. Người đó rời dự án thì phải chuyển quyền sở hữu tay. Dùng Shared Drive sẽ giải quyết triệt để nếu sau này tài khoản được nâng lên Google Workspace.
- Sheet tạo qua API mặc định `locale: vi_VN` + `timeZone: Etc/GMT`; script tự sửa về `en_US` + `Asia/Ho_Chi_Minh`. Không sửa thì mọi công thức nhiều tham số (`=HYPERLINK("a","b")`) đều `#ERROR!` vì vi_VN ngăn tham số bằng `;`.
- Ở chế độ `imageDisplay: "link"`, mọi ảnh của một người nằm gọn trong **1 ô**, mỗi ảnh một dòng. Không dùng `=HYPERLINK` được (một ô chỉ chứa 1 link) nên script gắn link bằng `textFormatRuns` — sửa tay nội dung ô đó trong Sheets sẽ làm mất link, phải chạy lại script.
- Ở chế độ `imageDisplay: "image"` thì ngược lại: một ô chỉ chứa được 1 `=IMAGE()`, nên cột `images` nở ra thành `Evidence 1`, `Evidence 2`, … đúng bằng số ảnh nhiều nhất của một người. Số cột vì vậy thay đổi theo dữ liệu.
- Chỉ tổng hợp người **có gửi file**. Muốn liệt kê cả người chưa nộp thì yêu cầu riêng (Action 2 trong `SKILL.md`).
- Bot phải được `/invite` vào kênh trước khi chạy. Theo tài liệu Slack, `channels:history` cho đọc cả lịch sử **trước** lúc bot tham gia nên ảnh cũ vẫn tải được — nhưng điều này **chưa được kiểm chứng thực tế**, cần thử ngay lần chạy đầu với một thread cũ.
