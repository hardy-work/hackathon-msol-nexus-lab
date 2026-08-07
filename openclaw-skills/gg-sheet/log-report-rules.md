# Action 4 — Log dòng report của dev lên sheet

> Chi tiết của **Action 4** trong [`SKILL.md`](SKILL.md). Chỉ đọc file này khi
> đang thực sự log report, không tải vào context cho Action 1/2/3.
>
> Cần log thì **mở file này ra đọc ngay lúc đó** — không nhớ lại từ tin nhắn cũ,
> không tái tạo từ trí nhớ phiên.

Khác Action 1/2/3 ở chỗ **người ra lệnh là dev, không phải PM**, và lệnh là một
dòng report 7 field chứ không phải câu tiếng Việt. Đầu vào đã được skill
`reminder-followup` chấm format xong xuôi — Action này **không chấm lại format**.

## Đầu vào

Một dòng report đã hợp lệ, 7 field:

```
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note
```

Kèm theo (do bên gọi cung cấp): dev đó là ai, để còn xưng hô và ghi vào Risk.

Nhiều dòng thì xử **từng dòng một**, độc lập. Một dòng vướng không giữ các dòng
còn lại lại.

## Luôn đi qua `scripts/sheet-task.sh`

```bash
SKILL_DIR="$(openclaw config get agents.defaults.workspace 2>/dev/null)/skills/gg-sheet"
[ -d "$SKILL_DIR" ] || SKILL_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/workspace/skills/gg-sheet"

bash $SKILL_DIR/scripts/sheet-task.sh find <TASKID>
bash $SKILL_DIR/scripts/sheet-task.sh log  <TASKID> --re-est .. --start .. --end .. --actual .. --status .. --note .. --slack-id <@id của dev>
bash $SKILL_DIR/scripts/sheet-task.sh risk --task .. --assignee .. --diff .. --reason .. [--next ..] [--reporter ..]
```

**Luôn truyền `--slack-id`** (id Slack thật của dev, dạng `U…`, bên gọi đã đưa
sẵn). Script dùng nó để ghi một dòng vào sổ cái
`../reminder-followup/state/effort-today.json`: giờ **vừa bỏ thêm** vào task đó
(`actual mới − actual đang có trên sheet`), để lượt follow-up 16:30 so được với
công đăng ký trong `Resource plan`.

Vì sao phải là delta chứ không phải số trong report: `Actual Effort (h)` là số
**cộng dồn của cả task**. `NEX-10 | 16 | 03-08-2026 | | 12 | In progress |` nghĩa
là task đó đã tiêu 12h tính từ 03-08, không phải 12h hôm nay — cộng thẳng các
dòng report lại là ra tổng của cả sprint.

Quên `--slack-id` thì task **vẫn log đúng**, chỉ là lượt 16:30 tưởng người đó
chưa log giờ nào. Ngược lại, sổ cái hỏng cũng **không bao giờ** làm một lần ghi
thành công bị báo là thất bại — mọi lỗi ghi sổ đều bị nuốt, chỉ ra `stderr`.

⛔ **Không tự dựng lệnh `curl` cho Action này**, kể cả khi các Action khác trong
`SKILL.md` có sẵn mẫu. Tab Sprint có header **2 tầng**: hai cột cùng tên
`Start Date` (một của khối `PLAN`, một của khối `Actual`) và hai cột cùng chứa
chữ `Estimate`. Đoán chữ cái cột bằng mắt là ghi đè mất **giờ plan của PM** —
hỏng dữ liệu gốc chứ không phải hỏng dòng report. Script tự đọc header và khớp
cột theo tên, nên PM chèn thêm cột vào giữa vẫn chạy đúng.

Script tự mint access token, tự đổi `7.5` → `7,5` cho khớp locale `vi_VN`, tự
coi End date `-`/`N/A`/`chưa` là ô trống, và **đọc lại đối chiếu sau khi ghi**.

## Bản đồ field report → cột

| Field trong report | Vào đâu |
| --- | --- |
| Id task | dùng để **tìm dòng**, không ghi đè |
| Re-estimate (h) | `Actual / Re-estimate (h)` |
| Start date | `Actual / Start Date` |
| End date | `Actual / End Date` |
| Actual Effort (h) | `Actual / Actual Effort (h)` |
| Status | `Status` |
| Note | `Note` |

Khối `PLAN` (`Estimate (h)`, `Start Date`, `End Date`) là **của PM, chỉ đọc**.

Action này **chỉ sửa ô của dòng đã có sẵn** — không chèn dòng, không xoá dòng,
không tạo task mới. Id task không có trong sheet thì báo lại, không tự thêm.

