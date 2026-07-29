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
                "GOOGLE_SHEETS_CREDENTIALS_JSON",
                "GOOGLE_SHEETS_SPREADSHEET_ID",
              ],
          },
      },
  }
---

## Quy tắc bất biến

- Không ghi Sheets/Jira mà không preview + xác nhận trước (như
  [`../jira-task/SKILL.md`](../jira-task/SKILL.md)).
- Thiếu `task`/`status` → hỏi lại, không đoán.
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
      "reporter": "Núi", "messageTs": "...", "task": "...",
      "status": "Đang làm", "blocker": "Không có",
      "pushState": "pending|confirmed|declined",
      "sheetRow": 42, "jiraIssue": "NEX-30"
    }
  }
}
```

## Format report chuẩn

```
📋 Report ngày <DD/MM>
Task: <nội dung>
Trạng thái: Đang làm / Hoàn thành / Blocked
Blocker: <nội dung, hoặc "Không có">
```

Report = reply vào thread `reminderThreadTs` trong `SLACK_REPORT_CHANNEL`
(không phải tin rời trong kênh), hoặc DM lại tin nhắc ở job follow-up. Chấp
nhận lệch nhỏ so với format, hoặc fallback tự do (VN/EN) nếu có đủ task +
trạng thái — ưu tiên hướng người dùng theo đúng format khi có thể.

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
report → nếu còn ai chưa, đăng tin @-mention kèm format chuẩn ở trên → lưu
`ts` vào `reminderThreadTs`.

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
| task | Có | Giữ riêng issue key `NEX-\d+` nếu có |
| status | Có | Chuẩn hoá "Đang làm"/"Hoàn thành"/"Blocked" |
| blocker | Không | "Không có" nếu trống |
| date | Có | Hôm nay (tz `REMINDER_TIMEZONE`) hoặc ngày ghi trong report |

Thiếu task/status → hỏi lại. Sau khi extract, reply trong thread report:

```
Đã nhận report của <reporter>:
• Task: <task>  • Status: <status>  • Blocker: <blocker>
Đẩy Sheets? Có issue Jira liên kết? (có / issue key / không)
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
  mới) + update Jira nếu có `jiraIssue` (qua flow xác nhận của jira-task) →
  cập nhật state với data mới. "không" → giữ nguyên dữ liệu đã ghi, chỉ cập
  nhật task/status/blocker trong state (đánh dấu `syncedWithEdit: false`).
- `declined` → coi như report mới, chạy lại từ đầu.

## Đẩy dữ liệu (sau xác nhận)

Sheets: `append_report_row(values=[date, reporter, task, status, blocker])`
lần đầu (lưu `row` trả về vào state); dùng `update_report_row` nếu đã có
`sheetRow` (case edit). Jira: nếu có issue key, update theo "Action 2" của
[`../jira-task/SKILL.md`](../jira-task/SKILL.md) (preview/xác nhận riêng).
Xong cả hai → `pushState: "confirmed"`. Phản hồi: `✓ Đã ghi Sheets. ✓ Đã cập
nhật NEX-xxx (nếu có).`

## Q&A

Câu hỏi khác (không phải report) → trả lời trực tiếp; hỏi về issue Jira →
tra cứu qua API (xem `jira-task/SKILL.md`) thay vì đoán.

## Lỗi

| Lỗi | Phản hồi |
|-----|---------|
| Sheets API lỗi | "Không ghi được Sheets: <lỗi>. Report vẫn ghi nhận, thử lại sau." |
| Không tìm thấy issue Jira | "Không tìm thấy <key>, report vẫn lưu Sheets bình thường." |
| Thiếu task/status | Hỏi lại, không đoán |
| Follow-up không đọc được state | Coi như chưa ai report, log lỗi, không crash job |
