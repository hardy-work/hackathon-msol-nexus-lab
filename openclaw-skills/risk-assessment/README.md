# risk-assessment — Cách dùng

Skill giúp PM **đánh giá tiến độ dự án hằng ngày** từ dữ liệu tiến độ (Sprint tab + Resource plan + Overtime trên Google Sheet): sprint/người/category có nguy cơ không kịp deadline hay không, kèm đề xuất. Đồng thời đọc lại Risk/Isssue management thật để thống kê risk/issue đã có sẵn đang ở trạng thái nào.

**Skill này CHỈ ĐỌC + ĐÁNH GIÁ — không ghi gì vào Sheet.** Việc ghi risk/issue vào Risk/Isssue management do skill khác ("daily report") đảm nhiệm.

Rủi ro/issue chia 2 nguồn:
- **Đã có sẵn trên Sheet** — đọc trực tiếp Risk/Isssue management, chia theo Status: `Open`/`Pending` = "chưa xử lý", `In progress` = "đang xử lý" (`Done`/`Cancel` bỏ qua, coi như đã đóng).
- **Rule engine tự đánh giá** — 12 rule chia theo 4 layer **Người → Task → Sprint → Category** (layer chỉ là cách phân tích nội bộ, không hiện ra ngoài report), có cascade thật (vd 1 người nghỉ → tự tìm ra đúng sub-task/module bị ảnh hưởng). Report mặc định chỉ hiện phần tóm tắt "Đánh giá" (sprint/người/category có kịp không); chi tiết từng risk/issue chỉ đưa ra khi PM hỏi thêm.

Chưa cấu hình gì cả — cứ gõ thẳng yêu cầu, skill sẽ tự hỏi bạn link Google Sheet nếu cần.

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Quét đánh giá tiến độ | "đánh giá rủi ro dự án hôm nay", "sprint có kịp không", "check issue giúp tôi" |
| Hỏi chi tiết sau khi nhận đánh giá | "tại sao sprint lại không kịp", "chi tiết SơnBH bị sao" |

## Quy trình

1. `python scripts/scan.py` đọc Sprint tab + Resource plan + Overtime, áp 12 rule (P1-P4/T1-T4/S1-S2/M1-M2) + tính sức khỏe sprint (`compute_sprint_health`), đọc lại Risk/Isssue management thật (chỉ đọc), ghi report vào `drafts/`. **Không bao giờ ghi vào Sheet.**
2. Skill trình bày report trong chat — lấy nguyên văn từ field `narrative` mà `scan.py` in ra (mục Đánh giá + Chưa xử lý/Đang xử lý + tally).
3. PM hỏi thêm chi tiết cụ thể → agent tự tra trong field `passiveRisks`/`passiveIssues` của JSON block (đã chạy sẵn, không cần chạy lại `scan.py`) để trả lời.

Gộp toàn bộ đọc dữ liệu + rule engine + ghi report vào 1 lệnh Python để hạn chế số lần Claude Code phải hỏi quyền chạy lệnh.

## Cấu hình

Copy `config.example.json` → `config.json`, điền `fileId`/`currentSprint`/cấu trúc cột Sprint tab/`personCodeMap` (map người trong Resource plan ↔ Assignee trong Sprint tab). Copy `.env.example` → `.env`, chỉ cần `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` (API key đã bỏ hẳn — sheet private nên API key luôn 403, xác nhận qua test thật).

## Rule engine

Toàn bộ logic (đọc/chuẩn hoá Sprint tab, Resource plan, Overtime, 12 rule, sức khỏe sprint) nằm ở `scripts/lib/` — Python thuần chuẩn thư viện, không cài package ngoài. Mỗi module có test riêng cùng thư mục (`<tên>_test.py`). Chạy từng file:

```bash
cd scripts/lib
python rule_engine_test.py
python normalize_test.py
python resource_plan_test.py
python overtime_test.py
python summary_project_test.py
python draft_test.py
python google_auth_test.py
python load_env_test.py
```

Lệnh Python trên máy: `python` và `python3` đều chạy được, dùng lệnh nào cũng như nhau. Ký JWT (Service Account) qua `openssl` CLI (subprocess) thay vì cài `cryptography`/`PyJWT` — Python stdlib không có sẵn RSA signing như Node's `crypto`.

`scan.py` chỉ gọi các module trong `lib/` — không tự tính điểm/parse dữ liệu bằng tay trong SKILL.md.
