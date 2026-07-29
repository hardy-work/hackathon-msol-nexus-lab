---
name: daily-report
description: Nhắc report task hàng ngày qua cron chính xác, follow-up DM riêng người thiếu, xử lý report bị sửa, đẩy Google Sheets / Jira sau xác nhận.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📋",
        "requires":
          {
            "env":
              [
                "SLACK_REPORT_CHANNEL",
                "SLACK_REPORT_CHANNEL_ID",
                "REMINDER_TIME",
                "REMINDER_TIMEZONE",
                "FOLLOWUP_INTERVAL_MINUTES",
                "FOLLOWUP_CUTOFF_TIME",
              ],
          },
      },
  }
---

## Quy tắc bất biến

- Không ghi Sheets/Jira mà không preview + xác nhận trước (như
  [`../jira-task/SKILL.md`](../jira-task/SKILL.md)).
- Thiếu `issueKey`/`status`/`hoursWorked`/`note` (hoặc thiếu
  `extraHoursNeeded` khi chưa "Hoàn thành") → hỏi lại, không đoán.
- Lỗi API → báo rõ, không tự retry.
- **Không bao giờ giao việc đọc/gửi Slack (đọc kênh, đọc thread, DM, đăng
  tin) cho subagent** — tool `slack` chỉ cấp cho phiên chính (main/cron
  session), subagent gọi sẽ luôn lỗi `No such tool available: slack`. Mọi
  bước liên quan Slack trong skill này phải chạy trực tiếp (inline) trong
  phiên đang xử lý job, không delegate.

## State file

`{baseDir}/state/<YYYY-MM-DD>.json`, tạo mới rỗng mỗi ngày:

```json
{
  "reminderThreadTs": "1690000000.000100",
  "reports": {
    "<slack_user_id>": {
      "reporter": "MH_SonBH", "messageTs": "...", "issueKey": "NEX-30",
      "status": "Đang làm", "hoursWorked": "3h", "note": "...",
      "extraHoursNeeded": "2h",
      "pushState": "pending|confirmed|declined",
      "sheetRow": 42
    }
  }
}
```

## Format tin nhắc chuẩn (BẮT BUỘC, không được diễn giải lại)

