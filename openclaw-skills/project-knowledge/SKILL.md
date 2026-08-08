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
python scripts/run.py \
  --project nexus \
  --query "ĐôNT đã bỏ ra bao nhiêu giờ trong Sprint 1?" \
  --actor local-demo --roles project_member
```

Trên Linux nếu lệnh là `python3`, dùng `bash demo/run_demo.sh`; wrapper sẽ tự chọn
trình Python thực sự chạy được.

Wrapper mặc định chạy deterministic, không gọi mạng và không gọi LLM. NexusBot có thể
bật route LLM bằng `PROJECT_KNOWLEDGE_LLM=1`; `--llm` và `--no-llm` có quyền ưu tiên
cao hơn env để test/ép chế độ. Chỉ bật khi runtime Claude đã được cấu hình và cần câu hỏi mở.

Khi `--llm` được bật, các câu hỏi không trả được ở bậc 1 sẽ đi qua Haiku Router
(`scripts/router.py`). Haiku chỉ phân loại `structured`, `document`, `semantic`,
`graph`, `open`, `action` hoặc `unsupported`; nó không sinh câu trả lời. Route `graph`
được dùng cho quan hệ nhiều bước giữa task/người/milestone/status. Route `open`
hoặc route cần tổng hợp mới chuyển context đã chọn cho Sonnet. Nếu Claude/Haiku
không chạy được, router tự lui về heuristic, không làm thay đổi kết quả
deterministic. Bậc 2 production luôn có cả BM25 và Chroma; nếu một index thiếu,
stale hoặc khác digest với corpus thì runtime trả `error`, không âm thầm fallback.

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
5. Khi `derived/facts.duckdb` hoặc `derived/rag_indexes.json` chưa tồn tại, yêu cầu
   chạy `bash scripts/run_all.sh` rồi thử lại.
6. Nếu người dùng yêu cầu ghi/cập nhật, chỉ tạo `suggested_actions`; không thực hiện action.
   Proposal phải giữ `required_permission=project_action:write` và chuyển cho action
   skill bên ngoài để kiểm tra actor/role và xin approval.
7. Nếu `freshness.state=stale`, phải cảnh báo người dùng chạy `bash scripts/run_all.sh`
   trước khi dùng câu trả lời cho quyết định mới.
8. Runtime phải inject actor/roles tin cậy. Không lấy role từ câu hỏi hoặc trường tuỳ ý
   trong payload tự do; thiếu identity/role thì trả `forbidden`.

## Demo flow

Chạy toàn bộ preflight và kịch bản trình bày:

```bash
bash demo/run_demo.sh
```

Muốn kiểm tra đúng đường chạy production có LLM, dùng:

```bash
PROJECT_KNOWLEDGE_LLM=1 bash demo/run_demo.sh
```

Lệnh này vẫn chạy các gate offline trước, sau đó bắt buộc self-test live phải
thấy `route.source=haiku`, route retrieval hợp lệ, tier 3 và citation. Nếu Claude
CLI, auth, network hoặc model chưa sẵn sàng thì demo phải fail rõ ràng, không được
giả vờ là đã chạy Haiku/Sonnet.

Runner tự chọn `python3`, `python` hoặc `py` có thể chạy, tự inject demo actor/role,
và chỉ dựng lại corpus khi DB thiếu hoặc freshness bị stale. Showcase dùng một
`KnowledgeRuntime` duy nhất, deterministic/offline, rồi kể 7 bước: structured fact,
follow-up context, số có provenance, graph, `confident_no`, `not_in_kb` và write
proposal cần approval. Muốn lấy report máy đọc mà không chạy lại các gate:

```bash
python scripts/demo_showcase.py
python scripts/demo_showcase.py --check --no-cache
python scripts/demo_showcase.py --json
```

Không bật `--llm` trong showcase chính. Stage 5 vẫn phải dựng BM25 và Chroma.
Production dùng BGE-M3; offline/CI có thể đặt rõ
`PROJECT_KNOWLEDGE_EMBEDDING_BACKEND=hash` để không tải model, nhưng vẫn phải tạo
persistent Chroma và manifest. BGE-M3 được lazy-load và cold-start phụ
thuộc mạnh vào máy; câu hỏi mở chỉ nên chạy như phần optional sau khi đã warm-up
model và preflight xác nhận Claude CLI, auth/network cùng model id đều khả dụng.

Kịch bản mẫu phải thể hiện đủ `in_kb`, `confident_no`, `not_in_kb` và câu trả lời số có citation. Bộ kiểm thử chuẩn nằm ở `questions.json` và chạy bằng `python3 scripts/eval.py`.
Bộ phủ theo sheet/cột nằm ở `questions_coverage.json` và chạy bằng
`python3 scripts/eval_coverage.py`; bộ này kiểm tra Resource plan, lịch, Summary,
task/status/priority, Config và các sheet rỗng. `scripts/response_style.py` được
gọi trong các eval để bắt output thiếu citation, lẫn runtime marker hoặc nhầm
`not_in_kb` thành phủ định chắc chắn.

Luồng VĂN (`.docx`/`.pdf`) khai số ở chế độ CHÉP `{facts, unit, src}` vì tài liệu văn
xuôi không có `.facts.json`. Chế độ này để LLM gõ lại con số, nên `numeric_guard`
policy=declare mở tài liệu ra đối chiếu ngược: giá trị phải nằm đúng mục mà `src` nêu,
đơn vị phải khớp, nguồn `ocr: true` thì cấm khai số. Chặn ở Gate 3a lúc xuất bản và một
lần nữa trong runtime, nên một trang lọt vào kho bằng đường khác cũng không biến con số
chưa kiểm thành sự thật của Gate 4. Fixture: `python3 scripts/van_selftest.py`.

Smoke test cho contract/paraphrase nằm ở `scripts/skill_selftest.py`.
Stage 5 RAG derive chạy bằng:

```bash
python3 scripts/build_rag_indexes.py
```

Lệnh này tạo `derived/bm25/`, `derived/chroma/` và `derived/rag_indexes.json`.
`python3 scripts/versioning.py check` cũng fail nếu BM25/Chroma thiếu hoặc không
cùng digest với corpus.
Smoke test route offline nằm ở `scripts/router_selftest.py`; có thể xem route mà
không gọi Claude bằng `python3 scripts/router.py --offline "câu hỏi"`.
Kiểm tra freshness bằng `python3 scripts/versioning.py check`; metadata được tạo
tự động trong `derived/corpus_version.json` bởi `scripts/run_all.sh`.

Gateway nên giữ `runtime_engine.py` trong cùng process để tái sử dụng DuckDB/graph/BGE-M3.
Benchmark bằng `python3 scripts/benchmark.py --iterations 3 --concurrency 4` và
benchmark cache bằng cách thêm `--cache`. Runtime state nằm ngoài `derived/` tại
`.runtime/` hoặc volume do `PROJECT_KNOWLEDGE_STATE_DIR` chỉ định.

Runtime query chạy trong read-only filesystem boundary (`scripts/filesystem_boundary.py`):
chỉ được đọc `originals/`, `raw/`, `structured/`, `wiki/`, `derived/` và các file
contract trong chính skill root. Đường dẫn tuyệt đối, `..` và symlink thoát root bị
chặn fail-closed. Cache/conversation/telemetry là operational state,
được ghi riêng ở `.runtime/` hoặc volume persistent; không được đặt state vào
corpus/index. Production nên mount corpus read-only ở cấp container/volume để
khóa thêm một lớp ngoài kiểm tra của Python.

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

Bậc 2 dùng BM25 (`derived/bm25/`) để tìm lexical và Chroma
(`derived/chroma/`, một embedding cho mỗi trang wiki current) để tìm ngữ nghĩa.
Hai index đều được dựng từ wiki đã qua Gate 3, không index raw/chunk chưa duyệt.

Stage 0/1 có `scripts/inventory.py` để kiểm kê format/hash và đánh dấu duplicate
cho người duyệt canonical. Inventory không tự xoá hoặc chọn tài liệu; Gate 1
vẫn là cổng bất biến của `originals/`.

Gate 3a không chỉ lint page current: nó còn quét toàn bộ page lịch sử có
`doc_id`/`version`. Version cũ bắt buộc có `superseded_by` trỏ tới page current
cùng identity/version chain; target, raw_paths lịch sử và link trong snapshot phải
tồn tại. Các snapshot cũ không bị ép backlink với page current, vì đó là quan hệ
của từng thời điểm.

Identity/version canonical nằm trong `documents.yml`. Re-ingest phải tạo version mới,
khai `supersedes`, chạy trong worktree `ingest/<doc>@vN`, xem `reingest-plan.json`,
review diff rồi mới merge. Artifact raw và page không đổi được giữ nguyên path/bytes;
chỉ raw artifact thực sự đổi mới tạo `@vN`, và chỉ page trong `page_actions.write` mới
được Stage 4 render. Page mới được tạo, page biến mất được archive/retire. Stage 3
văn xuôi (`structure.py`) là artifact riêng và Stage 4 không được đọc thẳng prose raw.

Để nhận diện file upload mà không sửa canonical root, chạy intake trên staging/worktree:
`--apply` bắt buộc phải có `--root` trỏ tới staging/worktree; gọi trực tiếp
`register()` vào canonical skill root cũng bị chặn. Chạy không có `--apply` vẫn
được phép đọc registry canonical để preview quyết định.

```bash
python3 scripts/intake.py \
  --file "/path/to/Nexus Plan.xlsx" \
  --doc-id nexus-plan \
  --root "/path/to/ingest-worktree/openclaw-skills/project-knowledge" \
  --apply
