---
name: daily-report
description: Nhắc report task hàng ngày qua cron, và follow-up DM riêng người chưa report.
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

- **Không bao giờ giao việc đọc/gửi Slack (đọc kênh, đọc thread, DM, đăng
  tin) cho subagent** — tool `slack` chỉ cấp cho phiên chính (main/cron
  session), subagent gọi sẽ luôn lỗi `No such tool available: slack`. Mọi
  bước liên quan Slack trong skill này phải chạy trực tiếp (inline) trong
  phiên đang xử lý job, không delegate.
- Skill này **chỉ nhắc report và follow-up DM người chưa report** — không
  thu thập/parse nội dung report, không xác nhận, không đẩy đi đâu (không
  Google Sheets, không Jira). Cron job chạy xong và tin nhắn được gửi là
  xong việc.

## State file

`{baseDir}/state/<YYYY-MM-DD>.json`, tạo mới rỗng mỗi ngày:

```json
{
  "reminderThreadTs": "1690000000.000100",
  "reportedUserIds": ["U0BKL0DJV7B", "U0BKKXXXXXX"]
}
```

`reportedUserIds` = danh sách user id đã reply (bất kỳ nội dung gì) vào
thread `reminderThreadTs` hôm nay — chỉ dùng để biết **ai đã report**, không
đọc/lưu nội dung report thật sự.

## Format tin nhắc chuẩn (BẮT BUỘC, không được diễn giải lại)

Mọi tin nhắc report — dù do Job A (cron) tự động chạy, hay do ai đó nhắn tay
bảo bot nhắc (vd "nhắc report đi", "nhắc lại mọi người report", "xem ai chưa
report") — **PHẢI dùng đúng nguyên văn template dưới đây**, chỉ được thay
danh sách `@mention` (hoặc `<!channel>` nếu không lấy được danh sách ai chưa
report). KHÔNG được tự thêm/bớt câu chữ, không đổi icon, không viết lại theo
văn phong khác mỗi lần, không thêm bullet "Hôm qua làm gì / Hôm nay làm gì"
tự chế:

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
- Đây chỉ là **gợi ý format** cho người report tự điền — bot không đọc/parse
  lại nội dung reply, chỉ cần biết **có** reply hay chưa (xem "State file").

## Cron (setup 1 lần, dùng cron expression thật — không diễn giải giờ chung
chung để tránh trôi giờ)

**Không gán `--model` cho 2 job dưới đây.** Để cron dùng model mặc định của
workspace/agent. Pin cứng một model id vào skill sẽ vỡ ngay khi workspace đổi
`agents.defaults.models` allowlist — job fail với `cron payload.model <x>
rejected by agents.defaults.models allowlist`. Nếu một job cũ đã lỡ pin model,
gỡ bằng `openclaw cron edit <id> --clear-model`.

**Job A — nhắc (`REMINDER_TIME`, mặc định 11:00 → `0 11 * * *`; đổi field
giờ/phút nếu khác, vd 09:30 → `30 9 * * *`):**

```bash
openclaw cron create "0 11 * * *" \
  "Việc A skill daily-report: đăng tin nhắc report, lưu message ts vào state." \
  --name daily-report-reminder --tz "$REMINDER_TIMEZONE" \
  --session isolated --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```
`--announce` bắt buộc — thiếu nó, cron chạy xong vẫn không tự đẩy kết quả ra
Slack (`delivered: false` dù `status: ok`).

Chạy: reset state ngày mới (`reminderThreadTs`, `reportedUserIds` rỗng) nếu
chưa có → lấy danh sách thành viên kênh, trừ đi `reportedUserIds` → nếu danh
sách chưa report rỗng → bỏ qua, không cần nhắc. Ngược lại đăng tin **đúng
nguyên văn "Format tin nhắc chuẩn"** ở mục trên (không tự diễn giải lại) →
lưu `ts` (message timestamp) vào `reminderThreadTs`.

**Job B — follow-up (mỗi `FOLLOWUP_INTERVAL_MINUTES` phút, mặc định 90, dùng
`--every` vì 90 phút không chia đều theo giờ chẵn để viết bằng cron
giờ/phút):**

```bash
openclaw cron create --every "${FOLLOWUP_INTERVAL_MINUTES:-90}m" \
  "Việc B skill daily-report: kiểm tra ai chưa report, DM riêng từng người." \
  --name daily-report-followup --tz "$REMINDER_TIMEZONE" \
  --session isolated --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```

Chạy: nếu đã qua `FOLLOWUP_CUTOFF_TIME` hoặc chưa có `reminderThreadTs` hôm
nay → bỏ qua. Ngược lại đọc reply mới trong thread `reminderThreadTs` (bất kỳ
ai reply gì cũng tính là đã report — **không** cần đúng format, không đọc nội
dung) → cập nhật `reportedUserIds`. Lấy danh sách thành viên kênh trừ
`reportedUserIds` → nếu rỗng → bỏ qua. Ngược lại DM riêng (không đăng gì vào
thread/kênh) từng người còn thiếu — mỗi người chỉ 1 DM/lần chạy, không spam.

## Q&A

Câu hỏi khác (không phải yêu cầu nhắc report) → trả lời trực tiếp bằng khả
năng hội thoại thông thường, không cần tra cứu gì thêm.

## Lỗi

| Lỗi | Phản hồi |
|-----|---------|
| Không đọc được lịch sử kênh/thread | Coi như chưa ai report, log lỗi, không crash job |
| Không lấy được danh sách thành viên kênh | Dùng `<!channel>` thay cho `<mention_list>`, không tự đoán danh sách |
