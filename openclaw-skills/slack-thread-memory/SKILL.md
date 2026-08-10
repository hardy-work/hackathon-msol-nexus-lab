---
name: slack-thread-memory
description: Lưu và truy xuất lịch sử hội thoại của đúng một Slack thread cho chatbot. Chỉ dùng khi bot được tag trong thread; không đọc channel history và không ghi dữ liệu vào project knowledge.
---

# Slack thread memory

## Contract

Skill này chỉ xử lý conversation state của Slack. Input bắt buộc phải có:

- `channel_id`
- `thread_ts` (message gốc nếu mention ở top-level)
- danh sách message thuộc chính thread đó

`thread_id` canonical là `channel_id:thread_ts`. Mọi message khác channel hoặc có
`thread_ts` khác đều bị từ chối. Gateway phải lấy scope từ Slack event `app_mention`,
không lấy từ câu chữ người dùng.

## Storage boundary

- DB, summary và metadata nằm trong Slack Conversation Store riêng.
- Không thêm Slack message vào `documents.yml`, `raw/`, `structured/`, `wiki/` hoặc
  `derived/` của project knowledge.
- Không có global search API trong skill này; context chỉ truy xuất theo một
  `thread_id` cụ thể.
- Project Wiki, nếu gateway muốn dùng, là nguồn riêng được ghép vào prompt bởi
  gateway; Slack history không tự động promote thành wiki fact.

## Context policy

- Thread ngắn: dùng các message chưa bị xóa theo thứ tự thời gian.
- Thread dài: dùng rolling summary và các message gần nhất.
- Message `deleted` được giữ lại để audit nhưng không xuất hiện trong context.
- Summary chỉ là conversational memory, không phải nguồn sự thật chính thức.

## Local tools

Trước khi nối vào botchat hiện tại, đọc [`INTEGRATION_NOTE.md`](INTEGRATION_NOTE.md).
Botchat vẫn là nơi nhận Slack event/fetch replies; skill này chỉ validate và lưu
thread vào DB riêng, không đăng ký Slack event và không gọi LLM.

```bash
python scripts/import_fixture.py --fixture tests/fixtures/thread.json --print-context
python scripts/ingest_event.py --event tests/fixtures/app_mention.json --print-context
python scripts/selftest.py
```

Khi cần lưu một fact vào wiki, gateway phải có flow explicit như `save this to wiki`
và tạo candidate riêng để review. Không tự động ghi từ chat history.
