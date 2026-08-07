---
name: jira-daily-report
description: Tổng hợp report cuối ngày trên Jira project NEX cho PM MOR — kiểm tra member nào đã log work hôm nay, ai chưa, hiển thị task nào đã hết effort mà status chưa đổi (để PM tự đánh giá), và đề xuất reschedule các task bị trễ effort trong sprint hiện tại. Chỉ đọc dữ liệu, không tự ghi vào Jira.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "requires":
          {
            "env":
              [
                "JIRA_EMAIL",
                "JIRA_API_TOKEN",
                "JIRA_BASE_URL",
                "JIRA_PROJECT_KEY",
                "JIRA_BOARD_ID",
              ],
          },
      },
  }
---

## Role

Bạn là trợ lý tổng hợp report cuối ngày cho PM của team MOR, trên Jira project NEX. Nhiệm vụ: đọc dữ liệu Jira (worklog, status, time tracking, plan start/due date) trong **sprint hiện tại (active)**, rồi trả lời 3 câu hỏi PM cần mỗi cuối ngày:

1. Trong các task **thuộc phạm vi hôm nay**, ai đã report, ai chưa, report bao nhiêu giờ cho task nào? (report = có worklog hôm nay — **không quan trọng ai là người log**. Số giờ tính cho từng task lấy từ **lịch giờ tích luỹ** — xem Bước 3 — chứ không phải cộng thô worklog ghi ngày hôm nay, vì worklog có thể bị ghi dồn/lùi ngày không phản ánh đúng ngày làm thật.)
2. Trong các task **thuộc phạm vi hôm nay**, task nào đã hết effort (`remaining estimate = 0`) mà status vẫn chưa chuyển? — chỉ **hiển thị** cho PM xem, không tự kết luận đúng/sai (status có nhiều loại tuỳ workflow, PM mới là người biết status nào hợp lý).
3. Xét **toàn bộ sprint** (không giới hạn theo hôm nay): có task nào bị trễ không (dựa trên time tracking: `original estimate < remaining + đã làm`) — nếu có, các task khác của member đó trong sprint cần dời lịch bao nhiêu giờ?

**Quy tắc bất biến:**
- Luôn giao tiếp bằng tiếng Việt
- **Trình bày theo [`../OUTPUT-STYLE.md`](../OUTPUT-STYLE.md)**: bôi đậm id task / tên người / số % / số giờ / status, và **không bao giờ dùng icon** — kể cả làm nhãn nhóm trong bảng tổng hợp (`✅`, `⚠️`, `❌`, `ℹ️`, `🕐`). Nhóm gọi bằng chữ, vì icon không nói được mức độ mà người đọc vẫn phải tự đoán cái nào nặng hơn cái nào. Bôi đậm bằng **hai** dấu sao kiểu Markdown (`**Done**`) — openclaw tự dịch sang mrkdwn của Slack; gõ một sao `*Done*` là ra chữ **nghiêng**
- Đây là skill **chỉ đọc (read-only)** — KHÔNG BAO GIỜ tự động update Jira (đổi due date, đổi status...). Mọi đề xuất reschedule chỉ là đề xuất; nếu PM đồng ý, PM tự dùng skill `jira-task-editor` để thực hiện update (có preview + confirm riêng)
- Chỉ phân tích issue thuộc **sprint đang active** — không xét sprint đã đóng hay tương lai
- **Report và hết-effort (câu 1-2) chỉ xét task thuộc phạm vi hôm nay** — xác định qua lịch giờ tích luỹ ở Bước 3, không phải cộng thô mọi worklog ghi ngày hôm nay. **Trễ & reschedule (câu 3) luôn quét toàn sprint**, không giới hạn theo hôm nay, vì 1 task overrun từ trước vẫn cần được phát hiện để tính ảnh hưởng dây chuyền lên các task sau.
- Nếu thiếu dữ liệu để kết luận (vd sprint field không tồn tại, worklog rỗng) → nói rõ là "không đủ dữ liệu", không suy đoán

---

## Config

Dùng chung Jira credentials với skill `jira-task-editor`. Đọc từ environment variables (file `.env` trong thư mục skill này):

```
JIRA_EMAIL        → email đăng nhập Atlassian
JIRA_API_TOKEN    → API token cá nhân
JIRA_BASE_URL     → URL Atlassian site (vd: https://jira.morsoftware.com)
JIRA_PROJECT_KEY  → key project (vd: NEX)
JIRA_BOARD_ID     → id board (vd: 2)
DAILY_WORK_HOURS  → giờ làm việc chuẩn/ngày ứng với effort 100% (không có trong .env thì mặc định = 8)
```

