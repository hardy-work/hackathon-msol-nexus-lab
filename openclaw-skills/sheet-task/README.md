# sheet-task

Backend cho bot quản lý tiến độ dự án trên Google Sheet **NexusBot_Schedule_v2.1**.

Bot đọc backlog, ghi báo cáo tiến độ (Actual Effort / Status / ngày), và tự dồn
lại lịch PLAN khi thực tế lệch ước lượng — tất cả qua một Apps Script Web App,
không cần server, không cần Google Cloud.

Về bản chất đây là một **backend nhỏ**: Apps Script đóng vai BE (xác thực,
validate, business logic), Google Sheet đóng vai database, lớp AI/chat đóng vai
frontend ra lệnh.

## Các file

| File               | Vai trò                                                         | Chạy ở đâu              |
| ------------------ | --------------------------------------------------------------- | ----------------------- |
| `Code.gs`          | Backend chính: doGet/doPost, validate, dồn lịch, định danh dòng | Apps Script (đã deploy) |
| `SlackMap.gs`      | Danh bạ `slack_id → assignee` (thay `user/search` của Jira)     | Apps Script             |
| `Backfill.gs`      | Gắn `taskId` bền cho từng dòng — chạy tay 1 lần                 | Apps Script             |
| `FillPlanDates.gs` | Tính lại toàn bộ lịch từ đầu — chạy tay 1 lần                   | Apps Script             |
| `Test.gs`          | Kiểm thử backend, không sửa sheet — chạy tay                    | Apps Script             |
| `SKILL.md`         | Hướng dẫn cho agent: luồng giao việc + nhận report              | Lớp AI                  |
| `sheet.sh`         | Wrapper `curl` (xử lý redirect 302 + unicode)                   | Máy/agent               |
| `.env`             | `SHEET_WEBHOOK_URL` + `SHEET_API_TOKEN` (gitignored)            | Máy/agent               |

## Vì sao Apps Script, không phải OAuth2 / Service Account

Google Sheets API **không cho ghi bằng API key** — chỉ OAuth2 hoặc Service
Account, cả hai đều cần ký token và kèm script Python/Node chạy ngoài.

Apps Script gắn trong chính file sheet nên đã có sẵn quyền: không share cho ai,
không Google Cloud, agent gọi vào bằng một dòng `curl`. Vì một bot phụ trách một
sheet cố định, đây là lựa chọn gọn nhất. Logic nghiệp vụ (dồn lịch, validate)
thì đường nào cũng phải tự viết — nằm trong `Code.gs`.

## Kiến trúc

```
Lớp AI / chat  ──HTTP──►  Web App /exec  ──►  Code.gs  ──►  Google Sheet
  (ra lệnh)      token       (doGet/doPost)   (BE logic)     (database)
```

- **GET** (`?action=...&token=...`): ping · tabs · list · get · holidays · map · resolve
- **POST** (`{action, token, ...}`): update · reschedule · fillplan · map_set

`reschedule` vs `fillplan`: `fillplan` lập lịch mới từ cột **Estimate** (dùng
đầu sprint, ghi đè plan cũ); `reschedule` điều chỉnh lịch có sẵn khi thực tế
lệch (giữ task đang làm dở, trừ giờ đã làm, không kéo lên sớm). Cả hai né T7/CN
+ lễ và có `dryRun`.

Web App deploy dạng _Execute as: Me_ → bot thao tác dưới tài khoản người deploy.
_Who has access: Anyone_ → gọi được không cần đăng nhập Google; hàng rào thật là
`API_TOKEN`, request sai token bị trả `unauthorized`.

## Cấu trúc sheet

Nhiều tab cùng khung bảng: `Config` (danh mục Status/PIC/Type + lịch lễ),
`Backlog_OLD`, các tab sprint, UAT, CR. Bot chỉ dùng **tab sprint** (chọn bằng
`SHEET_GID`).

Layout tab sprint:

```
dòng 1     B1 = tên sprint
dòng 4-6   header (merge 3 dòng, nhóm cha PLAN / Actual)
dòng 8     hàng tổng
dòng 9+    dữ liệu thật   (DATA_START_ROW = 9)
```

19 cột A→S. Ba cột là **công thức, không ghi đè**: `no` (A), `progress` (O),
`remaining_h` (Q). Bot chỉ ghi 9 cột trong `WRITABLE`: assignee, plan_start/end,
actual_reestimate_h, actual_start/end, actual_effort_h, status, note.

`Status` hợp lệ (từ tab `Config`): Open · Study · Code done · Reviewing ·
Testing · Verify bug · Done · In progress · N/A · ﾕｰﾄﾞﾑ様確認待ち · Pending ·
Chờ KH phản hồi · Cancel.

## Cài đặt

**Trên trình duyệt (một lần):**

1. Mở Sheet → **Tiện ích mở rộng → Apps Script**
2. Dán `Code.gs`, thêm file `SlackMap.gs` và `Backfill.gs`
3. Chạy `setupToken` → mở **Nhật ký** copy token
4. **Triển khai → Ứng dụng web**: _Execute as: Me_, _Who has access: Anyone_
5. Copy URL `.../exec`
6. Chạy `backfillTaskIds` một lần → gắn `taskId` cho tab sprint
7. (Tùy) chạy `createSlackMapTab` → tạo danh bạ Slack