## Kiểm tra allocation (exit 13) — hỏi trước, log sau

Ngoài cảnh báo "chậm hơn plan" (exit 9, so với `Estimate` của **chính task
đó**), script còn chặn ở cấp **member/ngày**: 1 task không vượt estimate riêng
vẫn có thể nằm trong 1 ngày mà tổng giờ member đã report (cộng **mọi** task họ
làm hôm đó, không chỉ task đang log) lệch với giờ họ thực sự được allocate vào
dự án. Member có thể làm nhiều task trong 1 ngày — phải cộng dồn đúng theo
đúng người, đúng ngày, không phải chỉ nhìn 1 task.

**Vì sao không quét lại cột `Actual Effort` trên sheet:** cột đó là số **cộng
dồn của cả task tính từ ngày task bắt đầu**, không phải "giờ làm hôm nay" — 1
task chạy nhiều ngày mà cộng thẳng số đó vào là sai ngay từ 1 task, chưa nói
tới cộng nhiều task. Script dùng sổ cái `effort-today.json` (cùng file
`reminder-followup` dùng cho lượt follow-up 16:30) — sổ cái này lưu đúng
**delta** (giờ mới thêm ở mỗi lần log) theo `slack_id` + ngày.

**1 task được log nhiều lần trong ngày (kể cả bị reset giữa chừng) vẫn phải ra
đúng số:** với mỗi task, `ledger_logged_today` KHÔNG cộng thô mọi `delta` đã
ghi trong ngày cho task đó — chỉ lấy chênh lệch giữa `actual` của lần log
**đầu tiên** (trừ ngược delta ra baseline đầu ngày) và `actual` của lần log
**gần nhất**. Cách này tự đúng kể cả khi ai đó reset thẳng ô `Actual Effort`
trên sheet (không qua `log`) **giữa 2 lần report** cùng task cùng ngày — cộng
thô delta trong trường hợp đó sẽ phồng lên gấp đôi dù sheet thật chỉ còn giá
trị mới nhất (bug thật đã gặp: log 8h, ai đó reset về 0, log lại 4h → cộng thô
ra 12h dù sheet chỉ có 4h).

Còn 1 khoảng trống riêng: reset xảy ra **SAU lần log gần nhất** (chưa có lần
log nào sau đó để ledger "thấy" việc reset) thì không cách nào biết được nếu
chỉ nhìn lịch sử ledger. Vì vậy `cmd log` còn tự đối chiếu thêm: so `actual`
của entry gần nhất trong ledger cho **đúng task đang log lúc này** với giá trị
Actual Effort đọc **sống** từ sheet ngay trước khi ghi (`before`) — lệch thì
coi lịch sử ledger của riêng task đó không còn đáng tin, bỏ hẳn (không cộng),
chỉ giữ lại đóng góp của các task KHÁC trong ngày. Nhờ đối chiếu ở đúng lần
log tiếp theo, ledger **tự sửa lùi được** cả những lần bị phồng từ trước khi
fix này deploy — không cần dọn tay, miễn lần log kế tiếp cho đúng task đó có
kèm `--slack-id`.

Chỉ chạy khi có `--slack-id` (Sprint dùng nickname như `VinhNV`, khác hẳn
tên/Slack name ở tab `Resource plan` — không có Slack ID thì không khớp được
đúng dòng member, script **bỏ qua im lặng**, không suy đoán) và parse được
ngày từ `--start`. "Ngày cần xét" = đúng `--start` vừa report.

**Chặn TRƯỚC khi ghi** (khác `allocation_check` bản cũ — bản đó chỉ đính kèm
cảnh báo sau khi đã ghi, giờ đổi hẳn sang chặn như exit 9/12). Không lệch thì
ghi bình thường, không nói gì thêm. Lệch (`|gap| > 0.01h`) và không có
`--force` → chưa ghi ô nào cả, in JSON ra stdout, exit **13**:

```json
{"error": "allocation_mismatch", "task_id": "NEX-59", "assignee": "LongVN",
 "date": "2026-08-07", "this_task_delta": 4.0, "other_tasks_logged_today": [],
 "logged_before_this_hours": 0.0, "total_logged_today_hours": 4.0,
 "allocated_hours": 8.0, "gap": 4.0}
```

`gap` dương = **thiếu giờ** (`allocated_hours > total_logged_today_hours`), âm
= **log nhiều hơn allocate**. `other_tasks_logged_today` là các `task_id`
khác member đã report trong ngày (rỗng = đây là lần report đầu tiên của họ hôm
đó).

