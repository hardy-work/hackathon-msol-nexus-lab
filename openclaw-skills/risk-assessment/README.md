# risk-assessment — Cách dùng

Skill giúp PM **phát hiện rủi ro/issue dự án hằng ngày** từ dữ liệu tiến độ (Sprint tab + bảng "Thời gian làm việc mỗi ngày" trên Google Sheet), đề xuất phương án xử lý bằng ngôn ngữ tự nhiên, và (sau khi PM duyệt) ghi vào Risk management / Isssue management.

Rủi ro chia 2 loại:
- **Chủ động** — dòng `Status=Pending` do 1 skill khác ghi vào lúc dev tự log task cuối ngày (nếu task có vấn đề, dev đưa nguyên nhân) — `risk-assessment` chỉ đọc lại, gợi ý Next Action nếu còn trống.
- **Bị động** — rule engine tự quét, 12 rule chia theo 4 layer **Người → Task → Sprint → Module**, có cascade thật (vd 1 người nghỉ → tự tìm ra đúng sub-task/module bị ảnh hưởng).

Chưa cấu hình gì cả — cứ gõ thẳng yêu cầu, skill sẽ tự hỏi bạn link Google Sheet nếu cần.

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Quét rủi ro thủ công | "đánh giá rủi ro dự án hôm nay", "check issue giúp tôi" |
| Duyệt draft vừa nhận | "tôi ghi nhận, cập nhật giúp tôi" (sau khi đọc report trong chat) |
| Duyệt 1 phần | "chỉ lùi task AU-1 thôi, không cần OT" |

## Quy trình

1. **Action Scan** (cron hằng ngày hoặc PM gọi tay) — `python scripts/scan.py` đọc Sprint tab + Resource plan, áp 12 rule (P1-P4/T1-T4/S1-S2/M1-M2), đọc lại dòng Pending có sẵn, ghi/update draft trong `drafts/`. **Không bao giờ ghi vào Sheet thật ở bước này.**
2. Skill trình bày report dạng tường thuật trong chat — lấy nguyên văn từ field `narrative` mà `scan.py` in ra, chia rõ chủ động/bị động, bị động nhóm theo layer.
3. PM phản hồi tự nhiên → agent diễn giải ý PM. Ý đã rõ ràng → agent ghi `state/pending-apply.json` rồi gọi `python scripts/apply.py` để ghi thật (update dòng theo `id` cho rủi ro chủ động, tạo dòng mới ID tự tăng cho rủi ro bị động), rồi báo lại kết quả. Ý còn mơ hồ mới hỏi làm rõ trước.
4. `apply.py` tự ghi log thao tác sau khi thành công (`risk-assessment-audit.log`).

Gộp toàn bộ đọc dữ liệu + rule engine + ghi draft/snapshot vào 1 lệnh Python mỗi Action để hạn chế số lần Claude Code phải hỏi quyền chạy lệnh.

## Cấu hình

Copy `config.example.json` → `config.json`, điền `fileId`/`currentSprint`/cấu trúc cột Sprint tab/`personCodeMap` (map người trong Resource plan ↔ Assignee trong Sprint tab). Copy `.env.example` → `.env`, chỉ cần `GOOGLE_SERVICE_ACCOUNT_KEY_FILE` (API key đã bỏ hẳn — sheet private nên API key luôn 403, xác nhận qua test thật).

## Rule engine

Toàn bộ logic (đọc/chuẩn hoá Sprint tab, đọc bảng Resource plan, 12 rule, Trend) nằm ở `scripts/lib/` — Python thuần chuẩn thư viện, không cài package ngoài. Mỗi module có test riêng cùng thư mục (`<tên>_test.py`). Chạy từng file:

```bash
cd scripts/lib
python rule_engine_test.py
python normalize_test.py
python resource_plan_test.py
python draft_test.py
python google_auth_test.py
python load_env_test.py
```

Lưu ý môi trường: lệnh Python trên máy là `python`, **không phải `python3`**. Ký JWT (Service Account) qua `openssl` CLI (subprocess) thay vì cài `cryptography`/`PyJWT` — Python stdlib không có sẵn RSA signing như Node's `crypto`.

`scan.py`/`apply.py` chỉ gọi các module trong `lib/` — không tự tính điểm/trend/parse dữ liệu bằng tay trong SKILL.md.
