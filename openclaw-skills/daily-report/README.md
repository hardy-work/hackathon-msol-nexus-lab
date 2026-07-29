# daily-report

Nhắc nhở team report task hàng ngày trong Slack qua cron, và follow-up DM
riêng người chưa report. Xem [`SKILL.md`](SKILL.md) cho luồng chi tiết.

## Setup

### 1. Kết nối Slack qua plugin chính thức của OpenClaw

Không cần code riêng — OpenClaw có plugin Slack (Bolt SDK) built-in:

```bash
openclaw plugins install @openclaw/slack   # xác nhận đúng package id qua `openclaw plugins list`
openclaw channels add                       # wizard hỏi bot token / app config
```

Restart Gateway sau khi cài xong. Xem thêm
[docs.openclaw.ai/channels](https://docs.openclaw.ai/channels).

### 2. Env vars cho skill này

```bash
cp .env.example .env
# điền SLACK_REPORT_CHANNEL, SLACK_REPORT_CHANNEL_ID, REMINDER_TIME,
# REMINDER_TIMEZONE, REMINDER_WEEKDAYS_ONLY, FOLLOWUP_INTERVAL_MINUTES,
# FOLLOWUP_CUTOFF_TIME
```

`SLACK_REPORT_CHANNEL_ID` là ID Slack thật (vd `C0BKLP5KYD7`, xem trong
"About" của kênh) — bắt buộc cho bước 4 dưới đây (`openclaw cron create --to
channel:<id>` cần ID, không nhận tên kênh).

### 3. (Tuỳ chọn) copy vào OpenClaw workspace

```bash
mkdir -p ~/.openclaw/workspace/skills
ln -s "$(pwd)" ~/.openclaw/workspace/skills/daily-report
```

### 4. Đăng ký 2 cron job (1 lần duy nhất)

Skill chỉ mô tả *cách* nhắc/follow-up — cron job thật sự phải được tạo qua
`openclaw cron create` (chính xác theo giờ, không trôi như polling/heartbeat).
Xem chi tiết ở [`SKILL.md`](SKILL.md#cron-setup-1-lần-dùng-cron-expression-thật--không-diễn-giải-giờ-chung-chung-để-tránh-trôi-giờ-gán---model-sonnet-vì-việc-này-không-cần-reasoning-nặng-giảm-độ-trễ-xử-lý).
Cách đơn giản nhất là nhắn trong Slack: `@<tên bot> thiết lập 2 cron job nhắc
report theo skill daily-report` — agent sẽ tự chạy đúng 2 lệnh `openclaw cron
create` với giá trị lấy từ `.env`. Kiểm tra lại bằng `openclaw cron list`.

## Known limitations

- Chỉ nhắc + follow-up DM — không thu thập/parse nội dung report, không đẩy
  đi Google Sheets hay Jira. Ai muốn theo dõi nội dung report thì tự đọc lại
  trong thread Slack.
- Reminder/follow-up dựa vào đọc lịch sử kênh trong ngày để biết ai chưa
  report — nếu channel history bị giới hạn (Slack free tier) thì có thể nhắc
  nhầm.
- State file (`state/<ngày>.json`) là file cục bộ trên máy chạy Gateway —
  không đồng bộ nếu bạn chạy Gateway trên nhiều máy cùng lúc (xem cảnh báo ở
  README gốc repo về việc chỉ nên chạy 1 Gateway tại 1 thời điểm).
