# Nexus Project Knowledge — flow status

| Flow stage | Implementation | Current boundary |
|---|---|---|
| Stage 0 · Inventory | `scripts/inventory.py` | Scans format/hash/duplicates; canonical choice remains human-owned |
| Stage 1 · Intake | `originals/` + Gate 1 | SHA-256 manifest; source is append-only by policy |
| Stage 2 · Extract | `extract_nexus.py`, `extract_van.py` | Nexus `.xlsx` is live; DOCX/PDF/OCR is opt-in |
| Stage 3 · Structure | raw facts + schema + provenance | Numbers stay in facts/source cells |
| Stage 4 · Wiki ingest | `build_nexus_wiki.py`, `ingest_van.py` | Nexus wiki is committed; general prose ingest needs explicit Claude run |
| Gate 2 | `numeric_guard.py` | Numeric input guard is green |
| Gate 3a | `lint.py` | Wiki contract/lint is green |
| Gate 3b | `review.py` | Sonnet review is opt-in; previous Nexus run passed 8/8 |
| Stage 6 · Publish | DuckDB + wiki index | Rebuildable from source; `derived/` is intentionally ignored |
| Graph derive/retrieval | `build_graph.py`, `graph_retrieval.py` | 60 task nodes and provenance edges; no invented dependency edges |
| Vector retrieval | `embed_index.py` / BGE-M3 | Optional local accelerator; keyword fallback remains available |
| Version/freshness | `versioning.py` | Version, input digest, as-of and stale detection in JSON contract |
| Q&A routing | `answer.py`, Haiku router | Tier 1 first; graph/keyword/vector; Sonnet only for synthesis |
| Slack | local adapter + `slack_http.py` | Signed HTTP boundary ready; credentials/deployment remain environment work |
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
