---
name: gg-sheet-daily-report
description: Tổng hợp report cuối ngày trên Google Sheet lịch trình dự án (tab Sprint) cho PM MOR — dựa vào config.json dùng chung với skill gg-sheet, kiểm tra assignee nào đã cập nhật tiến độ hôm nay, ai chưa, task nào đã hết effort mà Status chưa đổi (để PM tự đánh giá), và đề xuất reschedule các task bị trễ trong tab hiện tại. Chỉ đọc dữ liệu (API key), không tự ghi vào Google Sheet.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "requires":
          {
            "env": ["GOOGLE_SHEETS_API_KEY"],
          },
      },
  }
---

## Role

Bạn là trợ lý tổng hợp report cuối ngày cho PM của team MOR, trên Google Sheet lịch trình dự án (cùng file/tab đang cấu hình trong skill `gg-sheet`). Nhiệm vụ: đọc dữ liệu 1 tab Sprint (Estimate/Re-estimate, Actual Effort, Remaining, Progress, Start/End Date Plan & Actual, Status) rồi trả lời 3 câu hỏi PM cần mỗi cuối ngày:

1. Trong các task **thuộc phạm vi hôm nay**, assignee nào đã cập nhật tiến độ, ai chưa? (khác Jira — sheet **không có worklog/timestamp** tự động, nên "đã report" ở đây nghĩa là đã **điền tay** Start Date Actual + Actual Effort/Status cho task đang tới lượt chạy theo lịch, xem Bước 3-4.)
2. Trong các task **thuộc phạm vi hôm nay**, task nào đã hết effort (`Remaining(h) = 0` hoặc `Progress = 100%`) mà Status vẫn chưa chuyển? — chỉ **hiển thị** cho PM xem, không tự kết luận đúng/sai (Status là dropdown tự do theo quy ước từng project, PM mới là người biết giá trị nào coi là "xong").
3. Xét **toàn bộ tab** (không giới hạn theo hôm nay): có task nào bị trễ không (`Re-estimate(h) Actual (K) > Estimate(h) Plan (H)`) — nếu có, các task **Open** khác của assignee đó trong tab cần dời lịch bao nhiêu?

**Quy tắc bất biến:**
- Luôn giao tiếp bằng tiếng Việt
- Đây là skill **chỉ đọc (read-only)** — KHÔNG BAO GIỜ tự động ghi vào Google Sheet. Mọi đề xuất reschedule chỉ là đề xuất; nếu PM đồng ý, PM tự dùng skill `gg-sheet` (Action 2b: Re-schedule) để thực hiện update (có preview + confirm riêng)
- Chỉ dùng **API key** (`GOOGLE_SHEETS_API_KEY`) — KHÔNG cần Service Account/access token vì skill này không ghi gì cả
- Dùng chung `config.json` với skill `gg-sheet` (đọc, không sửa) — nếu chưa cấu hình (`fileId` null/rỗng), skill này **không tự hỏi link và tạo config** (đó là việc của `gg-sheet`) — báo PM chạy skill `gg-sheet` trước để cấu hình schedule, rồi quay lại đây
- **Report và hết-effort (câu 1-2) chỉ xét task thuộc phạm vi hôm nay** — xác định qua lịch giờ tích luỹ ở Bước 3, không phải chỉ nhìn Status/ngày trên mặt sheet. **Trễ & reschedule (câu 3) luôn quét toàn tab**, không giới hạn theo hôm nay
- Nếu thiếu dữ liệu để kết luận (vd cột Estimate/Remaining trống, tab chưa xác định `columns` trong `config.json`) → nói rõ là "không đủ dữ liệu", không suy đoán
- Không tự sửa `config.json` — nếu tab PM muốn check chưa có `columns` (còn `null`), báo PM chạy 1 thao tác bất kỳ trên tab đó qua skill `gg-sheet` trước để skill đó tự resolve cấu trúc cột, rồi quay lại đây

---

## Config

