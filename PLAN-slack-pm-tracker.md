# Plan: Skill quản lý task qua Slack (backend Google Sheet "Handy_Project Schedule_v2.1")

## 1. Quyết định đã chốt với PM

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | Có dùng `3. Backlog` không? | **Bỏ qua** — ngoài scope v1 |
| 2 | Sprint hiện tại xác định sao? | **Theo thời gian thực** — so ngày hôm nay với `PLAN Start/End Date` của từng sprint trong `1.Summary Project`. Vì file hiện có là dữ liệu cũ (sprint gần nhất kết thúc 2026-01-30, trong khi hôm nay là 2026-07-24), rất có thể **không có sprint nào khớp** → xử lý fallback (xem mục 5) |
| 3 | Có dùng tab `CR` không? | **Bỏ qua** — làm sau |
| 4 | Có dùng `4. Next Action Plan` không? | **Bỏ qua** — làm sau |
| 5 | Progress % tính sao? | **Có công thức**, dựa trên `Actual Effort (h)` / `Re-estimate (h)` → bot **không bao giờ ghi trực tiếp vào cột Progress**, chỉ ghi Actual Effort/Re-estimate, Progress tự tính |
| 6 | Quyền Service Account? | **Cấp Editor toàn file** — vì mọi thao tác sau này đều qua Slack (không ai sửa tay sheet song song), không cần giới hạn theo tab |

→ **Scope v1**: chỉ thao tác trên các tab `2.x.Sprint N` + đọc `1.Summary Project` (tổng hợp tiến độ) + đọc `Config` (enum Status, danh sách PIC). Không đụng `CR`, `3. Backlog`, `4. Next Action Plan`, `2.Master schedule`, `ROC`.

---

## 2. Schema tab Sprint (đã verify đầy đủ cột, vd `2.2.Sprint 1`)

| Cột | Ý nghĩa | Bot có ghi trực tiếp? |
|---|---|---|
| No. | STT trong sprint | Tự tăng khi thêm task mới |
| Category Milestone | Nhóm task lớn | Có |
| Type | BrSE / BE / FE / QC / Design / Common | Có |
| Sprint | Tên sprint (vd "Sprint 1") | Có (khi tạo) |
| Task | Mô tả tiếng Anh/Nhật | Có |
| Sub-task Vietnamese | Mô tả tiếng Việt | Có |
| Assignee | Format `[Role] Tên`, dropdown | Có |
| Estimate (h) | Giờ ước tính ban đầu | Có |
| PLAN Start/End Date | Ngày kế hoạch | Có |
| Re-estimate (h) | Ước tính lại | Có |
| Actual Start/End Date | Ngày thực tế | Có |
| Actual Effort (h) | Giờ thực tế đã làm | Có |
| **Progress (%)** | **Công thức** = Actual Effort / Re-estimate | **Không** — chỉ đọc |
| Remaining (h) | Giờ còn lại | Có thể là công thức — không ghi tay, cần kiểm tra khi build |
| **Status** | dropdown theo enum ở `Config` | Có |
| Note | Ghi chú tự do | Có |

Enum `Status` (từ tab `Config`): `Open, Study, Code done, Reviewing, Testing, Verify bug, Done, In progress, N/A, ユーザー様確認待ち, Pending, Chờ KH phản hồi, Cancel`.

---

## 3. Kiến trúc

```
PM gõ trong Slack (kênh nexus-lab)
   → NexusBot (plugin "slack" có sẵn trong OpenClaw gateway trên server 192.168.4.15)
   → Skill "sheet-pm-tracker" (SKILL.md mới, openclaw-skills/, symlink vào workspace-hackathon/skills/)
   → gsheet-mcp (MCP server mới, bọc Google Sheets API)
   → Đọc/ghi đúng tab Sprint tương ứng
   → Trả lời trong Slack (preview, xác nhận, kết quả)
```

- **Auth Google**: Service Account, cấp quyền **Editor toàn file**.
- **Slack surface**: **không cần Claude Tag** — server `192.168.4.15` đã chạy sẵn OpenClaw gateway với plugin `slack` (bot NexusBot, socket mode, đang nhận `app_mention` trong kênh `nexus-lab`). Chỉ cần đăng ký `gsheet-mcp` vào gateway đó và symlink skill vào `~/.openclaw/workspace-hackathon/skills/`, giống hệt cách `jira-task`/`meeting-notetaker` đã làm.
- Theo đúng convention repo: `openclaw-skills/sheet-pm-tracker/SKILL.md` + `openclaw-skills/sheet-pm-tracker/gsheet-mcp/` (giống mẫu `vexa-mcp`).

