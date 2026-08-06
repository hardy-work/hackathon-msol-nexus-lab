---
name: reminder-followup
description: Nhắc report task hàng ngày qua cron, tag từng người theo danh sách trong tab "Resource plan" của Google Sheet logtime, follow-up tag người chưa report trong thread, chấm format dòng report, rồi chuyển dòng hợp lệ sang skill gg-sheet (Action 4) để log lên sheet. BẮT BUỘC mở skill này trước khi trả lời mỗi khi có người tag bot kèm dòng report task (dòng có dấu "|" và mã task đầu dòng, kiểu "NEX-1 | 8 | 03-08-2026 | ..."), khi ai đó trả lời/giải thích vì sao task chậm hơn plan, hoặc khi hỏi về mẫu report / sao bị nhắc sai format — luật chấm và câu trả lời mẫu nằm trong skill, tuyệt đối không tự chấm bằng trí nhớ.
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
                "FOLLOWUP_CRON_1",
                "FOLLOWUP_CRON_2",
                "FOLLOWUP_CUTOFF_TIME",
                "GOOGLE_SHEETS_API_KEY",
                "LOGTIME_SHEET_LINK",
              ],
          },
      },
  }
---

## Quy tắc bất biến

- **Phiên cron KHÔNG có tool `slack`.** Đã dò thực tế (2026-07-30): session
  `isolated` của cron chỉ có `Agent, AskUserQuestion, Bash, Edit, Read,
  ReportFindings, Skill, ToolSearch, Write` — gọi `slack` luôn lỗi
  `No such tool available: slack`, và `ToolSearch` cũng không tìm ra tool Slack
  nào. Mọi thao tác Slack cần tool phải đi qua **CLI `openclaw message`** bằng
  tool `Bash` (xem Job B). Cấp `--tools` cho job cũng vô ích: backend
  `claude-cli` báo lỗi `cannot enforce runtime toolsAllow`.
- **Không delegate bước Slack nào cho subagent** — chạy trực tiếp (inline)
  trong phiên đang xử lý job.
- **MỌI tin nhắc của skill này đều tag đích danh từng người bằng `<@id>`.**
  Tuyệt đối không dùng `<!here>` / `<!channel>` ở bất kỳ tin nào — trong kênh có
  người không phải report (PM, khách, bot), ping cả kênh là làm phiền nhầm
  người. Danh sách id lấy từ Google Sheet, xem mục dưới.
- **Skill này không tự ghi lên Google Sheet.** Sheet ở đây là **chỉ đọc**, và
  chỉ để biết phải tag ai. Việc ghi dòng report vào lịch trình là của skill
  **`gg-sheet`, Action 4** — skill này chấm format xong thì chuyển sang đó, không
  tự dựng lệnh `curl`, không tự mint token. Ranh giới: skill này nắm **hội thoại
  Slack** (ai report, tag ai, hạn bao lâu), `gg-sheet` nắm **cấu trúc sheet** (cột
  nào, ghi thế nào).
- **Bị tag là PHẢI có phản hồi — kể cả khi hỏng.** Không log được vì bất kỳ lý
  do gì (mã task không có trong sheet, mất mạng, hết quyền ghi, script lỗi, đọc
  file lỗi, không hiểu dev nói gì) thì **nói ra ngay tại chỗ**, kèm lý do ngắn
  bằng tiếng Việt và việc dev cần làm tiếp. Tuyệt đối không im, không `NO_REPLY`,
  không "để lát nữa Job B nhắc", không thả mỗi emoji rồi thôi. Im lặng là lỗi
  **nặng hơn** lỗi ghi: dev tưởng đã log xong nên đi về, tới cuối sprint mới lòi
  ra là sheet trống. Không chắc chuyện gì đang xảy ra → nói thẳng "mình chưa log
  được, đang lỗi <…>" rồi hỏi lại, đừng đoán rồi im.
- Skill này **không đẩy gì sang Jira** và không tổng hợp tiến độ.
- Bot **chỉ kiểm cấu trúc dòng report** (xem "Luật kiểm format"), **không đánh
  giá nội dung**: không phán task này làm đúng chưa, giờ khai có hợp lý không,
  ghi chú đủ chi tiết chưa. Sai cấu trúc thì nhắc sửa, không bao giờ bình luận
  về chất lượng công việc của ai.
- **Follow-up không DM ai cả.** Mọi lời nhắc lại đều là reply vào chính thread
  của tin nhắc hôm đó (Job A), tag người chưa report. Tuyệt đối không đăng tin
  mới ra kênh ở Job B.
- **Trong thread report, mặc định là IM LẶNG** — chỉ nói khi bị tag trực tiếp,
  hoặc khi Job B chạy. Xem mục "Im lặng trong thread" ngay dưới.

## Im lặng trong thread — chỉ nói khi được tag

Bot là người mở thread nên **mọi tin nhắn trong thread đó đều được đẩy về bot**.
Đó **không** phải lời mời trả lời. Mặc định trong thread report là **im lặng
tuyệt đối**.

> ⚠️ **Luật này chỉ áp cho THREAD report do bot mở.** Ngoài kênh chính, bot cư
> xử như thành viên bình thường. Và **hễ bị tag `<@bot_id>` là PHẢI trả lời** —
> ở kênh hay trong thread, dù tin đó có ra câu hỏi hay không. `alo`, `ping`,
> `còn sống không`, hay tag trống: đáp ngắn gọn một câu. Bị tag chính là lời
> mời, bot không có quyền tự chấm xem tin đó có đáng trả lời hay không.
>
> Lỗi đã xảy ra thật (05-08-2026): phiên mới trả về `NO_REPLY` cho
> `<@bot> alo alo`, nhìn từ ngoài y như bot chết, người dùng phải đi hỏi tại sao.
> **Đừng bao giờ để ai phải phân vân bot còn sống hay không.**

**Chỉ được nhắn vào thread trong đúng 2 trường hợp:**

1. Có người **tag trực tiếp** `<@bot_id>` (hoặc DM bot). Tag một lần rồi mọi
   người nói chuyện tiếp với nhau → vẫn im, không coi là được mời vào cả cuộc
   hội thoại.
2. **Job B (cron follow-up) đang chạy** — và khi đó chỉ đăng đúng nguyên văn
   template "Tin nhắc lại", không thêm câu dẫn, không thêm lời bình.

**Tuyệt đối không tự nhảy vào để:**

- Xác nhận ai đó vừa report (*"ghi nhận NEX-004 nhé"*, *"mình nhận đủ rồi 👍"*).
- Nhắc format khi thấy dòng report thiếu/sai. **Đó là việc của Job B**, gom một
  lần rồi tag — không nhắc lẻ từng người ngay lúc họ vừa gõ xong.
- Đáp lại chat vặt giữa người với người: *"oke"*, *"task hôm nay gần xong rồi"*,
  *"để em hoàn thành nốt"*, *"thế thì làm tiếp cho xong đi nhé"* → **im**.
- Hối/dặn dò: *"xong nhớ quăng dòng report vào đây nha"*, *"không là mai anh
  nhắc tiếp đó"*.

Đây là lỗi đã xảy ra thật (2026-07-31): trong một thread, bot tự rep liền 3 tin
cho những câu trao đổi bình thường giữa 2 người — vừa ồn, vừa đi giục đúng người
vừa nói là sắp xong. Nếu thấy cần ghi nhận thì **thả emoji react**, không nhắn.

Nguyên tắc gọn: **nhắc report là việc của cron, không phải việc của bot trong
lúc người ta đang trao đổi.**

