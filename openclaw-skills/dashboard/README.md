# dashboard — Cách dùng

Skill giúp PM có **1 bản tóm tắt sức khỏe dự án** (tiến độ sprint hiện tại, risk/issue đang mở/đang xử lý) từ dữ liệu đã có sẵn trên Google Sheet, dùng để theo dõi hằng ngày và làm bằng chứng định lượng khi cần pitch/báo cáo ra ngoài team.

**Bản này đọc + ghi lại vào tab "Dashboard"** (tự tạo tab nếu chưa có, chỉ đụng đúng tab này). Đây là bước 1+2 trong lộ trình 5 bước (xem "Roadmap" bên dưới).

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Xem tổng quan dự án | "cho tôi dashboard dự án", "tổng quan tiến độ thế nào", "sức khỏe dự án hôm nay" |
| Hỏi chi tiết sau khi nhận tổng quan | "risk ưu tiên cao nào đang mở", "chi tiết issue X" |

## Quy trình

1. `python3 scripts/build_dashboard.py` đọc tab "Summary project" (tiến độ sprint hiện tại — sprint có Status chứa "In progress"), "Risk management" và "Isssue management" (đếm theo Status, cùng quy ước với skill `risk-assessment`: Open/Pending = chưa xử lý, In progress = đang xử lý, Done/Cancel = bỏ qua).
2. Nếu có cấu hình Service Account (`GOOGLE_SERVICE_ACCOUNT_KEY_FILE`), script ghi kết quả vào tab "Dashboard" — tự tạo tab nếu chưa có, xoá sạch nội dung cũ của CHÍNH tab đó rồi ghi lại (không đụng tab nào khác).
3. In ra JSON gồm `narrative` (text sẵn để trình bày trong chat), `summary` (số liệu thô), `written` + `dashboardTabUrl` (nếu đã ghi thành công).
4. Skill trình bày nguyên văn `narrative` trong chat, kèm link tab Dashboard nếu đã ghi.

## Cấu hình

Copy `config.example.json` → `config.json`, điền `fileId`, tên 3 tab nguồn, và `outputTab.name` (mặc định `"Dashboard"`). Copy `.env.example` → `.env`: `GOOGLE_SHEETS_API_KEY` để đọc, `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` để ghi (bỏ trống nếu chỉ muốn chạy chế độ đọc).

**Lưu ý tên tab:** điền đúng nguyên văn tên tab thật trên Sheet, kể cả khoảng trắng thừa nếu có — đã xác nhận trên sheet đang dùng chung, tab risk có tên thật là `"Risk management "` (thừa 1 dấu cách cuối), khác `"Isssue management"` (không thừa). Gõ sai/thiếu khoảng trắng sẽ ra lỗi `Unable to parse range` từ Sheets API.

**Service Account cần quyền Editor** trên spreadsheet (giống `gg-sheet`/`risk-assessment`) để tạo tab mới và ghi giá trị — chia sẻ file với email trong `service-account.json` (field `client_email`).

## Cấu trúc code

Theo đúng khuôn mẫu skill `risk-assessment`/`gg-sheet` trong repo này — tách phần gọi mạng (không test) khỏi phần tính toán thuần (có test cạnh mỗi module):

- `scripts/lib/sheets_client.py` — đọc Sheets API v4 bằng API key (không test, thuần I/O)
- `scripts/lib/sheets_write.py` — ghi Sheets API v4 bằng OAuth token (tạo tab/xoá/ghi, không test, thuần I/O)
- `scripts/lib/google_auth.py` — mint OAuth token từ Service Account JSON (copy nguyên bản từ `risk-assessment`, đã có test riêng)
- `scripts/lib/parse.py` — parse dòng "Summary project" + Risk/Issue management (số giờ/% kiểu dấu phẩy thập phân Việt Nam, tự dò cột theo tên header) — có test
- `scripts/lib/tally.py` — đếm Risk/Issue theo Status, lọc top ưu tiên cao — có test
- `scripts/lib/narrative.py` — build text hiển thị trong chat theo `OUTPUT-STYLE.md` — có test
- `scripts/lib/dashboard_rows.py` — build mảng 2 chiều để ghi vào tab Dashboard — có test
- `scripts/build_dashboard.py` — entrypoint duy nhất, gộp đọc + tính + ghi + in JSON

Chạy test từng module:

```bash
cd scripts/lib
python3 -m unittest parse_test tally_test narrative_test dashboard_rows_test google_auth_test
```

## Roadmap (xem thêm `NexusBot_Slide_Brief.md` ở gốc repo — Vision Giai đoạn 1)

1. **[Xong]** Đọc + tổng hợp trong chat
2. **[Xong]** Ghi kết quả vào tab "Dashboard" mới (tab riêng, không đụng tab nào khác)
3. Nối vào cron có sẵn của `reminder-followup` để tự động post Slack theo tuần
4. Mở rộng nguồn dữ liệu: `reminder-followup` log follow-up, `slack-evidence-sheet` log vòng thu thập bằng chứng
5. Deploy lên server (thêm vào `agents.defaults.skills`, rsync, kickstart)

Mỗi bước cần PM xác nhận riêng trước khi làm bước tiếp theo — bước 3 trở đi đụng vào lịch tự động hoặc skill khác đang chạy production.