---

## 4. gsheet-mcp — các tool cần có

| Tool | Việc làm | Ghi chú |
|---|---|---|
| `list_task_tabs()` | Liệt kê các tab dạng `Sprint N` hiện có trong file | Tự phát hiện tab mới, không hardcode |
| `get_current_sprint()` | Đọc `1.Summary Project`, tìm sprint có `Start Date ≤ hôm nay ≤ End Date` | Xem logic fallback mục 5 |
| `get_sprint_tasks(sprint_tab, filter?)` | Đọc toàn bộ rows của 1 tab Sprint | filter theo Assignee/Status |
| `find_task(keyword_or_no, sprint_tab?)` | Tìm 1 row theo No. hoặc tên Task gần đúng | Mặc định tìm trong sprint hiện tại |
| `append_task(sprint_tab, fields)` | Thêm 1 row mới vào đúng tab Sprint | Tự tăng cột `No.`, không đụng dòng tổng hợp |
| `update_task(sprint_tab, row_no, fields)` | Sửa 1 hoặc nhiều cell trên 1 row | **Không bao giờ ghi cột Progress** (công thức); không chèn/xoá cột |
| `get_progress_summary(scope)` | Đọc `1.Summary Project` (theo sprint/toàn dự án) hoặc tự đếm Status trong 1 sprint tab | scope: sprint hiện tại / toàn dự án / theo người |

---

## 5. Logic xác định "sprint hiện tại" theo thời gian thực

1. Đọc `1.Summary Project`, lấy danh sách sprint kèm `Start date`/`End date`.
2. Tìm sprint có `Start date ≤ hôm nay ≤ End date`.
3. **Nếu tìm thấy đúng 1** → dùng làm sprint mặc định cho Action 1/2/3 khi PM không chỉ định rõ.
4. **Nếu không tìm thấy sprint nào** (toàn bộ đã kết thúc, như tình trạng hiện tại của file — sprint gần nhất kết thúc 2026-01-30) → báo PM:
   > "Không có sprint nào đang chạy tính đến hôm nay (sprint gần nhất là <tên>, kết thúc <ngày>). Bạn muốn log/update vào sprint đó, hay đã có sprint mới cần tôi tạo tab?"
   Không tự đoán, không tự tạo tab mới nếu chưa được xác nhận.
5. **Nếu PM tự chỉ định sprint** ("log vào Sprint 3", "check tiến độ Sprint 7") → bỏ qua logic tự động, dùng thẳng sprint PM nói.

---

## 6. SKILL.md — hành vi (theo pattern đã dùng ở `jira-task`)

**Quy tắc bất biến (giữ nguyên tinh thần jira-task):**
- Giao tiếp tiếng Việt, không ghi sheet khi chưa preview + xác nhận, không tự đoán field bắt buộc thiếu, không tự retry khi lỗi.

### Action 1 — Log task mới
1. Nhận intent ("tạo task...", "log task...", "thêm task...").
2. Hỏi field bắt buộc còn thiếu: `Task`, `Type`, `Assignee`. Tuỳ chọn: `Sub-task Vietnamese`, `Estimate(h)`, `PLAN Start Date`.
3. Xác định sprint đích theo logic mục 5.
4. Map `Status` PM nói (nếu có) → đúng giá trị enum ở `Config`; nếu không khớp, liệt kê enum hợp lệ và hỏi lại.
5. Preview đầy đủ → xác nhận → `append_task`.

### Action 2 — Cập nhật task
1. Nhận diện task theo `No.` hoặc tên gần đúng, trong sprint đã chỉ định hoặc sprint hiện tại (mục 5).
2. Nếu trùng nhiều task → liệt kê, hỏi PM chọn theo `No.`.
3. Lấy state hiện tại, diff theo field muốn đổi (Status, Assignee, Estimate, Re-estimate, Actual Effort, ngày Actual...).
4. Nếu PM nói "cập nhật % xong" → **không ghi thẳng Progress**, hỏi lại Actual Effort tương ứng để công thức tự tính ra đúng %.
5. Preview chỉ phần thay đổi → xác nhận → `update_task`.

