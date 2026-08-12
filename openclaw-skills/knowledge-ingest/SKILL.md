---
name: knowledge-ingest
description: >
  Nạp, nhập, upload hoặc ingest file vào LLM Wiki/KB; dùng cả khi người dùng
  muốn thêm, bổ sung, cập nhật, sửa hay thay thế dữ liệu/tài liệu hiện có và có
  file Excel, Markdown, DOCX hoặc PDF đính kèm. Luồng tự phân biệt nạp mới với
  re-ingest, đồng thời kiểm tra Slack user ID trong allowlist, hash, loại file,
  review, isolated worktree và chỉ publish sau khi các gate đạt yêu cầu. Không
  dùng để trả lời truy vấn thông thường hoặc thay đổi dữ liệu ngoài pipeline.
---

# Knowledge ingest

Skill này chỉ xử lý luồng nạp tài liệu vào LLM Wiki/KB. Engine ingest
được dùng chung với `knowledge-base`, nhưng routing, quyền và side effect
được tách khỏi skill truy vấn read-only.

## Khi nào dùng

Chọn skill này khi có cả hai tín hiệu:

1. Người dùng muốn nạp/nhập/upload/ingest, thêm/bổ sung, cập nhật/sửa hoặc thay
   thế dữ liệu hay tài liệu trong Wiki/KB; và
2. Bot nhận được file đính kèm cùng mention hoặc request ingest có context
   Slack đáng tin cậy.

Không yêu cầu agent tự quyết định đây là nạp mới hay sửa bản hiện có.
`intake.py` phân loại `initial_ingest`, `reingest`, `duplicate`, `no_op` hoặc
`identity_review` từ hash và document identity.

Không chọn skill này cho câu hỏi như “ai làm task này?”, “Sprint 1 có bao nhiêu
giờ?” hoặc các truy vấn không có yêu cầu nạp file. Các câu hỏi đó thuộc
`knowledge-base`.

## Ranh giới an toàn

- Slack gateway phải truyền `user_id` thật; không dùng display name hoặc nội
  dung tin nhắn để cấp quyền.
- File phải nằm trong staging upload, không phải symlink; pipeline tự kiểm tra
  loại file, kích thước và SHA-256.
- Proposal state và review artifact nằm ngoài corpus tại
  `KNOWLEDGE_BASE_STATE_DIR`.
- Mọi ingest chạy trong isolated Git worktree. Không chạy extractor trực tiếp
  trên corpus canonical và không tự merge vào `main`.
- Review artifact là bản kiểm tra/audit, không phải source of truth.
- Chỉ deployment layer mới được publish atomically, reload runtime và ghi nhận
  `published`; `ready_to_publish` chưa có nghĩa là tài liệu đã khả dụng.

Allowlist hiện được khai báo tại:

```text
openclaw-skills/knowledge-base/access.yml
```

## Luồng chuẩn

NexusBot gọi các entrypoint trong skill `knowledge-base` theo thứ tự:

```text
mention + file
  → ingest_proposal.py create
  → review_artifact.py
  → confirm-identity (nếu cần)
  → ingest_runner.py run
  → isolated worktree
  → intake / extract / structure / wiki ingest
  → Gate 1, Gate 2, Gate 3a, Gate 3b
  → DuckDB / graph / RAG derive
  → ready_to_publish
  → deployment publish + runtime reload
  → record-published
```

Tài liệu vận hành chi tiết nằm tại
`openclaw-skills/knowledge-base/INGEST_PROPOSAL.md`.

## Runtime server

Trong production, phải gọi runner từ Git repository chính, không gọi bản copy
skill trong OpenClaw workspace runtime. Host runner cần có:

```bash
export KNOWLEDGE_BASE_REPO=/path/to/hackathon-msol-nexus-lab
export KNOWLEDGE_BASE_STATE_DIR=/path/to/persistent/runtime-state
export KNOWLEDGE_BASE_PYTHON=/path/to/project-venv/bin/python

$KNOWLEDGE_BASE_PYTHON \
  "$KNOWLEDGE_BASE_REPO/openclaw-skills/knowledge-base/scripts/ingest_runner.py" \
  run <proposal_id>
```

`KNOWLEDGE_BASE_REPO` phải là Git repository có `.git`. Nếu thiếu biến này,
runtime copy không thể tạo worktree an toàn và phải fail closed.

## Trạng thái và phản hồi Slack

Luôn phân biệt các trạng thái `FAILED`, `READY_TO_PUBLISH` và `PUBLISHED`:

```text
[NẠP TÀI LIỆU – KẾT QUẢ XỬ LÝ]

- Tài liệu: [tên file]
- Người nạp: [tên] ([Slack User ID])
- Proposal ID: [proposal_id]
- Kiểm tra: Quyền ✓ | Hash ✓ | Pipeline ✓ | Citation ✓
- Trạng thái: [PUBLISHED / READY_TO_PUBLISH / FAILED]
- Corpus version: [version hoặc —]
- Runtime: [Đã reload / Chưa reload]

Kết luận: [một câu phù hợp với trạng thái].
```

Chỉ dùng `PUBLISHED` khi proposal có `corpus_version` mới và
`runtime_reloaded=true`. Với `READY_TO_PUBLISH`, nói rõ pipeline đã đạt gate
nhưng deployment/publish và reload còn chờ xử lý. Với `FAILED`, nêu lỗi ngắn
gọn và không nói tài liệu đã được nạp.

## Không làm

Skill này không ghi Jira, Google Sheet, Slack message hay dữ liệu ngoài pipeline
ingest được kiểm soát. Publisher Google Sheet/Doc và deployment publish là các
lớp bên ngoài, có permission và audit riêng.
