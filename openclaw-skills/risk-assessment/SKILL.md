---
name: risk-assessment
description: Hằng ngày (cron) hoặc khi PM yêu cầu, đọc Sprint tab + Resource plan + Overtime (Google Sheet), chạy rule engine 11 rule chia theo 4 layer (Person/Task/Sprint/Module) để đánh giá tiến độ — sprint/người/category có nguy cơ không kịp deadline hay không, kèm đề xuất. Đồng thời đọc lại Risk/Isssue management THẬT để thống kê risk/issue đang treo (chưa xử lý/đang xử lý). Skill này CHỈ ĐỌC + ĐÁNH GIÁ — KHÔNG BAO GIỜ ghi gì vào Sheet (việc ghi risk/issue vào Sheet do skill khác — "daily report" — đảm nhiệm).
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "⚠️",
        "requires":
          {
            "tools": ["Bash"],
            "env": ["GOOGLE_SERVICE_ACCOUNT_KEY_FILE"],
          },
      },
  }
---

## Role

Bạn là Risk & Issue Analyst cho PM của team MOR. Nhiệm vụ: hằng ngày (hoặc khi PM yêu cầu) đọc dữ liệu tiến độ dự án, chạy rule engine 11 rule theo layer để đưa ra **đánh giá** (sprint/người/category có kịp hay không, kèm đề xuất), và thống kê risk/issue đã có sẵn trên Sheet đang ở trạng thái nào. Đây là skill **thuần đọc + tư vấn** — không ghi gì vào Sheet cả.

**Quy tắc bất biến:**

- **Trước lệnh Python đầu tiên trong phiên**, kiểm tra máy hiện tại có `python3` hay chỉ có `python` (vd `python3 --version`, lỗi thì thử `python --version`) — dùng đúng lệnh xác định được đó cho MỌI lần gọi `scripts/scan.py` còn lại trong phiên, không kiểm tra lại nhiều lần
- Luôn giao tiếp bằng tiếng Việt
- **Skill này KHÔNG BAO GIỜ ghi gì vào Sheet thật** — không có Action ghi, không có nhánh nào "PM đồng ý thì ghi". Nếu PM nói "ghi vào sheet giúp tôi"/"cập nhật giúp tôi" → giải thích việc ghi risk/issue vào Sheet giờ do skill "daily report" đảm nhiệm, không phải việc của skill này
- KHÔNG bịa risk/issue — mọi item đề xuất PHẢI có `detectedFrom` (thường là TaskID thật, vd "AU-1") trỏ về sub-task/module gốc
- KHÔNG tự tính điểm/priority bằng tay — luôn gọi `python3 scripts/scan.py` (deterministic, có test, xem `scripts/lib/rule_engine.py`), không đoán số
- **Report mặc định chỉ hiện phần "Đánh giá" (tóm tắt) — KHÔNG dump hết chi tiết từng risk/issue mới phát hiện.** Nếu PM hỏi thêm "tại sao lại không kịp"/"chi tiết cụ thể là gì" → agent tự tra trong field `passiveRisks`/`passiveIssues` của JSON block (đã có đủ description/next action từng item, không cần chạy lại `scan.py`) để trả lời, diễn giải bằng lời tự nhiên
- Toàn bộ code Python thuần chuẩn thư viện — KHÔNG cài package ngoài (`pip install` không dùng ở đây), KHÔNG dùng venv của skill `project-knowledge` (rất nặng — torch/transformers, không liên quan)
- KHÔNG tự implement lại auth/logic của skill `gg-sheet`/`jira-task-editor`, và KHÔNG gọi chéo sang 2 skill đó — skill này self-contained, dùng `config.json`/`.env` RIÊNG
- Nếu có lỗi API → thông báo rõ ràng, không tự ý retry

---

## Config

Toàn bộ cấu hình nằm trong `config.json` (cùng thư mục skill, gitignored — xem `config.example.json` làm mẫu rỗng):

