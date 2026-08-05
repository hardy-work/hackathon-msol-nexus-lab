# slack-evidence-sheet — Cách dùng

Skill gom **1 thread Slack thu thập bằng chứng** thành **1 Google Sheet mới**: mỗi người 1 dòng, có tên, email, giờ gửi và ảnh đính kèm đã upload lên Google Drive. Xem [`SKILL.md`](SKILL.md) cho luồng chi tiết.

Ví dụ câu lệnh: _"tổng hợp thread này thành sheet log evidence"_ kèm link thread.

## Vì sao skill này dùng OAuth chứ không dùng Service Account như `gg-sheet`

`gg-sheet` chỉ **sửa** một sheet có sẵn do người thật sở hữu, nên Service Account đủ dùng. Skill này phải **tạo file mới**, mà Service Account không có storage quota — `files.create` luôn trả `storageQuotaExceeded`, kể cả khi ghi vào folder do người dùng sở hữu, vì owner của file mới vẫn là SA.

Ranh giới chung cho repo: **skill chỉ sửa file có sẵn thì dùng Service Account, skill tạo file mới thì dùng OAuth.**

## Yêu cầu trước setup

- **Node.js** v14+ (cài từ https://nodejs.org)
- **npm** (đi kèm Node.js)
- **Tài khoản Google** có Google Workspace hoặc tài khoản cá nhân
- **Slack workspace** + bot token có đủ scope
- **Git** (để clone repo)

Kiểm tra:
```bash
node --version    # v14+
npm --version     # có version
```

---

## Setup

### 1. Google — OAuth client

#### Nếu chưa có GCP project

Vào **https://console.cloud.google.com**:

1. Bấm **Select a Project** (ở top) → **New Project** → điền tên (ví dụ "evidence-bot")
2. Chọn project vừa tạo
3. Vào **APIs & Services → Library**, tìm và bật:
   - **Google Drive API** → bấm **Enable**
   - **Google Sheets API** → bấm **Enable**

#### Setup OAuth client

Trong GCP Console (project vừa tạo hoặc project có sẵn):

1. Vào **APIs & Services → OAuth consent screen**:
   - Nếu chưa setup → bấm **Get started** → chọn Audience:
     - **External** (nếu tài khoản không phải Google Workspace)
     - **Internal** (nếu tài khoản thuộc Google Workspace công ty)
   - Điền **App name** + **Email** → **Create**
   
   > Sau khi "OAuth configuration created!", tiếp tục các bước dưới

2. Vào tab **Audience** (ở sidebar):
   - Ở phần **Test users** → bấm **Add users**
   - Điền email của account sẽ **sở hữu file evidence** (công cụ sẽ chạy nhân danh account này)

3. Ở phần **Publishing status** → bấm nút xanh **"Publish app"**:
   - ⚠️ Bắt buộc để refresh token không hết hạn sau 7 ngày
   - Scope `drive.file` là non-sensitive nên publish ngay, không cần chờ Google kiểm duyệt
   - Sau khi publish, status sẽ đổi thành "In production"

4. Vào **APIs & Services → Credentials** (ở sidebar):
   - Bấm **Create Credentials → OAuth client ID**
   - Application type: **Desktop app** → **Create**
   - Bấm nút **Download** (mũi tên ⬇️) → Copy JSON

5. Lưu `oauth-client.json` vào thư mục skill:
   ```bash
   cd openclaw-skills/slack-evidence-sheet
   # Dán JSON từ bước trên vào file oauth-client.json
   cat > oauth-client.json << 'EOF'
   {nội dung JSON tải được}
   EOF
   ```

#### Setup .env và lấy refresh token

6. Tạo file `.env`:
   ```bash
   cp .env.example .env
   ```

7. Sửa `.env`, điền **SLACK_BOT_TOKEN** (bot cần scope: `channels:history`, `groups:history`, `files:read`, `users:read`, `users:read.email`):
   ```
   SLACK_BOT_TOKEN=xoxb-...
   GOOGLE_OAUTH_CLIENT_FILE=./oauth-client.json
   GOOGLE_OAUTH_TOKEN_FILE=./oauth-token.json
   ```

8. Cài package `dotenv` (để script tự load `.env`):
   ```bash
   npm install dotenv
   ```

9. Chạy script OAuth setup:
   ```bash
   node scripts/oauth-setup.js
   ```
   
   Script sẽ:
   - Tải `.env` tự động (từ package `dotenv`)
   - Kiểm tra file `oauth-client.json`
   - In ra 1 URL dài (bắt đầu bằng `https://accounts.google.com/...`)
   - Dừng lại chờ bạn

   Khi thấy URL, **copy → dán vào trình duyệt → Enter**

10. Đăng nhập và cấp quyền:
   - **Thấy màn "Sign in"** → chọn hoặc nhập email **BotNexusAcc** (account sẽ sở hữu file)
   - **Nhập password**
   - **Thấy màn "App requests access to..."** → bấm nút xanh **"Allow"** hoặc **"Agree"**
   
   > Nếu gặp **"Google hasn't verified this app"** → bấm **Advanced** → **Go to ...** (bình thường cho app tự tạo)

11. Hoàn tất:
   - Browser hiển thị **"Authorization successful"** hoặc tương tự
   - Quay lại **terminal** → script đã tự viết file `oauth-token.json` ✅
   - Nếu terminal vẫn chạy, bấm **Ctrl+C** để thoát
   - Kiểm tra file được tạo:
     ```bash
     ls -la oauth-token.json
     ```

#### Setup Config cho từng đợt

12. Copy config mẫu:
   ```bash
   cp config.example.json config.json
   ```

13. Sửa `config.json` theo nhu cầu của đợt:
   ```json
   {
     "sheetTitle": "Evidence log {date}",      // Tên file sheet (hỗ trợ {date})
     "folderName": "Evidence {date}",          // Tên folder Drive
     "imageFolderName": "Ảnh evidence",        // Tên folder con chứa ảnh
     "imageSharing": "anyone",                 // "anyone" = ai có link xem được, "restricted" = chỉ viewers
     "viewers": [],                            // Email được share (để trống = chỉ mình bạn)
     "imageDisplay": "link",                   // "link" = link tới Drive, "image" = nhúng ảnh vào ô
     "columns": [                              // Các cột trong sheet
       { "key": "stt", "header": "STT", "width": 50 },
       { "key": "name", "header": "Tên", "width": 180 },
       { "key": "email", "header": "Email", "width": 220 },
       { "key": "sentAt", "header": "Giờ gửi", "width": 140 },
       { "key": "images", "header": "Evidence", "width": 260 },
       { "key": "note", "header": "Ghi chú", "width": 200 }
     ]
   }
   ```

   **Lưu ý:**
   - `imageDisplay: "image"` chỉ hoạt động khi `imageSharing: "anyone"` (Google Sheets tải ảnh ẩn danh)
   - Nếu chọn `imageSharing: "anyone"` → bất kỳ ai có link đều xem được ảnh, kể cả ngoài công ty
   - Custom field: thêm `{ "key": "your-key", "header": "Tên cột", "width": 200 }` để tạo cột tùy biến

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

## Tên hiển thị

Hai thứ không lấy nguyên bản từ Slack:

- **Tên người** — lấy `profile.display_name` (`MH_HoangMV`, `PhongDT`), không phải `real_name` (`Viethoang Mai`). Đây là tên team thực sự gọi nhau trong Slack nên dễ đối chiếu hơn. Ai không đặt display name thì tự động rơi về `real_name`.
- **Tên ảnh** — rút gọn thành `ảnh 1`, `ảnh 2`, … cả trong ô Evidence lẫn tên file trên Drive (`MH_HoangMV — ảnh 1`). Tên gốc từ Slack thường là `Screenshot 2026-07-29 at 15.18.55.png`, dài và không mang thông tin gì.

## Định dạng câu trả lời

`SKILL.md` có hai section **Preview Format** và **Response Format** quy định bot nói gì với PM ở bước xác nhận và bước báo kết quả. Đây là nguồn duy nhất — các bước trong Action 1 chỉ trỏ tới chúng.

OpenClaw **không** đọc template từ frontmatter (`metadata.openclaw` chỉ dùng để gating `requires.bins` / `requires.env`), nên template phải nằm trong phần body của `SKILL.md` thì model mới thấy. Muốn đổi cách bot phát biểu thì sửa hai section đó.

### Sửa SKILL.md giữa phiên thì phải bảo bot đọc lại

Bot giữ nội dung `SKILL.md` trong ngữ cảnh của phiên, **không tự đọc lại khi file đổi**. Sửa xong mà nhờ bot chạy luôn thì nó vẫn dùng bản cũ, ra kết quả y như chưa sửa gì — rất dễ kết luận nhầm là bản sửa không có tác dụng rồi đi sửa tiếp thứ vốn đã đúng.

Muốn bản mới có hiệu lực thì nói thẳng, ví dụ:

```
@NexusBot đọc lại SKILL.md rồi chạy lại giúp anh
```

Không cần commit hay push — bot đọc thẳng file trong thư mục làm việc, kể cả khi đang sửa dở chưa commit.

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
- Ở chế độ `imageDisplay: "link"`, mọi ảnh của một người nằm gọn trong **1 ô**, mỗi ảnh một dòng. Không dùng `=HYPERLINK` được (một ô chỉ chứa 1 link) nên script gắn link bằng `textFormatRuns` — link được gắn theo **offset ký tự**, nên sửa tay nội dung ô đó trong Sheets sẽ làm lệch hoặc mất link, phải chạy lại script.
- Ở chế độ `imageDisplay: "image"` thì ngược lại: một ô chỉ chứa được 1 `=IMAGE()`, nên cột `images` nở ra thành `Evidence 1`, `Evidence 2`, … đúng bằng số ảnh nhiều nhất của một người. Số cột vì vậy thay đổi theo dữ liệu.
- `build-sheet.js` lỗi giữa chừng **trước** khi ghi được dữ liệu vào sheet thì tự xoá folder vừa tạo trên Drive — đừng đi tìm, nó biến mất có chủ đích để Drive không tích tụ folder dở dang. Lỗi **sau** khi dữ liệu đã ghi xong thì giữ lại và in link, vì sheet lúc đó đã dùng được, chỉ thiếu định dạng. Không có cơ chế chạy tiếp từ chỗ dở: chạy lại là làm lại từ đầu.
- Chỉ tổng hợp người **có gửi file**. Muốn liệt kê cả người chưa nộp thì yêu cầu riêng (Action 2 trong `SKILL.md`).
- Bot phải được `/invite` vào kênh trước khi chạy. Theo tài liệu Slack, `channels:history` cho đọc cả lịch sử **trước** lúc bot tham gia nên ảnh cũ vẫn tải được — nhưng điều này **chưa được kiểm chứng thực tế**, cần thử ngay lần chạy đầu với một thread cũ.
