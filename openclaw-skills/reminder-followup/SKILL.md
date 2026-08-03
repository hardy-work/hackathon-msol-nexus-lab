---
name: reminder-followup
description: Nhắc report task hàng ngày qua cron, và follow-up tag người chưa report ngay trong thread tin nhắc.
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
- Skill này **chỉ nhắc report và follow-up trong thread** — không thu thập nội
  dung report, không xác nhận, không đẩy đi đâu (không Google Sheets, không
  Jira). Cron job chạy xong và tin nhắn được gửi là xong việc.
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

**Chỉ được nhắn vào thread trong đúng 2 trường hợp:**

1. Có người **tag trực tiếp** `<@bot_id>` (hoặc DM bot) để hỏi/nhờ bot việc gì
   đó. Tag một lần rồi mọi người nói chuyện tiếp với nhau → vẫn im, không coi là
   được mời vào cuộc hội thoại.
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

## Roster — ai phải report

`{baseDir}/roster/<SLACK_CHANNEL_ID>.json`, mỗi nhóm 1 file (xem
[`roster/README.md`](roster/README.md)):

```json
[
  { "id": "U0BKL0DJV7B", "name": "Kiên" },
  { "id": "U0BKKXXXXXX", "name": "Tên nhân viên khác" }
]
```

Đây là **nguồn duy nhất** xác định ai phải report. **Không** dùng danh sách
thành viên kênh (`conversations.members`) nữa — ai không có trong roster thì
không bao giờ bị nhắc, dù đang ở trong kênh.

Đọc roster theo channel id của job đang chạy. File không tồn tại / rỗng / parse
lỗi / sau khi bỏ bot còn 0 người → **chưa có roster**: không nhắc ai, không
fallback sang member kênh, không tự đoán danh sách, không dùng `<!channel>` để
nhắc bừa cả kênh.

**Chưa có roster thì phải HỎI, không được im.** Job B reply ngay vào thread của
Job A hôm nay để xin danh sách — xem "Chưa có roster → hỏi trong thread" bên
dưới. Tuyệt đối **không** được trả về `tat ca da report`: chưa khai ai và mọi
người đã report xong là hai chuyện khác hẳn nhau, gộp lại là báo cáo sai.

### Setup kênh mới → phải hỏi danh sách nhân viên

Khi được yêu cầu bật reminder-followup cho một kênh **chưa có** file roster (hoặc
được yêu cầu thêm/bớt người), **hỏi người dùng danh sách nhân viên trước** —
không tự lấy thành viên kênh, không tự đoán, không tạo file rỗng rồi chạy.

Hỏi đúng ý này: *"Gửi danh sách người phải report của kênh &lt;tên kênh&gt;, mỗi
dòng `<user_id> | <tên>` (lấy ID: Slack → profile → More → Copy member ID)."*

Nhận được danh sách → **tự động tạo/cập nhật** `roster/<CHANNEL_ID>.json` theo
đúng format trên, rồi báo lại đã ghi bao nhiêu người. Khi parse danh sách:

- Bỏ qua mọi dòng là **bot** (kể cả chính bot report) — bot không phải report,
  và Job B vốn đã trừ chính bot ra.
- Dòng không có user id dạng `U...` → hỏi lại, không tự suy ra id từ tên.
- Đã có file rồi → nói rõ đang thêm hay ghi đè trước khi sửa, không âm thầm
  xoá người cũ.

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

## Luật kiểm format — reply thế nào thì tính là đã report

Reply vào thread **không** mặc nhiên là đã report. Người chỉ nói chuyện công
việc kiểu "hôm nay em fix bug login xong rồi" vẫn tính là **chưa report**.

Một dòng log task gồm **7 field, đúng thứ tự này**:

```
Id task | Re-estimate (h) | start date | end date | Actual Effort (h) | status | note
```

**Dọn dòng trước khi tách field** (làm đúng thứ tự này, bỏ bước nào là nhắc oan
người ta):

- Bỏ khoảng trắng đầu/cuối dòng.
- Bỏ ký tự liệt kê / định dạng ở **đầu** dòng nếu có: `-`, `–`, `*`, `•`, `>`,
  `1.`, `2)`… và dấu bôi đậm/`code` bọc quanh. Người ta gõ
  `- NEX-123 | …` hay `• NEX-123 | …` là **bình thường**, không phải lỗi.
