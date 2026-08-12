---
name: knowledge-ingest
description: >
  Nạp, nhập, upload hoặc ingest file vào LLM Wiki/KB; dùng cả khi người dùng
  muốn thêm, bổ sung, cập nhật, sửa hay thay thế dữ liệu/tài liệu hiện có và có
  file Excel, Markdown, DOCX hoặc PDF đính kèm. Luồng tự phân biệt nạp mới với
  re-ingest, đồng thời kiểm tra Slack user ID trong allowlist, hash, loại file,
  review, isolated worktree, background job và chỉ publish artifact đúng digest
  sau khi các gate đạt yêu cầu. Dùng entrypoint submit một lần và ACK Slack ngay;
  không dùng để trả lời truy vấn thông thường hoặc thay đổi dữ liệu ngoài pipeline.
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
- Markdown thường không cần có YAML frontmatter. Intake giữ nguyên original và
  sinh metadata cho raw/wiki theo thứ tự: `domain` trong file → `org` trong file
  → domain của version hiện tại khi re-ingest → `ingest.default_domain` đã
  curate trong `access.yml`. Domain được khai rõ nhưng không nằm trong
  `schema.yml` phải fail sớm; không để LLM tự đoán hay lấy domain từ text Slack.
- Chỉ deployment layer mới được publish atomically, reload runtime và ghi nhận
  `published`; `ready_to_publish` chưa có nghĩa là tài liệu đã khả dụng.

Allowlist hiện được khai báo tại:

```text
openclaw-skills/knowledge-base/access.yml
```

## Luồng chuẩn

NexusBot gọi đúng một entrypoint `ingest_job.py submit`. Không để LLM tự dò và
gọi lần lượt Git, build, merge, reload hoặc `record-published`.

```text
mention + file
  → ingest_job.py submit
  → proposal + background job persistent
  → ACK Slack ngay với proposal_id
  → worker tạo review artifact
  → confirm-identity (nếu cần)
  → ingest_runner.py run
  → isolated worktree
  → intake / extract / structure / wiki ingest
  → Gate 1, Gate 2, Gate 3a, Gate 3b
  → DuckDB / graph / RAG derive
  → publish gates + release manifest
  → ready_to_publish
  → ingest_publisher.py: ff-only merge + exact artifact promotion
  → digest auto-reload + record-published
  → gateway gửi completion artifact vào Slack thread
```

Tài liệu vận hành chi tiết nằm tại
`openclaw-skills/knowledge-base/INGEST_PROPOSAL.md`.

## Submit từ Slack

Truyền Slack user ID từ event envelope, không lấy từ text/display name:

```bash
$KNOWLEDGE_BASE_PYTHON \
  "$KNOWLEDGE_BASE_REPO/openclaw-skills/knowledge-base/scripts/ingest_job.py" \
  submit \
  --file /staging/upload.xlsx \
  --actor U0APQSSGKTM \
  --name MH_DoNT \
  --channel-id C123 \
  --thread-ts 1785313275.818529 \
  --message-ts 1785313276.100000
```

Khi command trả `accepted=true`, phản hồi Slack ngay, không chờ worker:

```text
Đã nhận <file>. Proposal: <proposal_id>. Mình đang kiểm tra và nạp dữ liệu.
```

Gateway đọc `ingest_job.py status <proposal_id>` hoặc completion artifact trong
`$KNOWLEDGE_BASE_STATE_DIR/ingest-jobs/` để gửi kết quả cuối vào đúng thread.

## Runtime server

Trong production, phải gọi runner từ Git repository chính, không gọi bản copy
skill trong OpenClaw workspace runtime. Host runner cần có:

```bash
export KNOWLEDGE_BASE_REPO=/path/to/hackathon-msol-nexus-lab
export KNOWLEDGE_BASE_STATE_DIR=/path/to/persistent/runtime-state
export KNOWLEDGE_BASE_PYTHON=/path/to/project-venv/bin/python
export KNOWLEDGE_BASE_RUNTIME_ROOT=/path/to/runtime/skills/knowledge-base
export KNOWLEDGE_BASE_CLAUDE_BIN=/path/to/claude

$KNOWLEDGE_BASE_PYTHON \
  "$KNOWLEDGE_BASE_REPO/openclaw-skills/knowledge-base/scripts/ingest_job.py" \
  submit --file <staging-file> --actor <trusted-slack-user-id>
```

`KNOWLEDGE_BASE_RUNTIME_ROOT` phải resolve tới canonical skill, thường bằng
symlink. Publisher cố ý từ chối một runtime copy độc lập vì copy nhiều thư mục
không thể atomic và dễ tạo trạng thái source mới/index cũ.

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

## Chính sách chất lượng và hiệu năng

- Không chạy `run_all.sh` mặc định trên mỗi upload. `ingest_runner.py` chạy bộ
  publish gates trên đúng artifact vừa derive; full regression chỉ dùng
  `--full-regression` trong CI/chẩn đoán.
- Không rebuild `derived/` sau merge. Publisher chỉ promote artifact có
  `release_manifest.json` và `input_sha256` trùng tuyệt đối với corpus sau merge.
- Generic Excel source page chỉ được miễn Gate 3b khi
  `spreadsheet_contract.py` chứng minh original SHA, cell locator, formula/value,
  raw body và wiki body khớp một-một. Trang do LLM viết/tóm tắt vẫn review K=3.
- Base branch thay đổi sau lúc test, file ngoài phạm vi ingest, artifact hash lệch
  hoặc runtime root không trỏ canonical skill đều phải fail closed.

## Không làm

Skill này không ghi Jira, Google Sheet, Slack message hay dữ liệu ngoài pipeline
ingest được kiểm soát. Publisher Google Sheet/Doc và deployment publish là các
lớp bên ngoài, có permission và audit riêng.