Mọi tin nhắc report — dù do Job A (cron) tự động chạy, hay do ai đó nhắn tay
bảo bot nhắc (vd "nhắc report đi", "nhắc lại mọi người report", "xem ai chưa
report") — **PHẢI dùng đúng nguyên văn template dưới đây**, chỉ được thay 2
chỗ: danh sách `@mention` (hoặc `<!channel>` nếu không lấy được danh sách ai
chưa report) và `<DD/MM>`. KHÔNG được tự thêm/bớt câu chữ, không đổi icon,
không viết lại theo văn phong khác mỗi lần, không thêm bullet "Hôm qua làm
gì / Hôm nay làm gì" tự chế:

```
⏰ Đến giờ report task rồi: <mention_list> chưa report hôm nay nhé!

Report theo mẫu sau (copy và điền vào):
<NEX-số> | <trạng thái> | <giờ đã làm> | <ghi chú>
(Chưa xong thì thêm: · cần thêm <N>giờ)
```

- `<mention_list>` = `@user1 @user2 ...` (danh sách ai chưa report, lấy theo
  logic Job A ở dưới) — nếu không xác định được danh sách (vd lỗi đọc lịch sử
  kênh/thành viên), dùng `<!channel>` thay cho `<mention_list>`, **không** đổi
  sang icon/câu chữ khác để "linh hoạt hơn".
- Nếu người dùng nhắn tay yêu cầu nhắc lại (không phải qua cron), vẫn áp dụng
  đúng template này, không tự sáng tác lời nhắc mới mỗi lần được hỏi.

## Format report chuẩn

```
<NEX-số> | <trạng thái> | <giờ đã làm> | <ghi chú>
```
Nếu `<trạng thái>` khác "Hoàn thành", nối thêm ở cuối dòng:
```
 · cần thêm <N>giờ
```

Ví dụ:
```
NEX-30 | Hoàn thành | 4h | Fix xong bug login SSO
NEX-45 | Đang làm | 3h | Đang debug API auth · cần thêm 2h
NEX-12 | Blocked | 1h | Chờ credential từ DevOps · cần thêm 2h
```

- `<NEX-số>` = issue key Jira (bắt buộc, đúng dạng `NEX-\d+`).
- `<trạng thái>` = "Đang làm" / "Hoàn thành" / "Blocked" (chuẩn hoá nếu người
  dùng viết khác đi, vd "done" → "Hoàn thành", "vướng" → "Blocked").
- `<giờ đã làm>` = số giờ đã làm hôm nay cho issue này, dạng `<X>h` (vd `4h`,
  `1.5h`).
- `<ghi chú>` = mô tả ngắn công việc đã làm (đóng vai trò vừa là note vừa là
  mô tả task, không có field task riêng nữa).
- `cần thêm <N>giờ` = ước tính số giờ còn cần để xong issue — **bắt buộc**
  nếu trạng thái khác "Hoàn thành", **không có** nếu đã "Hoàn thành".

Report = reply vào thread `reminderThreadTs` trong `SLACK_REPORT_CHANNEL`
(không phải tin rời trong kênh), hoặc DM lại tin nhắc ở job follow-up. Chấp
nhận lệch nhỏ so với format (vd thiếu dấu cách quanh `|`), hoặc fallback tự do
(VN/EN) nếu suy ra đủ issue key + trạng thái + giờ đã làm — ưu tiên hướng
người dùng theo đúng format khi có thể.

## Cron (setup 1 lần, dùng cron expression thật — không diễn giải giờ chung
chung để tránh trôi giờ; gán `--model sonnet` vì việc này không cần reasoning
nặng, giảm độ trễ xử lý)

**Job A — nhắc (`REMINDER_TIME`, mặc định 11:00 → `0 11 * * *`; đổi field
giờ/phút nếu khác, vd 09:30 → `30 9 * * *`):**

```bash
openclaw cron create "0 11 * * *" \
  "Việc A skill daily-report: đăng tin nhắc report, lưu message ts vào state." \
  --name daily-report-reminder --tz "$REMINDER_TIMEZONE" \
  --session isolated --model sonnet --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```
`--announce` bắt buộc — thiếu nó, cron chạy xong vẫn không tự đẩy kết quả ra
Slack (`delivered: false` dù `status: ok`).
Chạy: reset state ngày mới nếu chưa có → đọc thread cũ + state để biết ai đã
report → nếu còn ai chưa, đăng tin **đúng nguyên văn "Format tin nhắc chuẩn"**
ở mục trên (không tự diễn giải lại) → lưu `ts` vào `reminderThreadTs`.

**Job B — follow-up (mỗi `FOLLOWUP_INTERVAL_MINUTES` phút, mặc định 90, dùng
`--every` vì 90 phút không chia đều theo giờ chẵn để viết bằng cron
giờ/phút):**

```bash
openclaw cron create --every "${FOLLOWUP_INTERVAL_MINUTES:-90}m" \
  "Việc B skill daily-report: kiểm tra ai chưa report, DM riêng từng người." \
  --name daily-report-followup --tz "$REMINDER_TIMEZONE" \
  --session isolated --model sonnet --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```
Chạy: nếu đã qua cutoff hoặc mọi người đã report → bỏ qua. Ngược lại đọc
reply trong thread + state, DM riêng (không đăng gì vào thread/kênh) từng
người còn thiếu — mỗi người chỉ 1 DM/lần chạy, không spam.

## Thu thập report