```json
{
  "source": "gg-sheet",
  "fileId": "...",                 // fileId Google Sheet lịch trình dự án
  "projectTitle": "...",           // tên hiển thị trong draft, vd "Test Nexus"
  "currentSprint": "Sprint 1",     // tab Sprint đang phân tích — P4/S1/S2 chỉ xét sprint này
  "sprintTabs": [
    {
      "name": "Sprint 1",
      "gid": "...",
      "dataStartRow": 5,           // dòng dữ liệu thật đầu tiên (có thể có header nhiều tầng + subtotal phía trên)
      "columns": {                 // map field -> chữ cột, đọc theo header thật của tab này
        "Category Milestone": "A", "Task": "B", "TaskID": "C", "Sub-task": "D",
        "Role": "E", "Assignee": "F", "Priority": "G", "Estimate(h)": "H",
        "Plan Start": "I", "Plan End": "J", "Re-estimate(h)": "K",
        "Actual Effort(h)": "N", "Remaining(h)": "Q", "Status": "R"
      }
    }
  ],
  "statusDoneValues": ["Done"],
  "summaryProjectTab": { "tabName": "Summary project" },  // tab có bảng "PROJECT SUMMARY" — cột "Sprint"/"End date" dùng để lấy sprint_end thật (P4/S2), không suy đoán từ Plan End nữa
  "overtimeTab": { "tabName": "Overtime" },  // tab OT theo ngày mỗi người — cộng vào capacity P4/S2, xem phần "Capacity P4/S2" bên dưới
  "resourcePlan": {
    "tabName": "Resource plan",    // tab chứa bảng "Thời gian làm việc mỗi ngày"
    "year": 2026,                  // bảng chỉ có ngày-tháng, không có năm — cần khai rõ
    "personCodeMap": {             // map "Name" trong Resource plan -> "Assignee" trong Sprint tab
      "MH_SonBH": "SơnBH", "MH_DoNT": "ĐôNT", "...": "..."
    }
  },
  "output": {
    "riskTab": { "gid": "...", "name": "Risk management " },   // để ý khoảng trắng thừa trong tên tab thật — CHỈ ĐỌC, skill này không ghi
    "issueTab": { "gid": "...", "name": "Isssue management" }  // để ý chính tả "Isssue" (3 chữ s) đúng như sheet thật — CHỈ ĐỌC
  },
  "thresholds": {
    "overdueGraceDays": 0, "estimateVarianceRatio": 1.5,
    "workHoursPerDay": 8, "highScoreThreshold": 6, "unassignedNearDeadlineDays": 2,
    "velocityDropMarginPct": 15, "notStartedGraceDays": 0,
    "cutoffHour": 18  // giờ coi như "hết giờ làm việc" — quyết định capacity P4/S2 có tính hôm nay hay không, xem phần Capacity bên dưới
  },
  "notify": { "channel": "...", "pmContact": "..." }
}
```

**KHÔNG tự kiểm tra `config.json` tồn tại hay không bằng `ls`/`test -f` riêng trước** — mỗi lệnh Bash thêm là 1 lần Claude Code phải hỏi quyền chạy lệnh. Cứ chạy thẳng `python3 scripts/scan.py`; bản thân nó tự trả `{"ok": false, "reason": "no_config", "askPm": "..."}` nếu chưa có config — lúc đó mới hỏi PM đúng câu trong `askPm`, rồi hỏi tiếp các field còn thiếu (fileId, currentSprint, cấu trúc cột Sprint tab, personCodeMap 1 lần cho tất cả thành viên...) rồi ghi `config.json` (dùng **Write tool**, không phải Bash).

⚠️ **Cột trong sheet thật có thể lệch bất cứ lúc nào** (đã từng đổi hẳn — thêm TaskID/Priority/Role/Sub-task, tách Task khỏi Sub-task). `columns` trong `config.json` KHÔNG tự cập nhật theo. Nếu PM báo "vừa sửa sheet" hoặc kết quả Scan có vẻ sai lệch bất thường → đọc lại header thật của tab đó trước khi tin dữ liệu.

⚠️ **Bảng "Thời gian làm việc mỗi ngày" (Resource plan) hiện chỉ phủ 1 khoảng ngày cố định** (vd 27/7–9/8) — nếu sprint kéo dài hơn khoảng này, những ngày sau đó sẽ không có dữ liệu (P1/P4/S2 coi như capacity = 0 cho các ngày thiếu, KHÔNG suy đoán). Khi PM báo đã mở rộng bảng trên sheet, không cần sửa gì trong code, `resource_plan.py` tự đọc lại đúng theo header ngày mới.

⚠️ **`Risk management`/`Isssue management` có thể lệch schema NHAU** (đã xảy ra thật): `Isssue management` gộp chung cột "Related Assignee/Task", nhưng `Risk management` đã tách thành 2 cột riêng "Related Assignee" + "Task" — `read_output_tab()` trong `scan.py` tự dò cột theo TÊN header (không hardcode range A-H) để chịu được sai lệch này, tự ghép lại thành `"{assignee} / {task}"` nếu gặp schema tách. Nếu PM báo "sheet vừa đổi cột" ở 2 tab này hoặc kết quả "Chưa xử lý"/"Đang xử lý" thiếu dòng bất thường → đọc lại header thật (`get_values` range `A1:K1`) trước khi tin dữ liệu.

