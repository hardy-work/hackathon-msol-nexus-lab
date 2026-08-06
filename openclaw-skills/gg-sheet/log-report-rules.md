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
SKILL_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/workspace/skills/gg-sheet"

bash $SKILL_DIR/scripts/sheet-task.sh find <TASKID>
bash $SKILL_DIR/scripts/sheet-task.sh log  <TASKID> --re-est .. --start .. --end .. --actual .. --status .. --note ..
bash $SKILL_DIR/scripts/sheet-task.sh risk --task .. --assignee .. --diff .. --reason .. [--next ..] [--reporter ..]
```

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

## Đọc exit code, đừng đọc chữ trong output

| Exit | Nghĩa | Làm gì |
| --- | --- | --- |
| `0` | Đã ghi xong | Báo lại đã log, echo đúng cái vừa ghi |
| `7` | Không có id đó trong sheet | Báo dev mã task sai, **không** tự tạo task |
| `8` | Id trùng ở nhiều tab | Hỏi tab nào, **không tự chọn** |
| `9` | **Chậm hơn plan** — chưa ghi gì | Sang mục dưới |
| `2` | Thiếu env / sai tham số | Cấu hình hỏng — báo dev là bot đang lỗi cấu hình, nhờ báo PM |
| `3` | Đọc sheet lỗi | Mạng hoặc API key — báo "chưa đọc được sheet" |
| `4` | Sheet đổi cấu trúc cột | Báo PM: tab thiếu cột bắt buộc, không tự đoán cột khác |
| `10` | Không mint được token | Service Account hỏng/hết quyền — báo là chưa ghi được |
| `11` | Ghi lỗi, hoặc đọc lại không khớp | **Có thể đã ghi một phần** — nói rõ điều đó, nhờ dev/PM kiểm sheet |

### Exit nào cũng phải trả lời dev — kể cả exit lỗi

**Không bao giờ im.** Mọi nhánh lỗi đều phải ra một tin nhắn, mở đầu bằng `<@id>`
của dev, nói **chưa log được** + lý do ngắn bằng tiếng Việt + việc họ cần làm:

```
<@U0BK2KAN86B> mình chưa log PCS-10 lên sheet được nhé — bot chưa có quyền ghi vào file (lỗi 403).
Bạn báo PM share quyền Editor cho service account giúp mình, report của bạn mình giữ nguyên đây.
```

Cấm tuyệt đối: im luôn, `NO_REPLY`, thả mỗi emoji, "để lát nữa nhắc lại", hoặc
nói "đã log" khi script chưa trả `0`. Im lặng **tệ hơn** lỗi ghi — dev tưởng
xong việc rồi đi về, tới cuối sprint mới lòi ra là sheet trống.

Lỗi thì **không tự chạy lại nhiều lần** (nhất là `11`: có thể đã ghi một phần,
chạy lại là ghi đè lung tung). Chạy lại đúng một lần rồi thôi, còn lại báo người.

## Task chậm hơn plan (exit 9) — hỏi lý do rồi vẫn log

Chậm = `Actual Effort (h)` dev report **lớn hơn** `Estimate (h)` (khối `PLAN`)
của chính task đó. Mốc so là **giờ plan trong sheet**, không phải `Re-estimate`
dev tự khai — dev khai lại bằng đúng số giờ đã làm là thoát cảnh báo, thành ra
không cảnh báo được ai.

Exit 9 in ra JSON có `estimate`, `actual`, `diff`, `assignee`, `tab`, `row`, và
**chưa ghi ô nào cả**.

Đây **không phải là từ chối log** — chỉ là hoãn lại để lấy lý do. Hỏi:

```
<@U0BK2KAN86B> mình thấy task PCS-7 đang bị chậm so với plan: plan 8h mà thực tế 9h, vượt 1h.
Lý do là gì để mình log vào tab Risk management rồi log task luôn nhé?
```

Chỉ nêu **con số**: plan bao nhiêu, thực tế bao nhiêu, chênh bao nhiêu. **Không**
bình luận làm nhanh hay chậm, không hỏi sao lâu thế, không gợi ý chia nhỏ task,
không nhắc chuyện OT. Việc của skill là ghi số, không phải đánh giá người.

### Dev trả lời lý do → ghi Risk trước, log task sau

```bash
bash $SKILL_DIR/scripts/sheet-task.sh risk --task PCS-7 --assignee VinhNV \
  --diff 1 --reason "<nguyên văn lý do dev nói>" --reporter "long.vn"

bash $SKILL_DIR/scripts/sheet-task.sh log PCS-7 --re-est 8 --start 03-08-2026 \
  --end 04-08-2026 --actual 9 --status Done --note "" --force
```

Đúng thứ tự đó. Ghi risk lỗi thì **dừng, đừng log** — task được log mà không có
dòng risk đi kèm chính là tình huống cần tránh. `--force` chỉ được dùng ở đây,
sau khi đã có lý do và đã ghi risk xong; không bao giờ dùng để "cho nhanh".

Log lại **đúng số dev đã report lúc đầu**, không hỏi lại số liệu, không lấy số
mới trong câu trả lời lý do.

`--reason` giữ **nguyên văn lý do dev nói**, không tóm tắt theo ý mình, không
sửa câu chữ. Script tự sinh `R-xx` kế tiếp, tự điền ngày, tự chọn Priority
(chênh ≥ 4h → `High`, dưới → `Medium`), tự đặt `Status = Open`.

Xong thì báo lại, nêu cả mã risk:

```
<@U0BK2KAN86B> ok mình ghi lý do vào Risk management (R-02) và log PCS-7 lên Sprint 1 rồi nhé ✅
```

### Bao lâu chưa trả lời thì thôi

Hạn chờ **không** thuộc Action này — Action này không có bộ đếm giờ và không
theo dõi hội thoại. Bên gọi (`reminder-followup`) giữ hạn 1 tiếng và tự nhắc
người quá hạn. Ở đây chỉ cần nhớ: **chưa có lý do thì chưa `--force`**.

## Không hỏi xác nhận, nhưng phải echo cái vừa ghi

Action 1/2/3 bắt buộc preview + chờ PM xác nhận. Action này **không** — dòng
report chính là lệnh của dev, hỏi lại "xác nhận không?" mỗi lần report là phiền.

Đổi lại, câu trả lời **phải echo đúng cái vừa ghi** (id task, tab, số giờ,
status) để dev bắt lỗi ngay:

```
<@U0BK2KAN86B> log lên Sprint 1 rồi nhé ✅
• AU-1 — 8h, Done
• UPM-3 — 4h, In progress
```

Có dòng không log được thì nói rõ dòng nào, vì sao, đừng gộp thành "có lỗi":

```
<@U0BK2KAN86B> log được 1 task, còn 1 task chưa nhé:
• AU-1 — 8h, Done → đã ghi vào Sprint 1 ✅
• NEX-1 → không có mã này trong sheet, bạn kiểm lại giúp mình
```

**Không bịa kết quả**: chưa chạy script thì chưa được nói "đã log". Script lỗi
thì nói lỗi. Không liệt kê giá trị cũ trong sheet, không so với hôm qua, không
tự tổng hợp tiến độ — đó là việc của skill khác.
