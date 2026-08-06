# Luật log task — nguồn duy nhất

> **Đây là bản gốc.** Mọi chỗ khác (`SKILL.md`, `cron/job-b.prompt.txt`) chỉ
> được **trỏ về file này**, không được chép lại nội dung. Cần chấm một dòng
> report thì **mở file này ra đọc ngay lúc đó** — không nhớ lại từ tin nhắn cũ,
> không tái tạo từ trí nhớ phiên. Lỗi đã xảy ra thật ba lần: bản copy cũ nằm sẵn
> trong context luôn thắng bản mới nằm trong file.

Bot **chỉ kiểm cấu trúc dòng**, tuyệt đối **không đánh giá nội dung công việc**:
không phán giờ khai hợp lý hay không, không so với Jira/Sheet, không nhận xét
task làm nhanh hay chậm.

## Một dòng log task

7 field, đúng thứ tự này, ngăn bằng dấu `|`:

```
Id task | Re-estimate (h) | Start date | End date | Actual Effort (h) | Status | Note
```

Ví dụ: `NEX-214 | 8 | 03-08-2026 | 04-08-2026 | 7.5 | Done | xong sớm nửa buổi`

## Bước 1 — Dọn dòng trước khi tách field

Làm đúng thứ tự, bỏ bước nào là nhắc oan người ta:

- Bỏ khoảng trắng đầu/cuối dòng.
- Bỏ ký tự liệt kê / định dạng ở **đầu** dòng nếu có: `-`, `–`, `*`, `•`, `>`,
  `1.`, `2)`… và dấu bôi đậm / `` ` `` bọc quanh. Gõ `- NEX-123 | …` hay
  `• NEX-123 | …` là **bình thường**, không phải lỗi.
- Bỏ dấu `|` thừa ở **đầu** dòng (dán từ Excel/Google Sheet thường ra dạng
  `|NEX-123|8|…|`).
- **Không bao giờ bỏ dấu `|` ở cuối.** Dấu cuối cùng chính là chỗ đánh dấu
  `Note` để trống — bỏ nó đi là dòng đang đúng bỗng thành thiếu field.

## Bước 2 — Dòng nào bị đem ra chấm

Chỉ chấm dòng **có ý định là log task** = có ít nhất 1 dấu `|` **và** field đầu
**có chứa số**. Gọi đó là **dòng log**.

Mọi dòng khác **bỏ qua hoàn toàn**, không bao giờ là lý do báo sai format: câu
dẫn ("em báo cáo ạ"), giải thích thêm, ảnh, emoji, và cả **dòng tiêu đề** nếu ai
đó copy nguyên bảng (`Id task | Re-estimate (h) | …` — field đầu không có số).

Cũng **bỏ qua** dòng nào sau khi dọn **trùng khít với dòng `VD:`** trong tin
nhắc — đó là dán nguyên mẫu chứ không phải report thật.

"Bỏ qua" nghĩa là không chấm dòng đó, **không** phải người đó được tha: ai chỉ
có toàn dòng bị bỏ qua = **không có dòng log nào** → vẫn là sai format.

## Bước 3 — Chấm từng dòng log

Dòng **hợp lệ** phải thoả **tất cả** 7 điều:

1. **Đủ field** — có **ít nhất 6 dấu `|`**. Thừa field vẫn nhận (phần dư coi như
   `Note`). Thiếu dấu `|` là **sai**, kể cả khi field cuối để trống: vị trí là
   thứ duy nhất phân biệt cột nào ra cột nào, thiếu một dấu là mọi cột phía sau
   lệch hết.
2. **Id task** — đầu dòng là mã task **có chứa số**. **Không có quy định nào về
   dạng mã**: tiền tố chữ tuỳ ý, không phân biệt hoa thường. `4`, `NEX-100`,
   `DWM-2222`, `abc 12` hợp lệ như nhau. Thiếu khoảng trắng trước dấu `|` cũng
   vẫn hợp lệ.
3. **Re-estimate (h)**, **Actual Effort (h)**, **Status** — bắt buộc, **không
   được để trống**. Nội dung viết gì cũng nhận: `8`, `8h`, `1.5`, `0`, `-`,
   `In progress`, `đang làm`. Không kiểm đơn vị, không kiểm giá trị.
4. **Start date** — bắt buộc, đúng dạng **`DD-MM-YYYY`** (2 số ngày, 2 số tháng,
   4 số năm, ngăn bằng `-`), vd `03-08-2026`. `3-8-2026`, `03/08/2026`,
   `2026-08-03` là **sai**.
5. **End date khi Status khác Done** — được để trống. Người ta ngại ô trống nên
   hay điền cho có: `-`, `--`, `x`, `?`, `N/A`, `n/a`, `chưa`, `chưa xong`,
   `TBD` **tính y như để trống**, vẫn hợp lệ. Điền một ngày thật thì ngày đó
   phải đúng `DD-MM-YYYY`.
6. **End date khi Status là Done** — **bắt buộc** là ngày thật đúng
   `DD-MM-YYYY`. Để trống, hoặc điền `-`/`N/A`/chữ bất kỳ, đều **sai**.
7. **Note** — để trống thoải mái, **không bao giờ** là lý do báo sai format.

### Thế nào là "Status là Done"

Chuẩn hoá field Status trước — bỏ emoji, bỏ dấu câu, bỏ khoảng trắng thừa,
chuyển chữ thường, bỏ tiền tố `đã ` — rồi so **bằng đúng** với một trong:

`done` · `completed` · `finished` · `xong` · `hoàn thành` · `hoan thanh` · `hoàn tất`

So **bằng đúng**, tuyệt đối **không** so kiểu "có chứa chữ done":

- `not done`, `chưa done`, `chưa xong`, `hoàn thành 90%` → **không phải Done** →
  không được đòi End date của mấy dòng đó.
- `Done`, `DONE`, `done ✅`, `đã hoàn thành` → **là Done** → thiếu End date là sai.

### Ngoài 7 điều trên thì không kiểm gì nữa

Không đối chiếu Re-estimate với Actual Effort. Không kiểm End date có sau Start
date không. Không kiểm ngày có thật (`31-02-2026` vẫn nhận vì đúng dạng). Không
đối chiếu Id task với Google Sheet hay Jira.

**Không chắc một dòng có hợp lệ hay không → coi là hợp lệ.** Thà bỏ sót còn hơn
báo sai format cho người đã report tử tế.

### ⛔ Tuyệt đối không nhắc ai về dạng mã task

`004 | 18 | 01-08-2026 | 03-08-2026 | 18 | đã hoàn thành | không có` và
`DWM-2222| 8 | 03-08-2026 |  | 8 | đang tiến hành |` đều **hợp lệ hoàn toàn**.

Không được rep kiểu *"nhắc nhẹ mẫu chuẩn là NEX-004…"*, không "ghi mã dạng
NEX-số cho gọn", không đòi đổi tiền tố, không bắt thêm khoảng trắng quanh `|`.
Đây là lỗi đã xảy ra thật: template ghi `NEX-214` nên bot tự suy ra là bắt buộc.
**`NEX-214` chỉ là ví dụ, không phải luật.**

## Bước 4 — Kết luận cho từng người (chấm cả cụm)

**Đã report** = có **ít nhất 1 dòng log** *và* **tất cả** dòng log của họ đều
hợp lệ.

Chỉ cần **một** dòng log sai là vào nhóm **sai format** — dù các dòng khác đúng
hết. Có reply nhưng **không có dòng log nào** cũng là sai format.

Đây là điểm cố ý khác bản cũ ("có 1 dòng đúng là thoát"): bản cũ khiến người
khai 5 task sai 4 dòng vẫn được tính là xong, tức là mọi công validate đổ sông
đổ biển.

| Nhóm | Điều kiện |
|------|-----------|
| Đã report | Có ≥1 dòng log, và **mọi** dòng log đều hợp lệ |
| Chưa report | Không reply gì |
| Sai format | Có reply nhưng **không có dòng log nào**, hoặc có dòng log mà **≥1 dòng sai** |

## Bộ ví dụ chuẩn

```
NEX-123 | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done | xong sớm   → hợp lệ
  nex-45 | 5 | 03-08-2026 |  | 2 | In progress |                → hợp lệ (chưa Done: End date + Note trống vẫn ok)