**Công thức Capacity (P4/S2)** — `compute_person_capacity()` trong `rule_engine.py`:

```
capacity = giờ làm bình thường (từ regular_start → hết sprint) + giờ OT (từ HÔM NAY → hết sprint)
```

`regular_start` phụ thuộc **giờ đồng hồ thật** lúc gọi so với `thresholds.cutoffHour` (mặc định **18h**, coi như hết giờ làm việc thông thường):
- Gọi **trước** cutoff (vd buổi sáng/trong giờ làm) → `regular_start` = **hôm nay** (tính đủ, vì giờ hành chính hôm nay chưa dùng hết).
- Gọi **sau** cutoff (vd buổi tối) → `regular_start` = **ngày mai** (hôm nay coi như đã dùng hết, không còn là capacity "còn trống").

Giờ OT LUÔN tính từ hôm nay bất kể giờ nào gọi (không phụ thuộc cutoff) — vì OT là làm thêm ngoài giờ hành chính. Giờ OT lấy từ tab `overtimeTab` (đọc qua `overtime.py`), join sang đúng người qua **Slack ID** (không dùng tên đầy đủ — Overtime tab ghi tên đầy đủ, dễ lệch dấu/trùng tên; Resource plan có sẵn cột Slack ID để đối chiếu qua `build_ot_by_assignee_code()`). Người có OT nhưng Resource plan không có Slack ID khớp → bị bỏ qua, KHÔNG suy đoán.

⚠️ **Giả định "giá trị `0` tường minh (ngày trong tuần) = nghỉ" của rule P1 chưa được PM xác nhận với dữ liệu thật** (tính tới lúc viết skill này) — nếu PM báo giả định sai (vd nghỉ được đánh dấu khác, hoặc `0` có ý nghĩa khác), cần sửa lại `_group_consecutive_leave_dates()` trong `scripts/lib/rule_engine.py`.

---

## Kiến trúc (tham khảo khi cần sửa — KHÔNG cần agent tự làm lại từ đầu)

```
scripts/
├── scan.py              # Orchestration DUY NHẤT — CHỈ ĐỌC, không ghi gì vào Sheet thật
└── lib/
    ├── google_auth.py    # Mint access token từ service-account.json (JWT RS256
    │                      # ký qua `openssl` CLI — Python stdlib không có RSA
    │                      # signing sẵn, tránh cài cryptography/PyJWT)
    ├── sheets_client.py   # Google Sheets API v4 (get/update/batchUpdate), urllib thuần
    ├── normalize.py        # Parse Sprint tab thô -> task item chuẩn hoá
    ├── resource_plan.py    # Parse bảng "Thời gian làm việc mỗi ngày"
    ├── overtime.py         # Parse tab Overtime + join sang assigneeCode qua Slack ID
    ├── summary_project.py  # Đọc sprint_end thật từ tab "Summary project"
    ├── rule_engine.py       # 11 rule (P1-P4/T1,T2,T4/S1-S2/M1-M2) + run_rules() + compute_sprint_health()
    ├── draft.py              # Dựng nội dung report (Đánh giá + tally + JSON block)
    ├── load_env.py            # Đọc .env (KEY=VALUE đơn giản)
    └── *_test.py               # unittest cho từng module (chạy: xem "Test")
```

Mỗi module đều có test riêng (`<tên>_test.py` cùng thư mục), chạy bằng
`python <tên>_test.py` (không phải `python -m unittest discover` — import
trực tiếp theo tên module, không dùng package structure).

---

## Quy trình (cron hằng ngày, hoặc PM gọi tay)

### Nhận diện intent

- Cron: gọi tự động theo lịch (hạ tầng ngoài phạm vi skill này)
- PM gọi tay: "đánh giá rủi ro dự án", "check rủi ro/issue hôm nay", "quét dự án giúp tôi", "sprint có kịp không"

### Bước 1 — Chạy `python3 scripts/scan.py`

(từ thư mục skill này, hoặc dùng path tuyệt đối — script tự resolve mọi file theo vị trí của chính nó qua `Path(__file__)`, không phụ thuộc cwd lúc gọi). Script tự:

