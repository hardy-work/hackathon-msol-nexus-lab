# Nexus Project Knowledge — flow status

| Flow stage | Implementation | Current boundary |
|---|---|---|
| Stage 0 · Inventory | `scripts/inventory.py` | Detects exact/near duplicates and halts on unregistered canonical choices |
| Stage 1 · Intake | `scripts/intake.py`, `originals/`, `documents.yml`, Gate 1 | Hash + filename identity + semantic workbook digest; duplicate/no-op/initial/re-ingest decision; new version is registered only in the supplied staging root |
| Stage 2 · Extract | `extract_nexus.py`, `extract_van.py`, `extract_markdown.py` | Nexus `.xlsx` is live; DOCX/PDF run whenever `extract/van-docs.yml` lists a registered document; OCR stays opt-in (`--ocr`) because tesseract output is not reproducible, and its text is frozen into `ocr/` so rebuilds stay deterministic; Markdown source pass-through is deterministic |
| Stage 3 · Structure | `structure.py` → `structured/` | Independent prose pass; exact date/number/unit transform gate |
| Stage 4 · Wiki ingest | `build_nexus_wiki.py`, `ingest_van.py` | Reads Stage 3 output; model has no filesystem tools; `validate_page()` gates prose body and YAML declarations separately, then the script writes |
| Re-ingest | `reingest.py`, `ingest_flow.py` | Raw diff + authoritative selective page write-set; unchanged raw/page bytes are retained; new/retired pages handled in isolated `ingest/<doc>@vN` worktree |
| Gate 2/4 | `numeric_guard.py` | Citation-scoped exact number/date/unit checks; no rounded-value allowance; identifiers masked by real position, not by proximity |
| Gate 3a · numeric declare | `numeric_guard.check_page_declarations` | Copy-mode `{facts, unit, src}` is resolved back to the exact section `src` names; wrong section, wrong unit, missing locator and OCR-sourced numbers all fail closed at Gate 3a and again in the runtime guard |
| Gate 3a | `lint.py` | Contract, current version, visibility, references and numeric provenance |
| Gate 3b | `review.py` | Sonnet review is opt-in; previous Nexus run passed 8/8 |
| Stage 6 · Publish | DuckDB + wiki index | Rebuildable from source; `derived/` is intentionally ignored |
| Stage 5 · RAG Derive | `build_rag_indexes.py` | Mandatory BM25 + persistent Chroma store, bound to current input digest |
| Keyword retrieval | `bm25_index.py` | `bm25s` index over current Gate-3 wiki pages; missing/stale index fails closed |
| Graph derive/retrieval | `build_graph.py`, `graph_retrieval.py` | 60 task nodes and provenance edges; no invented dependency edges |
| Vector retrieval | `embed_index.py` / BGE-M3 + Chroma | Persistent Chroma collection is mandatory; hash embeddings exist only for offline/CI contract runs |
| Version/freshness | `versioning.py` | Digest includes originals/raw/structured/wiki/schema/coverage/registry/access |
| Q&A routing | `answer.py`, Haiku router | Tier 0 catalog → Tier 1 → graph → scoped BM25/Chroma → Sonnet synthesis |
| Access + coverage | `access_control.py`, `access.yml` | Fail-closed actor/role; page ACL reaches DuckDB/graph/wiki; approval authority is external |
| Cache + context | `query_cache.py`, `conversation.py` | Version/access/history key, TTL/max retention, persistent `.runtime/` volume |
| Long-lived runtime | `runtime_engine.py`, `benchmark.py` | Reuses access-scoped DuckDB views, graph, BGE-M3 and cache connections |
| Read-only filesystem boundary | `scripts/filesystem_boundary.py` | Runtime chỉ đọc corpus/index trong skill root; chặn traversal/symlink escape; cache/telemetry nằm ở `.runtime` hoặc volume riêng |
| Gateway integration | External NexusBot owns transport; this skill exposes `scripts/run.py` | Trusted actor/roles, history and JSON response contract; no Slack adapter in this skill |
| Slack ingest proposal | `scripts/ingest_proposal.py`, `scripts/review_artifact.py`, `scripts/ingest_runner.py` | File/hash/type + Slack ID allowlist → review artifact → isolated ingest worktree; no human approval step; stops before deployment publish |
| Telemetry | `telemetry.py`, `/health` | Query/queue latency and state without raw question, answer or actor identity |
| Production eval | onboarding + production suites | Auth/context/cache/concurrency and 10 PM/new-dev representative questions |
| Demo showcase | `demo/run_demo.sh`, `scripts/demo_showcase.py` | Freshness-aware, one-process, offline 7-step story; human and JSON output |
| Action boundary | `suggested_actions` | Approval/permission proposal only; action skill owns writes/RBAC |

## Data gaps that code cannot invent

- Workbook có vocabulary `tech_stack` nhưng chưa có mapping người–tech-stack.
- Risk, Issue và Backlog đang không có dòng nghiệp vụ thực.
- Dependency/blocker giữa task chưa có trong nguồn, nên graph không tự suy ra.
- Meeting note cần được đưa qua một ingest adapter riêng trước khi trở thành
  Project Knowledge source.

Sau khi thay workbook hoặc wiki nguồn, chạy:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 bash scripts/run_all.sh
python3 scripts/versioning.py check
```

Khi thêm version tài liệu: đăng ký version + `supersedes` trong `documents.yml`, sau
đó dùng `scripts/ingest_flow.py --prepare ...`; chỉ merge worktree sau khi review diff
và các gate xanh. Không thay file canonical tại chỗ.