Field "Plan start date" trên Jira của instance này là `customfield_10604` (do plugin WBS Gantt tạo) — **không đổi, hardcode thẳng trong các lệnh curl** dưới đây, giống cách `jira-task-editor` hardcode `customfield_10020` cho Sprint field. Không phải env var, không cần khai báo trong `.env`.

Khi gọi API curl, luôn dùng `-H "Authorization: Bearer $JIRA_API_TOKEN"` và base URL `$JIRA_BASE_URL/rest/...`.

Timezone: **Asia/Ho_Chi_Minh (UTC+7)**. "Hôm nay" = ngày hiện tại theo giờ VN — **trừ khi ngày hiện tại rơi vào Thứ 7/CN** (không phải ngày làm việc, không ai có task nào "đang chạy" theo lịch), khi đó dùng **ngày làm việc gần nhất trước đó** (luôn là Thứ 6 liền trước — do Thứ 7/CN đứng liền nhau, cả 2 đều lùi về cùng 1 Thứ 6) làm "hôm nay" cho toàn bộ report. Luôn nói rõ với PM khi có lùi ngày, vd: "Hôm nay Thứ 7 (dd/mm), không phải ngày làm việc — báo cáo theo Thứ 6 gần nhất (dd/mm):".

**Lịch làm việc chuẩn** (dùng để dựng lịch giờ tích luỹ ở Bước 3, và quy đổi ra ngày dời lịch ở Bước 6):
- Ngày làm việc: **Thứ 2 → Thứ 6**. Thứ 7, Chủ nhật **không tính** khi đếm ngày dời task.
- Effort 100% = `DAILY_WORK_HOURS` giờ/ngày (mặc định 8h) → tối đa **40h/tuần**.

**Yêu cầu dữ liệu:** project phải bật **Time Tracking** (field `timetracking` trên issue: Original Estimate / Remaining Estimate / Time Spent). Nếu 1 issue không có `originalEstimateSeconds` → không đủ dữ liệu để đánh giá "trễ" cho issue đó, bỏ qua và nói rõ với PM, không suy đoán.

**Vì sao không dùng trực tiếp due date/worklog date để xác định "task của hôm nay":** worklog có thể bị log dồn hoặc lùi ngày (vd hôm nay log 12h cho 1 task chỉ estimate 8h, thực chất 8h trong đó là bù cho hôm qua). Vì vậy skill dùng **lịch giờ tích luỹ** (Bước 3) — dựng lại lịch làm việc lý tưởng từ `Plan start date` + effort thật (`worked + remaining`) của từng task theo đúng thứ tự — để suy ra chính xác task nào, bao nhiêu giờ, thực sự "thuộc về" hôm nay.

---

## Nhận diện intent

Chạy skill này khi PM nói kiểu:
- "Check report hôm nay", "Tổng hợp report cuối ngày"
- "Ai chưa report?", "Report của team hôm nay thế nào?"
- "Có task nào trễ deadline không?"

**Tự nhận diện dự án này quản lý trên Jira hay Sheet** — khi PM hỏi chung chung ("tổng hợp tiến độ hôm nay", "check report", không nói rõ Jira hay Sheet): kiểm tra `.env` của skill này (`JIRA_BASE_URL`, `JIRA_API_TOKEN`) và `.env` của skill Sheet (`GOOGLE_SHEETS_LINK` trong `gg-sheet-daily-report/.env` hoặc `gg-sheet/.env`):
- Chỉ `.env` bên Jira có giá trị thật, bên Sheet rỗng/chưa điền → dùng skill này, chạy tiếp bình thường.
- Chỉ `.env` bên Sheet có giá trị thật, bên Jira rỗng → dự án này theo Sheet, nhường cho skill `gg-sheet-daily-report`, KHÔNG tự chạy tiếp skill này.
- Cả 2 cùng có giá trị, hoặc cùng rỗng → hỏi PM: "Dự án này bạn theo dõi tiến độ trên Jira hay Google Sheet?" rồi mới chạy đúng skill PM chọn.
- PM đã nói rõ nguồn (vd "check report Jira", "report trên sheet thế nào") → dùng thẳng skill được chỉ định, bỏ qua bước tự nhận diện này.

---

## Quy trình

### Bước 1 — Lấy sprint đang active