- Bỏ dấu `|` thừa ở **đầu** dòng (dán từ Excel/Google Sheet ra thường có dạng
  `|NEX-123|8|…|`). **Không** bỏ dấu `|` ở cuối — dấu cuối cùng chính là chỗ
  đánh dấu `note` để trống, bỏ nó đi là dòng đang đúng bỗng thành thiếu field.

Sau khi dọn, một **dòng hợp lệ** phải thoả tất cả:

1. Có **ít nhất 6 dấu `|`** → đủ 7 field. Thừa field vẫn nhận (phần dư coi như
   `note`). Thiếu dấu `|` là **sai**, kể cả khi field cuối để trống — vị trí là
   thứ duy nhất phân biệt được cột nào ra cột nào, thiếu một dấu là mọi cột
   phía sau lệch hết.
2. **Id task**: đầu dòng phải là một mã task **có chứa số**. **Không có quy định
   nào về dạng mã** — tiền tố chữ là tuỳ ý và không phân biệt hoa thường: `4`,
   `NEX-100`, `DWM-2222`, `abc 12` đều hợp lệ như nhau.
3. **Re-estimate (h)**, **Actual Effort (h)**, **status**: bắt buộc, **không
   được để trống**. Nội dung viết gì cũng nhận — `8`, `8h`, `1.5`,
   `In progress`, `đang làm` đều được; không kiểm đơn vị, không kiểm giá trị,
   không phán giờ khai có hợp lý hay không.
4. **start date**: bắt buộc, phải đúng dạng **`DD-MM-YYYY`** (2 số ngày, 2 số
   tháng, 4 số năm, ngăn bằng dấu `-`), vd `03-08-2026`. `3-8-2026` hay
   `2026-08-03` là **sai**.
5. **end date**: được để trống khi status **khác** Done. Người ta ngại để ô
   trống nên hay điền cho có — `-`, `--`, `x`, `?`, `N/A`, `chưa`, `chưa xong`,
   `TBD` đều **tính y như để trống**, hợp lệ. Điền một ngày thật thì phải đúng
   `DD-MM-YYYY`.
6. **status là Done → end date bắt buộc** và phải là ngày thật đúng
   `DD-MM-YYYY` (mấy chữ thay-cho-trống ở trên **không** được chấp nhận nữa).
7. **note**: để trống thoải mái, không bao giờ là lý do báo sai format.

**Thế nào là "status Done":** chuẩn hoá field status trước — bỏ emoji, dấu câu,
khoảng trắng thừa, chuyển thường, bỏ tiền tố `đã ` — rồi so **bằng đúng** một
trong: `done`, `completed`, `finished`, `xong`, `hoàn thành`, `hoan thanh`,
`hoàn tất`.

So **bằng đúng**, tuyệt đối **không** so kiểu "có chứa chữ done": `not done`,
`chưa done`, `chưa xong`, `hoàn thành 90%` đều **không phải Done** → không được
đòi end date của mấy dòng đó. Ngược lại `Done`, `DONE`, `done ✅`, `đã hoàn
thành` đều **là Done** → thiếu end date là sai.

Ngoài 7 điều trên thì **không kiểm gì nữa**: không đối chiếu Re-estimate với
Actual Effort, không kiểm end date có sau start date không, không kiểm ngày có
thật (`31-02-2026` vẫn nhận vì đúng dạng). Chỉ kiểm cấu trúc.

**TUYỆT ĐỐI không nhắc ai về dạng mã task.** `004 | 18 | 01-08-2026 |
03-08-2026 | 18 | đã hoàn thành | không có` và `DWM-2222| 8 | 03-08-2026 |  | 8
| đang tiến hành |` đều **hợp lệ hoàn toàn** — không được rep kiểu *"nhắc nhẹ
mẫu chuẩn là NEX-004…"*, không "ghi mã dạng NEX-số cho gọn", không đòi đổi tiền
tố, không bắt thêm khoảng trắng quanh `|`. Đây là lỗi đã xảy ra thật: template
cũ ghi `NEX-số` nên bot tự suy ra là bắt buộc. Góp ý về format **chỉ được nói
khi dòng thật sự sai** theo đúng 7 điều kiện trên.

