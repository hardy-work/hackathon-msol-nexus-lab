# gg-sheet — Cách dùng

Skill giúp PM **thêm / sửa / xóa task** trong Google Sheet lịch trình dự án bằng ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh). Skill **chỉ CRUD từng dòng task**, KHÔNG dùng để tổng hợp/báo cáo tiến độ.

Chưa cấu hình gì cả — cứ gõ thẳng yêu cầu, skill sẽ tự hỏi bạn link Google Sheet nếu cần.

## Cài đặt (bắt buộc, 1 lần)

Viết xong `SKILL.md` là **chưa đủ** — bot không thấy skill nào không nằm trong
workspace của Gateway. Cần đủ 3 bước:

```bash
ln -sfn "$(pwd)" ~/.openclaw/workspace/skills/gg-sheet
```

Thêm dòng này vào `~/.config/systemd/user/openclaw-gateway.service.d/override.conf`
(Linux/systemd) rồi `systemctl --user daemon-reload && systemctl --user restart openclaw-gateway.service`:

```
EnvironmentFile=-/duong/dan/toi/openclaw-skills/gg-sheet/.env
```

```bash
openclaw skills info gg-sheet   # phải thấy "✓ Ready" và "Visible to model: yes"
```

### Đường dẫn — cái gì portable, cái gì không

Gateway chạy với cwd là `~/.openclaw/workspace`, **không** phải thư mục repo, nên
đường dẫn tương đối trong tài liệu/lệnh sẽ trỏ vào hư không. Nhưng hardcode
`/home/<user>/…` cũng sai vì mỗi máy/server một đường dẫn. Cách xử lý:

| Chỗ | Dạng đường dẫn | Vì sao |
| --- | --- | --- |
| `SKILL.md` | `$SKILL_DIR`, tính từ `${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/workspace/skills/gg-sheet` | Chạy được trên mọi máy/user, và đúng cả khi dùng `--profile` riêng |
| `scripts/get-token.sh` | tự dò thư mục của chính nó qua `readlink -f "${BASH_SOURCE[0]}"` | Không phụ thuộc cwd, không cần biến env nào |
| `.env` → `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` | tương đối (`service-account.json`) | `get-token.sh` tự tính từ thư mục skill; ghi tuyệt đối cũng được, script nhận cả hai |
| `override.conf` → `EnvironmentFile=` | **tuyệt đối, bắt buộc** | systemd không nở `$HOME` hay `~`. Đây là file cấu hình của từng máy, không commit — sửa tay khi deploy |

⚠️ Thiếu biến khai trong `requires.env` là skill tụt xuống `△ needs setup` và
**`Visible to model: no`** — bot vẫn trả lời bạn như thường nhưng nội dung tự
bịa, không hề đọc `SKILL.md`. Nghi ngờ thì chạy `openclaw skills check`.

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Thêm task | "thêm task Fix bug login vào Sprint 1, assignee H.Anh, estimate 4h" |
| Sửa task | "sửa task No.28 sang Status Done" |
| Xóa task | "xóa task No.267 ở tab Backlog" |

## Action 4 — log report hàng ngày của dev

Ba Action trên là **PM** thao tác bằng lời. Action 4 khác hẳn: **dev** gửi một
dòng report 7 field trong Slack, skill tìm đúng dòng theo `TaskID` rồi ghi vào
khối `Actual` + `Status` + `Note`.

```
AU-1 | 8 | 03-08-2026 | 04-08-2026 | 8 | Done | xong sớm
```

- Đầu vào đã được skill [`reminder-followup`](../reminder-followup) chấm format,
  Action 4 **không chấm lại**.
- **Không hỏi PM xác nhận** — dòng report chính là lệnh. Bù lại chỉ được sửa ô
  của **dòng đã có sẵn**: không chèn/xoá dòng, không tạo task mới, không đụng
  khối `PLAN` (giờ plan của PM).
- **Task chậm hơn plan** (Actual Effort > `Estimate (h)`) → chưa ghi gì, hỏi lý
  do trước. Có lý do thì ghi 1 dòng vào tab `Risk management` (tự sinh `R-xx`)
  rồi log task như thường. Hạn chờ do `reminder-followup` giữ.

Chốt này nằm trong [`scripts/sheet-task.sh`](scripts/sheet-task.sh) (exit code
`9`), **không** nằm trong prompt — không có cách nào "quên" mà log thẳng. Luật
đầy đủ: [`log-report-rules.md`](log-report-rules.md).

```bash
bash scripts/sheet-task.sh find AU-1          # xem task nằm tab nào, plan bao nhiêu
```

## Quy trình mỗi thao tác

1. Hỏi lại nếu thiếu thông tin (tab, No. task, field cần sửa...) — không tự đoán.
2. Hiển thị **preview** thay đổi, chờ bạn xác nhận (có/không) trước khi ghi thật vào sheet.
3. Nếu task có Assignee, tự kiểm tra tổng giờ/lịch của người đó và đề xuất cách xử lý nếu bị lệch.
4. Ghi log lại thao tác sau khi thành công.

Riêng **Xóa task** sẽ có cảnh báo riêng vì khó hoàn tác (khôi phục được qua Version History của Google Sheets nếu lỡ tay).