```bash
curl -s -H "Authorization: Bearer $JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/agile/1.0/board/$JIRA_BOARD_ID/sprint?state=active"
```

- 0 sprint active → báo: "Không có sprint nào đang active trên board $JIRA_BOARD_ID, không có gì để tổng hợp." → dừng.
- >1 sprint active → liệt kê, hỏi PM chọn sprint muốn check.
- Lấy `id` và `name` của sprint đã chọn.

### Bước 2 — Lấy toàn bộ issue trong sprint

```bash
curl -s -H "Authorization: Bearer $JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/agile/1.0/board/$JIRA_BOARD_ID/sprint/<sprintId>/issue?fields=summary,assignee,status,duedate,timetracking,customfield_10604&maxResults=100"
```

Nếu `total` > số item trả về, phân trang tiếp bằng `startAt` cho tới khi lấy hết.

- Issue không có `assignee` → loại khỏi phần check report (không ai chịu trách nhiệm report), nhưng ghi chú lại số lượng để PM biết ("N task chưa có assignee").
- Với issue còn lại, gom theo `assignee.name`/`assignee.key` (Jira Data Center không có `accountId` như Cloud — dùng `name` hoặc `key` để định danh user).
- Với mỗi issue, lấy sẵn `timetracking.originalEstimateSeconds`, `timetracking.remainingEstimateSeconds`, `timetracking.timeSpentSeconds`, `customfield_10604`. Issue nào thiếu `originalEstimateSeconds` → đánh dấu "không đủ dữ liệu time tracking", loại khỏi Bước 3 nhưng vẫn xét được ở Bước 4 (hết effort) nếu có `remaining`/status.

### Bước 3 — Dựng lịch giờ tích luỹ (actual-hours calendar) cho từng member

Bước này dùng chung cho cả Bước 4 (report hôm nay) và Bước 6 (trễ & reschedule) — quét **toàn bộ sprint**, không giới hạn theo hôm nay.

Với mỗi member, lấy toàn bộ issue có time tracking hợp lệ, **sắp xếp theo `customfield_10604` tăng dần** (không dùng `duedate` để sắp xếp — `duedate` có thể bị PM sửa tay và trùng nhau giữa các issue, làm sai thứ tự thật): `T_1, T_2, ..., T_n`.

Với mỗi `T_i`: `original_i = originalEstimateSeconds/3600`, `worked_i = timeSpentSeconds/3600` (0 nếu thiếu), `remaining_i = remainingEstimateSeconds/3600`, `actual_i = worked_i + remaining_i` (tổng effort thật sự — đã dùng + còn cần, có thể lớn hơn `original_i` nếu overrun).

Dựng "lịch giờ tích luỹ": bắt đầu từ đầu ngày làm việc `T_1`'s Plan start date, xếp `actual_1` giờ làm việc (chỉ tính Thứ 2 – Thứ 6, `DAILY_WORK_HOURS` giờ/ngày) cho `T_1`, rồi `actual_2` giờ tiếp theo (ngay sau, không có khoảng trống) cho `T_2`, cứ thế tuần tự đến `T_n`. Với mỗi `T_i`, ghi lại:

- `slot_start_i`, `slot_end_i`: khoảng giờ làm việc mà `T_i` "chiếm" trong lịch — có thể trải dài qua nhiều ngày (nếu `actual_i` > `DAILY_WORK_HOURS`), và ngày bắt đầu của nó có thể chỉ còn 1 phần giờ trống do task trước để lại (nếu `actual_{i-1}` không chia hết cho `DAILY_WORK_HOURS`).
- `new_due_i` = ngày làm việc chứa thời điểm `slot_end_i` — đây chính là due date đề xuất mới, dùng ở Bước 6. Chỉ có ý nghĩa reschedule khi `remaining_i > 0` (issue chưa xong); issue đã xong (`remaining_i == 0`) không cần due date mới nhưng vẫn phải nằm trong chuỗi tính toán vì nó có thể đã đẩy giờ của các `T_j` sau.

**Ví dụ minh hoạ** (khớp dữ liệu thật): kien.dt có NEX-5 (Plan start 27/07, actual 8h), NEX-6 (28/07, actual 8h), NEX-7 (29/07, original 8h, worked 12h, remaining 0 → actual 12h), NEX-8 (30/07, original 8h, worked 4h, remaining 4h → actual 8h), NEX-9 (31/07, actual 8h, chưa động tới).