## Ai phải report — lấy từ Google Sheet logtime (tab `Resource plan`)

**Nguồn duy nhất** xác định ai phải report là tab `Resource plan` của Google
Sheet logtime khai trong `.env`:

| Env | Ý nghĩa |
|-----|---------|
| `LOGTIME_SHEET_LINK` | Link đầy đủ của Google Sheet logtime (fallback: `GOOGLE_SHEETS_LINK`) |
| `LOGTIME_SHEET_TAB` | Tên tab, mặc định `Resource plan` — chỉ khai khi tab tên khác |
| `GOOGLE_SHEETS_API_KEY` | API key đã bật Google Sheets API (chỉ cần quyền đọc) |
| `EFFORT_TOLERANCE_H` | Dung sai khi so giờ, mặc định `1` — thiếu dưới ngần này thì im, khỏi hỏi ai vì `7,5` với `8` |

Trong tab đó phải có một bảng với các cột header **`Member`**, **`Slack ID`**,
`Slack name`, `Role`, kèm khối công *"Thời gian làm việc mỗi ngày"* (mỗi ngày 1
cột). Mỗi dòng có `Slack ID` hợp lệ = **một người trong danh sách**.

> Không có file roster nữa. Người được thêm/bớt bằng cách sửa thẳng Google
> Sheet, có hiệu lực ngay lượt cron kế tiếp — không cần sửa file, không cần
> restart Gateway.

### Ai nghỉ hôm nay thì KHÔNG nhắc

Ô công của **đúng ngày hôm nay** trống, `0`, `-`, `P`, `nghỉ`, `off` → người đó
**nghỉ**: không tag, không tính vào "chưa report", **không hỏi han gì cả** — im
hẳn. Không cần kiểm họ có trong group chat hay không, sheet nói nghỉ là nghỉ.

Nhờ vậy T7/CN (ô công để trống) không ai bị nhắc mà không phải khai lịch nghỉ ở
đâu khác. Ô ghi chữ lạ không hiểu được → coi như **đi làm** (thà nhắc thừa 1
người còn hơn im lặng bỏ sót người phải report).

### Lấy danh sách — luôn dùng script, không tự parse sheet bằng mắt

```bash
# JSON đầy đủ
bash {baseDir}/scripts/resource-plan-members.sh

# Chuỗi mention của riêng người phải report hôm nay: "<@U09QRTUHX24> <@U0APQSSGKTM> ..."
bash {baseDir}/scripts/resource-plan-members.sh --mentions

# Ai hôm nay log thiếu giờ so với công đăng ký (xem mục "Log thiếu giờ …")
bash {baseDir}/scripts/resource-plan-members.sh --effort-check
```

```json
{
  "date": "05-08-2026",
  "found_day_column": true,
  "people": [{ "id": "U09QRTUHX24", "name": "Bùi Hồng Sơn", "slack_name": "MH_SonBH", "role": "BE", "hours": 8 }],
  "off": [],
  "no_id": [],
  "bad_id": []
}
```

`hours` = số giờ công **đăng ký cho hôm nay**, lấy nguyên con số trong ô (`8` =
đủ công, `4` = nghỉ nửa buổi). `null` = sheet chưa có cột cho hôm nay hoặc ô ghi
chữ lạ — **đừng lấy 8 làm mặc định**.

- `people` — **phải report hôm nay**. Chỉ tag đúng nhóm này.
- `off` — nghỉ hôm nay. **Tuyệt đối không tag, không nhắc, không nhắn gì.**
- `bad_id` — có `Slack ID` nhưng id đó **không tồn tại trong workspace** (hoặc đã
  nghỉ việc). Script đã tự loại khỏi chuỗi mention. **Không** thêm dòng nào vào
  tin Slack vì chuyện này, **không** đoán id khác, **không** tag bằng tên —
  người đó coi như không có trong danh sách hôm nay.
- `no_id` — có tên trong sheet nhưng thiếu ô `Slack ID` nên không tag được.
  Khác rỗng → vẫn nhắc bình thường những người còn lại, và thêm vào **cuối** tin
  đúng 1 dòng: `(Chưa có Id Slack nên mình không tag được: <tên 1>, <tên 2>)`.
- `found_day_column: false` — sheet chưa kéo dài cột ngày tới hôm nay. **Không
  phải lỗi**: script trả về cả đội, cứ nhắc bình thường, chỉ thêm vào **cuối**
  tin đúng 1 dòng:
  `(Bảng công trong sheet chưa có cột cho hôm nay, nhờ PM kéo dài giúp mình nhé.)`

Hai dòng phụ trên là **ngoại lệ duy nhất** được thêm vào template — ngoài chúng
ra không được chế thêm câu nào.

Script tự dò **header theo tên cột** (`Slack ID`, `Member`…) và tự dò cột ngày
theo tên tháng ở dòng header + số ngày ở dòng kế dưới, không hardcode dòng/cột —
sheet chèn thêm dòng tiêu đề hay dịch bảng sang phải vẫn chạy đúng. Dòng không
có user id dạng `U…`/`W…` bị bỏ qua (dòng SUM, dòng trống), id trùng chỉ lấy 1
lần. "Hôm nay" tính theo `REMINDER_TIMEZONE`, không theo giờ máy chạy Gateway.

Script còn **đối chiếu từng id với workspace** (`users.info`) trước khi in. Đúng
cú pháp `<@U…>` không có nghĩa là người đó có thật: Slack render id lạ thành một
**pill trống**, tin vẫn đăng, vẫn xanh, mà không ai nhận notification và không
lỗi nào nổ ra. Đã dính thật ngày 06-08-2026 — cả 6 id trong sheet là của
workspace khác, tin 9:00 tag vào hư không. Id sai bị **loại thẳng**; loại hết thì
script trả exit 5 chứ không đăng tin rỗng. Không lấy được token Slack thì script
bỏ qua bước này và giữ nguyên danh sách — thà tag một id đáng ngờ còn hơn im
lặng bỏ sót người phải report.

**Không tự gọi thẳng Sheets API rồi tự đoán cột.** Bảng trong `Resource plan`
nằm lẫn với bảng kế hoạch nguồn lực khác ở cùng vùng dòng — đọc bằng mắt rất dễ
bắt nhầm cột tên và tag sai người.

Exit code của script — **không được nuốt lỗi**:

| Exit | Nghĩa | Xử lý |
|------|-------|-------|
| 0 | OK, có ít nhất 1 người phải report hôm nay | Chạy tiếp |
| 2 | Thiếu env / tham số sai | Dừng, báo lỗi — PM khai thiếu env |
| 3 | Gọi Sheets API lỗi (sai link, chưa share, hết quota) | Dừng, báo lỗi |
| 4 | Tab không có cột `Slack ID` | Dừng, báo lỗi — sai tab hoặc header bị đổi |
| 5 | Có cột nhưng không có dòng người nào, **hoặc mọi id đều không tồn tại trong workspace** | Dừng, báo lỗi |
| 6 | Đọc được sheet nhưng **hôm nay cả đội nghỉ** (T7/CN…) | **SKIP im lặng** — không đăng gì cả, đây KHÔNG phải lỗi |

Exit 2/3/4/5 → **không nhắc ai**, không fallback sang thành viên kênh, không tự
đoán danh sách, không dùng `<!here>` để nhắc bừa cả kênh, và **không** được báo
`tat ca da report` (chưa đọc được danh sách và mọi người đã report xong là hai
chuyện khác hẳn nhau, gộp lại là báo cáo sai). Xem "Không đọc được sheet" bên
dưới để biết báo ra ngoài thế nào.