### Action 3 — Kiểm tra tiến độ
1. Nhận intent ("tiến độ sao rồi", "check progress", "sprint này còn bao nhiêu task chưa xong"...).
2. Xác định phạm vi: sprint cụ thể / toàn dự án / theo 1 assignee (mặc định sprint hiện tại theo mục 5 nếu PM không nói rõ).
3. Gọi `get_progress_summary`, trả lời gọn:
   - Toàn dự án: đọc `1.Summary Project` dòng `全システム進捗`.
   - 1 sprint: đếm task theo Status, liệt kê task quá hạn (PLAN End Date đã qua mà Status ≠ Done), liệt kê task có Note đáng chú ý (blocker).
   - Theo người: liệt kê task đang mở (Status ≠ Done/Cancel) của người đó, kèm Remaining(h) tổng.

---

## 7. Rủi ro / phức tạp cần lưu ý khi build

- **Sprint hiện tại có thể không tồn tại** (xem mục 5) — đây là tình trạng thực tế của file lúc này, phải test kỹ nhánh fallback, không được để bot tự chọn đại 1 sprint.
- **Không ghi cột Progress/Remaining trực tiếp** nếu là công thức — cần xác nhận công thức chính xác khi build (đọc formula thật trong cell) để biết chắc field nào bot được phép ghi.
- **Không chèn/xoá cột hoặc dòng tổng hợp** (row 8 mỗi tab Sprint có công thức tổng Estimate/Re-estimate/Progress) — chỉ ghi vào cell task cụ thể.
- **Format PIC** `[Role]Tên` không nhất quán khoảng trắng → cần fuzzy-match khi resolve assignee, không so khớp tuyệt đối.
- **Song ngữ**: cột Task tiếng Anh/Nhật, Sub-task tiếng Việt — khi log task mới cần hỏi rõ PM muốn điền cột nào.

---

## 8. Các bước triển khai

1. Tạo Google Cloud Service Account, share sheet cho email service account với quyền Editor, bật Sheets API.
2. Đọc formula thật của cột Progress/Remaining trong 1 tab Sprint để xác nhận chính xác field bot được/không được ghi.
3. Build `gsheet-mcp` với 6 tool ở mục 4 (đặc biệt kỹ `get_current_sprint()` với nhánh fallback), test độc lập (không qua Slack) trước.
4. Viết `openclaw-skills/sheet-pm-tracker/SKILL.md` theo mục 6.
5. Đăng ký `gsheet-mcp` vào cấu hình MCP của OpenClaw gateway trên `192.168.4.15` (nơi NexusBot đang chạy), symlink skill vào `~/.openclaw/workspace-hackathon/skills/sheet-pm-tracker` — giống hệt cách đã làm với `jira-task`.
6. Test 4 flow qua Slack thật (kênh `nexus-lab`): log task thiếu field, update task trùng tên, check progress, và **case không có sprint hiện tại** (fallback mục 5) — nên test trên 1 sprint tab nháp trước khi dùng tab thật.

---

## 9. Slack Interactive UX (nút bấm/menu chọn) — plan để review trước khi làm

### 9.1 Vì sao không làm modal/form kiểu Meetless

Đã verify trực tiếp trên gateway (`192.168.4.15`, bản OpenClaw `2026.7.1-2`, đã là bản mới nhất): `views.open` (API mở modal popup) **không có trong runtime đã cài** (chỉ có `views.publish` cho App Home). Muốn có modal thật phải fork/nâng cấp extension Slack — việc lớn, không làm trong scope này.

### 9.2 Giải pháp khả thi ngay: inline buttons/select (không phải modal)

Gateway hỗ trợ sẵn 2 directive để skill tự phát nút/menu ngay trong message trả lời (đã verify cú pháp từ source `interactive-replies-CXpT-vA_.js`):

```
[[slack_buttons: Label:value, Label2:value2]]        → tối đa 5 nút, click trả "value" về agent
[[slack_select: Placeholder | Label:value, ...]]     → tối đa 100 option (dropdown)
```

**Tiện hơn nữa**: nếu message kết thúc bằng 1 dòng `Options: A, B, C.` (2–12 từ đơn giản, chỉ chữ/số/space/`_`/`+`/`-`, không trùng nhau) thì hệ thống **tự động** biến thành nút/menu — không cần nhớ cú pháp `[[...]]`. Giới hạn 12 option nên chỉ dùng được cho enum ngắn (vd Type: BE/FE/BrSE/QC/Design/Common = 6 giá trị); enum dài hơn 12 (vd Status ở sheet cũ có 13 giá trị) phải dùng `[[slack_select:...]]` tường minh.

