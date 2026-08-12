# Slack thread memory

Kho lưu lịch sử hội thoại riêng cho chatbot Slack. Mỗi thread là một scope độc lập:
bot chỉ được đưa vào context các message có cùng `channel_id` và `thread_ts` với event
đã tag bot. Kho này không phải là nguồn của `knowledge-base` và không ghi vào
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

CLI replay vẫn nhận Slack `app_mention` cùng danh sách reply đã lấy bằng
`conversations.replies`:

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

Production không chạy CLI này theo từng message. Gateway link
`openclaw-plugin/`, dùng internal `message:preprocessed` để gọi trực tiếp
`ThreadStore.context()` trước lượt LLM và `message:sent` để lưu phản hồi. Plugin
không đăng ký `app_mention`, không gọi LLM và không phải Slack adapter thứ hai.
Scope lấy từ session key/context trusted của gateway; không nhận `thread_id` từ
nội dung người dùng. Nếu mention ở message gốc thì `thread_ts` chính là `ts` của
message đó.

## Runtime storage

CLI Python mặc định DB ở `.runtime/` của skill và bị ignore khỏi Git. Runtime
plugin mặc định dùng state của OpenClaw (`$OPENCLAW_STATE_DIR/state/...`).
Production nên đặt `SLACK_THREAD_MEMORY_STATE_DIR` trên volume/database riêng,
không trỏ vào `openclaw-skills/knowledge-base`.

```text
SLACK_THREAD_MEMORY_STATE_DIR=/var/lib/nexus/slack-thread-memory
```

Raw text được lưu sau khi che các mẫu secret phổ biến (`xoxb-...`, Bearer token,
`password=...`). Message đã bị Slack xóa vẫn được đánh dấu `deleted`, nhưng không
được đưa vào context trả lời.

Node runtime test cần Node có `node:sqlite`:

```bash
node --test tests/runtime_scope.test.mjs tests/runtime_thread_store.test.mjs
```