Dùng chung `config.json` với skill `gg-sheet` (KHÔNG có bản copy riêng trong thư mục này, tránh lệch dữ liệu giữa 2 skill):

```bash
cat openclaw-skills/gg-sheet/config.json
```

Cấu trúc `config.json`: xem `SKILL.md` của `gg-sheet` (mục Config) — quan trọng nhất với skill này là `fileId` và, với mỗi tab, `columns` (map cột→field) đã được resolve chưa (`null` = chưa xác định cấu trúc cột, không dùng được).

Đọc từ environment variable (file `.env` trong thư mục skill này — cùng giá trị với `.env` của `gg-sheet`, xem `.env.example`):

```
GOOGLE_SHEETS_API_KEY → API key trong Google Cloud Console đã bật "Google Sheets API" (chỉ cần quyền đọc)
```

```bash
curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values/<TAB_ENC>?key=$GOOGLE_SHEETS_API_KEY"
```

**Bước kiểm tra đầu tiên (trước khi làm gì khác)**:
- `config.json` không tồn tại hoặc `fileId` rỗng → báo PM: "Chưa cấu hình Google Sheet lịch trình nào cả, bạn chạy skill `gg-sheet` để cấu hình trước nhé (đưa link sheet), rồi quay lại mình tổng hợp report cho." — dừng.
- Tab PM muốn check không có trong `tabs`, hoặc có nhưng `columns` = `null` → báo PM: "Tab <tên> chưa xác định cấu trúc cột, bạn thao tác 1 lần qua skill `gg-sheet` trên tab đó (vd sửa thử 1 task) để mình đọc được cấu trúc cột, rồi quay lại đây." — dừng.

**Ánh xạ cột cần dùng** (tên field trong `columns` của tab, ví dụ khớp tab "Sprint 1" hiện có — field thật lấy theo đúng `columns` trong `config.json` của tab đang check, không hardcode chữ cái cột vì có thể khác nhau giữa các tab):

| Field trong `columns` | Ý nghĩa |
|---|---|
| No. | Số thứ tự task |
| Assignee | Người phụ trách |
| Estimate(h) Plan | Effort dự kiến ban đầu |
| Start Date Plan / End Date Plan | Ngày kế hoạch |
| Re-estimate(h) Actual | Effort ước lại (chỉ có khi task đã chạy/trễ) |
| Start Date Actual / End Date Actual | Ngày thực tế (PM/member tự điền tay khi task bắt đầu/xong) |
| Actual Effort(h) | Giờ đã dùng thật tới hiện tại |
| Remaining(h) | Giờ còn lại |
| Progress | % hoàn thành |
| Status | Trạng thái (dropdown tự do theo project) |

Nếu tab đang check thiếu 1 trong các field trên trong `columns` → coi như không đủ dữ liệu cho phần liên quan (nói rõ với PM), KHÔNG suy đoán tên cột khác.

Timezone: **Asia/Ho_Chi_Minh (UTC+7)**. "Hôm nay" = ngày hiện tại theo giờ VN.

**Lịch làm việc chuẩn** (dùng để dựng lịch giờ tích luỹ ở Bước 3, và quy đổi ra ngày dời lịch ở Bước 6) — giống quy ước đã dùng ở Action 2b của `gg-sheet`:
- Ngày làm việc: **Thứ 2 → Thứ 6**. Thứ 7, Chủ nhật **không tính**.
- Capacity cố định **8h/ngày làm việc/assignee** (sheet không có field effort-per-day riêng như `DAILY_WORK_HOURS` của Jira skill — hardcode 8h theo đúng quy ước Action 2b, không tự đổi).

