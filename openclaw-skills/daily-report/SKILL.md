---
name: daily-report
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
lỗi → **dừng job, log lỗi, không nhắc gì cả** — không fallback sang member kênh,
không tự đoán danh sách, không dùng `<!channel>` để nhắc bừa cả kênh.

### Setup kênh mới → phải hỏi danh sách nhân viên

Khi được yêu cầu bật daily-report cho một kênh **chưa có** file roster (hoặc
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

Một **dòng hợp lệ** phải thoả cả 2:

1. **Đầu dòng phải là một mã task có chứa số** (cho phép khoảng trắng đầu dòng).
   **Không có quy định nào về dạng mã** — tiền tố chữ là tuỳ ý và không phân biệt
   hoa thường: `4`, `NEX-100`, `DWM-2222`, `abc 12` đều hợp lệ như nhau. Chỉ cần
   field đầu tiên trông như một mã task và có chữ số trong đó.
2. Có **ít nhất 3 dấu `|`** → từ 4 field trở lên:
   `<mã task> | <trạng thái> | <giờ> | <ghi chú>`. Thừa field vẫn hợp lệ, vd
   `1 | chưa xong | 8h | khách đổi figma | cần thêm 4h` — nhận.

Nội dung từng field **không kiểm**: trạng thái viết gì cũng được, giờ ghi `3h`
hay `3 tiếng` đều nhận, ghi chú để trống cũng nhận. Chỉ kiểm cấu trúc.

**TUYỆT ĐỐI không nhắc ai về dạng mã task.** `004 | đã hoàn thành | 18 | không
có` và `DWM-2222| đang tiến hành | 8 | không có` đều **hợp lệ hoàn toàn** —
không được rep kiểu *"nhắc nhẹ mẫu chuẩn là NEX-004…"*, không "ghi mã dạng
NEX-số cho gọn", không đòi đổi tiền tố, không bắt thêm khoảng trắng quanh `|`.
Đây là lỗi đã xảy ra thật: template cũ ghi `NEX-số` nên bot tự suy ra là bắt
buộc. Góp ý về format **chỉ được nói khi dòng thật sự sai** theo đúng 2 điều
kiện trên (đầu dòng không phải mã task, hoặc chưa đủ 4 field).

Một người tính là **đã report** khi có **ít nhất 1 dòng hợp lệ** trong các
reply của họ. Các dòng thừa xung quanh ("em báo cáo ạ", giải thích thêm, ảnh,
emoji) không làm hỏng — có 1 dòng đúng là đủ.

Từ đó roster chia làm 3 nhóm mỗi lần chạy Job B:

| Nhóm | Điều kiện | Xử lý |
|------|-----------|-------|
| Đã report | Có ≥1 dòng hợp lệ | Bỏ qua, không tag |
| Chưa report | Không reply gì trong thread | Tag ở dòng "chưa report" |
| Sai format | Có reply nhưng không dòng nào hợp lệ | Tag ở dòng "sai format" |

Ví dụ:

```
NEX-123 | done | 3h | fix login                    → hợp lệ
  nex-45 | đang làm | 2h |                         → hợp lệ (thường/thiếu ghi chú vẫn ok)
4 | đã hoàn thành | 18 | không có                  → hợp lệ (số trần, không cần tiền tố)
DWM-2222| đang tiến hành | 8 | không có            → hợp lệ (tiền tố khác, thiếu space vẫn nhận)
100 | chưa xong | 4h | đổi figma | cần thêm 14h    → hợp lệ (thừa field vẫn nhận)
NEX-123 | done | 3h                                → SAI (thiếu field thứ 4)
Hôm nay em làm xong NEX-123 rồi ạ                  → SAI (không đủ 4 field)
xong hết việc rồi nhé | ok | 8h | ...              → SAI (đầu dòng không phải mã task)
```

## Format tin nhắc chuẩn (BẮT BUỘC, không được diễn giải lại)

Mọi tin nhắc report — dù do cron tự chạy, hay do ai đó nhắn tay bảo bot nhắc
(vd "nhắc report đi", "nhắc lại mọi người report", "xem ai chưa report") —
**PHẢI dùng đúng nguyên văn template dưới đây**, chỉ được thay
`<mention_list>`. KHÔNG được tự thêm/bớt câu chữ, không đổi icon, không viết
lại theo văn phong khác mỗi lần, không thêm bullet "Hôm qua làm gì / Hôm nay
làm gì" tự chế.

**Tin mở thread (Job A — đăng ra kênh):** dùng `<!here>`, **không** liệt kê
mention từng người — đầu giờ chưa ai report nên tag cả roster chỉ tổ ồn:

```
<!here> ⏰ Đến giờ report task rồi, mọi người report hôm nay giúp mình nhé!

Report theo mẫu sau (copy và điền vào):
mã task | trạng thái | giờ đã làm | ghi chú
(Chưa xong thì thêm: · cần thêm N giờ)
```

Câu `⏰ Đến giờ report task rồi` là **mốc nhận diện** Job B dùng để tìm lại
thread — đổi câu này thì phải đổi cả bước 2 của Job B.

**Tin nhắc lại (Job B — reply trong thread, không đăng ra kênh):**

```
⏰ Nhắc lại: <mention_chua_report> chưa report hôm nay nhé!
⚠️ <mention_sai_format> đã report nhưng chưa đúng mẫu, sửa lại giúp mình nhé!

Report theo mẫu sau (copy và điền vào):
mã task | trạng thái | giờ đã làm | ghi chú
(Chưa xong thì thêm: · cần thêm N giờ)
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
- Đây chỉ là **gợi ý format** cho người report tự điền — bot không đọc/parse
  lại nội dung reply, chỉ cần biết **có** reply hay chưa.

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
openclaw cron create "0 11 * * *" \
  "Việc A skill daily-report: đăng tin nhắc report, lưu message ts vào state." \
  --name daily-report-reminder --tz "$REMINDER_TIMEZONE" \
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
`daily-report-followup-1630` và `daily-report-followup-1700`. Sửa prompt thì
**phải sửa cả 2**, lệch nhau là hai lượt nhắc hành xử khác nhau.

**Đừng dùng `--every`.** Mốc của `--every` bị neo lại theo thời điểm sửa job, nên
mỗi lần `cron edit` là giờ chạy trôi đi (13:47, 15:47…) và không đoán trước được;
ngoài ra nó chạy cả ban đêm chỉ để `SKIP`, tốn token vô ích.

```bash
for slot in "1630:${FOLLOWUP_CRON_1:-30 16 * * *}" "1700:${FOLLOWUP_CRON_2:-0 17 * * *}"; do
  openclaw cron create --cron "${slot#*:}" \
    --message "Việc B skill daily-report: tag người chưa report / sai format vào thread tin nhắc hôm nay." \
    --name "daily-report-followup-${slot%%:*}" --tz "$REMINDER_TIMEZONE" \
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
3. Đọc reply trong thread đó. Với mỗi user id đã reply, xét toàn bộ dòng trong
   các reply của họ theo "Luật kiểm format" → có ≥1 dòng hợp lệ = **đã
   report**, có reply nhưng không dòng nào hợp lệ = **sai format**.
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
SKIP | <lý do: qua gio cutoff / khong tim thay thread hom nay / tat ca da report>
ERROR | <mô tả ngắn>
```

Dòng này **không** ra Slack vì Job B để `delivery: none`.

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
| Có người thắc mắc "tôi report rồi mà vẫn bị nhắc" | Trả lời là do dòng report chưa đủ 4 field `mã task \| trạng thái \| giờ \| ghi chú`, chỉ nói lại mẫu — không phán nội dung công việc |