### Dòng nào bị đem ra chấm

Trong reply của một người, chỉ những dòng **có ý định là log task** mới bị chấm:
dòng **có ít nhất 1 dấu `|`** *và* field đầu **có chứa số**. Gọi đó là các
**dòng log**.

Mọi dòng còn lại **bỏ qua hoàn toàn**, không bao giờ là lý do báo sai format:
câu dẫn ("em báo cáo ạ", "hôm nay em làm mấy việc này"), giải thích thêm, ảnh,
emoji, và cả **dòng tiêu đề** nếu ai đó copy nguyên bảng
(`Id task | Re-estimate (h) | …` — field đầu không có số nên không phải dòng
log).

### Chấm cả cụm: một dòng sai là bị nhắc

Một người tính là **đã report** khi: có **ít nhất 1 dòng log**, **và** *tất cả*
dòng log của họ đều hợp lệ.

Chỉ cần **một** dòng log sai là vào nhóm **sai format** và bị tag nhắc sửa — dù
các dòng khác đúng hết. Đây là điểm cố ý khác với bản cũ ("có 1 dòng đúng là
thoát"): bản cũ khiến người khai 5 task, sai 4 dòng, vẫn được tính là xong —
tức là bao nhiêu công validate ngày tháng đổ sông đổ biển.

Từ đó roster chia làm 3 nhóm mỗi lần chạy Job B:

| Nhóm | Điều kiện | Xử lý |
|------|-----------|-------|
| Đã report | Có ≥1 dòng log, và **mọi** dòng log đều hợp lệ | Bỏ qua, không tag |
| Chưa report | Không reply gì trong thread | Tag ở dòng "chưa report" |
| Sai format | Có reply nhưng **không có dòng log nào**, hoặc có dòng log mà **≥1 dòng sai** | Tag ở dòng "sai format" |

Vẫn giữ nguyên luật **"Im lặng trong thread"**: thấy dòng sai lúc 10h thì
**không** được nhảy vào nhắc ngay. Gom lại, đến Job B (16:30 / 17:00) mới tag
một lần. Không có dòng sai nào thì tuyệt đối im — không xác nhận, không khen,
không thả câu "đã ghi nhận".

Ví dụ:

```
NEX-123 | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done | xong sớm   → hợp lệ
  nex-45 | 5 | 03-08-2026 |  | 2 | In progress |                → hợp lệ (chưa Done: end date + note trống vẫn ok)
4 | 16 | 28-07-2026 | 03-08-2026 | 18 | đã hoàn thành | không có → hợp lệ (Done tiếng Việt, có end date)
DWM-2222| 8 | 03-08-2026 |  | 8 | đang tiến hành |              → hợp lệ (tiền tố khác, thiếu space vẫn nhận)
100 | 4 | 03-08-2026 |  | 4h | đang làm | đổi figma | +14h      → hợp lệ (thừa field vẫn nhận)
- NEX-9 | 8 | 03-08-2026 |  | 8 | đang làm |                    → hợp lệ (gạch đầu dòng: dọn rồi mới chấm)
|NEX-9|8|03-08-2026||8|đang làm|                                → hợp lệ (dán từ Excel, bỏ dấu | đầu dòng)
NEX-9 | 8 | 03-08-2026 | - | 8 | đang làm |                     → hợp lệ (chưa Done: '-' tính như để trống)
NEX-9 | 8 | 03-08-2026 |  | 8 | hoàn thành 90% |                → hợp lệ (KHÔNG phải Done → không đòi end date)
NEX-9 | 8 | 03-08-2026 | 05-08-2026 | 8 | done ✅ | ok           → hợp lệ (Done kèm emoji, có end date)
NEX-123 | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done              → SAI (thiếu note, chưa đủ 6 dấu |)
NEX-123 | 8 | 1-8-2026 |  | 2 | In progress |                   → SAI (start date không đúng DD-MM-YYYY)
NEX-123 | 8 | 2026-08-01 |  | 2 | In progress |                 → SAI (ngày viết ngược)
NEX-123 | 8 | 01-08-2026 |  | 7.5 | Done | xong rồi             → SAI (status Done mà bỏ trống end date)
NEX-123 |  | 01-08-2026 |  | 2 | In progress |                  → SAI (Re-estimate để trống)
NEX-123 | 8 | 01-08-2026 |  |  | In progress |                  → SAI (Actual Effort để trống)
NEX-9 | 8 | 03-08-2026 |  | 8 | đã hoàn thành |                 → SAI (là Done mà bỏ trống end date)
NEX-9 | 8 | 03-08-2026 | - | 8 | Done | xong                    → SAI (Done thì end date phải là ngày thật)

em báo cáo ạ                                                    → BỎ QUA (không có dấu |)
Id task | Re-estimate (h) | start date | ...                    → BỎ QUA (dòng tiêu đề, field đầu không có số)
xong hết việc rồi nhé | 8 | 03-08-2026 |  | 8 | đang làm |       → BỎ QUA (field đầu không có số)
```

"BỎ QUA" nghĩa là **không chấm dòng đó**, chứ không phải người đó được tha: ai
chỉ có toàn dòng bị bỏ qua = **không có dòng log nào** → vẫn vào nhóm sai
format. Chấm cả cụm:

```
em báo cáo ạ                                          ← bỏ qua
NEX-1 | 8 | 03-08-2026 | 03-08-2026 | 8 | Done | xong ← hợp lệ
NEX-2 | 8 | 3-8-2026 |  | 8 | đang làm |              ← SAI (ngày)
→ người này vào nhóm SAI FORMAT (1 dòng sai là đủ), dù dòng đầu đã đúng.
```

## Format tin nhắc chuẩn (BẮT BUỘC, không được diễn giải lại)

Mọi tin nhắc report — dù do cron tự chạy, hay do ai đó nhắn tay bảo bot nhắc
(vd "nhắc report đi", "nhắc lại mọi người report", "xem ai chưa report") —
**PHẢI dùng đúng nguyên văn template dưới đây**, chỉ được thay
`<mention_list>`. KHÔNG được tự thêm/bớt câu chữ, không đổi icon, không viết
lại theo văn phong khác mỗi lần, không thêm bullet "Hôm qua làm gì / Hôm nay
làm gì" tự chế.

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

**Tin mở thread (Job A — đăng ra kênh):** dùng `<!here>`, **không** liệt kê
mention từng người — đầu giờ chưa ai report nên tag cả roster chỉ tổ ồn:

```
<!here> ⏰ Đến giờ report task rồi, mọi người report hôm nay giúp mình nhé!

Report theo mẫu sau (copy và điền vào):
Id task | Re-estimate (h) | start date | end date | Actual Effort (h) | status | note

• Ngày viết dạng DD-MM-YYYY (vd 03-08-2026)
• Bắt buộc: Id task, Re-estimate, start date, Actual Effort, status
• end date chỉ bắt buộc khi status = Done — chưa xong thì để trống nhưng vẫn giữ đủ dấu |
• note để trống cũng được

VD: NEX-xxx | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done | xong sớm
VD: DWM-yyy | 5 | 03-08-2026 |  | 2 | In progress |
```

Câu `⏰ Đến giờ report task rồi` là **mốc nhận diện** Job B dùng để tìm lại
thread — đổi câu này thì phải đổi cả bước 2 của Job B.

**Tin nhắc lại (Job B — reply trong thread, không đăng ra kênh):**

```
⏰ Nhắc lại: <mention_chua_report> chưa report hôm nay nhé!
⚠️ <mention_sai_format> đã report nhưng chưa đúng mẫu, sửa lại giúp mình nhé!

Report theo mẫu sau (copy và điền vào):
Id task | Re-estimate (h) | start date | end date | Actual Effort (h) | status | note

• Ngày viết dạng DD-MM-YYYY (vd 03-08-2026)
• Bắt buộc: Id task, Re-estimate, start date, Actual Effort, status
• end date chỉ bắt buộc khi status = Done — chưa xong thì để trống nhưng vẫn giữ đủ dấu |
• note để trống cũng được

VD: NEX-xxx | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done | xong sớm
VD: DWM-yyy | 5 | 03-08-2026 |  | 2 | In progress |
```

- Nhóm nào rỗng thì **bỏ hẳn dòng đó**, không in ra dòng cụt không có mention.
  Cả 2 nhóm rỗng → không reply gì cả.
- Giữ nguyên phần "Report theo mẫu sau" kể cả khi chỉ còn 1 dòng nhắc.

- `<mention_chua_report>` / `<mention_sai_format>` (chỉ có ở tin nhắc lại của
  Job B) = `<@U03H0QB426A> <@U03Q60UCBJS> ...` — user id **lấy từ roster**,
  phân nhóm theo bảng ở mục "Luật kiểm format", cách nhau bởi dấu cách. Mention
  bằng `<@id>` chứ không gõ tên, để Slack thật sự ping đúng người.
- Không lấy được roster → **không nhắc lại** (xem mục "Roster"). Không dùng
  `<!channel>`/`<!here>` thay cho danh sách mention ở Job B — nhắc lại mà ping
  cả kênh là làm phiền người đã report.
- Không liệt kê dòng sai của ai ra thread, không trích lại nội dung họ đã gõ —
  chỉ tag và trỏ về mẫu.
- Nếu người dùng nhắn tay yêu cầu nhắc lại (không phải qua cron), vẫn áp dụng
  đúng template này, không tự sáng tác lời nhắc mới mỗi lần được hỏi.
- Bot chỉ soi **cấu trúc** dòng theo "Luật kiểm format" để chia nhóm — không
  đọc hiểu nội dung từng field, không đối chiếu giờ, không phán công việc.

## Cron (setup 1 lần, dùng cron expression thật — không diễn giải giờ chung
chung để tránh trôi giờ)