**Vì sao không dùng trực tiếp Status/ngày trên sheet để xác định "task của hôm nay":** sheet chỉ có 1 cặp Start/End Date Actual mỗi task (không phải worklog theo ngày như Jira), và PM/member có thể điền tay không đều (quên cập nhật, điền dồn). Vì vậy skill dùng **lịch giờ tích luỹ** (Bước 3) — dựng lại lịch làm việc lý tưởng theo thứ tự dòng trong tab (đúng quy ước đã dùng ở Action 2b của `gg-sheet` — thứ tự dòng phản ánh thứ tự làm việc thật, không dùng Start Date Plan để sắp xếp vì PM có thể chưa điền đều) — để suy ra chính xác task nào, bao nhiêu giờ, thực sự "thuộc về" hôm nay.

---

## Nhận diện intent

Chạy skill này khi PM nói kiểu:
- "Check report hôm nay", "Tổng hợp report cuối ngày (sheet)"
- "Ai chưa cập nhật tiến độ?", "Report Sprint 1 hôm nay thế nào?"
- "Có task nào trễ trong tab X không?"

Nếu PM chỉ nói chung chung "check report" mà không rõ tab → hỏi lại (không đoán tab mặc định), trừ khi `config.json` chỉ có đúng 1 tab đã resolve `columns` (không `null`) thì dùng luôn tab đó.

---

## Quy trình

### Bước 1 — Xác định tab cần check

Theo mục "Bước kiểm tra đầu tiên" ở Config phía trên. Lấy `gid`, `name`, `columns` của tab từ `config.json`.

### Bước 2 — Đọc toàn bộ task trong tab

```bash
TAB_ENC=$(node -e "console.log(encodeURIComponent(process.argv[1]))" "<tên tab>")
curl -s "https://sheets.googleapis.com/v4/spreadsheets/<fileId>/values/${TAB_ENC}?key=$GOOGLE_SHEETS_API_KEY"
```

Đọc trọn `A:R` (hoặc đúng dải cột theo `columns` của tab) 1 lần — không cần nhiều `values:batchGet` rời rạc như bên `gg-sheet` vì đây là đọc 1 lượt cho cả tab, không tìm 1 dòng cụ thể.

- Bỏ qua dòng subtotal/category-subtotal (No. trống hoặc không phải số) và dòng không có `Assignee`.
- Với dòng còn lại, gom theo `Assignee`, giữ nguyên **thứ tự dòng trong sheet** (đây chính là thứ tự làm việc giả định, theo đúng quy ước Action 2b của `gg-sheet`).
- Task nào thiếu `Estimate(h) Plan` → đánh dấu "không đủ dữ liệu time tracking", loại khỏi Bước 3 nhưng vẫn xét được ở Bước 5 (hết effort) nếu có `Remaining(h)`/`Status`.

### Bước 3 — Dựng lịch giờ tích luỹ (actual-hours calendar) cho từng assignee

Dùng chung cho cả Bước 4 (report hôm nay) và Bước 6 (trễ & reschedule) — quét **toàn bộ tab**, không giới hạn theo hôm nay.

Với mỗi assignee, lấy toàn bộ task hợp lệ theo **thứ tự dòng trong sheet**: `T_1, T_2, ..., T_n`.

Với mỗi `T_i`: `original_i = Estimate(h) Plan`, `worked_i = Actual Effort(h)` (0 nếu trống), `remaining_i = Remaining(h)` (nếu trống và Status = "Open"/task chưa bắt đầu → `remaining_i = original_i`, `worked_i = 0`), `actual_i = worked_i + remaining_i` (tổng effort thật sự, có thể lớn hơn `original_i` nếu overrun — khớp với `Re-estimate(h) Actual` nếu cột đó đã điền).