4 | 16 | 28-07-2026 | 03-08-2026 | 18 | đã hoàn thành | không có → hợp lệ (Done tiếng Việt, có End date)
DWM-2222| 8 | 03-08-2026 |  | 8 | đang tiến hành |              → hợp lệ (tiền tố khác, thiếu space vẫn nhận)
100 | 4 | 03-08-2026 |  | 4h | đang làm | đổi figma | +14h      → hợp lệ (thừa field vẫn nhận)
- NEX-9 | 8 | 03-08-2026 |  | 8 | đang làm |                    → hợp lệ (gạch đầu dòng: dọn rồi mới chấm)
|NEX-9|8|03-08-2026||8|đang làm|                                → hợp lệ (dán từ Excel, bỏ dấu | đầu dòng)
NEX-9 | 8 | 03-08-2026 | - | 8 | đang làm |                     → hợp lệ (chưa Done: '-' tính như để trống)
NEX-9 | 8 | 03-08-2026 |  | 8 | hoàn thành 90% |                → hợp lệ (KHÔNG phải Done → không đòi End date)
NEX-9 | 8 | 03-08-2026 | 05-08-2026 | 8 | done ✅ | ok           → hợp lệ (Done kèm emoji, có End date)

NEX-123 | 8 | 01-08-2026 | 03-08-2026 | 7.5 | Done              → SAI (thiếu Note, chưa đủ 6 dấu |)
NEX-123 | 8 | 1-8-2026 |  | 2 | In progress |                   → SAI (Start date không đúng DD-MM-YYYY)
NEX-123 | 8 | 2026-08-01 |  | 2 | In progress |                 → SAI (ngày viết ngược)
NEX-123 | 8 | 01-08-2026 |  | 7.5 | Done | xong rồi             → SAI (Status Done mà bỏ trống End date)
NEX-123 |  | 01-08-2026 |  | 2 | In progress |                  → SAI (Re-estimate để trống)
NEX-123 | 8 | 01-08-2026 |  |  | In progress |                  → SAI (Actual Effort để trống)
NEX-9 | 8 | 03-08-2026 |  | 8 | đã hoàn thành |                 → SAI (là Done mà bỏ trống End date)
NEX-9 | 8 | 03-08-2026 | - | 8 | Done | xong                    → SAI (Done thì End date phải là ngày thật)

em báo cáo ạ                                                    → BỎ QUA (không có dấu |)
Id task | Re-estimate (h) | Start date | ...                    → BỎ QUA (dòng tiêu đề, field đầu không có số)
xong hết việc rồi nhé | 8 | 03-08-2026 |  | 8 | đang làm |       → BỎ QUA (field đầu không có số)
```

Chấm cả cụm:

```
em báo cáo ạ                                          ← bỏ qua
NEX-1 | 8 | 03-08-2026 | 03-08-2026 | 8 | Done | xong ← hợp lệ
NEX-2 | 8 | 3-8-2026 |  | 8 | đang làm |              ← SAI (ngày)
→ người này vào nhóm SAI FORMAT (1 dòng sai là đủ), dù dòng đầu đã đúng.
```
