# Luật trình bày tin nhắn

Áp cho **mọi chữ bot gửi ra cho người dùng**: tin Slack, reply trong thread, báo
lỗi, bảng tổng hợp report.

**Đang áp cho 4 skill:** [`reminder-followup`](reminder-followup/SKILL.md),
[`gg-sheet`](gg-sheet/SKILL.md),
[`gg-sheet-daily-report`](gg-sheet-daily-report/SKILL.md),
[`dashboard`](dashboard/SKILL.md) — tức là toàn bộ luồng
report hàng ngày qua Google Sheet.

Các skill khác (`jira-daily-report`, `jira-task-editor`, `slack-evidence-sheet`,
`meeting-notetaker`, `knowledge-base`) **cố ý chưa áp** — không phải quên.
Thêm skill mới vào luồng report thì áp luật này và ghi tên nó vào danh sách
trên.

## 1. Bôi đậm các giá trị dữ liệu

Bôi đậm đúng **5 loại**, vì đây là thứ người đọc cần bắt bằng mắt trong một tin
dài, không phải đọc từng chữ:

| Loại | Ví dụ trong tin |
| --- | --- |
| Id task | `**NEX-49**`, `**AU-1**`, `**R-02**` |
| Tên người | `**SơnBH**`, `**VinhNV**` |
| Số % tiến độ | `**90%**` |
| Số giờ | `**8h**`, `**7.5h**`, `**4h**` |
| Status | `**Done**`, `**In progress**`, `**Open**` |

**Viết HAI dấu sao `**Done**` kiểu Markdown chuẩn, KHÔNG phải một sao.** Nghe
ngược với tài liệu Slack (Slack dùng mrkdwn, ở đó `*x*` mới là đậm), nhưng bot
không nói chuyện thẳng với Slack: nó đi qua `openclaw message send`, và openclaw
**đọc chuỗi như Markdown rồi tự dịch sang mrkdwn**. Nên trong Markdown `*x*` là
*nghiêng*, và nó dịch ra đúng chữ nghiêng.

Đã thử thật trên Slack ngày 06-08-2026, cùng một kênh, cùng một lệnh:

| Gõ vào `--message` | Slack hiện ra |
| --- | --- |
| `*NEX-49*` | *NEX-49* — **nghiêng**, không phải đậm |
| `**NEX-49**` | **NEX-49** — đậm, đúng ý |

(Gõ tay `*NEX-49*` thẳng vào ô soạn thảo Slack lại ra **nguyên dấu sao** — đường
thứ ba, khác cả hai đường trên. Đừng lấy kết quả gõ tay để suy ra hành vi của
bot.)

Chỉ bôi đậm **giá trị**, không bôi đậm nhãn: `plan **8h**, thực tế **9h**`, không
phải `**plan** 8h`. Bôi đậm cả câu là không còn gì nổi bật nữa.

Mention `<@U0BK2KAN86B>` **để nguyên, không bọc sao** — Slack tự dựng chip tên
người, bọc thêm là hỏng chip.

## 2. Không bao giờ dùng icon

Không emoji, không ký hiệu trang trí, **kể cả** trong tin báo lỗi, tin xác nhận
đã ghi xong, hay tiêu đề bảng tổng hợp:

Cấm: ❌ ✅ ⚠️ 🎉 👍 🙌 📋 📊 🔴 ℹ️ 🕐 ✓ ✗ ⛔ 📁 🎙️ 📺 📝 …

Thay bằng chữ. Trạng thái thì gọi thẳng tên:

```
Sai:   ✅ Đã log AU-1 lên Sprint 1
Đúng:  Đã log *AU-1* lên Sprint 1

Sai:   ⚠️ Mình chưa đọc được sheet
Đúng:  Mình chưa đọc được sheet
```

Emoji do **dev gõ trong report** (`done ✅`) thì vẫn đọc/chấp nhận như thường —
luật này chỉ cấm bot **tự sinh ra** icon, không cấm bot hiểu icon người khác gõ.

## Phạm vi

Luật này áp cho **tin nhắn gửi đi**. Không áp cho:

- Ký hiệu `⚠️`/`⛔` trong file `.md` của repo — đó là biển báo cho người và cho
  model đọc tài liệu, không ai gửi nó cho dev.
- Field `emoji` trong metadata skill — đó là icon hiển thị của OpenClaw, không
  phải nội dung tin nhắn.
