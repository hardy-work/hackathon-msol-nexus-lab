# Tích hợp với botchat Slack của NexusBot

## Quyết định kiến trúc

OpenClaw Slack adapter vẫn là nơi duy nhất đăng ký `app_mention` và gọi LLM.
Skill này không đăng ký Slack event, không poll Slack, không gọi LLM và không
được deploy như một adapter/service riêng.

Runtime plugin `openclaw-plugin/` được link vào **cùng gateway** và đăng ký
typed hooks của OpenClaw:

```text
Slack adapter duy nhất
    ├─ message_received → append inbound message vào ThreadStore
    ├─ before_prompt_build (awaited)
    │    ├─ ThreadStore.context(thread_id)
    │    └─ return prependContext cho đúng lượt LLM hiện tại
    └─ message_sent → append câu trả lời NexusBot vào cùng ThreadStore
```

`before_prompt_build` là hook có kết quả được gateway await; không dùng
`message:preprocessed` fire-and-forget để sửa bản copy của context. Như vậy
không có `app_mention` thứ hai, không có LLM caller thứ hai và mọi tác
vụ dùng cùng một Slack token trong service environment của NexusBot.

## Ranh giới dữ liệu

- Canonical id là `channel_id:thread_ts`; scope lấy từ session key/context của
  gateway, không lấy từ câu chữ người dùng.
- Chỉ lưu context hội thoại của Slack vào DB riêng `SLACK_THREAD_MEMORY_STATE_DIR`.
- Không ghi Slack message vào `documents.yml`, `raw/`, `structured/`, `wiki/`,
  `derived/` hoặc `knowledge-base` conversation DB.
- Context được đánh dấu là dữ liệu hội thoại không tin cậy; không coi chat là
  wiki fact nếu không có flow ingest explicit.
- Retry cùng message là upsert idempotent; thread khác không thể đọc context.
- Credential Slack không nằm trong skill `.env`; `slack-fetch.js` dùng token
  được gateway NexusBot inject.

## Cài đặt gateway

Từ thư mục skill, cài plugin dạng link vào gateway đang chạy:

```bash
openclaw plugins install --link openclaw-plugin
```

Sau đó restart đúng gateway profile của NexusBot và kiểm tra plugin ở trạng
thái loaded. Không sửa file `openclaw/dist/...` vì sẽ bị ghi đè khi nâng cấp.

## Kiểm thử

```bash
python scripts/selftest.py
node --test tests/runtime_scope.test.mjs tests/runtime_thread_store.test.mjs
```

Node test cần Node có `node:sqlite` (Node 22+); trên máy local thiếu module này
thì chạy test ở LLM server, đúng service environment của gateway.

Smoke test production cần xác nhận: mention đầu tiên lưu inbound/outbound,
mention thứ hai trong cùng thread nhận được context cũ, retry không nhân đôi
message, và mention ở thread khác không nhìn thấy lịch sử thread trước.