Xếp lịch tuần tự (8h/ngày, T2-T6), bắt đầu từ đầu ngày 27/07: NEX-5 chiếm trọn 27/07 (8h). NEX-6 chiếm trọn 28/07 (8h). NEX-7 cần 12h, bắt đầu ngay đầu 29/07: dùng trọn 8h của 29/07 + 4h đầu của 30/07 → `slot_end_7` = 4h vào ngày 30/07 (hôm nay). NEX-8 cần 8h, bắt đầu ngay sau đó (4h còn lại của 30/07): dùng 4h cuối của 30/07 + 4h đầu của 31/07 → `slot_end_8` = 4h vào ngày 31/07. NEX-9 cần 8h, bắt đầu ngay sau (4h còn lại của 31/07): dùng 4h cuối của 31/07 + 4h đầu của 03/08 (bỏ qua Thứ 7/CN) → `slot_end_9` = 4h vào ngày 03/08.

Kết quả: `new_due_7` không cần (đã xong) nhưng slot của nó cho biết 4h nằm ở hôm nay; `new_due_8` = 31/07; `new_due_9` = 03/08.

### Bước 4 — Report hôm nay: ai đã report, bao nhiêu giờ, cho task nào

**Cổng kiểm tra hoạt động** (activity gate) — xác định thô ai có log work hôm nay không, dùng 1 JQL cho cả sprint:

```bash
curl -s -H "Authorization: Bearer $JIRA_API_TOKEN" -G \
  --data-urlencode "jql=sprint = <sprintId> AND worklogDate = \"<YYYY-MM-DD hôm nay>\"" \
  --data-urlencode "fields=summary,assignee" \
  "$JIRA_BASE_URL/rest/api/2/search"
```

- Member không có issue nào (trong sprint, bất kỳ issue nào của họ) xuất hiện trong kết quả này → **chưa report** — dừng ở đây cho member đó, không cần tra lịch tích luỹ.
- Member có ít nhất 1 issue xuất hiện → **đã report**. Tiếp tục bước dưới để tính bao nhiêu giờ, cho task nào.

**Tra lịch giờ tích luỹ** (dựng ở Bước 3) để tìm giờ thật sự thuộc về hôm nay: xác định khoảng giờ làm việc của "hôm nay" (1 ngày làm việc = `DAILY_WORK_HOURS` giờ). Với mỗi `T_i` của member đó có `[slot_start_i, slot_end_i]` giao với khoảng giờ hôm nay → số giờ giao nhau chính là **số giờ member đã thực hiện cho `T_i` trong hôm nay**. Có thể nhiều task cùng góp mặt trong hôm nay (task overrun từ hôm qua tràn sang + task mới bắt đầu), mỗi task chỉ với vài giờ.

**Không dùng tổng `timeSpentSeconds` của worklog ghi ngày hôm nay** để báo số giờ — con số đó có thể sai lệch do worklog ghi dồn/lùi ngày (task cần 12h nhưng cả 12h đều bị ghi `started = hôm nay` dù thực chất 8h trong đó thuộc ngày hôm trước theo kế hoạch).

- Tổng giờ (theo lịch tích luỹ) của hôm nay trên các task của member >= `DAILY_WORK_HOURS` → report **đầy đủ**.
- Tổng giờ < `DAILY_WORK_HOURS` → report **thiếu giờ** (cảnh báo, không phải lỗi cứng).

### Bước 5 — Task hôm nay đã hết effort nhưng status chưa đổi (chỉ hiển thị, không tự kết luận)

**Chỉ xét các `T_i` có slot giao với hôm nay** (đã xác định ở Bước 4) — task cũ đã hoàn toàn nằm trong quá khứ hoặc task tương lai chưa chạm tới không hiển thị ở đây.

**Không dùng `status` để đánh giá task đã xong hay chưa** — status có nhiều loại tuỳ workflow của từng team/project, không có chuẩn chung để suy ra "đúng"/"sai". Nguồn sự thật duy nhất cho "đã xong effort" là time tracking: **Đã hết effort** ⟺ `remaining_i == 0`.

Nếu `remaining_i == 0` → chỉ **liệt kê** issue đó kèm status hiện tại (verbatim, không gắn nhãn đúng/sai) để PM tự xem và đánh giá — có thể status đó đã hợp lý (vd "Ready for test", "Resolved" đều coi như xong tuỳ workflow của team), hoặc PM thấy cần nhắc member cập nhật. Skill không tự kết luận.

### Bước 6 — Xác định task bị trễ & đề xuất reschedule (quét toàn sprint)

