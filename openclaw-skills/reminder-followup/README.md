# reminder-followup

Nhắc nhở team report task hàng ngày trong Slack qua cron, và follow-up tag
người chưa report ngay trong thread của tin nhắc. Xem [`SKILL.md`](SKILL.md)
cho luồng chi tiết.

**Ai bị nhắc** lấy từ tab `Resource plan` của Google Sheet logtime (cột `Member`
+ `Slack ID`) — mọi tin nhắc đều **tag đích danh từng người**, không dùng
`@here`, và không còn file roster nào.

**Luật chấm format** dòng log task nằm ở
[`template/log-task-rules.md`](template/log-task-rules.md) — **nguồn duy nhất**.
`SKILL.md` và `cron/job-b.prompt.txt` chỉ trỏ về đó chứ không chép lại; job B
`cat` file này ra đọc ngay trước khi chấm. Sửa luật thì sửa đúng một chỗ đó.

Dev cũng có thể **tag bot kèm dòng report** để được chấm format ngay tại chỗ,
không phải đợi lượt follow-up chiều (xem `SKILL.md`, mục "Dev tag bot để
report").

## Report hợp lệ → chuyển sang `gg-sheet` để log

Dòng report hợp lệ không dừng ở lời xác nhận nữa: skill này chấm format xong thì
**chuyển sang skill [`gg-sheet`](../gg-sheet) (Action 4)** để ghi vào đúng dòng
`TaskID` trong tab Sprint. Skill này **không tự ghi sheet** — ranh giới là:

| Việc | Của ai |
| --- | --- |
| Ai phải report, tag ai, nhắc lúc nào | `reminder-followup` |
| Dòng report đúng mẫu chưa | `reminder-followup` |
| Ghi vào cột nào, tab nào, quyền ghi | `gg-sheet` |
| So giờ thực tế với giờ plan | `gg-sheet` |
| Tính `delta` giờ vừa log + ghi sổ cái | `gg-sheet` |
| **Đồng hồ đếm 1 tiếng chờ giải trình** | `reminder-followup` |
| So tổng giờ trong ngày với công đăng ký | `reminder-followup` |

**Task chậm hơn plan** (giờ thực tế > `Estimate (h)` trong sheet): `gg-sheet`
chưa ghi gì mà hỏi lý do trước. Đây không phải từ chối log — có lý do là ghi
`Risk management` rồi **log task như thường**.

Skill này giữ hạn chờ, vì `gg-sheet` không theo dõi hội thoại:

- Dev trả lời trong **1 tiếng** → ghi risk + log task.
- Quá 1 tiếng → không tự log nữa, đẩy về PM.
- Im luôn → Job B 16:30 tag kèm id task bị treo, nhắc đúng một lần rồi xoá.

Danh sách task đang chờ giải trình nằm ở `state/pending-overtime.json` (không
commit). Mất file này thì các task đang treo coi như chưa từng được hỏi.

Skill `gg-sheet` phải được cài cạnh skill này thì luồng log mới chạy.

### Log thiếu giờ so với công đăng ký

Lượt 16:30 còn hỏi thêm một chuyện: hôm nay người đó đã log **đủ số giờ đã đăng
ký** chưa. Mốc là ô công trong `Resource plan` — chính ô đang dùng để biết ai
nghỉ, chỉ khác là giữ lại con số (`8` đủ công, `4` nghỉ nửa buổi) thay vì chỉ
lấy có/không. Nhờ vậy **nghỉ nửa buổi không cần luật riêng**.

Giờ trong ngày phải tính bằng **delta** (`actual mới − actual đang có trên
sheet`), vì `Actual Effort (h)` là số cộng dồn của cả task chứ không phải giờ làm
hôm nay. `gg-sheet` ghi delta vào `state/effort-today.json`, skill này đọc.

Thiếu giờ thì **rẽ nhánh theo Status**, không rẽ theo số giờ:

| Tình huống | Làm gì |
| --- | --- |
| Còn task **In progress** | Hỏi lý do → ghi `Risk management` |
| Mọi task đều **Done** | Xong sớm hơn plan → **không risk**, chỉ hỏi nhẹ một câu |

Gộp hai nhánh này là biến "làm nhanh hơn plan" thành rủi ro dự án. Est 8h làm 3h
rồi nhảy task khác 5h thì tổng vẫn 8h → **đủ công, im hẳn**; đó cũng là lý do
phải cộng tổng cả ngày chứ không xét từng task.

Hỏi **đúng một lần** ở lượt 16:30 (lượt 17:00 thì dev không kịp trả lời trước
cutoff 17:30), không ghi pending, không nhắc lại. Khác exit 9: ở đó task **chưa
được ghi** nên phải đuổi cho bằng được; ở đây task đã ghi xong rồi, câu hỏi chỉ
để bổ sung thông tin.

Sổ cái này còn trả lời được câu *"dev tự mở thread riêng rồi tag bot vào log thì
có bị nhắc oan không"*: Job B chấm "chưa report" bằng reply trong thread 9:00 nên
sẽ không thấy họ — ai có mặt trong sổ cái là đã log thật, được trừ ra.

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
# FOLLOWUP_CRON_2, FOLLOWUP_CUTOFF_TIME,
# LOGTIME_SHEET_LINK, LOGTIME_SHEET_TAB, GOOGLE_SHEETS_API_KEY
```

`SLACK_REPORT_CHANNEL_ID` là ID Slack thật (vd `C0BKLP5KYD7`, xem trong
"About" của kênh) — bắt buộc cho bước 4 dưới đây (`openclaw cron create --to
channel:<id>` cần ID, không nhận tên kênh).

⚠️ **Quote mọi giá trị bắt đầu bằng `#`** (vd `SLACK_REPORT_CHANNEL="#nexus-lab"`).
Không quote thì gateway hiểu `#` là bắt đầu comment và **bỏ qua cả dòng** —
biến không tồn tại (chứ không phải rỗng), `openclaw skills check` báo thiếu
mà không có gợi ý gì thêm. Root-caused 2026-08-04.

### 3. Khai danh sách người phải report trên Google Sheet

Ai phải report lấy từ tab `Resource plan` của Google Sheet logtime khai ở
`LOGTIME_SHEET_LINK`. Tab đó cần một bảng có header:

| Member | Slack ID | Slack name | Role |
|--------|----------|------------|------|
| Bùi Hồng Sơn | U09QRTUHX24 | MH_SonBH | BE |

Mỗi dòng có `Slack ID` hợp lệ = 1 người bị nhắc (tag `<@id>`). Dòng thiếu
`Slack ID` bị bỏ qua — lấy user ID: Slack → profile người đó → **More** →
*Copy member ID*. Thêm/bớt người = sửa thẳng sheet, có hiệu lực ngay lượt cron
kế tiếp, không cần sửa file hay restart Gateway.

**Ai nghỉ hôm đó thì không bị nhắc.** Skill đọc thêm khối công *"Thời gian làm
việc mỗi ngày"* trong cùng tab: ô của đúng ngày hôm nay trống / `0` / `P` /
`nghỉ` → bỏ qua người đó hoàn toàn (không tag, không tính là chưa report).
Nhờ vậy T7/CN không ai bị nhắc, và cả đội nghỉ thì bot không đăng gì cả.

Sheet chỉ được **đọc** (API key read-only là đủ) — skill này không bao giờ ghi
ngược lên sheet.

Kiểm tra nhanh xem bot đang thấy những ai:

```bash
bash scripts/resource-plan-members.sh
```

Trả về `people` (phải report hôm nay), `off` (nghỉ), `no_id` (thiếu Slack ID),
`bad_id` (có id nhưng id không có thật — xem dưới).
Giả lập ngày khác để soi: `LOGTIME_TODAY=2026-08-01 bash scripts/resource-plan-members.sh`.

### Id sai thì bị loại, không tag

Mỗi id còn được đối chiếu với workspace qua `users.info` trước khi tag. **Đúng
cú pháp không có nghĩa là có thật**: Slack render `<@U…>` lạ thành một pill
trống — tin vẫn đăng, vẫn xanh, mà không ai nhận notification và không lỗi nào
nổ ra. Ngày 06-08-2026 cả 6 id trong sheet hoá ra là của workspace khác, tin
9:00 tag vào hư không, mất nguyên buổi sáng mới phát hiện.

Id không tồn tại (hoặc chủ nhân đã nghỉ việc) bị **loại thẳng** khỏi chuỗi
mention, những người còn lại vẫn được nhắc bình thường; tên người bị loại chỉ ra
`stderr` và trường `bad_id`, **không** chen vào tin Slack. Sai hết → exit `5`,
bot đăng bản cảnh báo thay vì đăng một tin toàn pill trống.

Token lấy từ `SLACK_BOT_TOKEN`, không có thì đọc `channels.slack.botToken` trong
`openclaw.json` — không cần khai thêm env. Không lấy được token, hoặc Slack lỗi
mạng/thiếu scope, thì bước đối chiếu **bị bỏ qua** và danh sách giữ nguyên: thà
tag một id đáng ngờ còn hơn im lặng bỏ sót người phải report vì bot đang hỏng.

Script tự dò cột theo tên header nên không sợ sheet chèn thêm dòng/cột. Exit
`6` = hôm nay cả đội nghỉ (bot im hẳn, đúng ý). Exit `2/3/4/5` = không đọc được
danh sách → skill **không nhắc ai** và báo lỗi ra Slack thay vì im lặng (xem
`SKILL.md`, mục "Không đọc được sheet").

Nhiều nhóm thì mỗi nhóm 1 sheet/tab riêng + 1 cặp cron job trỏ vào channel id
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

⚠️ **Thêm biến mới vào `.env` thì phải nạp lại env cho Gateway** (restart với
systemd, `gateway install --force` với launchd). Bản refactor bỏ roster có thêm
2 biến bắt buộc là `LOGTIME_SHEET_LINK` và `GOOGLE_SHEETS_API_KEY` — chưa nạp
thì skill tụt xuống `△ needs setup` và bot lại không thấy `SKILL.md`.

### 5. Đăng ký 2 cron job (1 lần duy nhất)

Skill chỉ mô tả *cách* nhắc/follow-up — cron job thật sự phải được tạo qua
`openclaw cron create` (chính xác theo giờ, không trôi như polling/heartbeat).
**Prompt của 2 job nằm ở [`cron/`](cron/README.md)** — đó mới là thứ chạy thật;
sửa `SKILL.md` mà quên apply lại prompt thì ngoài Slack không đổi gì cả.
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
  | End date | Actual Effort (h) | Status | Note`, ngày dạng `DD-MM-YYYY`,
  end date bắt buộc khi status là Done) để biết ai report cho có lệ, nhưng
  không đánh giá nội dung — dòng thiếu field/sai dạng ngày bị tính là chưa
  report và sẽ bị nhắc sửa mẫu.
- Ai phải report lấy từ tab `Resource plan`, nên sheet phải được cập nhật tay
  khi có người vào/ra nhóm — bot không tự đồng bộ theo thành viên kênh, và
  người thiếu ô `Slack ID` sẽ không bao giờ được nhắc.
- Mỗi lượt cron đều gọi Google Sheets API 1 lần — sheet bị unshare/đổi tab hay
  API key hết quota là cả ngày hôm đó không tag được ai (bot sẽ báo ra thread
  chứ không im lặng).
- Follow-up dựa vào đọc reply trong thread để biết ai đã report — nếu channel
  history bị giới hạn (Slack free tier) thì có thể nhắc nhầm người đã report.
- State file (`state/<ngày>.json`) là file cục bộ trên máy chạy Gateway —
  không đồng bộ nếu bạn chạy Gateway trên nhiều máy cùng lúc (xem cảnh báo ở
  README gốc repo về việc chỉ nên chạy 1 Gateway tại 1 thời điểm).
- Sổ cái `state/effort-today.json` chỉ ghi khi log đi qua `--slack-id`. PM sửa
  tay số giờ thẳng trên sheet thì sổ cái không biết → lượt 16:30 vẫn tưởng
  thiếu giờ.
- Report bù ngày hôm trước: delta khi đó gộp cả 2 ngày vào hôm nay, nên tổng có
  thể **vượt** công 1 ngày. Hiện chưa cảnh báo chiều vượt (tab `Overtime` chưa
  được dùng), nên chưa hại — nhưng đừng thêm cảnh báo OT trước khi xử chỗ này.

## Test

```bash
bash openclaw-skills/tests/run.sh
```

Offline, không cần mạng/API key, không đụng sheet thật. Bao phần dò cột ngày,
đọc công đăng ký, và chia nhóm thiếu giờ — xem [`tests/README.md`](../tests/README.md).