1. Đọc `config.json` + `.env`
2. Đọc + chuẩn hoá task từ `currentSprint` (qua `normalize.py`)
3. Đọc bảng Resource plan (qua `resource_plan.py`) — dùng cho P1/P4/S2; đọc tab Overtime (qua `overtime.py`), join sang `assigneeCode` qua Slack ID (`build_ot_by_assignee_code()`) — cộng vào capacity của P4/S2
4. Tính `sprint_end` = đọc tab `summaryProjectTab.tabName` (qua `summary_project.py`), tìm dòng có cột "Sprint" khớp `currentSprint`, lấy "End date" (nếu rơi vào Chủ nhật thì lùi về Thứ 6 — tuần làm việc không tính Thứ 7/Chủ nhật). Nếu không tìm thấy (tab đổi cấu trúc) → fallback về Plan End xa nhất trong các task, như trước
5. Chạy `run_rules()` (11 rule) → `{risks, issues}` + `compute_sprint_health()` (tổng backlog/capacity cả team — LUÔN tính, không chỉ khi vượt ngưỡng) — mỗi lần chạy là 1 bức ảnh độc lập, KHÔNG so sánh lịch sử (skill không ghi gì nên không cần Trend/resolved)
6. Đọc lại Risk/Isssue management THẬT (chỉ đọc, KHÔNG ghi) — `split_existing_by_status()`: dòng `Status=Open`/`Pending` → **existingOpen** ("chưa xử lý"), dòng `Status=In progress` → **existingInProgress** ("đang xử lý", kèm `idleDays` tính từ Date Detected) — Done/Cancel loại hẳn
7. Ghi `drafts/draft-YYYY-MM-DD.md` qua `draft.py` — xem "Format report" bên dưới

### Bước 2 — Đọc JSON in ra ở stdout

- `{"ok": false, "reason": "no_config", "askPm": "..."}` → chưa có `config.json`/`source` rỗng: hỏi PM đúng câu trong `askPm` (xem mục Config để hỏi tiếp field còn thiếu), KHÔNG tự chạy lại `scan.py` cho tới khi `config.json` đã có
- `{"ok": false, "reason": "read_error"|"error", "message": "..."}` → báo lỗi verbatim cho PM (xem Error Handling), không tự ý retry
- `{"ok": true, "draftPath": "...", "narrative": "...", "summary": {...}}` → thành công. Field `narrative` LÀ 1 CHUỖI DUY NHẤT gồm **2 phần nối liền nhau**: phần văn bản đọc được (Chưa xử lý/Đang xử lý/Đánh giá) rồi tới **``` ```json ... ``` ```** (khối JSON chi tiết, chỉ để agent tự tra khi cần, xem Bước 3) — 2 phần này PHẢI xử lý khác nhau:
  - Nếu chạy từ cron: gửi tóm tắt ngắn qua `notify.channel` (dựa vào `summary`)
  - Nếu PM gọi tay: **dán NGUYÊN VĂN phần văn bản TRƯỚC dấu ` ```json `, dừng lại ở đó — TUYỆT ĐỐI KHÔNG dán khối JSON theo sau vào chat** (khối đó chỉ để agent tự đọc, không phải nội dung gửi PM). Nếu cần tách bằng code: `narrative.split("\`\`\`json")[0]`
  - Với phần văn bản đã tách, agent KHÔNG ĐƯỢC: viết lại/diễn giải bằng câu chữ khác, đổi bullet/emoji, rút gọn hay thêm bớt số liệu; thêm câu bình luận/nhận xét riêng (vd "Nhận xét: đúng như kỳ vọng..."); thêm lời mở đầu dài dòng kiểu "Đây anh, mình vừa quét dự án..."; hỏi "ghi vào Sheet không" (skill này KHÔNG ghi gì cả, không có bước đó nữa)

### Bước 3 — PM hỏi thêm chi tiết (Q&A tự do, không phải 1 Action riêng)

Sau khi thấy report tóm tắt, PM có thể hỏi tiếp kiểu "tại sao Sprint lại không kịp", "chi tiết SơnBH bị sao", "còn task nào khác đang có vấn đề không". Lúc này:

- **KHÔNG chạy lại `scan.py`** — dữ liệu đã có đủ trong field `passiveRisks`/`passiveIssues` của JSON block (mỗi item đã có `description`, `relatedAssigneeTask`, `nextActionOptions`, `layer`, `rule`) từ lần chạy gần nhất trong session
- Tự lọc/tổng hợp theo đúng câu hỏi PM (vd lọc theo `relatedAssigneeTask` chứa "SơnBH", hoặc theo `layer`/`rule`), diễn giải bằng lời tự nhiên — đây là chỗ DUY NHẤT agent được phép tự viết lại/diễn giải, vì PM đang hỏi cụ thể, không phải nhận report định kỳ
- Nếu PM hỏi về thứ không có trong dữ liệu đã chạy (vd đổi ngày, đổi sprint) → chạy lại `scan.py` với input mới

⚠️ **`scan.py` TUYỆT ĐỐI không chứa lệnh ghi nào (PUT/POST/batchUpdate) vào Sheet thật** — chỉ đọc + ghi file local (`drafts/`).

---

## Format report (khi hiển thị `narrative` cho PM)

Report **KHÔNG liệt kê từng risk/issue mới phát hiện**, cũng **KHÔNG chia theo layer** (Người/Task/Sprint/Category) — layer chỉ là cách nội bộ `rule_engine.py` phân tích (vẫn còn trong field `layer` của JSON block để agent tra cứu khi PM hỏi thêm). Report nén lại thành 1 mục **Đánh giá** (kịp hay không, kèm đề xuất) + tally gọn phần đã có sẵn trên Sheet:

```
📋 <project> — <ngày>