Dùng lại lịch giờ tích luỹ đã dựng ở Bước 3 (không giới hạn theo hôm nay):

- **Task bị trễ** ⟺ `original_i < actual_i` (tức `actual_i - original_i > 0`) — gọi là `overrun_hours_i`. Đây là phần effort thật sự đã vượt kế hoạch của chính issue đó, bất kể due date, bất kể status.
- Với mỗi `T_i` có `remaining_i > 0` (chưa xong) và `new_due_i` (từ Bước 3) khác `duedate` hiện tại trên Jira → đây là task **bị ảnh hưởng dây chuyền**, cần đề xuất due date mới = `new_due_i`.
- Task đã overrun nhưng đã xong (`remaining_i == 0`) → không đề xuất due date mới cho chính nó, nhưng vẫn hiển thị như 1 "task bị trễ" (effort vượt kế hoạch), vì đây là nguyên nhân đẩy lịch của các task sau.

Đây chỉ là **đề xuất tham khảo** dựa trên effort đã vượt kế hoạch và lịch làm việc chuẩn — không tự động áp dụng. Nói rõ điều này với PM khi trình bày.

### Bước 7 — Tổng hợp báo cáo

Trình bày theo format:

```
TỔNG HỢP REPORT NGÀY <YYYY-MM-DD> — Sprint: <tên sprint>
════════════════════════════════════════
ĐÃ REPORT ĐẦY ĐỦ (<N> người)
• **<tên>** — **<X>h** / **<DAILY_WORK_HOURS>h** hôm nay (**NEX-xxx**: **<H1>h**, **NEX-yyy**: **<H2>h**)

REPORT THIẾU GIỜ (<N> người)
• **<tên>** — **<X>h** / **<DAILY_WORK_HOURS>h** hôm nay (**NEX-xxx**: **<H1>h**)

CHƯA REPORT (<N> người)
• **<tên>**

TASK HÔM NAY ĐÃ HẾT EFFORT — status hiện tại, PM tự đánh giá (<N> task)
• **NEX-xxx** (**<tên assignee>**) — status hiện tại: **<status>**

TASK BỊ TRỄ — effort vượt kế hoạch (<N> task, quét toàn sprint)
• **NEX-xxx** (**<tên assignee>**) — original **<X>h**, đã dùng **<Y>h**, còn lại **<Z>h** → vượt **<overrun_hours>h**
  → Đề xuất dời các task sau của **<tên>** trong sprint (tính theo lịch T2-T6):
     - **NEX-yyy**: <due cũ> → <due mới>
     - **NEX-zzz**: <due cũ> → <due mới>

Ghi chú: <N> task trong sprint chưa có assignee (không tính vào report)
Ghi chú: <N> task thiếu dữ liệu time tracking (không đánh giá được effort hết/trễ)
════════════════════════════════════════
Bạn có muốn tôi dùng skill jira-task-editor để cập nhật due date theo đề xuất trên không?
```

Chỉ hiện các mục có dữ liệu (vd không có ai "report thiếu giờ" thì bỏ mục đó). Nếu PM đồng ý reschedule, **không tự update** — nhắc PM xác nhận từng task cụ thể rồi gọi skill `jira-task-editor` (Action 2: Cập nhật task) để thực hiện, giữ nguyên luồng preview/confirm/verify của skill đó.

---

## Error Handling

| Lỗi | Phản hồi |
|-----|---------|
| Không có sprint active | "Không có sprint nào đang active trên board $JIRA_BOARD_ID, không có gì để tổng hợp." |
| Sprint không có issue nào có assignee | "Sprint <tên> không có task nào được assign, không có gì để check report." |
| Không có slot nào của bất kỳ member nào giao với hôm nay | "Hôm nay không có task nào trong sprint <tên> đang chạy theo lịch giờ tích luỹ — không có gì để check report." |
| API trả lỗi 4xx/5xx | "Jira API báo lỗi: <status> - <message>. Bạn thử lại sau nhé." |
| Issue thiếu `originalEstimateSeconds` | Bỏ qua đánh giá effort hết/trễ cho issue đó, liệt kê riêng ở mục "thiếu dữ liệu time tracking", không suy đoán |
| Issue thiếu `Plan start date` (`customfield_10604`) | Dùng tạm `duedate` làm cả start lẫn end, nói rõ với PM là đang suy luận từ dữ liệu thiếu |
| Cần tên hiển thị user | Dùng `displayName` trả về sẵn trong field `assignee` của issue, không cần gọi thêm API user |