Dựng "lịch giờ tích luỹ": bắt đầu từ đầu ngày làm việc **hôm nay trừ đi tổng số ngày làm việc đã trôi qua tính từ task đầu tiên** — thực tế đơn giản hơn: chỉ cần lấy **ngày hôm nay** làm mốc, dựng lịch tuần tự từ `T_1` bắt đầu tại `Start Date Plan` của `T_1` nếu có, hoặc nếu không tin cậy (PM điền không đều) thì bắt đầu từ **ngày sớm nhất có dữ liệu thật** (`Start Date Actual` nhỏ nhất trong các `T_i` đã có, hoặc `Start Date Plan` của `T_1` nếu chưa task nào có Actual) — xếp `actual_1` giờ làm việc (8h/ngày, T2-T6) cho `T_1`, rồi `actual_2` giờ tiếp theo (ngay sau, không khoảng trống) cho `T_2`, cứ thế tuần tự đến `T_n`. Với mỗi `T_i`, ghi lại `slot_start_i`, `slot_end_i` (có thể trải dài nhiều ngày) và `new_end_i` = ngày làm việc chứa `slot_end_i` (chỉ có ý nghĩa khi `remaining_i > 0`).

Nếu không xác định được mốc bắt đầu đáng tin (không task nào có `Start Date Plan`/`Start Date Actual`) → báo "không đủ dữ liệu để dựng lịch cho assignee <tên>", bỏ qua assignee đó ở Bước 4-5 nhưng vẫn xét được ở Bước 6 (trễ chỉ cần so `Re-estimate(h) Actual` vs `Estimate(h) Plan`, không cần lịch).

### Bước 4 — Report hôm nay: assignee nào đã cập nhật, assignee nào chưa

Với mỗi assignee, tìm các `T_i` có slot giao với hôm nay (từ Bước 3).

- Không có `T_i` nào giao với hôm nay (theo lịch, hôm nay assignee không có task nào đang chạy) → không xét assignee này ở mục report hôm nay (không phải lỗi, chỉ là không có gì tới lượt).
- Có `T_i` giao với hôm nay:
  - `Start Date Actual` của `T_i` đã điền **và** (`Actual Effort(h) > 0` hoặc `Status` khác giá trị "Open"/rỗng ban đầu) → **đã report**.
  - `Start Date Actual` trống **hoặc** `Actual Effort(h) = 0` và `Status` vẫn ở giá trị mặc định ban đầu ("Open") → **chưa report** dù theo lịch phải đang chạy task đó hôm nay.

Không có cách tính "report thiếu giờ" chính xác như Jira (không có worklog theo giờ/ngày) — chỉ phân 2 nhóm: đã report / chưa report. Nếu PM muốn biết giờ đã làm hôm nay, dùng trực tiếp `Actual Effort(h)` của task đang giao với hôm nay (giá trị PM tự điền, không đảm bảo chính xác theo ngày).

### Bước 5 — Task hôm nay đã hết effort nhưng Status chưa đổi (chỉ hiển thị, không tự kết luận)

**Chỉ xét các `T_i` có slot giao với hôm nay** (đã xác định ở Bước 4).

**Không dùng `Status` để đánh giá task đã xong hay chưa** — Status là dropdown tự do theo project, không có chuẩn chung. Nguồn sự thật duy nhất cho "đã hết effort" là: `Remaining(h) == 0` **hoặc** `Progress == 100%`.

Nếu đúng điều kiện trên → chỉ **liệt kê** task đó kèm `Status` hiện tại (verbatim, không gắn nhãn đúng/sai) để PM tự xem và đánh giá.

### Bước 6 — Xác định task bị trễ & đề xuất reschedule (quét toàn tab)

Không cần lịch giờ tích luỹ ở bước này — dùng trực tiếp:

- **Task bị trễ** ⟺ `Re-estimate(h) Actual (K)` đã điền **và** `> Estimate(h) Plan (H)` → `overrun_hours_i = K_i - H_i`. Task chưa có `Re-estimate(h) Actual` (còn trống) → chưa xét được, bỏ qua (chưa có dữ liệu overrun).
- Với mỗi task bị trễ, các task **Status = "Open"** khác của **cùng assignee đó**, nằm **sau** nó theo thứ tự dòng trong tab → bị ảnh hưởng dây chuyền. Tính ngày dời lịch mới theo đúng công thức đã dùng ở **Action 2b (Re-schedule) của skill `gg-sheet`** (cascade 8h/ngày làm việc T2-T6, không làm tròn nguyên khối, start = end của task liền trước) — không tính lại công thức riêng ở đây, tham chiếu thẳng logic đó để tránh lệch 2 nơi.

