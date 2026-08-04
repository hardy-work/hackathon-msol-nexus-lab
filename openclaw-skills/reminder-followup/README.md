# reminder-followup

Nhắc nhở team report task hàng ngày trong Slack qua cron, và follow-up tag
người chưa report ngay trong thread của tin nhắc. Xem [`SKILL.md`](SKILL.md)
cho luồng chi tiết.

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
# REMINDER_TIMEZONE, REMINDER_WEEKDAYS_ONLY, FOLLOWUP_CRON_1,
# FOLLOWUP_CRON_2, FOLLOWUP_CUTOFF_TIME
```

`SLACK_REPORT_CHANNEL_ID` là ID Slack thật (vd `C0BKLP5KYD7`, xem trong
"About" của kênh) — bắt buộc cho bước 4 dưới đây (`openclaw cron create --to
channel:<id>` cần ID, không nhận tên kênh).

⚠️ **Quote mọi giá trị bắt đầu bằng `#`** (vd `SLACK_REPORT_CHANNEL="#nexus-lab"`).
Không quote thì gateway hiểu `#` là bắt đầu comment và **bỏ qua cả dòng** —
biến không tồn tại (chứ không phải rỗng), `openclaw skills check` báo thiếu
mà không có gợi ý gì thêm. Root-caused 2026-08-04.

### 3. Khai roster cho nhóm

Tạo `roster/<SLACK_REPORT_CHANNEL_ID>.json` liệt kê ai phải report — xem
[`roster/README.md`](roster/README.md). Đây là nguồn duy nhất, bot **không**
đọc danh sách thành viên kênh.

Nhiều nhóm thì mỗi nhóm 1 file roster + 1 cặp cron job trỏ vào channel id
tương ứng; skill dùng chung, không phải sửa `SKILL.md`.

### 4. (Tuỳ chọn) copy vào OpenClaw workspace

```bash
mkdir -p ~/.openclaw/workspace/skills
ln -s "$(pwd)" ~/.openclaw/workspace/skills/reminder-followup
```

Symlink thôi là **chưa đủ**. Skill khai `requires.env` trong frontmatter, và
OpenClaw đối chiếu với **biến môi trường của tiến trình Gateway** — nó *không*
tự đọc file `.env` của skill. Thiếu bất kỳ biến nào là skill tụt xuống
`△ needs setup` và **`Visible to model: no`**, tức là bot hoàn toàn không thấy
`SKILL.md`; nó vẫn trả lời như thường nhưng nội dung là tự bịa.

**Linux/systemd** — nạp `.env` qua drop-in
`~/.config/systemd/user/openclaw-gateway.service.d/override.conf`:

```
[Service]
EnvironmentFile=-/duong/dan/toi/openclaw-skills/reminder-followup/.env
```

```bash
systemctl --user daemon-reload && systemctl --user restart openclaw-gateway.service
openclaw skills info reminder-followup   # phải thấy "Visible to model: yes"
```

⚠️ **Đổi tên thư mục skill thì phải sửa lại đường dẫn này.** Dấu `-` đầu đường
dẫn khiến systemd bỏ qua **im lặng** khi file không tồn tại — không log, không
lỗi, service vẫn `active`. Đây đúng là lỗi đã xảy ra (2026-08-03): rename
`daily-report` → `reminder-followup` làm đường dẫn chết, skill vô hình với bot
suốt nhiều ngày mà nhìn bên ngoài vẫn như đang chạy tốt.

**macOS/launchd** — không có `EnvironmentFile=` kiểu systemd. Thay vào đó,
biến phải được thêm vào file `.env` gốc mà OpenClaw dùng để generate service
env (thường là `~/.openclaw-<profile>/.env`, ví dụ `~/.openclaw-hackathon/.env`
— **không phải** `.env` trong thư mục skill này, file đó chỉ để tham khảo/chạy
tay), rồi chạy:

```bash
openclaw --profile <profile> gateway install --force   # regenerate service-env + reinstall launchd job
openclaw --profile <profile> skills check               # xác nhận "Missing requirements: 0"
```

`gateway install --force` giữ nguyên port/token hiện có (không truyền `--port`/
`--token` thì nó tự đọc lại config cũ) — an toàn để chạy lại mỗi khi thêm biến
mới. Đây đúng là lỗi đã xảy ra (2026-08-04): tưởng tạo `.env` trong thư mục
skill là đủ, skill vẫn `△ needs setup` cho tới khi biến được thêm vào file gốc
và chạy `gateway install --force`.

Kiểm nhanh khi nghi ngờ (cả 2 hệ điều hành): `openclaw skills check` (liệt kê
skill còn thiếu requirement) và `openclaw skills info <tên>`.

### 5. Đăng ký 2 cron job (1 lần duy nhất)

Skill chỉ mô tả *cách* nhắc/follow-up — cron job thật sự phải được tạo qua
`openclaw cron create` (chính xác theo giờ, không trôi như polling/heartbeat).
Xem chi tiết ở [`SKILL.md`](SKILL.md#cron-setup-1-lần-dùng-cron-expression-thật--không-diễn-giải-giờ-chung-chung-để-tránh-trôi-giờ).
Lưu ý: **không** gán `--model` cho cron job — để nó dùng model mặc định của
workspace, tránh vỡ khi allowlist `agents.defaults.models` thay đổi.
Cách đơn giản nhất là nhắn trong Slack: `@<tên bot> thiết lập 2 cron job nhắc
report theo skill reminder-followup` — agent sẽ tự chạy đúng 2 lệnh `openclaw cron
create` với giá trị lấy từ `.env`. Kiểm tra lại bằng `openclaw cron list`.

## Known limitations

- Chỉ nhắc + follow-up trong thread — không thu thập nội dung report, không
  đẩy đi Google Sheets hay Jira. Ai muốn theo dõi nội dung report thì tự đọc
  lại trong thread Slack.
- Bot có kiểm **cấu trúc** dòng report (`Id task | Re-estimate (h) | Start date
  | End date | Actual Effort (h) | Status | note`, ngày dạng `DD-MM-YYYY`,
  end date bắt buộc khi status là Done) để biết ai report cho có lệ, nhưng
  không đánh giá nội dung — dòng thiếu field/sai dạng ngày bị tính là chưa
  report và sẽ bị nhắc sửa mẫu.
- Ai phải report lấy từ roster, nên roster phải được cập nhật tay khi có người
  vào/ra nhóm — bot không tự đồng bộ theo thành viên kênh.
- Follow-up dựa vào đọc reply trong thread để biết ai đã report — nếu channel
  history bị giới hạn (Slack free tier) thì có thể nhắc nhầm người đã report.
- State file (`state/<ngày>.json`) là file cục bộ trên máy chạy Gateway —
  không đồng bộ nếu bạn chạy Gateway trên nhiều máy cùng lúc (xem cảnh báo ở
  README gốc repo về việc chỉ nên chạy 1 Gateway tại 1 thời điểm).