| Field | Bắt buộc | Ghi chú |
|-------|----------|---------|
| reporter | Có | Slack user gửi tin |
| issueKey | Có | Dạng `NEX-\d+` |
| status | Có | Chuẩn hoá "Đang làm"/"Hoàn thành"/"Blocked" |
| hoursWorked | Có | Số giờ đã làm hôm nay, dạng `<X>h` |
| note | Có | Mô tả ngắn công việc (đóng luôn vai trò task description) |
| extraHoursNeeded | Có nếu status ≠ "Hoàn thành" | Số giờ ước tính còn cần; bỏ trống nếu đã "Hoàn thành" |
| date | Có | Hôm nay (tz `REMINDER_TIMEZONE`) hoặc ngày ghi trong report |

Thiếu issueKey/status/hoursWorked/note (hoặc thiếu extraHoursNeeded khi chưa
xong) → hỏi lại, không đoán. Sau khi extract, reply trong thread report:

```
Đã nhận report của <reporter>:
• Issue: <issueKey>  • Status: <status>  • Giờ đã làm: <hoursWorked>
• Ghi chú: <note>  • Cần thêm: <extraHoursNeeded, hoặc "—" nếu đã xong>
Đẩy Sheets? Cập nhật luôn Jira <issueKey>? (có / không)
```

Ghi ngay `pushState: "pending"` vào state (kèm `messageTs`). Nếu người report
từ chối → `pushState: "declined"`, không đẩy đi đâu.

## Xử lý report bị sửa (`message_changed`, đã có sẵn trong event đã bật)

Nếu `messageTs` đã có trong state hôm nay:

- `pending` → âm thầm cập nhật draft, không hỏi lại.
- `confirmed` → hỏi lại trước khi ghi đè:
  ```
  ⚠️ Report vừa sửa: <field cũ> → <field mới> (chỉ hiện dòng đổi)
  Cập nhật lại Sheets/Jira? (có / không)
  ```
  "có" → `update_report_row(row=<sheetRow>, values=[...])` (không tạo dòng
  mới) + update Jira issue `issueKey` (qua flow xác nhận của jira-task) →
  cập nhật state với data mới. "không" → giữ nguyên dữ liệu đã ghi, chỉ cập
  nhật issueKey/status/hoursWorked/note/extraHoursNeeded trong state (đánh
  dấu `syncedWithEdit: false`).
- `declined` → coi như report mới, chạy lại từ đầu.

## Đẩy dữ liệu (sau xác nhận)

Sheets: `append_report_row(values=[date, reporter, issueKey, status,
hoursWorked, note, extraHoursNeeded])` lần đầu (`extraHoursNeeded` = "" nếu
đã "Hoàn thành") (lưu `row` trả về vào state); dùng `update_report_row` nếu đã
có `sheetRow` (case edit). Jira: update issue `issueKey` theo "Action 2" của
[`../jira-task/SKILL.md`](../jira-task/SKILL.md) (preview/xác nhận riêng) —
dùng `status`/`hoursWorked`/`note`/`extraHoursNeeded` làm nội dung
comment/field tương ứng. Xong cả hai → `pushState: "confirmed"`. Phản hồi:
`✓ Đã ghi Sheets. ✓ Đã cập nhật <issueKey>.`

## Q&A

Câu hỏi khác (không phải report) → trả lời trực tiếp; hỏi về issue Jira →
tra cứu qua API (xem `jira-task/SKILL.md`) thay vì đoán.

## Lỗi

| Lỗi | Phản hồi |
|-----|---------|
| Sheets API lỗi (bao gồm chưa cấu hình `GOOGLE_SHEETS_CREDENTIALS_JSON`/`GOOGLE_SHEETS_SPREADSHEET_ID`) | "Không ghi được Sheets: <lỗi>. Report vẫn ghi nhận, thử lại sau." |
| Không tìm thấy issue Jira | "Không tìm thấy <key>, report vẫn lưu Sheets bình thường." |
| Thiếu issueKey/status/hoursWorked/note, hoặc thiếu extraHoursNeeded khi chưa "Hoàn thành" | Hỏi lại, không đoán |
| Follow-up không đọc được state | Coi như chưa ai report, log lỗi, không crash job |
