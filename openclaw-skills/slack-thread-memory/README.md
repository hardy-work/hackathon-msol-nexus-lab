# Slack thread memory

Kho lưu lịch sử hội thoại riêng cho chatbot Slack. Mỗi thread là một scope độc lập:
bot chỉ được đưa vào context các message có cùng `channel_id` và `thread_ts` với event
đã tag bot. Kho này không phải là nguồn của `project-knowledge` và không ghi vào
`documents.yml`, `raw/`, `wiki/` hoặc các index của project knowledge.

## Chạy local không cần Slack server

```bash
python scripts/import_fixture.py \
  --fixture tests/fixtures/thread.json \
  --db .runtime/slack-thread-memory.sqlite3 \
  --summary "Đã thống nhất dùng API v2 cho release đầu tiên"
```

Xem context của một thread:

```bash
python scripts/import_fixture.py \
  --fixture tests/fixtures/thread.json \
  --db .runtime/slack-thread-memory.sqlite3 \
  --print-context
```

Gateway nhận Slack `app_mention` có thể truyền event và danh sách reply đã lấy
bằng `conversations.replies`:

```bash
python scripts/ingest_event.py \
  --event tests/fixtures/app_mention.json \
  --db .runtime/slack-thread-memory.sqlite3 \
  --print-context
```

Chạy kiểm thử:

```bash
python scripts/selftest.py
```

Khi gateway nhận Slack `app_mention`, gateway cần lấy `channel` và `thread_ts` từ
event rồi gọi `ThreadStore`. Không nhận `thread_id` tùy ý từ nội dung người dùng.
Nếu mention ở message gốc thì `thread_ts` chính là `ts` của message đó.

## Runtime storage

Mặc định DB nằm ở `.runtime/` của skill và bị ignore khỏi Git. Production nên đặt
`SLACK_THREAD_MEMORY_STATE_DIR` trên volume/database riêng, không trỏ vào
`openclaw-skills/project-knowledge`.

```text
SLACK_THREAD_MEMORY_STATE_DIR=/var/lib/nexus/slack-thread-memory
```

Raw text được lưu sau khi che các mẫu secret phổ biến (`xoxb-...`, Bearer token,
`password=...`). Message đã bị Slack xóa vẫn được đánh dấu `deleted`, nhưng không
được đưa vào context trả lời.
