---
name: dashboard
description: Khi PM yêu cầu "tổng quan dự án"/"dashboard"/"cho tôi số liệu để pitch", đọc tab "Summary project" + "Risk management" + "Isssue management" (Google Sheet đang dùng chung), tổng hợp thành 1 bản tóm tắt sức khỏe dự án — tiến độ sprint hiện tại, risk/issue đang mở/đang xử lý, top risk ưu tiên cao — và ghi lại vào tab "Dashboard" (tự tạo nếu chưa có, chỉ đụng đúng tab này).
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "requires":
          {
            "tools": ["Bash"],
            "env": ["GOOGLE_SHEETS_API_KEY", "GOOGLE_SERVICE_ACCOUNT_KEY_FILE"],
          },
      },
  }
---

## Role

Bạn tổng hợp 1 bản "sức khỏe dự án" ngắn gọn cho PM từ dữ liệu đã có sẵn trên Google Sheet, và lưu lại vào tab "Dashboard" để tra cứu/pitch sau này — không tự đánh giá/suy diễn thêm gì ngoài số liệu đọc được (việc đánh giá rủi ro sâu là việc của skill `risk-assessment`, không phải skill này).

**Quy tắc bất biến:**

- **Trước lệnh Python đầu tiên trong phiên**, kiểm tra máy hiện tại có `python3` hay chỉ có `python` — dùng đúng lệnh xác định được đó cho MỌI lần gọi `scripts/build_dashboard.py` còn lại trong phiên, không kiểm tra lại nhiều lần
- Luôn giao tiếp bằng tiếng Việt
- **Ghi vào Sheet CHỈ được đụng đúng 1 tab "Dashboard"** (script tự tạo tab nếu chưa có, tự xoá sạch nội dung cũ của CHÍNH tab đó rồi ghi lại — không bao giờ đụng "Summary project"/"Risk management"/"Isssue management" hay bất kỳ tab nào khác). Đây là dữ liệu tổng hợp tự động, không phải nội dung PM gõ tay, nên KHÔNG cần xin xác nhận trước mỗi lần ghi như `gg-sheet`/`jira-task-editor` — nhưng nếu PM yêu cầu đổi tên tab output hoặc lo ngại về việc ghi, dừng lại hỏi trước khi tiếp tục
- KHÔNG tự tính/suy diễn số liệu bằng tay — luôn gọi `python3 scripts/build_dashboard.py`, không đoán số
- Toàn bộ code Python thuần chuẩn thư viện — KHÔNG cài package ngoài
- KHÔNG tự implement lại logic của `risk-assessment`/`gg-sheet` — skill này self-contained, dùng `config.json`/`.env` RIÊNG, chỉ đọc lại đúng 3 tab đã liệt kê ở trên
- Nếu có lỗi API (đọc hoặc ghi không được) → thông báo rõ tên tab lỗi, không tự ý retry, không bịa số liệu thay vào
- Áp dụng [`OUTPUT-STYLE.md`](../OUTPUT-STYLE.md): bôi đậm 2 dấu sao cho giá trị (task ID, tên người, %, giờ, status), không dùng emoji trong tin gửi cho PM

---

## Config

Toàn bộ cấu hình nằm trong `config.json` (cùng thư mục skill, gitignored — xem `config.example.json` làm mẫu rỗng):

- `fileId` — ID spreadsheet đang dùng chung cho báo cáo tiến độ
- `sourceTabs.summaryProject.name` / `sourceTabs.riskManagement.name` / `sourceTabs.issueManagement.name` — tên 3 tab đọc dữ liệu (khớp đúng tên tab thật trên Sheet, kể cả khoảng trắng thừa nếu có)
- `outputTab.name` — tên tab ghi kết quả, mặc định `"Dashboard"`

`.env` cần `GOOGLE_SHEETS_API_KEY` (đọc) và `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` (ghi — nếu để trống, script vẫn chạy được nhưng chỉ đọc, không ghi vào tab Dashboard).

Nếu `config.json` chưa tồn tại hoặc thiếu field → hỏi PM link Google Sheet + tên 3 tab, không tự đoán.

## Quy trình

1. Chạy `python3 scripts/build_dashboard.py` — script tự đọc `config.json`/`.env`, gọi Sheets API để đọc + tổng hợp + ghi lại tab "Dashboard", in JSON ra stdout.
2. Nếu `ok: false` → đọc `reason`/`message`, báo PM đúng nguyên văn lỗi, KHÔNG tự bịa số liệu.
3. Nếu `ok: true` → lấy nguyên văn field `narrative` trình bày trong chat (đã theo đúng OUTPUT-STYLE). Nếu `written: true`, thêm 1 dòng báo đã lưu vào tab Dashboard kèm `dashboardTabUrl`. Nếu `written: false` kèm `writeError`, báo PM lỗi ghi (đọc vẫn hiển thị bình thường).
4. PM hỏi thêm chi tiết 1 risk/issue cụ thể → tra trong field `summary.topHighPriorityRisks` (đã có sẵn trong JSON, không cần chạy lại script) để trả lời; nếu cần phân tích sâu hơn (vd "tại sao lại trễ") → gợi ý PM hỏi skill `risk-assessment`.

## Không nằm trong phạm vi bản v2 này

- Chưa có số liệu "năng suất follow-up" (`reminder-followup`) và "bằng chứng" (`slack-evidence-sheet`) — 2 skill đó hiện chưa log dữ liệu ra chỗ tổng hợp được
- Chưa tự động chạy theo lịch (cron) — chạy khi PM yêu cầu trong chat
- Chưa deploy lên server production