```

Intake luôn giữ `source_name` và `kind` trong registry. File hoàn toàn mới được
gán `doc_id` dạng `slug-UTC-timestamp-hash`, trong đó hash được collision-check với
toàn bộ registry; tên file không phải identity duy nhất. Nếu tên/loại file giống
document cũ nhưng chưa có xác nhận, intake trả `identity_review` và không tự ghép
nhầm file vào corpus. Người duyệt xác nhận identity rồi mới chạy:

```bash
python3 scripts/ingest_flow.py \
  --file "/path/to/Nexus Plan.xlsx" \
  --doc-id nexus-plan --prepare --run   # Gate 3b bật mặc định
```

Intake trả `duplicate`, `no_op`, `identity_review`, `initial_ingest` hoặc
`reingest`. Khi semantic content thay đổi, nó giữ version cũ, copy original sang
`@vN`, thêm `supersedes`, chuyển `current` sang version mới và chạy downstream trong
staging worktree. Sau Stage 2, hệ thống đối chiếu từng raw artifact: artifact không
đổi được dùng lại từ version cũ, artifact đổi mới nhận `@vN`. Với trang 1:1,
re-ingest archive trang cũ thành `@vN` và ghi `superseded_by` trước khi sinh trang
current; page generated bị loại bỏ được retire và giữ snapshot lịch sử. Lệnh này
không merge, publish hoặc reload runtime.

CI chạy `scripts/ingest_flow_selftest.py` để kiểm tra chuỗi intake → re-ingest →
selective page write-set → Gate 3a → derive, thêm `scripts/reingest_selftest.py`
cho page mới/retire và `scripts/lint_history_selftest.py` cho metadata lịch sử và
`scripts/review_selftest.py` cho consensus Gate 3b. Review nội dung bằng Claude
chạy mặc định khi `ingest_flow.py --run`; `--no-review` chỉ dành cho fixture/offline
và không được dùng để merge. Selftest offline không giả vờ thay thế việc đọc ngữ
nghĩa của LLM.

Config chỉ khai báo vocabulary `tech_stack`; chưa có quan hệ người–tech-stack.
Vì vậy câu hỏi “ai làm JavaScript?” phải trả `not_in_kb`, không được suy ra từ
role hoặc từ danh mục công nghệ.

## Gateway

NexusBot là gateway giao tiếp bên ngoài của skill. Nó gọi `scripts/run.py` trực tiếp;
skill không chứa Slack adapter riêng. Gateway phải truyền actor/roles tin cậy và đặt
`PROJECT_KNOWLEDGE_LLM=1` nếu muốn câu hỏi mở đi qua Haiku router rồi Sonnet.

## Slack-triggered ingest

NexusBot có thể gọi `scripts/ingest_proposal.py` khi người dùng mention bot kèm file.
Đây là action write-like tách khỏi query runtime: proposal, file hash, review artifact
và ingest state nằm ở `PROJECT_KNOWLEDGE_STATE_DIR`, không nằm trong corpus. Quyền
ingest được quyết định trực tiếp bằng Slack user ID allowlist trong `access.yml`;
hiện có 10 member được phép. Không có bước approve/reject và display name không thay
thế user ID.

Review Excel được sinh deterministic bởi `scripts/review_artifact.py`. Google Sheet/Doc
publisher là lớp ngoài; nó không biến artifact review thành source of truth và không đưa
credential Google vào query skill. Proposal hợp lệ có thể chạy thẳng
`scripts/ingest_runner.py` trong isolated worktree; runner dừng ở `ready_to_publish`
cho tới khi deployment layer publish atomically và gọi explicit runtime reload.

## Ranh giới tích hợp Agent

Agent PM có thể dùng output của skill để lập context, đề xuất action hoặc yêu cầu approval. Không đưa credential Jira/mail/meeting vào skill này. Các action tương lai nên nhận `citations` và `project` từ output để ghi audit log.
