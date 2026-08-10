# Note tích hợp với botchat Slack

## Ranh giới bắt buộc

`botchat adapter` hiện tại vẫn là đầu mối duy nhất nhận Slack event, xác thực
mention và gọi Slack Web API để lấy replies. `slack-thread-memory` **không** đăng
ký event handler, không tự poll Slack và không gọi LLM.

Adapter trong skill này chỉ làm hai việc:

1. Validate payload thuộc đúng một `channel_id + thread_ts`.
2. Upsert raw message/summary vào DB riêng của Slack conversation.

Không nối skill này vào `project-knowledge` và không ghi Slack message vào
`documents.yml`, `raw/`, `wiki/`, `derived/` hoặc conversation DB của project
knowledge.

## Luồng nên dùng khi tích hợp

```text
Slack app_mention
    ↓
botchat adapter hiện tại
    ├─ xác định channel + thread_ts từ event
    ├─ gọi conversations.replies cho đúng thread
    └─ gọi normalize_event(...) + ThreadStore
            ↓
      lấy context của đúng thread
            ↓
      botchat gọi LLM một lần
            ↓
      lưu reply của bot vào cùng thread store
```

Trong code production nên import trực tiếp `normalize_event` và `ThreadStore`;
không cần spawn subprocess cho mỗi message. CLI `ingest_event.py` chủ yếu để
replay/kiểm thử local.

## Checklist tránh xung đột

- [ ] Chỉ có một nơi đăng ký Slack `app_mention` handler: botchat adapter hiện tại.
- [ ] Không để cả hai lớp cùng gọi LLM cho cùng một event.
- [ ] Gateway truyền replies đã fetch; không truyền channel history toàn bộ.
- [ ] `thread_ts` lấy từ Slack event, không lấy từ câu chữ hoặc link do người dùng tự nhập.
- [ ] Mọi reply phải cùng `channel_id` và `thread_ts`; khác scope thì reject.
- [ ] Dùng cùng một DB riêng qua `SLACK_THREAD_MEMORY_STATE_DIR`.
- [ ] Nếu gateway đã có conversation store cũ, không merge tự động; chọn Slack
  ThreadStore làm nơi lưu Slack history hoặc viết migration có chủ đích.
- [ ] Khi retry event, dùng upsert; không tạo thêm lượt gọi LLM.
- [ ] Project Wiki chỉ được thêm vào prompt như nguồn riêng nếu flow botchat cho phép;
  Slack history không tự động promote thành wiki fact.

## Smoke test trước khi nối thật

```bash
python scripts/selftest.py
python scripts/ingest_event.py \
  --event tests/fixtures/app_mention.json \
  --db .runtime/slack-thread-memory.sqlite3 \
  --print-context
```

Sau khi nối gateway, kiểm tra 3 tình huống: retry cùng event không tăng số message,
message ở thread khác bị reject, và một thread mới không thấy context của thread cũ.