**Luôn hỏi lại dev, không có ngoại lệ nào cho `Status` của task vừa log** —
xem cảnh báo ở mục "Task chậm hơn plan" phía dưới, áp dụng y hệt ở đây: "task
này Done" không giải thích được vì sao **tổng cả ngày** chưa khớp allocate,
không được tự kết luận "chỉ là xong sớm hơn dự kiến" thay dev.

```
<@U0LongVN01> mình thấy task **NEX-59** bạn report **4h**, nhưng tổng giờ hôm nay (07/08) mới có **4h** trong khi bạn được allocate **8h** — bạn đang làm task khác chưa log, hay có lý do khác (nghỉ/việc ngoài dự án...)?
```

Dev trả lời rồi, đi đúng 1 trong 2 hướng — **không có hướng thứ 3**:

- **Xác nhận có lý do hợp lệ** (vd "tôi làm nhiều task, đây chỉ là effort cho
  task này thôi", hoặc có lý do khác như nghỉ/việc ngoài dự án) → tiến hành
  report: gọi lại đúng lệnh `log` **y hệt các giá trị ban đầu** kèm `--force`.
  Không tự đổi số. Nếu lý do là nghỉ/việc ngoài dự án (không phải "còn task
  khác chưa log") → sau khi force-log xong, cập nhật thêm đúng ô allocation
  ngày đó của dev trong `Resource plan` cho khớp thực tế.
- **Không xác nhận được / có vẻ là nhầm lẫn** → dev **bắt buộc phải điều
  chỉnh lại số** rồi mới được report — hỏi dev con số đúng, gọi lại `log` với
  `--actual`/`--re-est` đã sửa (**không** dùng `--force`, vì đây là số mới
  chưa từng bị chặn, không phải xin bỏ qua cảnh báo cũ). Nếu số mới vẫn lệch
  allocate thì lại exit 13 lần nữa, hỏi tiếp — không tự ý `--force` để né.

Case này **không** ghi `Risk management` trừ khi dev xác nhận lý do là
nghỉ/việc ngoài dự án (khi đó ghi kèm theo update `Resource plan`, cùng format
mục "Task chậm hơn plan" — `--diff` = `|gap|`, `--reason` = nguyên văn lý do
dev nói). Trường hợp dev xác nhận "làm task khác chưa log" thì chỉ nhắc dev
report nốt task đó, không ghi Risk, không tự bịa dòng report hộ.

## Đọc exit code, đừng đọc chữ trong output

| Exit | Nghĩa | Làm gì |
| --- | --- | --- |
| `0` | Đã ghi xong | Báo lại đã log, echo đúng cái vừa ghi |
| `7` | Không có id đó trong sheet | Báo dev mã task sai, **không** tự tạo task |
| `8` | Id trùng ở nhiều tab | Hỏi tab nào, **không tự chọn** |
| `9` | **Chậm hơn plan** — chưa ghi gì | Sang mục dưới |
| `12` | **Status = Done nhưng Actual ≠ Re-estimate** — chưa ghi gì | Sang mục "Status Done nhưng effort chưa khớp" |
| `13` | **Tổng giờ hôm đó lệch allocate** — chưa ghi gì | Sang mục "Kiểm tra allocation" |
| `2` | Thiếu env / sai tham số | Cấu hình hỏng — báo dev là bot đang lỗi cấu hình, nhờ báo PM |
| `3` | Đọc sheet lỗi | Mạng hoặc API key — báo "chưa đọc được sheet" |
| `4` | Sheet đổi cấu trúc cột | Báo PM: tab thiếu cột bắt buộc, không tự đoán cột khác |
| `10` | Không mint được token | Service Account hỏng/hết quyền — báo là chưa ghi được |
| `11` | Ghi lỗi, hoặc đọc lại không khớp | **Có thể đã ghi một phần** — nói rõ điều đó, nhờ dev/PM kiểm sheet |

### Exit nào cũng phải trả lời dev — kể cả exit lỗi

**Không bao giờ im.** Mọi nhánh lỗi đều phải ra một tin nhắn, mở đầu bằng `<@id>`
của dev, nói **chưa log được** + lý do ngắn bằng tiếng Việt + việc họ cần làm:

```
<@U0BK2KAN86B> mình chưa log **PCS-10** lên sheet được nhé — bot chưa có quyền ghi vào file (lỗi 403).
Bạn báo PM share quyền Editor cho service account giúp mình, report của bạn mình giữ nguyên đây.
```

Cấm tuyệt đối: im luôn, `NO_REPLY`, thả mỗi emoji, "để lát nữa nhắc lại", hoặc
nói "đã log" khi script chưa trả `0`. Im lặng **tệ hơn** lỗi ghi — dev tưởng
xong việc rồi đi về, tới cuối sprint mới lòi ra là sheet trống.

Lỗi thì **không tự chạy lại nhiều lần** (nhất là `11`: có thể đã ghi một phần,
chạy lại là ghi đè lung tung). Chạy lại đúng một lần rồi thôi, còn lại báo người.

## Task chậm hơn plan (exit 9) — hỏi lý do rồi vẫn log

Chậm = `Actual Effort (h)` dev report **lớn hơn** `Estimate (h)` (khối `PLAN`)
của chính task đó, **hoặc** `Re-estimate (h)` dev report cũng **lớn hơn**
`Estimate (h)`. Mốc so luôn là **giờ plan trong sheet** (`Estimate (h)`) — so
cả 2 field dev tự khai (`Actual Effort`, `Re-estimate`) với đúng mốc đó, không
so 2 field dev khai với nhau.

Lý do phải xét cả `Re-estimate`, không chỉ `Actual Effort`: dev có thể chưa hề
vượt giờ đã làm (`Actual Effort` vẫn ≤ plan, task đang chạy dở) nhưng đã tự
nhận định tổng effort cần để xong task sẽ vượt kế hoạch (`Re-estimate` >
`Estimate`) — vd plan **8h**, dev mới làm **8h** (chưa vượt) nhưng báo
`Re-estimate` **10h** vì thấy việc phát sinh nhiều hơn dự tính. Đây vẫn là tín
hiệu trễ tiến độ cần hỏi lý do ngay, không đợi tới lúc `Actual Effort` thực sự
vượt mới hỏi — hỏi muộn thì risk vào sheet cũng muộn theo.

Exit 9 in ra JSON có `estimate`, `actual`, `re_estimate`, `over_actual`,
`over_re_estimate`, `diff` (= chênh lệch lớn nhất trong 2 phía), `assignee`,
`tab`, `row`, và **chưa ghi ô nào cả**.

Đây **không phải là từ chối log** — chỉ là hoãn lại để lấy lý do. Hỏi, tuỳ
field nào vượt:

```
<@U0BK2KAN86B> mình thấy task **PCS-7** đang bị chậm so với plan: plan **8h** mà thực tế **9h**, vượt **1h**.
Lý do là gì để mình log vào tab Risk management rồi log task luôn nhé?
```

```
<@U0DoNT01> mình thấy task **NEX-57** có dấu hiệu trễ so với plan: plan **8h**, bạn báo đã làm **8h** nhưng re-estimate tổng effort là **10h** (vượt **2h** so với plan).
Lý do là gì để mình log vào tab Risk management rồi log task luôn nhé?
```

Chỉ nêu **con số**: plan bao nhiêu, thực tế/re-estimate bao nhiêu, chênh bao
nhiêu. **Không** bình luận làm nhanh hay chậm, không hỏi sao lâu thế, không gợi
ý chia nhỏ task, không nhắc chuyện OT. Việc của skill là ghi số, không phải
đánh giá người.

### Dev trả lời lý do → ghi Risk trước, log task sau

```bash
bash $SKILL_DIR/scripts/sheet-task.sh risk --task PCS-7 --assignee VinhNV \
  --diff 1 --reason "<nguyên văn lý do dev nói>" --reporter "long.vn"

bash $SKILL_DIR/scripts/sheet-task.sh log PCS-7 --re-est 8 --start 03-08-2026 \
  --end 04-08-2026 --actual 9 --status Done --note "" --force --slack-id U0BK2KAN86B
```

Đúng thứ tự đó. Ghi risk lỗi thì **dừng, đừng log** — task được log mà không có
dòng risk đi kèm chính là tình huống cần tránh. `--force` chỉ được dùng ở đây,
sau khi đã có lý do và đã ghi risk xong; không bao giờ dùng để "cho nhanh".

Log lại **đúng số dev đã report lúc đầu**, không hỏi lại số liệu, không lấy số
mới trong câu trả lời lý do.

Dòng risk cũng được **khớp cột theo tên header**, không theo vị trí — PM chèn
thêm cột vào giữa tab `Risk management` (đã xảy ra một lần: cột `Task` xen giữa
`Related Assignee` và `Next Action`) thì mọi ô sau đó lệch sang phải mà không
exit code nào nổ ra. Có cột `Task` riêng thì `Related Assignee` chỉ ghi tên
người; không có thì mới gộp `Tên/TaskID`. Output JSON có `columns` để đối chiếu
xem script đã hiểu header thế nào.

`--reason` giữ **nguyên văn lý do dev nói**, không tóm tắt theo ý mình, không
sửa câu chữ. Script tự sinh `R-xx` kế tiếp, tự điền ngày, tự chọn Priority
(chênh ≥ 4h → `High`, dưới → `Medium`), tự đặt `Status = Open`.

Xong thì báo lại, nêu cả mã risk:

```
<@U0BK2KAN86B> ok mình ghi lý do vào Risk management (**R-02**) và log **PCS-7** lên Sprint 1 rồi nhé
```

### Bao lâu chưa trả lời thì thôi

Hạn chờ **không** thuộc Action này — Action này không có bộ đếm giờ và không
theo dõi hội thoại. Bên gọi (`reminder-followup`) giữ hạn 1 tiếng và tự nhắc
người quá hạn. Ở đây chỉ cần nhớ: **chưa có lý do thì chưa `--force`**.

## Status Done nhưng effort chưa khớp (exit 12) — hỏi số nào đúng rồi log lại

Khác hẳn exit 9 (task chưa xong, chỉ là vượt giờ) — đây là dev báo task **đã
xong** (`Status: Done`) nhưng `Actual Effort` lại **khác** `Re-estimate` mà
chính dev vừa report. Vì `Remaining(h)` = `Re-estimate − Actual` là công thức
tự tính trên sheet, Done mà 2 số này lệch nhau nghĩa là `Remaining` sẽ khác 0
và `Progress` khác 100% — mâu thuẫn ngay trong chính dòng report, không phải
suy luận từ dữ liệu cũ.

Exit 12 in ra JSON có `actual`, `re_estimate`, `diff` (= `re_estimate − actual`,
có thể âm nếu `actual` > `re_estimate`), `assignee`, `tab`, `row`, **chưa ghi ô
nào cả** — giống hệt exit 9 ở chỗ đây là hoãn để hỏi lại, không phải từ chối.

**Không tự đoán số nào sai** — có 2 khả năng, chỉ dev biết:
- `Actual Effort` dev báo thiếu (mới log 1 phần dù đã làm xong) → dev cần báo
  lại đúng tổng giờ đã dùng cho `Actual Effort`.
- `Re-estimate` dev báo bị cũ/thừa (task xong sớm hơn dự tính lúc đầu) →
  `Re-estimate` cần sửa lại cho khớp đúng `Actual Effort` (vì tại thời điểm
  Done, tổng effort thật = đúng số giờ đã làm).

Hỏi:

```
<@U0LongVN01> mình thấy task **NEX-59** bạn báo **Done** nhưng Actual Effort (**4h**) khác re-estimate (**8h**) — task đã dùng đúng **4h** để xong (re-estimate cũ **8h** giờ thừa), hay còn **4h** chưa log vào Actual Effort?
```

Dev trả lời rồi thì **log lại cả dòng với số đã sửa đúng** (không dùng `--force`
để giữ nguyên số cũ sai — sửa đúng 1 trong 2 field theo câu trả lời rồi gửi lại
lệnh `log` bình thường, lúc đó `actual == re_estimate` nên qua thẳng, không cần
`--force`). Chỉ dùng `--force` nếu dev xác nhận **cả 2 số đều đúng như đã báo**
dù có vẻ mâu thuẫn (trường hợp hiếm, project có quy ước Remaining khác 0 vẫn
được đánh Done) — không tự ý `--force` thay dev.

Case này **không** cần ghi `Risk management` — đây là sửa lỗi số liệu tự báo
của chính dev, không phải giải trình lý do vượt giờ với PM.

## Không hỏi xác nhận, nhưng phải echo cái vừa ghi

Action 1/2/3 bắt buộc preview + chờ PM xác nhận. Action này **không** — dòng
report chính là lệnh của dev, hỏi lại "xác nhận không?" mỗi lần report là phiền.

Đổi lại, câu trả lời **phải echo đúng cái vừa ghi** (id task, tab, số giờ,
status) để dev bắt lỗi ngay:

```
<@U0BK2KAN86B> log lên Sprint 1 rồi nhé
• **AU-1** — **8h**, **Done**
• **UPM-3** — **4h**, **In progress**
```

Có dòng không log được thì nói rõ dòng nào, vì sao, đừng gộp thành "có lỗi":

```
<@U0BK2KAN86B> log được 1 task, còn 1 task chưa nhé:
• **AU-1** — **8h**, **Done** → đã ghi vào Sprint 1
• **NEX-1** → không có mã này trong sheet, bạn kiểm lại giúp mình
```

**Không bịa kết quả**: chưa chạy script thì chưa được nói "đã log". Script lỗi
thì nói lỗi. Không liệt kê giá trị cũ trong sheet, không so với hôm qua, không
tự tổng hợp tiến độ — đó là việc của skill khác.
