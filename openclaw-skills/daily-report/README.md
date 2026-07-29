# daily-report

Nhắc nhở team report task hàng ngày trong Slack, thu thập nội dung report,
trả lời câu hỏi, và đẩy report lên Google Sheets / Jira sau khi xác nhận. Xem
[`SKILL.md`](SKILL.md) cho luồng chi tiết.

## Setup

### 1. Kết nối Slack qua plugin chính thức của OpenClaw

Không cần code riêng — OpenClaw có plugin Slack (Bolt SDK) built-in:

```bash
openclaw plugins install @openclaw/slack   # xác nhận đúng package id qua `openclaw plugins list`
openclaw channels add                       # wizard hỏi bot token / app config
```

Restart Gateway sau khi cài xong. Xem thêm
[docs.openclaw.ai/channels](https://docs.openclaw.ai/channels).

### 2. sheets-bridge (Google Sheets MCP server)

```bash
cd sheets-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEETS_SPREADSHEET_ID
```

Chi tiết tạo service account + share sheet: xem
[`sheets-bridge/README.md`](sheets-bridge/README.md).

### 3. Đăng ký MCP server

Thêm `sheets-bridge` vào `.mcp.json` gốc repo (xem
[`sheets-bridge/README.md`](sheets-bridge/README.md#register-with-claude-code--openclaw)
để lấy đúng format).

### 4. Env vars cho skill này

```bash
cp .env.example .env
# điền SLACK_REPORT_CHANNEL, SLACK_REPORT_CHANNEL_ID, REMINDER_TIME,
# REMINDER_TIMEZONE, REMINDER_WEEKDAYS_ONLY, FOLLOWUP_INTERVAL_MINUTES,
# FOLLOWUP_CUTOFF_TIME
```

`SLACK_REPORT_CHANNEL_ID` là ID Slack thật (vd `C0BKLP5KYD7`, xem trong
"About" của kênh) — bắt buộc cho bước 6 dưới đây (`openclaw cron create --to
channel:<id>` cần ID, không nhận tên kênh).

Skill này cũng dùng lại env vars của `../jira-task/` (`JIRA_EMAIL`,
`JIRA_API_TOKEN`, `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_BOARD_ID`) khi
report có liên kết Jira issue.

### 5. (Tuỳ chọn) copy vào OpenClaw workspace

```bash
mkdir -p ~/.openclaw/workspace/skills
ln -s "$(pwd)" ~/.openclaw/workspace/skills/daily-report
```

### 6. Đăng ký 2 cron job (1 lần duy nhất)

Skill chỉ mô tả *cách* nhắc/follow-up — cron job thật sự phải được tạo qua
`openclaw cron create` (chính xác theo giờ, không trôi như polling/heartbeat).
Xem chi tiết ở [`SKILL.md`](SKILL.md#việc-1a-đăng-ký-cron-nhắc-report-setup-1-lần)
và [Việc 1b](SKILL.md#việc-1b-đăng-ký-cron-follow-up-định-kỳ-setup-1-lần).
Cách đơn giản nhất là nhắn trong Slack: `@<tên bot> thiết lập 2 cron job nhắc
report theo skill daily-report` — agent sẽ tự chạy đúng 2 lệnh `openclaw cron
create` với giá trị lấy từ `.env`. Kiểm tra lại bằng `openclaw cron list`.

## Known limitations

- Reminder dựa vào đọc lịch sử kênh trong ngày để biết ai chưa report — nếu
  channel history bị giới hạn (Slack free tier) thì có thể nhắc nhầm.
- `sheets-bridge` không validate header cột — thứ tự `values` trong
  `append_report_row`/`update_report_row` phải khớp tay với cột trong sheet
  thật.
- State file (`state/<ngày>.json`) là file cục bộ trên máy chạy Gateway —
  không đồng bộ nếu bạn chạy Gateway trên nhiều máy cùng lúc (xem cảnh báo ở
  README gốc repo về việc chỉ nên chạy 1 Gateway tại 1 thời điểm).
