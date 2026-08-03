# roster/

Danh sách người phải report, **tách theo từng nhóm**: mỗi kênh Slack 1 file
`<SLACK_CHANNEL_ID>.json`. Thêm nhóm mới = thêm 1 file + 1 cặp cron job trỏ
vào channel đó — không phải sửa `SKILL.md`.

```
roster/
  C0BKLP5KYD7.json   # nhóm #daily-report
  C0BKAAAAAAA.json   # nhóm khác, roster riêng
```

Format (`id` là Slack user ID, `name` chỉ để người đọc file cho dễ — bot
mention bằng `id`):

```json
[
  { "id": "U0BKL0DJV7B", "name": "Kiên" },
  { "id": "U0BKKXXXXXX", "name": "Tên nhân viên khác" }
]
```

Lấy user ID: Slack → profile người đó → **More** → *Copy member ID*.

Roster là **nguồn duy nhất** xác định ai phải report — bot không đọc danh
sách thành viên kênh nữa. Ai không có trong file thì không bị nhắc dù đang ở
trong kênh (khách, bot, PM chỉ ngồi xem). Ai nghỉ việc/chuyển nhóm thì xoá
khỏi file, có hiệu lực ngay lần chạy kế tiếp, không cần restart Gateway.

File `*.json` trong thư mục này bị gitignore vì chứa tên nhân viên thật; chỉ
`*.example.json` được commit.