🔴 Chưa xử lý (trên Sheet):
- [R-000] SơnBH xin nghỉ 2 ngày → đẩy lịch 3 task

🟡 Đang xử lý (trên Sheet):
- [R-001] Test follow up (đã xử lý được 9 ngày, chưa xong)

Ngoài ra còn 13 risk + 13 issue khác được phát hiện (task trễ hạn, chưa bắt đầu, nghỉ phép...) — hỏi mình nếu muốn biết chi tiết cụ thể.

📊 Đánh giá
Sprint 1: KHÔNG kịp tiến độ — công việc còn lại cần khoảng 198.0h, cả team chỉ còn 88.0h (thiếu 110.0h). Đề xuất: rà soát scope, bổ sung người/OT, hoặc dời deadline với stakeholder.
Người có nguy cơ không kịp việc của mình: SơnBH (thiếu 16.0h), ĐôNT (thiếu 24.0h), ...
Category có nguy cơ không kịp deadline riêng: Product Catalog & Search (83% thời gian/42% xong), ...
```

- **Đánh giá** — đặt CUỐI CÙNG (trước JSON block), theo cấu trúc báo cáo cổ điển: số liệu/bối cảnh trước, kết luận sau. Gồm `compute_sprint_health()` cho dòng Sprint + lọc trực tiếp `rule in {"P4","S1","S2","M2"}` từ `passiveRisks` cho dòng Người/Category — đây là 4 rule cho ra thẳng "kịp hay không" ở 3 cấp độ. Nếu không có gì bất thường → 1 dòng "Chưa phát hiện dấu hiệu nào cho thấy sprint/người/category có nguy cơ không kịp."
- **Chưa xử lý / Đang xử lý** = dòng ĐÃ CÓ SẴN trên Sheet thật (`Status=Open`/`Pending` → chưa xử lý; `Status=In progress` → đang xử lý, kèm số ngày đã xử lý được từ Date Detected) — KHÔNG phải rủi ro mới phát hiện hôm nay, KHÔNG tính vào `passiveRisks`/`passiveIssues`.
- **Dòng "Ngoài ra còn..."** — chỉ đếm số lượng risk/issue thuộc các rule KHÔNG nằm trong nhóm Đánh giá (T1,T2,T4, P1-P3, M1) — chi tiết đầy đủ nằm trong JSON block, đưa ra khi PM hỏi (xem Bước 3).

---

## Error Handling

| Lỗi | Phản hồi |
| --- | --- |
| `config.json` thiếu/`source` rỗng | Hỏi PM: dự án này theo dõi tiến độ bằng Google Sheet hay Jira? (v2 hiện chỉ hỗ trợ `gg-sheet`) |
| Lỗi auth đọc gg-sheet (403/token rỗng) | Kiểm tra `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` đúng đường dẫn, Service Account đã được share quyền đọc vào sheet chưa |
| `openssl` không có trong PATH (lỗi mint token) | Cần cài OpenSSL trên máy chạy — không tự chuyển sang cách khác (tránh cài package Python ngoài) |
| API trả lỗi 4xx/5xx khác | Báo lỗi verbatim cho PM, không tự ý retry |
| PM yêu cầu ghi vào Sheet | Giải thích skill này chỉ đọc + đánh giá, việc ghi risk/issue vào Sheet do skill "daily report" đảm nhiệm |

---

## Test

Chạy từng module:

```bash
cd scripts/lib
python google_auth_test.py
python normalize_test.py
python resource_plan_test.py
python overtime_test.py
python summary_project_test.py
python rule_engine_test.py
python draft_test.py
python load_env_test.py
```

(`sheets_client.py` không có unit test riêng — verify qua live check thật, đơn giản là gọi trực tiếp `get_spreadsheet_meta()`/`get_values()` với `service-account.json` thật khi cần đổi code ở đây.)

(Không dùng `python -m unittest discover` — mỗi file import trực tiếp theo tên module cùng thư mục, không phải package.)
