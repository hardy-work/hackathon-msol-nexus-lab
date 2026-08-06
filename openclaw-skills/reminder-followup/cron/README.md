# cron/ — prompt thật của 2 cron job

**Đây mới là thứ chạy lúc 09:00 / 16:30 / 17:00.** Phiên cron `isolated` không
tự đọc `SKILL.md` — nó chỉ có đúng cái prompt được nhét vào job. Sửa `SKILL.md`
mà quên apply lại prompt = **không có gì thay đổi ngoài Slack**.

Đây là lỗi đã xảy ra thật (05-08-2026): `SKILL.md` được sửa nhiều lần trong khi
prompt của job 09:00 vẫn giữ nguyên `<!here>` + template đời cũ, nên tin nhắc
mỗi sáng không hề đổi. Từ đó prompt được đưa vào repo để review/diff được cùng
skill.

| File | Job | Lịch |
|------|-----|------|
| [`job-a.prompt.txt`](job-a.prompt.txt) | `reminder-followup-0900` — đăng tin nhắc, tag từng người | `REMINDER_TIME` |
| [`job-b.prompt.txt`](job-b.prompt.txt) | `reminder-followup-1630` **và** `reminder-followup-1700` — follow-up trong thread | `FOLLOWUP_CRON_1/2` |

## Apply lên cron job đang chạy

```bash
cd openclaw-skills/reminder-followup
openclaw cron edit <id job 0900> --message "$(cat cron/job-a.prompt.txt)"
openclaw cron edit <id job 1630> --message "$(cat cron/job-b.prompt.txt)"
openclaw cron edit <id job 1700> --message "$(cat cron/job-b.prompt.txt)"
```

Lấy id bằng `openclaw cron list`. **Job B phải apply cho cả 2 job** — lệch nhau
là hai lượt nhắc hành xử khác nhau.

Kiểm lại: `openclaw cron list --json` rồi so `payload.message` với file ở đây.

## Lưu ý khi sửa

- Prompt cố ý **tự chứa** toàn bộ luật (không bảo agent đi đọc `SKILL.md`): nếu
  thiếu env thì skill tụt xuống `needs setup` và vô hình với bot, lúc đó prompt
  tự chứa vẫn chạy đúng. Đổi luật ở `SKILL.md` thì **phải sửa song song ở đây**.
- Đường dẫn script trong prompt là đường dẫn **tuyệt đối trong workspace của
  Gateway** (`~/.openclaw/workspace/skills/reminder-followup/scripts/...`), vì
  phiên cron không chạy ở thư mục repo. Đổi chỗ symlink thì phải sửa lại.
- `BOT_USER_ID` và `CHANNEL` hardcode trong `job-b.prompt.txt` theo đúng kênh
  đang dùng — thêm kênh mới thì copy file, đổi 2 giá trị đó, tạo cặp job riêng.