Exit 6 thì ngược lại: **tuyệt đối không báo lỗi ra Slack**. Cả đội nghỉ là
chuyện bình thường, đăng cảnh báo vào ngày nghỉ mới là làm phiền.

Ngoài ra: nếu chính bot report có mặt trong sheet thì **bỏ bot ra** — bot không
phải report.

Soi lỗi bằng tay ("hôm T7 bot có nhắc nhầm ai không?"): đặt `LOGTIME_TODAY=YYYY-MM-DD`
để giả lập ngày. Chỉ dùng khi chạy tay — cron **không bao giờ** set biến này.

## State file

`{baseDir}/state/<YYYY-MM-DD>.json`, tạo mới rỗng mỗi ngày:

```json
{
  "reminderThreadTs": "1690000000.000100"
}
```

Chỉ lưu `ts` của tin nhắc hôm nay (Job A ghi, Job B đọc để biết reply vào đâu).
Danh sách ai đã report **không** lưu vào state — mỗi lần chạy Job B đọc lại
reply trong thread rồi tính tươi, nên state hỏng/mất cũng không sai lệch.

### `state/pending-overtime.json` — task đang chờ giải trình

File thứ hai, **không** theo ngày (một pending mở lúc 16:50 phải sống qua nửa
đêm nếu cần). Đây là chỗ **duy nhất** biết task nào đang bị treo vì vượt giờ
plan, và mốc `asked_at` để tính hạn 1 tiếng.

```json
{ "pending": [ { "task_id": "PCS-7", "slack_id": "U...", "asked_at": 1754382000, "...": "..." } ] }
```

Cấu trúc đầy đủ, cách ghi/xoá, cách tính hạn: xem mục
"Task chậm hơn plan — hạn 1 tiếng" bên dưới.

Mất file này = mọi task đang treo coi như chưa từng bị hỏi: dev trả lời lý do sẽ
không khớp được vào đâu, và Job B không nhắc ai quá hạn. Không nghiêm trọng bằng
mất dữ liệu sheet, nhưng đừng xoá tay giữa ngày.

### `state/effort-today.json` — sổ cái giờ đã log

File thứ ba. **Skill này chỉ ĐỌC** — người ghi là `gg-sheet/scripts/sheet-task.sh`
sau mỗi lần log thành công (nó là chỗ duy nhất biết `delta` = giờ vừa bỏ thêm
vào, vì phải so với giá trị đang có trên sheet). File nằm bên này vì đây là nơi
dùng nó; hai skill là thư mục anh em trong workspace nên script bên kia tính
đường dẫn bằng `../reminder-followup/state/...`, không cần env nào.

```json
{ "entries": [
  { "date": "2026-08-06", "slack_id": "U...", "task_id": "NEX-1",
    "delta": 3, "actual": 8, "status": "Done", "at": 1754... }
] }
```

Tự dọn, chỉ giữ 7 ngày gần nhất. Mất file = lượt 16:30 coi như chưa ai log giờ
nào → không ai bị hỏi thiếu giờ. **Không** chặn việc log lên sheet, và cũng
không làm sai nhóm `CHUA_REPORT` (nhóm đó vẫn tính tươi từ thread).

Sổ cái này còn là câu trả lời cho *"dev tự mở thread riêng rồi tag bot vào log
thì Job B có thấy không"*: Job B chấm nhóm `CHUA_REPORT` bằng reply trong thread
9:00, nên report ở thread khác sẽ **không** được thấy. Ai có mặt trong sổ cái là
đã log thật, dùng nó mà trừ ra.

## Luật kiểm format — reply thế nào thì tính là đã report

Reply vào thread **không** mặc nhiên là đã report. Người chỉ nói chuyện công
việc kiểu "hôm nay em fix bug login xong rồi" vẫn tính là **chưa report**.

**Toàn bộ luật chấm nằm ở [`template/log-task-rules.md`](template/log-task-rules.md)
— đó là nguồn duy nhất.** File này cố ý **không** chép lại: 7 field, cách dọn
dòng, dòng nào bị chấm, thế nào là Done, chia 3 nhóm — tất cả ở đó.

⚠️ **Cần chấm thì `cat` file đó ra đọc ngay lúc chấm.** Không nhớ lại từ tin
nhắn cũ, không tái tạo từ trí nhớ phiên, không dựa vào bản tóm tắt nào. Lỗi đã
xảy ra thật ba lần: bản copy cũ nằm sẵn trong context luôn thắng bản mới nằm
trong file.

Vẫn giữ nguyên luật **"Im lặng trong thread"**: thấy dòng sai lúc 10h thì
**không** được nhảy vào nhắc ngay — trừ khi người đó **tag bot trực tiếp** (xem
mục dưới). Không ai tag thì gom lại, đến Job B (16:30 / 17:00) mới tag một lần.
Không có dòng sai nào thì tuyệt đối im — không xác nhận, không khen, không thả
câu "đã ghi nhận".

## Dev tag bot để report — kiểm format tại chỗ

Ngoài luồng cron, dev có thể **tag bot kèm dòng report** để được chấm ngay,
không phải đợi 16:30. Bị tag là **phải trả lời** (luật này đứng trên mọi luật im
lặng — xem `AGENTS.md`).

**Việc đầu tiên, trước khi nói bất cứ câu nào:** đọc
[`template/log-task-rules.md`](template/log-task-rules.md) rồi chấm từng dòng
log trong tin của họ. Không được trả lời trước rồi chấm sau, không được chấm
bằng trí nhớ.

Ba tình huống:

**1. Không có dòng log nào** (họ chỉ hỏi han, nhờ việc khác) → đây không phải
report. Trả lời bình thường theo nội dung họ hỏi, **không** lôi luật format ra.

**2. Mọi dòng log đều hợp lệ** → **chuyển sang skill `gg-sheet`, Action 4** để
log lên sheet. Không dừng ở câu "đã ghi nhận" nữa, và cũng **không tự ghi sheet
ở đây**: mở `gg-sheet/SKILL.md` mục "Action 4: Log report task của dev" rồi làm
theo `gg-sheet/log-report-rules.md`. Câu trả lời cuối cùng cho dev (log xong /
hỏi lý do task chậm / mã task không có trong sheet) lấy mẫu trong chính file đó.

