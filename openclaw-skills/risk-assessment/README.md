# risk-assessment — Cách dùng

Skill giúp PM **phát hiện rủi ro/issue dự án hằng ngày** từ dữ liệu tiến độ (Google Sheet hoặc Jira, tùy project), đề xuất phương án xử lý bằng ngôn ngữ tự nhiên, và (sau khi PM duyệt) ghi vào Risk management / Issue management / Next Action Plan.

Chưa cấu hình gì cả — cứ gõ thẳng yêu cầu, skill sẽ tự hỏi bạn nguồn dữ liệu (gg-sheet hay Jira) nếu cần.

## Ví dụ câu lệnh

| Việc cần làm | Câu ví dụ |
| --- | --- |
| Quét rủi ro thủ công | "đánh giá rủi ro dự án hôm nay", "check issue giúp tôi" |
| Duyệt draft vừa nhận | "tôi ghi nhận, cập nhật giúp tôi" (sau khi đọc report trong chat) |
| Duyệt 1 phần | "chỉ lùi Task A sang Sprint 2 thôi, không cần OT" |

## Quy trình

1. **Action Scan** (cron hằng ngày hoặc PM gọi tay) — đọc dữ liệu tiến độ, áp 7 rule phát hiện rủi ro, tính Risk Score/Trend, ghi/update draft trong `drafts/`. **Không bao giờ ghi vào Sheet/Jira thật ở bước này.**
2. Skill trình bày report dạng tường thuật trong chat (không phải checklist thô).
3. PM phản hồi tự nhiên → **Action Apply** diễn giải ý PM (toàn bộ/một phần/phương án cụ thể), preview lần cuối, chờ xác nhận, rồi mới ghi thật.
4. Ghi log lại thao tác sau khi thành công (`risk-assessment-audit.log`).

## Cấu hình

Copy `config.example.json` → `config.json`, điền `source` (`"gg-sheet"` hoặc `"jira"`) và các field tương ứng. Copy `.env.example` → `.env`, điền credentials tương ứng với `source` đã chọn (chỉ cần phần liên quan).

## Rule engine

Phần tính toán rủi ro (score, trend) nằm ở `scripts/rule-engine.js` — thuần deterministic, không có LLM, có test đi kèm (`scripts/rule-engine.test.js`, chạy bằng `node --test scripts/*.test.js` — lưu ý dùng glob tường minh, `node --test scripts/` bị lỗi `MODULE_NOT_FOUND` trên môi trường Windows/Git Bash). SKILL.md chỉ gọi script này qua Bash rồi diễn giải kết quả bằng tiếng Việt cho PM — không tự tính điểm/trend bằng tay.
