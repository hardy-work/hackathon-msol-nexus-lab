---
name: project-knowledge
description: Tra cứu thông tin dự án Nexus từ Excel/wiki/facts có provenance, citation và độ tin cậy rõ ràng. Dùng khi người dùng hỏi về task, assignee, role, sprint, effort, lịch, resource, risk, issue, backlog hoặc cần onboarding theo dữ liệu dự án; không dùng skill này để tự ý ghi Jira, gửi tin nhắn hay thay đổi dữ liệu.
---

# Project Knowledge

## Mục tiêu

Trả lời câu hỏi về dự án từ kho Nexus đã được kiểm chứng. Ưu tiên câu trả lời tất định từ DuckDB/facts; mọi số liệu phải truy được về nguồn. Không suy đoán khi kho thiếu dữ liệu.

## Cách gọi demo

Từ thư mục skill (`openclaw-skills/project-knowledge`):

```bash
python3 scripts/run.py \
  --project nexus \
  --query "ĐôNT đã bỏ ra bao nhiêu giờ trong Sprint 1?" \
  --actor local-demo --roles project_member
```

Wrapper mặc định chạy deterministic, không gọi mạng và không gọi LLM. Dùng `--llm` chỉ khi runtime Claude đã được cấu hình và cần câu hỏi mở; nếu không, giữ mặc định để bảo toàn tính tái lập.

Khi `--llm` được bật, các câu hỏi không trả được ở bậc 1 sẽ đi qua Haiku Router
(`scripts/router.py`). Haiku chỉ phân loại `structured`, `document`, `semantic`,
`graph`, `open`, `action` hoặc `unsupported`; nó không sinh câu trả lời. Route `graph`
được dùng cho quan hệ nhiều bước giữa task/người/milestone/status. Route `open`
hoặc route cần tổng hợp mới chuyển context đã chọn cho Sonnet. Nếu Claude/Haiku
không chạy được, router tự lui về heuristic và flow keyword/LLM cũ, không làm
thay đổi kết quả deterministic.

Khi tích hợp Claude, đọc adapter tại `adapters/claude/CLAUDE.md`; adapter chỉ thay lớp runtime, không thay contract facts/citation.

## Hợp đồng trả lời

Skill trả JSON gồm:

- `status`: `in_kb`, `confident_no`, `not_in_kb`, `forbidden` hoặc `error`;
- `answer`: câu trả lời tiếng Việt;
- `confidence`: `high`, `medium` hoặc `none`;
- `citations`: danh sách trang/ô nguồn;
- `reason`: giải thích ngắn về coverage, gate hoặc giới hạn dữ liệu;
- `tier`: bậc truy vấn đã trả lời;
- `project`: project đang tra cứu;
- `suggested_actions`: proposal read-only, luôn yêu cầu approval và mặc định rỗng.
- `route` (tuỳ chọn): route, confidence và nguồn của cheap router khi câu hỏi
  cần định tuyến; câu trả lời bậc 1 không gọi model nên không có trường này.
- `freshness`: trạng thái `fresh`, `stale` hoặc `unknown` của tầng derived;
  kèm `knowledge_version` và `knowledge_as_of` để biết câu trả lời dựa trên
  phiên bản corpus nào.
- `cache_hit`: kết quả có đến từ cache cùng corpus/access/history hay không;
- `effective_query` (tuỳ chọn): câu nối tiếp đã được khôi phục từ thread context.

Hiển thị citation cùng câu trả lời khi đưa lên giao diện chat. Giữ nguyên `not_in_kb` và `confident_no` như skill trả về, không đổi thành một loại “không có” chung.

## Quy tắc an toàn

1. Không tự tính hoặc làm tròn số nếu không có facts/source phù hợp.
2. `confident_no` chỉ hợp lệ khi dimension đóng, coverage có receipt và runtime
   xác thực `asserted_by` có `required_permission` cùng `approval_id` hợp lệ.
3. Sheet đã nạp nhưng chưa ký coverage chỉ được trả `not_in_kb`, không được khẳng định phủ định.
4. Không thực hiện write action. Nếu người dùng muốn sửa Jira/Excel, trả lời context hiện có và chuyển yêu cầu cho action skill có permission/approval.
5. Khi `derived/facts.duckdb` chưa tồn tại, yêu cầu chạy `bash scripts/run_all.sh` rồi thử lại.
6. Nếu người dùng yêu cầu ghi/cập nhật, chỉ tạo `suggested_actions`; không thực hiện action.
   Proposal phải giữ `required_permission=project_action:write` và chuyển cho action
   skill bên ngoài để kiểm tra actor/role và xin approval.
7. Nếu `freshness.state=stale`, phải cảnh báo người dùng chạy `bash scripts/run_all.sh`
   trước khi dùng câu trả lời cho quyết định mới.