Chuyển sang thì đưa đủ: **từng dòng report** đã chấm hợp lệ, `<@id>` và tên
Slack của dev. `<@id>` là bắt buộc, không phải để xưng hô: `gg-sheet` truyền nó
vào `--slack-id` để ghi sổ cái giờ đã log (xem "Log thiếu giờ so với công đăng
ký"). Việc còn lại — tìm dòng theo `TaskID`, ghi cột nào, so giờ plan — là của
`gg-sheet`.

**3. Có ≥1 dòng log sai** → chỉ ra **đúng dòng nào sai và sai điều gì**, trích
nguyên văn dòng đó, kèm bản sửa gợi ý. Mỗi dòng sai một gạch đầu dòng:

```
<@U0BK2KAN86B> dòng này chưa đúng mẫu nhé:
• `NEX-2 | 8 | 3-8-2026 |  | 8 | đang làm |` → Start date phải dạng DD-MM-YYYY (`03-08-2026`)

Report theo mẫu sau :
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note

VD: NEX-214 | 8 | 03-08-2026 | 04-08-2026 | 7.5 | Done | xong sớm nửa buổi
```

Sai format thì **không log gì lên sheet cả**, kể cả những dòng đúng trong cùng
tin nhắn. Sửa rồi report lại thì mới ghi.

**4. Dev đang giải trình task chậm** → đây **không** phải dòng report, đừng đem
đi chấm format. Xem mục "Task chậm hơn plan — hạn 1 tiếng" ngay dưới.

**5. Dev đang trả lời câu hỏi thiếu giờ** (bot vừa hỏi "hôm nay đăng ký 8h mà mới
log 5h…") → cũng không phải dòng report. Xem mục "Log thiếu giờ so với công đăng
ký". Nhận ra bằng ngữ cảnh y như case 4.

Nhận ra bằng **ngữ cảnh hội thoại**: tin gần nhất của chính bot trong thread/kênh
này có hỏi lý do một task chậm, và người đang nhắn chính là người bị hỏi. Câu trả
lời không cần đúng mẫu gì cả — *"lý do là phát sinh CR từ khách hàng"* là đủ.

⛔ **Không lấy `state/pending-overtime.json` làm điều kiện nhận diện.** File đó
là bản ghi phụ cho Job B, có thể chưa kịp ghi, có thể bị xoá. Không thấy file →
vẫn xử lý bình thường theo ngữ cảnh, rồi ghi file sau. Lỗi đã xảy ra thật
(05-08-2026): bot hỏi lý do task PCS-10, dev trả lời có tag bot, bot mở skill,
không thấy file pending nên không khớp case nào và **im luôn** — dev ngồi đợi
một câu không bao giờ tới.

⛔ **Bị tag thì không bao giờ được im**, kể cả khi không khớp case nào ở trên.
Không hiểu ý họ thì hỏi lại một câu, đừng `NO_REPLY`.

Ràng buộc khi trả lời:

- **Luôn mở đầu bằng `<@id>` của chính người vừa report** — cả khi đúng lẫn khi
  sai. Kênh `#daily` đông người và nhiều report chồng nhau, không tag thì không
  ai biết bot đang nói với ai, nhất là khi có 2-3 người report sát giờ nhau.
  Mention bằng `<@Uxxxx>` (id thật của họ), **không** gõ tên hay `@tên` —
  gõ tay ra chữ thường thì Slack không đẩy notification, người ta không thấy.
  Đúng một mention một tin: không tag thêm PM, không tag người khác vào.
- **Chỉ nói lý do có trong `log-task-rules.md`.** Không tự chế thêm quy tắc.
- **Không bao giờ nhắc về dạng mã task** — `4`, `abc 12`, `DWM-2222` đều hợp lệ.
- **Không đánh giá nội dung công việc**: không phán giờ khai hợp lý hay không,
  không hỏi sao task này lâu thế, không gợi ý chia nhỏ task.
- Dòng nào **bỏ qua** (câu dẫn, emoji, dòng tiêu đề) thì đừng nhắc tới nó.
- Trả lời **đúng chỗ họ tag**: tag trong thread thì rep trong thread, tag ngoài
  kênh thì rep ngoài kênh. Không mở thread mới.
- **Một tin duy nhất.** Không tách thành nhiều tin, không rep thêm lần hai cho
  cùng một report.

Chấm tại chỗ **không** thay thế Job B: người được chấm ở đây vẫn được Job B tính
lại từ đầu lúc 16:30 (Job B đọc lại thread và chấm tươi), nên nếu họ sửa lại
đúng thì tự khắc không bị tag nữa.

## Task chậm hơn plan — hạn 1 tiếng

`gg-sheet` Action 4 trả về **exit 9** khi giờ thực tế vượt giờ plan: nó **chưa
ghi gì**, và hỏi dev lý do. Đây **không phải là từ chối log** — có lý do là ghi
`Risk management` rồi log task như thường.

Phần `gg-sheet` lo: so giờ, soạn câu hỏi, ghi risk, ghi task. Phần **skill này**
lo: **đồng hồ**. `gg-sheet` không theo dõi hội thoại và không có bộ đếm giờ.

### Ghi pending ngay khi hỏi

File này **không phải điều kiện để nhận diện** dev đang giải trình (xem case 4)
— nó chỉ để **Job B 16:30** biết ai đã được hỏi mà im luôn. Ghi file lỗi thì cứ
tiếp tục hội thoại bình thường, đừng vì thế mà không trả lời dev.

`{baseDir}/state/pending-overtime.json` (chưa có thì tạo `{"pending": []}`),
mỗi task vướng một phần tử:

```json
{
  "task_id": "PCS-7",
  "slack_id": "U0BK2KAN86B",
  "slack_name": "long.vn",
  "assignee": "VinhNV",
  "channel": "C0BKLP5KYD7",
  "thread_ts": "1754...",
  "asked_at": 1754382000,
  "estimate": 8,
  "actual": 9,
  "diff": 1,
  "report": { "re_est": "8", "start": "03-08-2026", "end": "04-08-2026", "actual": "9", "status": "Done", "note": "" }
}
```

`asked_at` lấy **bằng lệnh** `date +%s`, không tự nhẩm.

Giữ nguyên `report` — lúc log lại thì dùng **đúng số cũ đã report**, không hỏi
lại dev số liệu, không lấy số mới trong câu trả lời lý do.

Đã có pending cùng `slack_id` + `task_id` → **cập nhật tại chỗ**, không thêm
phần tử thứ hai và **không gia hạn `asked_at`**. Hỏi lại lần nữa không phải là
được thêm một tiếng.

### Dev trả lời lý do

Câu trả lời **không cần đúng format report** — đây là câu giải thích. Chỉ vừa
hỏi một task thì lý do đó là của task đó, đừng hỏi lại cho chắc. Đang treo nhiều
task mà họ không nêu task nào → hỏi lại task nào, đừng gán bừa.

Tính tuổi: `AGE = $(date +%s) - asked_at`. **Không có `asked_at`** (chưa kịp ghi
pending) → lấy timestamp tin hỏi của bot trong thread; không lấy được nữa thì
**coi như còn hạn** và log luôn. Thà log một task muộn còn hơn bắt dev gõ lại từ
đầu vì bot đánh mất bản ghi của chính mình.

- **`AGE <= 3600`** → chuyển sang `gg-sheet` Action 4 kèm lý do: ghi
  `Risk management` **trước**, `log --force` **sau** (xem
  `gg-sheet/log-report-rules.md`). Xong thì xoá phần tử pending.
- **`AGE > 3600`** → **không log nữa**, dù lý do chính đáng đến đâu:

  ```
  <@U0BK2KAN86B> lý do này quá 1 tiếng rồi nên mình không tự log PCS-7 được nữa,
  bạn báo trực tiếp PM giúp mình nhé.
  ```

  Rồi xoá phần tử pending (đã trả lời thì Job B không nhắc lại nữa).

Ai im luôn thì Job B 16:30 quét pending quá hạn và tag một lần — xem mục
"Tin nhắc lại (Job B)".

## Log thiếu giờ so với công đăng ký — hỏi, không chặn

Ngoài chuyện *report có đúng mẫu không*, còn một câu hỏi nữa: hôm nay người đó
đã log **đủ số giờ đã đăng ký** chưa. Mốc nằm sẵn trong `Resource plan`, khối
"Thời gian làm việc mỗi ngày" — **chính là ô mà script đang đọc để biết ai nghỉ**,
chỉ khác là giờ giữ lại con số (`hours`) thay vì chỉ lấy có/không.

Nhờ vậy **nghỉ nửa buổi không cần luật riêng**: PM sửa ô hôm đó thành `4` thì mốc
tự thành 4, log 4h là khớp, bot im.

### Giờ hôm nay là DELTA, không phải số trong report

`Actual Effort (h)` là số **cộng dồn của cả task**, không phải giờ làm hôm nay.
`NEX-10 | 16 | 03-08-2026 | | 12 | In progress |` nghĩa là task đó đã tiêu 12h
tính từ 03-08 — cộng thẳng các dòng report lại là sai số ngay từ người đầu tiên.

`gg-sheet` Action 4 tính hộ: `delta = actual mới − actual đang có trên sheet`,
rồi ghi một dòng vào sổ cái `state/effort-today.json`. Skill này chỉ đọc sổ đó.
Delta âm (dev khai lại thấp hơn) là hợp lệ và làm tổng ngày **giảm**.

### Rẽ nhánh theo Status, không rẽ theo số giờ

Thiếu giờ chỉ là **triệu chứng**. Cùng triệu chứng, hai bệnh khác hẳn:

| Tình huống | Nghĩa | Làm gì |
|---|---|---|
| Còn ≥1 task **In progress** | Task chưa xong mà giờ bỏ vào cũng chưa đủ → tiến độ đang trôi thật | Hỏi lý do → ghi `Risk management` |
| Mọi task đều **Done** | Xong sớm hơn plan | **Không risk.** Hỏi nhẹ một câu, hết |

⛔ **Không gộp hai nhóm.** Gộp là biến "làm nhanh hơn plan" thành rủi ro dự án —
est 8h làm 5h rồi Done là chuyện tốt, hỏi han kiểu vướng mắc ở đó là phạt người
làm tốt. Và người **đủ giờ** (kể cả 3h task này + 5h task kia = 8h) thì tuyệt đối
im, không một chữ nào.

### Ai bị bỏ qua

- `du_gio` — đủ công, im.
- `chua_log` — chưa log gì cả, họ **đã** nằm trong nhóm `CHUA_REPORT`. Tag thêm
  lần nữa vì cùng một chuyện là phiền người ta hai lần trong cùng một tin.
- `hours` là `null` (sheet chưa có cột cho hôm nay, hoặc ô ghi chữ lạ) — **không
  lấy 8 làm mặc định**. Đoán mốc rồi đi hỏi người ta là nhắc oan.

### Chỉ hỏi ở lượt 16:30

Hạn cutoff là 17:30. Hỏi ở lượt 17:00 thì dev còn 30 phút, hỏi cũng như không.
Hỏi **đúng một lần**, không ghi pending, không nhắc lại, không lôi sang mai — ai
không trả lời thì thôi, PM tự thấy trên sheet.

Khác hẳn exit 9 (task vượt giờ plan): ở đó task **chưa được ghi** nên phải đuổi
cho bằng được, có bộ đếm 1 tiếng. Ở đây **task đã ghi xong xuôi rồi**, câu hỏi
chỉ để bổ sung thông tin — không có gì bị treo, nên không cần đồng hồ.

### Dev trả lời

Nhận ra bằng **ngữ cảnh**: tin gần nhất của bot có hỏi một trong hai câu trên, và
người đang nhắn chính là người bị hỏi.

- Nhóm **In progress** trả lời lý do → `gg-sheet`:
  `sheet-task.sh risk --task <task đang In progress> --assignee .. --diff <missing> --reason "<nguyên văn>"`.
  Đúng **1** task đang dở → gán thẳng, không hỏi lại. Từ **2** trở lên → hỏi task
  nào, **không gán bừa** (giống luật ở mục "Dev trả lời lý do" phía trên).
- Nhóm **Done** trả lời gì cũng **không ghi gì cả**. "Em nghỉ nửa buổi" → nghỉ
  phép không phải rủi ro dự án; ô công là dữ liệu plan của PM, cùng hạng với khối
  `PLAN` bên `Sprint 1`, skill này **chỉ đọc**. Cùng lắm nhắc PM sửa ô.
- Họ report bổ sung dòng còn thiếu → xử như report bình thường, sổ cái tự cộng
  thêm, không nhắc lại chuyện thiếu giờ nữa.

### Con số thì nêu, còn lại thì đừng

Mốc giờ trong sheet là **kế hoạch**, không phải sự thật đã kiểm chứng — nên luôn
**hỏi**, không bao giờ khẳng định kiểu "bạn thiếu 4h". Không hỏi "sao ít thế",
không đoán hộ ("chắc bạn nghỉ nửa buổi à"), không nhắc chuyện OT, không đánh giá
nội dung công việc.

## Format tin nhắc chuẩn (BẮT BUỘC, không được diễn giải lại)

Mọi tin nhắc report — dù do cron tự chạy, hay do ai đó nhắn tay bảo bot nhắc
(vd "nhắc report đi", "nhắc lại mọi người report", "xem ai chưa report") —
**PHẢI dùng đúng nguyên văn template dưới đây**, chỉ được thay phần
`<mention_…>`. KHÔNG được tự thêm/bớt câu chữ, không thêm icon, không viết lại
theo văn phong khác mỗi lần, không thêm bullet hướng dẫn ("Ngày viết dạng
DD-MM-YYYY", "Bắt buộc: …", "Hôm qua làm gì / Hôm nay làm gì") tự chế. Luật
format nằm ở mục "Luật kiểm format" là để **bot chấm**, không phải để dán vào
tin nhắn.

### ⛔ Lấy template từ FILE NÀY, không copy tin nhắc cũ

Khi ai đó tag bot nhờ nhắc, **phải mở `SKILL.md` đọc lại template ngay lúc đó**.
**TUYỆT ĐỐI không** dựng lại tin nhắc bằng cách nhìn tin nhắc trước đó trong
kênh / trong thread / trong lịch sử hội thoại rồi chép theo.

Đây là lỗi đã xảy ra thật và kéo dài nhiều ngày (03-08-2026): phiên Slack sống
liên tục từ 29-07-2026, trong lịch sử có tin nhắc cũ dùng template đời đầu
`<NEX-số> | <trạng thái> | <giờ đã làm> | <ghi chú>`. Mỗi lần được nhờ nhắc, bot
chép lại đúng tin cũ đó thay vì đọc skill — riêng ngày 03-08 đã chép 3 lần
(09:38, 10:33, 11:08). Nhìn bên ngoài y như bot đang chạy đúng, thực ra template
đã lạc hậu **5 ngày** và mọi thay đổi format ở file này đều vô hiệu.

Nguyên tắc: **tin nhắc cũ không phải là nguồn**. Nguồn duy nhất của template là
mục này trong `SKILL.md`. Tin cũ trong kênh chỉ chứng minh hôm qua bot đã nhắc,
không chứng minh hôm qua bot nhắc đúng.

### Tin mở thread (Job A — đăng ra kênh)

```
<mention_tat_ca>

Đến giờ report task rồi, mọi người report hôm nay giúp mình nhé!

Report theo mẫu sau :
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note

VD: NEX-214 | 8 | 03-08-2026 | 04-08-2026 | 7.5 | Done | xong sớm nửa buổi
```

- `<mention_tat_ca>` = **những người phải report hôm nay** (`people`), lấy
  nguyên văn output của `scripts/resource-plan-members.sh --mentions`. Đầu giờ
  chưa ai report nên ai đi làm cũng bị tag — đây là chủ ý, không phải thừa.
  Người nghỉ hôm nay đã bị script loại sẵn.
- **Không** dùng `<!here>`/`<!channel>` thay cho danh sách này.
- Chuỗi mention đứng **riêng một dòng**, cách câu "Đến giờ report task rồi" bằng
  một dòng trống. Sáu cái `@tên` dính liền đầu câu làm câu nhắc bị đẩy khuất
  sang phải, đọc trên mobile là mất hẳn. Đừng gộp lại thành một dòng.

Câu `Đến giờ report task rồi` là **mốc nhận diện** Job B dùng để tìm lại
thread — đổi câu này thì phải đổi cả bước 2 của Job B.

### Tin nhắc lại (Job B — reply trong thread, không đăng ra kênh)

```
Nhắc nhẹ mọi người trước khi hết ngày nhé 🙌

• Chưa report hôm nay: <mention_chua_report>
• Report chưa đúng mẫu, sửa lại giúp mình nhé: <mention_sai_format>

Mấy task này mình chưa log lên sheet được vì chưa có lý do vượt giờ plan:
• <@id> — <ids>

<một dòng cho mỗi người ở nhóm "thieu_gio_con_dang_lam">

<một dòng cho mỗi người ở nhóm "thieu_gio_da_xong_het">

Report theo mẫu sau :
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note

VD: NEX-214 | 8 | 03-08-2026 | 04-08-2026 | 7.5 | Done | xong sớm nửa buổi
```

Hai nhóm thiếu giờ chỉ xuất hiện ở **lượt 16:30**, xem mục "Log thiếu giờ so
với công đăng ký". Lượt 17:00 dùng đúng template này nhưng bỏ hẳn 2 khối đó.

- Nhóm nào rỗng thì **bỏ hẳn dòng đó** cùng dòng tiêu đề và dòng trống đi kèm,
  không in ra dòng cụt không có mention, không để tiêu đề "Mấy task này mình
  chưa log…" đứng trơ không ai bên dưới, không để 2 dòng trống liền nhau.
  Mọi nhóm rỗng → không reply gì cả.
- Mỗi nhóm **một dấu `•` riêng**, không gộp hai nhóm vào một dòng — gộp là mất
  luôn thông tin ai thuộc nhóm nào, mà đó chính là thứ duy nhất tin này mang.
- Nhóm quá hạn giải trình lấy từ `state/pending-overtime.json`: phần tử có
  `asked_at` cách hiện tại **hơn 3600 giây**. Nhóm này ghi **mỗi người một
  dòng** `• <@id> — <ids>` chứ không gộp mention, vì `<ids>` là task của **riêng
  người đó** — gộp chung là mỗi người thấy cả task của người khác. Nhắc xong thì **xoá** phần tử khỏi
  state — mỗi task chỉ bị nhắc đúng một lần, không lôi sang hôm sau.
  Đây là **ngoại lệ duy nhất** của luật "không trích lại nội dung của ai": không
  có id task thì dev không biết task nào bị treo, câu nhắc thành vô dụng. Vẫn
  chỉ nêu id, **không** nêu số giờ, không nêu lý do, không bình luận.
- Giữ nguyên phần "Report theo mẫu sau :" kể cả khi chỉ còn 1 dòng nhắc.
- `<mention_chua_report>` / `<mention_sai_format>` = `<@U09QRTUHX24>
  <@U0APQSSGKTM> …` — user id **lấy từ sheet**, phân nhóm theo bảng ở mục "Luật
  kiểm format", cách nhau bởi dấu cách. Mention bằng `<@id>` chứ không gõ tên,
  để Slack thật sự ping đúng người. Cột `Member`/`Slack name` chỉ để người đọc
  file/log cho dễ.
- Không lấy được danh sách từ sheet → **không nhắc lại** (xem mục "Ai phải
  report"). Không dùng `<!channel>`/`<!here>` thay cho danh sách mention — nhắc
  lại mà ping cả kênh là làm phiền người đã report.
- Không liệt kê dòng sai của ai ra thread, không trích lại nội dung họ đã gõ —
  chỉ tag và trỏ về mẫu.
- Nếu người dùng nhắn tay yêu cầu nhắc lại (không phải qua cron), vẫn áp dụng
  đúng template này, không tự sáng tác lời nhắc mới mỗi lần được hỏi.
- Bot chỉ soi **cấu trúc** dòng theo "Luật kiểm format" để chia nhóm — không
  đọc hiểu nội dung từng field, không đối chiếu giờ, không phán công việc.

## Cron (setup 1 lần, dùng cron expression thật — không diễn giải giờ chung
chung để tránh trôi giờ)

> ⚠️ **Prompt thật của 2 job nằm ở [`cron/`](cron/README.md), không phải ở
> file này.** Phiên cron `isolated` không đọc `SKILL.md` — nó chỉ có cái prompt
> được nhét vào job. Sửa luật ở đây thì **phải sửa song song
> `cron/job-a.prompt.txt` / `cron/job-b.prompt.txt` rồi apply lại**, không thì
> ngoài Slack không đổi gì cả (lỗi đã xảy ra thật 05-08-2026).

**Không gán `--model` cho 2 job dưới đây.** Để cron dùng model mặc định của
workspace/agent. Pin cứng một model id vào skill sẽ vỡ ngay khi workspace đổi
`agents.defaults.models` allowlist — job fail với `cron payload.model <x>
rejected by agents.defaults.models allowlist`. Nếu một job cũ đã lỡ pin model,
gỡ bằng `openclaw cron edit <id> --clear-model`.

**Job A — nhắc (`REMINDER_TIME`, mặc định 09:00 → `0 9 * * *`; đổi field
giờ/phút nếu khác, vd 09:30 → `30 9 * * *`):**

```bash
openclaw cron create "0 9 * * *" \
  "Việc A skill reminder-followup: lấy mention list từ Google Sheet rồi đăng tin nhắc report tag từng người." \
  --name reminder-followup-0900 --tz "$REMINDER_TIMEZONE" \
  --session isolated --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```
`--announce` bắt buộc — thiếu nó, cron chạy xong vẫn không tự đẩy kết quả ra
Slack (`delivered: false` dù `status: ok`).

Chạy:

1. `bash {baseDir}/scripts/resource-plan-members.sh --mentions` → chuỗi mention.
2. Exit 0 → xuất ra final message **đúng nguyên văn template "Tin mở thread"**,
   thay `<mention_tat_ca>` bằng chuỗi ở bước 1 (không tự diễn giải lại, không
   thêm lời dẫn) — `--announce` lo việc đăng vào kênh, nên job này không cần gọi
   tool Slack.
3. **Exit 6 (cả đội nghỉ hôm nay) → không đăng gì cả**, kết thúc bằng
   `SKIP | ca doi nghi hom nay`. Đây là cách T7/CN không có tin nhắc rác.
4. Exit 2/3/4/5 → **vẫn phải đăng tin nhắc**, nhưng theo template "Không đọc
   được sheet" ở mục dưới. Im lặng bỏ hẳn một ngày còn tệ hơn: thread không tồn
   tại thì Job B cũng chết theo mà không ai biết.

Job A không tự ghi được `reminderThreadTs` (nó không cầm `ts` của tin do
announce đăng) — đó là lý do bước 2 của Job B luôn có nhánh quét history để tìm
lại thread. Nếu sau này Job A chuyển sang tự `chat.postMessage`, hãy lưu `ts`
trả về vào state để Job B khỏi phải quét.

**Job B — follow-up. Đúng 2 lượt/ngày: `FOLLOWUP_CRON_1` (mặc định 16:30) và
`FOLLOWUP_CRON_2` (mặc định 17:00), đều trước `FOLLOWUP_CUTOFF_TIME`=17:30.**

Hai mốc này **không** nhét được vào một cron expression: `0,30 16,17 * * *` sẽ
dính thêm 16:00 và 17:30. Nên là **2 job riêng, dùng chung y hệt một prompt** —
`reminder-followup-1630` và `reminder-followup-1700`. Sửa prompt thì
**phải sửa cả 2**, lệch nhau là hai lượt nhắc hành xử khác nhau.

**Đừng dùng `--every`.** Mốc của `--every` bị neo lại theo thời điểm sửa job, nên
mỗi lần `cron edit` là giờ chạy trôi đi (13:47, 15:47…) và không đoán trước được;
ngoài ra nó chạy cả ban đêm chỉ để `SKIP`, tốn token vô ích.

```bash
for slot in "1630:${FOLLOWUP_CRON_1:-30 16 * * *}" "1700:${FOLLOWUP_CRON_2:-0 17 * * *}"; do
  openclaw cron create --cron "${slot#*:}" \
    --message "Việc B skill reminder-followup: tag người chưa report / sai format vào thread tin nhắc hôm nay." \
    --name "reminder-followup-${slot%%:*}" --tz "$REMINDER_TIMEZONE" \
    --session isolated \
    --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
  # cron create mặc định bật announce -> phải tắt, không thì dòng trạng thái
  # bị đăng ra kênh thành tin rác
  openclaw cron edit <id vừa tạo> --no-deliver
done
```

Dùng `--message` chứ không truyền prompt ở vị trí positional: khi đã có `--cron`,
positional đầu tiên bị hiểu là **tên job**, và lệnh fail với
`Choose exactly one payload`.

**Job B KHÔNG dùng `--announce`** (ngược với Job A): nó tự gọi tool Slack để
reply vào thread, nên announce chỉ tổ đăng thêm final text ra kênh thành tin
rác. Thay vì `NO_REPLY`, prompt phải kết thúc bằng **một dòng trạng thái** để còn
soi được log (`REPLIED | chua report: <N> | sai format: <M>` / `SKIP | <lý do>` /
`ERROR | <mô tả>`) — `NO_REPLY` từng khiến "đã đăng" và "chết giữa chừng" nhìn
giống hệt nhau suốt nhiều ngày.

Chạy, tuần tự, không delegate cho subagent. Mọi thao tác Slack dùng tool `Bash`
gọi CLI (không có tool `slack` — xem "Quy tắc bất biến"):

```bash
# đọc kênh
openclaw message read --channel slack --target "$SLACK_REPORT_CHANNEL_ID" --limit 30 --json
# đọc reply trong thread (--thread-id nhận Slack thread timestamp)
openclaw message read --channel slack --target "$SLACK_REPORT_CHANNEL_ID" --thread-id "$THREAD_TS" --json
# reply vào thread
openclaw message send --channel slack --target "$SLACK_REPORT_CHANNEL_ID" --reply-to "$THREAD_TS" --json --message "..."
```

Kết quả nằm trong `payload.messages`, là raw Slack API (có `user`, `ts`,
`text`, `thread_ts`).

1. Quá `FOLLOWUP_CUTOFF_TIME` (theo `REMINDER_TIMEZONE`) → dừng.
2. Xác định thread: đọc history kênh, lọc tin có `user` == user id của bot và
   `text` chứa `Đến giờ report task rồi`. **Lọc theo ngày phải làm bằng lệnh,
   không nhẩm** — model rất dễ đọc nhầm epoch và bám vào thread hôm qua:

   ```bash
   TODAY=$(TZ=Asia/Ho_Chi_Minh date +%F)
   MSGDAY=$(TZ=Asia/Ho_Chi_Minh date -d @<ts> +%F)   # ts nhận cả phần thập phân
   ```

   Chỉ nhận tin có `MSGDAY == TODAY`, rồi lấy tin **mới nhất** trong số đó;
   `THREAD_TS` = `ts` của nó. Không còn tin nào → dừng, **không** tự đăng tin
   nhắc mới ra kênh (việc của Job A) và **không đụng vào thread ngày cũ**.

   Đây là chỗ nguy hiểm nhất của Job B: các lần chạy trước giờ nhắc (rạng sáng)
   luôn thấy thread hôm qua là tin khớp mới nhất. Mất guard này là bot nhắc vào
   thread cũ. Thà bỏ một ngày còn hơn nhắc nhầm.
3. Đọc reply trong thread đó. Với mỗi user id đã reply, dọn dòng → lọc ra các
   **dòng log** → chấm từng dòng theo "Luật kiểm format" → **đã report** khi có
   ≥1 dòng log và **mọi** dòng log đều hợp lệ; **sai format** khi không có dòng
   log nào, hoặc có ≥1 dòng log sai.
4. Chạy `bash {baseDir}/scripts/resource-plan-members.sh` lấy danh sách từ
   sheet. Chỉ xét `people` (trừ chính bot) → chia 3 nhóm theo bảng ở "Luật kiểm
   format"; **`off` bị bỏ ra hoàn toàn**, kể cả khi họ không reply gì. Nhóm
   "chưa report" và "sai format" đều rỗng → dừng, không reply gì cả. Exit 6 →
   `SKIP | ca doi nghi hom nay`, không reply. Exit 2/3/4/5 → xem "Không đọc
   được sheet" bên dưới.
5. Reply **vào chính thread ở bước 2** (`thread_ts` = `reminderThreadTs`),
   đúng nguyên văn template "Tin nhắc lại", điền `<@id>` vào 2 nhóm mention
   (nhóm rỗng thì bỏ dòng). TUYỆT ĐỐI không đăng tin mới ra kênh, không DM ai.

Mỗi lần chạy đăng đúng 1 reply. Lỗi đọc Slack → dừng, log lỗi, không reply mù,
không crash job.

**Job B phải trả về đúng 1 dòng trạng thái** để soi được bằng
`openclaw cron runs --id <job>` — trước đây nó luôn trả `NO_REPLY` khiến "đã
đăng" và "dừng sớm" trông giống hệt nhau, che mất suốt nhiều ngày lỗi thiếu
tool Slack:

```
REPLIED | chua report: <N> | sai format: <M>
NOTIFIED | khong doc duoc sheet (exit <mã>)
SKIP | <lý do: qua gio cutoff / khong tim thay thread hom nay / tat ca da report
        / ca doi nghi hom nay / khong doc duoc sheet, da bao roi>
ERROR | <mô tả ngắn>
```

Dòng này **không** ra Slack vì Job B để `delivery: none`.

## Không đọc được sheet → phải báo ra ngoài, không im

> Mục này **chỉ áp dụng cho exit 2/3/4/5**. Exit 6 (cả đội nghỉ) là chuyện bình
> thường: im hẳn, không đăng gì, không cảnh báo ai.

Script lỗi mà cứ im lặng log `ERROR` là hỏng: Job B để `delivery: none` nên
không ai đọc được dòng đó, trong khi Job A vẫn đăng tin mỗi sáng → nhìn bên
ngoài y như đang chạy tốt, thực ra chả tag được ai suốt nhiều ngày.

**Job A** (script lỗi ở bước 1) — vẫn đăng tin, nhưng thay dòng mention bằng
cảnh báo, vẫn giữ nguyên câu mốc để Job B còn tìm được thread:

```
⚠️ Mình chưa đọc được danh sách người phải report từ Google Sheet logtime (tab Resource plan) nên hôm nay chưa tag được ai — nhờ PM kiểm tra lại link/quyền chia sẻ giúp mình nhé.

Đến giờ report task rồi, mọi người report hôm nay giúp mình nhé!

Report theo mẫu sau :
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note

VD: NEX-214 | 8 | 03-08-2026 | 04-08-2026 | 7.5 | Done | xong sớm nửa buổi
```

**Job B** (script lỗi ở bước 4) — reply đúng 1 lần vào thread hôm nay, **không
tag ai** (chưa biết ai mà tag), không đăng tin mới ra kênh:

```
⚠️ Mình chưa đọc được danh sách người phải report từ Google Sheet logtime (tab Resource plan) nên chưa nhắc được ai. Nhờ PM kiểm tra lại link/quyền chia sẻ của sheet giúp mình nhé.
```

Rồi trả về `NOTIFIED | khong doc duoc sheet (exit <mã>)`.

**Chống báo lặp:** trước khi đăng, soi lại reply trong thread (kể cả tin của
chính bot) xem đã có tin nào chứa `chưa đọc được danh sách người phải report`
chưa. Có rồi → `SKIP | khong doc duoc sheet, da bao roi`. Không có bước này thì
16:30 và 17:00 báo 2 lần y hệt nhau mỗi ngày.

Guard ngày vẫn giữ nguyên: không tìm thấy thread hôm nay thì dừng ở bước 2, câu
báo lỗi này **không** phải cái cớ để đăng tin mới ra kênh.

Sửa xong sheet/env là lượt cron kế tiếp nhắc được ngay — trừ khi phải thêm env
mới thì cần nạp lại env cho Gateway (xem README).

## Thêm/bớt người phải report

Ai đó nhờ *"thêm bạn X vào danh sách nhắc"*, *"bỏ bạn Y ra"*:

- **Không** tạo file roster, **không** ghi danh sách vào skill hay vào state —
  nguồn duy nhất là Google Sheet.
- Hướng dẫn sửa thẳng tab `Resource plan`: thêm/xoá dòng, điền đúng cột `Member`
  và `Slack ID` (lấy user ID: Slack → profile người đó → **More** → *Copy member
  ID*). Có hiệu lực ngay lượt cron kế tiếp.
- Skill này **chỉ đọc** sheet. Muốn bot tự ghi vào sheet thì đó là việc của skill
  `gg-sheet` (có Service Account quyền Editor) — không tự thêm quyền ghi vào đây.
- Ai hỏi *"ai đang trong danh sách nhắc?"* → chạy
  `scripts/resource-plan-members.sh` rồi trả lời bằng cột `Member`, không tag ai
  (chỉ liệt kê thì không cần ping).

## Tổng hợp theo yêu cầu (không qua cron)

Hai mốc 16:30 / 17:00 chỉ là lịch **tự động**. Khi có người **tag bot** và bảo
*"xem ai chưa report"*, *"tổng hợp đi"*, *"ai còn thiếu"*… thì **chạy ngay**,
bất kể đang là mấy giờ:

- **Bỏ qua `FOLLOWUP_CUTOFF_TIME` và bỏ qua lịch cron.** Yêu cầu tay lúc 09:15
  hay 21:00 đều phải chạy. Cutoff chỉ tồn tại để chặn cron, không phải để chặn
  người.
- Làm đúng **bước 2 → 4** của Job B (tìm thread hôm nay, đọc reply, đối chiếu
  danh sách từ sheet, chia 3 nhóm). Guard ngày vẫn giữ nguyên: không có thread
  hôm nay thì báo lại là chưa có tin nhắc, **không** tự đăng tin nhắc mới,
  **không** đụng thread hôm qua.
- Kết quả trả về:
  - Người hỏi chỉ muốn **biết** ("ai chưa report?") → trả lời ngay chỗ họ hỏi,
    liệt kê tên (cột `Member`), **không** reply vào thread và không tag ai. Xem
    tình hình không phải là đi nhắc.
  - Người hỏi bảo **nhắc** ("nhắc mấy người đó đi") → reply vào thread hôm nay
    theo đúng nguyên văn template "Tin nhắc lại", như Job B.
- Cả 2 nhóm rỗng → nói thẳng "cả danh sách đã report đủ", không reply vào thread.

Đây là lối vào duy nhất còn hoạt động ngoài giờ cron — đừng để luật "Im lặng
trong thread" chặn nhầm nó: luật đó cấm **tự ý** nói, còn đây là **được tag và
được nhờ**.

## Q&A

Câu hỏi khác (không phải yêu cầu nhắc report) → trả lời trực tiếp bằng khả
năng hội thoại thông thường, không cần tra cứu gì thêm. **Nhưng vẫn phải bị tag
mới nói** — mục này không phải cửa sau để nhảy vào thread khi không ai hỏi (xem
"Im lặng trong thread").

## Lỗi

| Lỗi | Phản hồi |
|-----|---------|
| `resource-plan-members.sh` exit 2/3/4/5 (thiếu env / API lỗi / sai tab / sheet rỗng) | Không nhắc ai, không fallback sang thành viên kênh, không dùng `<!channel>` — báo ra ngoài theo mục "Không đọc được sheet" |
| `resource-plan-members.sh` exit 6 (cả đội nghỉ hôm nay) | Im hẳn: không đăng tin, không cảnh báo, `SKIP \| ca doi nghi hom nay` |
| Sheet có người thiếu ô `Slack ID` (`no_id`) | Vẫn nhắc những người còn lại, thêm 1 dòng cuối tin liệt kê tên không tag được. **Không** tự đoán id từ tên |
| Sheet có id nhưng id không tồn tại trong workspace (`bad_id`) | Script đã loại sẵn. Nhắc những người còn lại như thường, **không** thêm dòng nào vào tin, **không** thay bằng tên. Sai hết → exit 5 |
| Ô công hôm nay ghi chữ lạ (không phải số, không phải chữ nghỉ) | Coi như đi làm → vẫn nhắc. Thà nhắc thừa còn hơn bỏ sót |
| Không đọc được lịch sử kênh/thread | Dừng job, log lỗi, không reply mù, không crash job |
| Job B không tìm thấy thread tin nhắc hôm nay | Dừng, không tự đăng tin nhắc mới ra kênh |
| Sheet có user id đã rời workspace | Vẫn mention theo id (Slack tự hiển thị inactive) — sửa bằng cách xoá dòng đó khỏi sheet |
| Không chắc một dòng có hợp lệ hay không | Coi là **hợp lệ** (không nhắc) — thà bỏ sót còn hơn báo sai format cho người đã report tử tế |
| `resource-plan-members.sh --effort-check` lỗi / sổ cái hỏng | Coi 2 nhóm thiếu giờ là rỗng, chạy tiếp bình thường. **Không** báo thêm lỗi, **không** vì thế mà bỏ luôn tin nhắc |
| Sheet chưa có cột công cho hôm nay (`hours` = `null`) | **Không lấy 8 làm mặc định.** Bỏ qua người đó ở phần so giờ — đoán mốc rồi đi hỏi là nhắc oan |
| Dev log đủ giờ nhưng report ở thread riêng của họ | Sổ cái vẫn ghi nhận → không tính vào `CHUA_REPORT`. Không nhắc, không đòi họ report lại vào thread 9:00 |
| Có người thắc mắc "tôi report rồi mà vẫn bị nhắc" | Trả lời là dòng report chưa đủ 7 field `Id task \| Re-estimate (h) \| Start date \| End date \| Actual Effort (h) \| Status \| Note`, hoặc ngày chưa đúng `DD-MM-YYYY`, hoặc Status Done mà thiếu End date — và nói rõ **chỉ cần 1 dòng sai là bị nhắc**, dù các dòng khác đã đúng. Chỉ nói lại mẫu, không phán nội dung công việc |
