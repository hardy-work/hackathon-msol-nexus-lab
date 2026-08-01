# gg-sheet — Cách dùng

Skill giúp PM **thêm / sửa / xóa task** trong Google Sheet lịch trình dự án bằng ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh). Skill **chỉ CRUD từng dòng task**, KHÔNG dùng để tổng hợp/báo cáo tiến độ.

Chưa cấu hình gì cả — cứ gõ thẳng yêu cầu, skill sẽ tự hỏi bạn link Google Sheet nếu cần.

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Thêm task | "thêm task Fix bug login vào Sprint 1, assignee H.Anh, estimate 4h" |
| Sửa task | "sửa task No.28 sang Status Done" |
| Xóa task | "xóa task No.267 ở tab Backlog" |

## Quy trình mỗi thao tác

1. Hỏi lại nếu thiếu thông tin (tab, No. task, field cần sửa...) — không tự đoán.
2. Hiển thị **preview** thay đổi, chờ bạn xác nhận (có/không) trước khi ghi thật vào sheet.
3. Nếu task có Assignee, tự kiểm tra tổng giờ/lịch của người đó và đề xuất cách xử lý nếu bị lệch.
4. Ghi log lại thao tác sau khi thành công.

Riêng **Xóa task** sẽ có cảnh báo riêng vì khó hoàn tác (khôi phục được qua Version History của Google Sheets nếu lỡ tay).
