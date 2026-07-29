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

1. **Action Scan** (cron hằng ngày hoặc PM gọi tay) — 1 lệnh duy nhất `node scripts/scan.js` đọc dữ liệu tiến độ, áp 9 rule phát hiện rủi ro, tính Risk Score/Trend, ghi/update draft trong `drafts/`. **Không bao giờ ghi vào Sheet/Jira thật ở bước này.**
2. Skill trình bày report dạng tường thuật trong chat (không phải checklist thô) — lấy nguyên văn từ field `narrative` mà `scan.js` in ra.
3. PM phản hồi tự nhiên → agent diễn giải ý PM. Nếu ý đã rõ ràng (toàn bộ/một phần/phương án cụ thể) → ghi thẳng, không hỏi lại: agent ghi quyết định vào `state/pending-apply.json` rồi gọi `node scripts/apply.js` (không tham số, không heredoc) để ghi thật, sau đó báo lại kết quả — **Action Apply**. Chỉ khi ý PM còn mơ hồ mới hỏi làm rõ trước.
4. `apply.js` tự ghi log thao tác sau khi thành công (`risk-assessment-audit.log`).

Gộp toàn bộ Source Adapter + rule engine + ghi draft/snapshot vào 1 lệnh Bash mỗi Action (thay vì nhiều bước curl/node -e rời rạc) để hạn chế số lần Claude Code phải hỏi quyền chạy lệnh khi thao tác.

## Cấu hình

Copy `config.example.json` → `config.json`, điền `source` (`"gg-sheet"` hoặc `"jira"`) và các field tương ứng. Copy `.env.example` → `.env`, điền credentials tương ứng với `source` đã chọn (chỉ cần phần liên quan).

## Rule engine

Phần tính toán rủi ro (score, trend) nằm ở `scripts/rule-engine.js` — thuần deterministic, không có LLM, có test đi kèm. Logic đọc/chuẩn hóa dữ liệu nguồn (parse ngày, forward-fill Category, nhận diện header row...) nằm ở `scripts/lib/normalize.js`, cũng có test riêng. Chạy toàn bộ test bằng:

```bash
node --test scripts/*.test.js scripts/lib/*.test.js
```

(lưu ý dùng glob tường minh, `node --test scripts/` bị lỗi `MODULE_NOT_FOUND` trên môi trường Windows/Git Bash). `scan.js`/`apply.js` chỉ gọi các module này qua require — không tự tính điểm/trend/parse dữ liệu bằng tay trong SKILL.md nữa.