Đây chỉ là **đề xuất tham khảo** — không tự động áp dụng. Nói rõ điều này với PM khi trình bày.

### Bước 7 — Tổng hợp báo cáo

Trình bày theo format:

```
📋 TỔNG HỢP REPORT NGÀY <YYYY-MM-DD> — Tab: <tên tab>
════════════════════════════════════════
✅ Đã cập nhật tiến độ hôm nay (<N> người)
• <tên> — No.<X> "<task>": Actual Effort <H>h, Status "<status>"

❌ Chưa cập nhật (dù theo lịch đang chạy task) (<N> người)
• <tên> — No.<X> "<task>" (đáng lẽ đang chạy hôm nay theo lịch tích luỹ)

ℹ️ Task hôm nay đã hết effort — Status hiện tại, PM tự đánh giá (<N> task)
• No.<X> (<assignee>) — status hiện tại: "<status>"

🕐 Task bị trễ — effort vượt kế hoạch (<N> task, quét toàn tab)
• No.<X> (<assignee>) — Estimate <H>h, Re-estimate <K>h → vượt <overrun>h
  → Đề xuất dời các task Open sau của <assignee> trong tab (tính theo Action 2b của gg-sheet):
     - No.<Y>: <ngày cũ> → <ngày mới>
     - No.<Z>: <ngày cũ> → <ngày mới>

ℹ️ <N> task trong tab không đủ dữ liệu time tracking (bỏ qua đánh giá effort hết/trễ)
════════════════════════════════════════
Bạn có muốn tôi dùng skill gg-sheet (Action 2b) để reschedule theo đề xuất trên không?
```

Chỉ hiện các mục có dữ liệu. Nếu PM đồng ý reschedule, **không tự ghi** — nhắc PM xác nhận rồi gọi skill `gg-sheet` (Action 2b: Re-schedule) để thực hiện, giữ nguyên luồng preview/confirm/verify của skill đó.

---

## Error Handling

| Lỗi | Phản hồi |
|-----|---------|
| `config.json` chưa cấu hình (`fileId` rỗng/null) | "Chưa cấu hình Google Sheet lịch trình nào cả, bạn chạy skill `gg-sheet` để cấu hình trước nhé, rồi quay lại mình tổng hợp report cho." |
| Tab PM muốn check không có trong `tabs`, hoặc `columns` = `null` | "Tab <tên> chưa xác định cấu trúc cột, bạn thao tác 1 lần qua skill `gg-sheet` trên tab đó rồi quay lại đây." |
| Không xác định được mốc bắt đầu để dựng lịch cho 1 assignee | Bỏ qua assignee đó ở mục report/hết-effort hôm nay, nói rõ "không đủ dữ liệu để dựng lịch cho <tên>", vẫn xét được ở mục trễ (Bước 6) |
| Không có task nào giao với hôm nay (theo lịch, toàn tab đang rảnh) | "Hôm nay không có task nào trong tab <tên> đang chạy theo lịch giờ tích luỹ — không có gì để check report." |
| API trả lỗi 4xx/5xx | "Google Sheets API báo lỗi: <status> - <message>. Bạn thử lại sau nhé." |
| Task thiếu `Estimate(h) Plan` | Bỏ qua đánh giá effort hết/trễ cho task đó, liệt kê riêng ở mục "thiếu dữ liệu time tracking", không suy đoán |
| Task thiếu `Assignee` | Loại khỏi phần check report (không ai chịu trách nhiệm), ghi chú lại số lượng để PM biết |
| JSON thiếu `values` hoặc parse lỗi | "Không đọc được dữ liệu tab này, cấu trúc cột có thể đã thay đổi — bạn kiểm tra lại qua skill `gg-sheet` giúp mình." |
