# gg-sheet-daily-report — Cách dùng

Skill giúp PM **tổng hợp report cuối ngày** dựa trên Google Sheet lịch trình dự án — cùng file/tab đang cấu hình trong skill [`gg-sheet`](../gg-sheet/). Chỉ **đọc** dữ liệu (API key), không ghi gì vào sheet.

## Điều kiện cần trước

- Đã cấu hình `config.json` qua skill `gg-sheet` (link Google Sheet + tab đã được resolve cấu trúc cột). Nếu chưa, skill này sẽ tự nhắc bạn chạy `gg-sheet` trước.
- Có `.env` trong thư mục này với `GOOGLE_SHEETS_API_KEY` (copy từ `.env.example`, dùng chung giá trị với `.env` của `gg-sheet`).

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Tổng hợp report cuối ngày | "check report hôm nay" |
| Check report 1 tab cụ thể | "tổng hợp report Sprint 1 hôm nay" |
| Check trễ tiến độ | "có task nào trễ trong Sprint 1 không?" |

## Skill trả lời 3 câu hỏi

1. Assignee nào đã cập nhật tiến độ hôm nay, ai chưa (dựa trên task đang "tới lượt chạy" theo lịch giờ tích luỹ, không phải worklog tự động như Jira — sheet không có timestamp).
2. Task nào hôm nay đã hết effort (`Remaining(h) = 0` hoặc `Progress = 100%`) mà `Status` chưa đổi — chỉ hiển thị, PM tự đánh giá.
3. Toàn tab: task nào bị trễ (`Re-estimate(h) Actual > Estimate(h) Plan`) và đề xuất dời lịch các task `Open` khác của cùng assignee.

Đây là skill **chỉ đọc** — mọi đề xuất reschedule đều cần bạn xác nhận rồi tự chạy qua skill `gg-sheet` (Action 2b: Re-schedule) để thực sự ghi vào sheet.