**Không gán `--model` cho 2 job dưới đây.** Để cron dùng model mặc định của
workspace/agent. Pin cứng một model id vào skill sẽ vỡ ngay khi workspace đổi
`agents.defaults.models` allowlist — job fail với `cron payload.model <x>
rejected by agents.defaults.models allowlist`. Nếu một job cũ đã lỡ pin model,
gỡ bằng `openclaw cron edit <id> --clear-model`.

**Job A — nhắc (`REMINDER_TIME`, mặc định 09:00 → `0 9 * * *`; đổi field
giờ/phút nếu khác, vd 09:30 → `30 9 * * *`):**

```bash
openclaw cron create "0 9 * * *" \
  "Việc A skill reminder-followup: đăng tin nhắc report, lưu message ts vào state." \
  --name reminder-followup-0900 --tz "$REMINDER_TIMEZONE" \
  --session isolated --announce \
  --channel slack --to "channel:$SLACK_REPORT_CHANNEL_ID"
```
`--announce` bắt buộc — thiếu nó, cron chạy xong vẫn không tự đẩy kết quả ra
Slack (`delivered: false` dù `status: ok`).

Chạy: xuất ra final message **đúng nguyên văn template "Tin mở thread"** ở mục
trên (không tự diễn giải lại, không thêm lời dẫn) — `--announce` lo việc đăng
vào kênh, nên job này không cần gọi tool Slack và không cần roster.

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
4. Đọc roster của kênh, trừ chính bot → chia 3 nhóm theo bảng ở "Luật kiểm
   format". Nhóm "chưa report" và "sai format" đều rỗng → dừng, không reply gì
   cả. Roster lỗi → dừng, log lỗi.
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
ASKED | chua co roster
SKIP | <lý do: qua gio cutoff / khong tim thay thread hom nay / tat ca da report
        / chua co roster, da hoi roi>
