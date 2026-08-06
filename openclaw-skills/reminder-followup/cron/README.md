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
- **Không gõ đường dẫn tay vào prompt.** Bước 0 của cả 2 file tự dò `SKILL_DIR`
  rồi mọi lệnh sau đều đi qua biến đó:

  ```bash
  SKILL_DIR="$(openclaw config get agents.defaults.workspace 2>/dev/null)/skills/reminder-followup"
  [ -d "$SKILL_DIR" ] || SKILL_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/workspace/skills/reminder-followup"
  ```

  Phiên cron không chạy ở thư mục repo nên vẫn cần đường dẫn tuyệt đối — nhưng
  phải **tính ra**, không hardcode. Lý do dòng 1 hỏi `openclaw config` chứ không
  ghép `$HOME/.openclaw/workspace` luôn: **tên thư mục workspace cũng cấu hình
  được**, không cố định là `workspace`. Server hackathon (macOS, profile
  `hackathon`) có đường dẫn thật là
  `/Users/<user>/.openclaw-hackathon/workspace-hackathon/skills/…` — cả username,
  cả state dir, cả tên workspace đều khác. Chỉ suy từ `OPENCLAW_STATE_DIR` là
  vẫn ra sai, nên dòng 2 chỉ là lưới đỡ khi `openclaw config get` không chạy
  được.

  Đây từng là lỗi thật của repo này: 2 file prompt hardcode
  `/home/sonbh/.openclaw/workspace/...` trong khi `gg-sheet/SKILL.md` ngay bên
  cạnh đang cấm đúng chuyện đó. Deploy sang máy khác thì job **vẫn chạy, vẫn
  báo ok**, chỉ là gọi vào path không tồn tại → không nhắc ai, mỗi ngày 3 lượt,
  không ai biết.
- `BOT_USER_ID` và `CHANNEL` hardcode trong `job-b.prompt.txt` theo đúng kênh
  đang dùng — thêm kênh mới thì copy file, đổi 2 giá trị đó, tạo cặp job riêng.