**Điều kiện bắt buộc**: cả 2 cách trên chỉ hoạt động khi `capabilities.interactiveReplies: true` được bật cho account Slack trong `openclaw.json` (đã verify: hiện **đang tắt** — key `capabilities` chưa tồn tại trong `channels.slack`). Cần sửa config + **restart gateway hackathon** để có hiệu lực — vì gateway đang phục vụ team thật qua NexusBot nên việc này cần xác nhận riêng trước khi làm (xem mục 9.5).

### 9.3 Flow đề xuất cho từng Action

**Action 1 — Tạo task mới:**
1. PM gõ 1 message dạng khối `key: value` (xem mẫu mục 9.6) hoặc câu tự nhiên.
2. Nếu thiếu `Type` → hỏi bằng select động (list Type có sẵn trong sprint đó, lấy qua `get_sprint_tasks`, không hardcode):
   `Chọn Type cho task: [[slack_select: Chọn Type | BE:BE, FE:FE, BrSE:BrSE, QC:QC]]`
3. Nếu thiếu `Assignee` → select từ danh sách người đã từng làm task trong sprint đó (lấy qua `get_sprint_tasks`, dedupe) — nếu sprint chưa có ai, fallback hỏi gõ tay tên.
4. Nếu PM cho `Status` không khớp `get_status_enum()` → hiện lại select đúng enum của project đó (không hardcode).
5. Bước xác nhận cuối, thay vì gõ "có/không":
   `Xác nhận tạo task? [[slack_buttons: Xác nhận:yes:primary, Huỷ:no:danger]]`
6. Agent nhận lại value (`yes`/`no`) như 1 message thường từ PM, xử lý y hệt hiện tại (chỉ khác PM không cần gõ chữ).

**Action 2 — Cập nhật task:** tương tự — select khi cần chọn giữa nhiều task trùng tên (label = "No.<n>: <task>"), select cho Status mới, buttons cho xác nhận cuối.

**Action 3 — Check tiến độ:** không bắt buộc cần interactivity; có thể thêm (tuỳ chọn, không phải v1) buttons gợi ý "Xem theo người / Xem sprint khác" cuối câu trả lời.

### 9.4 Giới hạn cần lưu ý

- Tối đa 5 nút / message → nếu enum có >5 giá trị (Type ở ví dụ trên) bắt buộc dùng `slack_select` (dropdown), không dùng `slack_buttons`.
- Đây là cơ chế "legacy directive" của gateway (comment trong source ghi `@deprecated`, khuyến nghị dài hạn chuyển sang "presentation payloads" mới hơn) — vẫn hoạt động ở bản đang cài, nhưng có thể đổi cách làm ở bản OpenClaw tương lai.
- Không thay thế được nhu cầu 1 form nhiều field nhập cùng lúc (vẫn phải hỏi tuần tự từng field thiếu, hoặc PM tự gõ đủ theo mẫu key:value).

### 9.5 Việc cần làm ở tầng hạ tầng (cần xác nhận riêng trước khi làm)

1. Sửa `~/.openclaw-hackathon/openclaw.json` → thêm vào `channels.slack`:
   ```json
   "capabilities": { "interactiveReplies": true }
   ```
2. Restart gateway hackathon (`launchctl kickstart` service tương ứng `ai.openclaw.hackathon.plist`, hoặc lệnh restart OpenClaw tương đương) — **gây gián đoạn NexusBot vài giây cho mọi người đang dùng trong kênh `nexus-lab`**, nên cần PM xác nhận thời điểm làm.

### 9.6 Mẫu input 1 lần cho PM (giảm hỏi qua lại)

```
@NexusBot tạo task
Task: Test API checkout
Type: BE
Assignee: SơnBH
Sprint: 2
Estimate: 4h
```
Chỉ `Task` bắt buộc; field nào thiếu bot mới hỏi lại (bằng select nếu đã bật interactivity, bằng câu hỏi text nếu chưa bật).

### 9.7 Việc cần làm để triển khai (sau khi review flow này)

1. Xác nhận với PM thời điểm bật cờ + restart gateway (mục 9.5).
2. Cập nhật `SKILL.md`: thêm cú pháp `[[slack_select]]`/`[[slack_buttons]]` vào các bước hỏi lại field thiếu và bước xác nhận, ở cả 3 Action.
3. Test qua Slack thật: field thiếu hiện đúng select, xác nhận hiện đúng buttons, click chọn được agent nhận đúng value.