ERROR | <mô tả ngắn>
```

Dòng này **không** ra Slack vì Job B để `delivery: none`.

## Chưa có roster → hỏi trong thread

Kênh chưa khai roster mà cứ im lặng log `ERROR` là hỏng: `delivery: none` nên
không ai đọc được dòng đó, trong khi Job A vẫn đăng tin nhắc mỗi sáng → nhìn
bên ngoài y như đang chạy tốt, thực ra chả nhắc được ai suốt nhiều ngày.

Nên khi **chưa có roster**, Job B reply đúng 1 lần vào thread hôm nay, **không
tag ai** (chưa biết ai mà tag), không đăng tin mới ra kênh:

```
📋 Mình chưa có danh sách người phải report cho kênh này, nên hôm nay chưa nhắc được ai.

Nhờ mọi người tag mình kèm danh sách, mỗi dòng 1 người:
<user_id> | <tên>

(Lấy user ID: Slack → profile người đó → More → Copy member ID)
```

Câu **"tag mình kèm danh sách"** là bắt buộc, không được bỏ: luật "Im lặng trong
thread" khiến bot bỏ qua mọi tin không tag nó — ai đó dán danh sách trần vào
thread thì bot **không hề thấy**. Phải nói rõ là phải tag.

**Chống hỏi lặp:** trước khi đăng, soi lại reply trong thread (kể cả tin của
chính bot) xem đã có tin nào chứa `chưa có danh sách người phải report` chưa. Có
rồi → `SKIP | chua co roster, da hoi roi`. Không có bước này thì 16:30 và 17:00
hỏi 2 lần y hệt nhau mỗi ngày.

Guard ngày vẫn giữ nguyên: không tìm thấy thread hôm nay thì dừng ở bước 2, câu
hỏi này **không** phải cái cớ để đăng tin mới ra kênh.

Có người tag kèm danh sách → xử lý theo "Setup kênh mới → phải hỏi danh sách
nhân viên" ở trên: ghi file roster, báo lại đã ghi bao nhiêu người. Lượt cron
kế tiếp là nhắc được ngay, không cần restart Gateway.

## Tổng hợp theo yêu cầu (không qua cron)

Hai mốc 16:30 / 17:00 chỉ là lịch **tự động**. Khi có người **tag bot** và bảo
*"xem ai chưa report"*, *"tổng hợp đi"*, *"ai còn thiếu"*… thì **chạy ngay**,
bất kể đang là mấy giờ:

- **Bỏ qua `FOLLOWUP_CUTOFF_TIME` và bỏ qua lịch cron.** Yêu cầu tay lúc 09:15
  hay 21:00 đều phải chạy. Cutoff chỉ tồn tại để chặn cron, không phải để chặn
  người.
- Làm đúng **bước 2 → 4** của Job B (tìm thread hôm nay, đọc reply, đối chiếu
  roster, chia 3 nhóm). Guard ngày vẫn giữ nguyên: không có thread hôm nay thì
  báo lại là chưa có tin nhắc, **không** tự đăng tin nhắc mới, **không** đụng
  thread hôm qua.
- Kết quả trả về:
  - Người hỏi chỉ muốn **biết** ("ai chưa report?") → trả lời ngay chỗ họ hỏi,
    liệt kê tên, **không** reply vào thread và không tag ai. Xem tình hình
    không phải là đi nhắc.
  - Người hỏi bảo **nhắc** ("nhắc mấy người đó đi") → reply vào thread hôm nay
    theo đúng nguyên văn template "Tin nhắc lại", như Job B.
- Cả 2 nhóm rỗng → nói thẳng "cả roster đã report đủ", không reply vào thread.

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
| Không đọc được roster của kênh (thiếu file/rỗng/parse lỗi) | Dừng job, log lỗi, **không** nhắc ai — không fallback sang thành viên kênh, không dùng `<!channel>` |
| Không đọc được lịch sử kênh/thread | Dừng job, log lỗi, không reply mù, không crash job |
| Job B không tìm thấy thread tin nhắc hôm nay | Dừng, không tự đăng tin nhắc mới ra kênh |
| Roster có user id đã rời workspace | Vẫn mention theo id (Slack tự hiển thị inactive) — sửa bằng cách xoá khỏi roster |
| Không chắc một dòng có hợp lệ hay không | Coi là **hợp lệ** (không nhắc) — thà bỏ sót còn hơn báo sai format cho người đã report tử tế |
| Có người thắc mắc "tôi report rồi mà vẫn bị nhắc" | Trả lời là dòng report chưa đủ 7 field `Id task \| Re-estimate \| start date \| end date \| Actual Effort \| status \| note`, hoặc ngày chưa đúng `DD-MM-YYYY`, hoặc status Done mà thiếu end date — và nói rõ **chỉ cần 1 dòng sai là bị nhắc**, dù các dòng khác đã đúng. Chỉ nói lại mẫu, không phán nội dung công việc |