**Trên máy:**

```bash
cp .env.example .env      # điền SHEET_WEBHOOK_URL (đuôi /exec) + SHEET_API_TOKEN
```

Cập nhật code sau này: sửa file `.gs` → **Triển khai → Quản lý các lần triển
khai → ✏️ → Phiên bản mới** (giữ nguyên URL). Nếu tạo deploy mới thì URL đổi,
phải sửa lại `.env`.

## Cách dùng — `sheet.sh`

Dùng `sheet.sh` thay vì `curl` trực tiếp: nó xử lý hai cái bẫy của Apps Script
(redirect 302 làm hỏng POST, và Windows làm hỏng ký tự tiếng Nhật/Việt).

```bash
# Đọc
./sheet.sh get ping
./sheet.sh get list 'assignee=Duy'
./sheet.sh get get 'row=9'

# Ghi (dryRun để xem trước, không sửa sheet)
./sheet.sh post '{"action":"update","dryRun":true,"updates":[
  {"taskId":"<id>","fields":{"actual_effort_h":8,"status":"In progress"}}]}'

# Payload dài / có tiếng Nhật → để trong file, tránh shell quoting
./sheet.sh post @report.json

# Dồn lịch (dryRun mặc định true)
./sheet.sh post '{"action":"reschedule","assignee":"Duy","from":"2026-07-28"}'
```

**Apps Script luôn trả HTTP 200 kể cả khi lỗi** — đọc trường `ok` trong JSON,
không nhìn status code.

## Định danh dòng — xếp tầng

Cột `No.` là công thức đếm theo vị trí, không phải ID. Bot định vị dòng theo thứ
tự bền dần:

1. **`taskId`** (Developer Metadata) — ID vô hình gắn trên dòng, đi theo dòng
   khi chèn/xoá/kéo thả, và không phải văn bản nên sửa tên task cũng không sao.
   Đường chính. `list`/`get` trả kèm `taskId`; gửi lại khi ghi. Nếu row lệch,
   backend tìm theo ID và báo `relocated`.
2. **Khoá 4 cột + `expect`** — `assignee`+`category`+`task`+`subtask_vi`. Đệm
   cho dòng PM mới gõ tay chưa có `taskId`.
3. **Từ chối ghi** — cả hai hỏng thì backend không ghi, agent hỏi lại.

Không cơ chế nào chịu được **copy-paste ô sang dòng mới** (tạo dữ liệu mới, ID
không theo) — trường hợp đó rơi về khoá 4 cột. `taskId` hoàn toàn ẩn với người
dùng.

## Ba lớp bảo vệ khi ghi

1. **Danh sách trắng `WRITABLE`** — chỉ 9 field ghi được; cột công thức và mốc
   định danh không nằm trong đó.
2. **`getFormula()`** — kiểm tra ô đích ngay trước khi ghi, có công thức thì từ
   chối (kể cả field hợp lệ). Ghi đè công thức là mất vĩnh viễn.
3. **`taskId` / `expect`** — đảm bảo đúng dòng (xem mục trên).

Thêm `LockService` chặn hai request ghi cùng lúc, và mọi `update`/`reschedule`
có `dryRun` để xem trước.

## Quy tắc dồn lịch (`reschedule`)

8h/ngày · giờ chảy liên tục (task dư giờ tràn sang ngày sau, task kế tiếp bắt
đầu từ giờ trống còn lại) · mỗi người một hàng đợi · bỏ T7/CN **và ngày lễ** ·
task đang làm dở giữ nguyên `plan_start`, chỉ đẩy `plan_end` · không kéo task
lên sớm hơn ngày PM đã xếp (`NEVER_EARLIER`) · giờ còn lại = (Re-estimate hoặc
Estimate) − Actual Effort.

Ngày lễ đọc thẳng từ cột **Date** của tab `Config` (`holidaySet_` trong
`Code.gs`) — PM sửa lễ trong Config là bot dùng ngay, không cần đụng code. Xem
danh sách bot đang dùng: `./sheet.sh get holidays`.

## Dữ liệu bẩn đã xử lý

- **Ngày rác** `30-12-1899` (mốc 0 của Sheets) và `29-12-4420` → trả `""`, chỉ
  nhận năm 2000-2100.
- **Ô `#REF!`** (công thức hỏng có sẵn) → trả `""` kèm `cell_errors` để agent
  biết ô hỏng, không tưởng là chưa nhập.
- **Cột P** (ô merge của Progress) → bỏ qua.
- **Tên có dấu cách thừa** (`"Review test case "`) → so sánh đều trim.

## Giới hạn đã biết

- **Phụ thuộc giữa task** chỉ nằm trong cột Note dạng văn xuôi, sheet không có
  cột phụ thuộc. Bot không tự suy thứ tự — cần PM quyết.
- **Phát sinh phạm vi và ước lượng sai bị gộp chung** vào Re-estimate.
- **Mọi thao tác bot mang tên tài khoản deploy** (Execute as: Me), không phân
  biệt được ai ra lệnh. Cần audit theo người thì phải ghi vào cột Note (tự khai)
  hoặc chuyển Service Account.