8. Runtime phải inject actor/roles tin cậy. Không lấy role từ câu hỏi hoặc trường tuỳ ý
   trong Slack payload; thiếu identity/role thì trả `forbidden`.

## Demo flow

Chạy toàn bộ kịch bản:

```bash
bash demo/run_demo.sh
```

Kịch bản mẫu phải thể hiện đủ `in_kb`, `confident_no`, `not_in_kb` và câu trả lời số có citation. Bộ kiểm thử chuẩn nằm ở `questions.json` và chạy bằng `python3 scripts/eval.py`.
Bộ phủ theo sheet/cột nằm ở `questions_coverage.json` và chạy bằng
`python3 scripts/eval_coverage.py`; bộ này kiểm tra Resource plan, lịch, Summary,
task/status/priority, Config và các sheet rỗng. `scripts/response_style.py` được
gọi trong các eval để bắt output thiếu citation, lẫn runtime marker hoặc nhầm
`not_in_kb` thành phủ định chắc chắn.

Smoke test cho contract/paraphrase nằm ở `scripts/skill_selftest.py`.
Smoke test route offline nằm ở `scripts/router_selftest.py`; có thể xem route mà
không gọi Claude bằng `python3 scripts/router.py --offline "câu hỏi"`.
Kiểm tra freshness bằng `python3 scripts/versioning.py check`; metadata được tạo
tự động trong `derived/corpus_version.json` bởi `scripts/run_all.sh`.

Slack dùng `runtime_engine.py` trong cùng process để tái sử dụng DuckDB/graph/BGE-M3.
Benchmark bằng `python3 scripts/benchmark.py --iterations 3 --concurrency 4` và
benchmark cache bằng cách thêm `--cache`. Runtime state nằm ngoài `derived/` tại
`.runtime/` hoặc volume do `PROJECT_KNOWLEDGE_STATE_DIR` chỉ định.

Bộ `eval_onboarding.py` kiểm 10 câu đại diện PM/dev mới. `eval_production.py` kiểm
fail-closed authorization, external coverage approval, follow-up context, cache
isolation, visibility và concurrent queries. Cả hai nằm trong `run_all.sh`.
Để đánh giá câu hỏi thật mà không commit dữ liệu nội bộ, tạo
`questions_onboarding.local.json` cùng schema với `questions_onboarding.json`; evaluator
tự động gộp file local này và Git bỏ qua nó.

Các câu hỏi quan hệ nhiều bước (task–assignee–role–milestone/status) được ưu
tiên qua `derived/graph.json`. Graph chỉ là index dẫn xuất; mọi task vẫn giữ
`src` từ `raw/nexus-sprint1.facts.json`, và không tự suy ra dependency nếu nguồn
chưa khai báo.

Stage 0/1 có `scripts/inventory.py` để kiểm kê format/hash và đánh dấu duplicate
cho người duyệt canonical. Inventory không tự xoá hoặc chọn tài liệu; Gate 1
vẫn là cổng bất biến của `originals/`.

Identity/version canonical nằm trong `documents.yml`. Re-ingest phải tạo version mới,
khai `supersedes`, chạy trong worktree `ingest/<doc>@vN`, xem `reingest-plan.json`,
review diff rồi mới merge. Stage 3 văn xuôi (`structure.py`) là artifact riêng và
Stage 4 không được đọc thẳng prose raw.

Config chỉ khai báo vocabulary `tech_stack`; chưa có quan hệ người–tech-stack.
Vì vậy câu hỏi “ai làm JavaScript?” phải trả `not_in_kb`, không được suy ra từ
role hoặc từ danh mục công nghệ.

## Slack

Khi Agent được gọi từ Slack, dùng adapter tại `adapters/slack/`. Adapter nhận
Events API/slash-command JSON, giữ `channel_id`, `user_id`, `thread_ts`, format
Block Kit và không thực hiện write action. Gateway ACK trước khi query, sau đó post
answer bất đồng bộ; conversation được khóa theo channel/thread. Map Slack user sang
role bằng `PROJECT_KNOWLEDGE_SLACK_ROLE_MAP` do host quản lý. Chạy smoke test bằng:

```bash
python3 adapters/slack/slack_selftest.py
bash demo/run_slack_demo.sh
```

Production dùng durable queue `adapters/slack/job_queue.py`: Slack retry cùng
`event_id` không tạo job mới, lỗi post có exponential retry và dead-letter. Có thể
chạy worker riêng bằng `python3 adapters/slack/slack_worker.py`.

## Ranh giới tích hợp Agent

Agent PM có thể dùng output của skill để lập context, đề xuất action hoặc yêu cầu approval. Không đưa credential Jira/mail/meeting vào skill này. Các action tương lai nên nhận `citations` và `project` từ output để ghi audit log.
