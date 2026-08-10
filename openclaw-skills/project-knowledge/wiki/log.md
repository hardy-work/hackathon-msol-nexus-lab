# Nhật ký Nexus Plan

## 2026-08-03 — Haiku router và Slack HTTP boundary

- Thêm `scripts/router.py`: Haiku chỉ phân loại `structured`, `document`,
  `semantic`, `open`, `action`, `unsupported`; không sinh câu trả lời và không
  được thay thế nguồn facts.
- Router chỉ chạy sau khi Tier 1 không trả được; lỗi model/JSON/timeout tự lui
  về flow cũ và heuristic an toàn. Output JSON có telemetry `route` tuỳ chọn.
- Thêm `router_selftest.py` (9/9) và đưa vào `scripts/run_all.sh`.
- Thêm `adapters/slack/slack_http.py`: verify signing secret, URL verification,
  Block Kit response và optional `chat.postMessage` bằng token từ environment;
  không ghi credential vào repo.
- Thêm HTTP boundary self-test 5/5; full pipeline rebuild giữ Gate 1, Gate 3a,
  baseline 12/12, extended 24/24 và coverage 21/21.
- Proposal action bổ sung `required_permission=project_action:write` và
  `approval_flow=external_action_skill`; quyền thực tế vẫn thuộc action skill,
  Project Knowledge không tự ghi dữ liệu.
- Mở rộng `build_graph.py` từ graph trang wiki thành graph task có 60 task node,
  quan hệ assignee/role/sprint/milestone/status/priority và provenance từng ô.
- Thêm `graph_retrieval.py` + graph self-test 5/5; câu hỏi như “liệt kê task thuộc
  Authentication” trả bằng quan hệ graph, không cần LLM.
- Thêm `versioning.py`: tạo `derived/corpus_version.json`, phát hiện input stale
  theo digest của originals/raw/wiki/schema/coverage và đưa `freshness`, version,
  as-of vào JSON contract.
- Bổ sung Stage 0/1 inventory: `inventory.py` ghi format/hash/duplicate và cờ
  canonical review; không tự mutate `originals/`.

## 2026-08-03 — mở rộng coverage và kiểm tra văn phong

- Router bậc 1 đã chọn được sheet/cột cho Resource plan, Master schedule, Summary và Sprint;
  câu hỏi task/status/priority/remaining không còn rơi vào dòng ngẫu nhiên.
- Stage 2 khai báo provenance cho aggregate status/priority/remaining; Gate 4 không còn
  nhầm số dòng Excel là số đo vì output không in metadata dòng.
- Config được đưa `tech_stack` vào schema/vocabulary; vẫn không gán công nghệ cho người
  vì workbook chưa có mapping.
- Thêm coverage eval 21/21 và style guard; baseline 12/12, extended 24/24, style self-test xanh.

## 2026-08-03 — Gate 3b dùng Sonnet 5

- Đổi model review của Gate 3b từ `claude-opus-4-8` sang `claude-sonnet-5`.
- Mục tiêu: tương thích Claude Pro subscription và tránh gọi Opus khi demo.
- Không chạy live review trong thay đổi này để không tiêu quota; chỉ kiểm tra local.

## 2026-08-03 — migration và làm sạch dữ liệu demo

- Nguồn nhập: `originals/nexus-plan.xlsx` (SHA256 `df3369a7bfbe56eb8d2222053f8e23c744d7dfee70640e37166175cbad2d6d58`).
- Phạm vi workbook: Resource plan, Summary project, Master schedule, Backlog, Sprint 1, Risk management, Isssue management và Config.
- Tám tuyến sheet được extract thành raw Markdown/facts; các dòng mẫu `R-000` và `I-000` được loại khỏi dữ liệu nghiệp vụ.
- Thay corpus Handy/Mor và tài liệu thử nghiệm cũ bằng Nexus; bản sao cũ phục hồi được lưu ngoài repo tại `/tmp/llm-wiki-old`.
- Dựng lại wiki gồm 1 source page và 7 entity pages; cập nhật schema, coverage, index, DuckDB và graph.

## 2026-08-03 — kiểm thử và publish

- Gate 1: xanh, manifest có 1 original và hash khớp.
- Gate 3a: xanh, 8 trang wiki, 9 nguồn facts, 0 cảnh báo.
- Numeric guard: 8/8 self-test qua; các số bịa/lệch đơn vị bị chặn.
- Eval Nexus: 12/12 câu hỏi qua, gồm in-KB, not-in-KB, confident-no và numeric.
- Publish: `dim_value=16`, `person=7`, `person_sprint=6`, `doc_cell=964`, `coverage=2`.
- Vector embedding: lần chạy đầu không tải được metadata do môi trường không có outbound network; chạy offline từ model cache đã thành công, tạo `derived/wiki_vectors.npz` cho 8 trang với vector 1024 chiều.
- Stage 5 RAG: thay vector `.npz` tùy chọn bằng persistent Chroma; thêm BM25 `bm25s`, manifest digest `derived/rag_indexes.json` và fail-closed khi một trong hai index thiếu/stale. Offline CI dùng embedding hash deterministic nhưng vẫn dựng Chroma thật.

## 2026-08-03 — đóng gói skill demo

- Khởi tạo skill `project-knowledge` theo cấu trúc chuẩn: `SKILL.md`, `agents/openai.yaml`, script và reference contract.
- Entrypoint JSON mặc định deterministic, không gọi mạng/LLM; ánh xạ kết quả lõi sang `in_kb`, `confident_no`, `not_in_kb`, `error`.
- Demo runner kiểm tra lint, numeric guard, eval rồi chạy năm truy vấn mẫu.
- Validation: skill valid, demo runner hoàn tất, eval 12/12; working tree chỉ còn thay đổi của skill demo và tài liệu liên quan.
- Đăng ký local bằng symlink `~/.codex/skills/project-knowledge`; symlink này không đưa vào Git.
- Thêm adapter Claude giữ nguyên contract JSON và cấm write trực tiếp từ Project Knowledge.
- Thêm `suggested_actions` có `requires_approval=true` cho yêu cầu ghi/cập nhật, không thực hiện side effect.
- Smoke test paraphrase: 5/5 câu qua.

## 2026-08-03 — Slack adapter

- Parser chuẩn hóa app mention/slash command thành query có `channel_id`, `user_id`, `thread_ts`.
- Formatter tạo payload Slack Block Kit, giữ citation/confidence và render approval button cho proposal.
- URL verification và HMAC signing helper đã có; transport HTTP/Slack API để adapter tích hợp sau.
- Local Slack demo: `slack_selftest.py` 8/8 (mention, slash command, thread, bot-loop, empty event, URL verification, HMAC) và `demo/run_slack_demo.sh` hoàn tất.

## 2026-08-03 — harden hỏi đáp demo

- Alias tự nhiên “Sprint đầu tiên” được chuẩn hóa về Sprint 1; câu hỏi ngày bắt đầu đi vào Summary project.
- Aggregate Sprint 1 được khai báo facts có nguồn: 60 task, 480 giờ estimate, 249 giờ actual effort.
- Handler Re-est/Start date đọc đúng Summary project và Gate 4 xác nhận số nguồn hợp lệ.
- Header task được làm rõ thành PLAN/Actual Start/End Date.
- Skill smoke test 9/9, numeric guard 8/8, eval 12/12, lint 0 cảnh báo.

## 2026-08-03 — extended Q&A suite

- Tạo `questions_extended.json` gồm 24 câu hỏi tự nhiên và `scripts/eval_extended.py`.
- Bao phủ paraphrase, aggregate, sheet rỗng, phủ định có coverage, thiếu dữ liệu và action guard.
- Kết quả: extended eval 24/24; baseline eval 12/12.

## 2026-08-03 — GATE 3b (đồng thuận 3 lượt)

### wiki/entities/tung-dv.md — **FINDING**

0/3 lượt PASS-sạch · 3/3 lượt đọc được
- [CHẮC 3/3] Các task của người này nằm trong bảng Sprint 1. — TùngDV không xuất hiện trong bảng Sprint 1 (raw/nexus-sprint1.md) — bảng đó chỉ có SơnBH, VinhNV, ĐôNT, HoàngMV, LongVN, KiênĐT. Rollup (raw/nexus-people.md) cho thấy TùngDV có task = 0, estimate_h = 0, actual_h = 0, tức là không có dòng task nào của TùngDV trong Sprint 1. (nguồn: raw/nexus-sprint1.md: bảng 6 dòng, không có TùngDV. raw/nexus-people.md: '| TùngDV | — | 0 | 0 | 0 |')
- [nghi 1/3] Vai trò theo dòng task được giữ ở nguồn raw; số liệu task và effort chỉ dùng qua facts_ref, không chép lại trong wiki. — Câu này ngụ ý có 'dòng task' với vai trò của TùngDV trong nguồn raw, nhưng thực tế không có dòng task nào của TùngDV — rollup ghi vai trò là '—' (không có), không phải một vai trò cụ thể được giữ ở raw. (nguồn: raw/nexus-people.md: cột vai trò của TùngDV là '—'; TùngDV vắng mặt hoàn toàn trong raw/nexus-sprint1.md)
- [nghi 1/3] Vai trò theo dòng task được giữ ở nguồn raw. — Không có dòng task nào của TùngDV trong nguồn để có "vai trò theo dòng task" — rollup ghi vai trò là "—" (rỗng), nên câu này ngụ ý tồn tại thông tin vai trò theo task mà thực tế không có. (nguồn: raw/nexus-people.md: | TùngDV | — | 0 | 0 | 0 |)

## 2026-08-03 — Gate 3b sửa finding zero-task

- Sửa `scripts/build_nexus_wiki.py` để trang người có 0 task không dùng câu template
  dành cho người có task; trang TùngDV giờ ghi rõ không có dòng task/role theo task.
- Gate 3a, numeric guard và eval sau khi regenerate vẫn xanh.
- Review lại `wiki/entities/tung-dv.md` bằng `claude-sonnet-5`, K=3: **PASS 3/3**.
- Kết hợp 7 trang PASS ở lượt full trước với trang đã sửa: toàn bộ 8 trang Gate 3b đạt,
  không còn finding đa số.

## 2026-08-08 · noi-quy-lao-dong-20260808T041339Z-aa1429cc79 · Stage 4 WIKI-INGEST (source VĂN) · OK
- Sinh/cập nhật 1 trang wiki; `build_index.py` đồng bộ lại `index.md`.

## 2026-08-09 · noi-quy-lao-dong-20260808T041339Z-aa1429cc79 · Stage 4 WIKI-INGEST (source VĂN) · OK
- Sinh/cập nhật 1 trang wiki; `build_index.py` đồng bộ lại `index.md`.
