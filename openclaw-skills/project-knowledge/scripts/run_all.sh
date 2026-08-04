#!/usr/bin/env bash
# Dựng lại toàn bộ từ originals/. Dùng để kiểm tính tái lập và để demo.
# KHÔNG chạy lại Stage 4 (ingest bằng LLM) — wiki/ được commit và là tầng người duyệt.
set -euo pipefail
cd "$(dirname "$0")/.."

# Trình Python: KHÔNG hardcode `python3`. Trên Windows `python3` thường là store-alias
# hỏng (in "Python was not found" rồi thoát != 0) tuy vẫn nằm trên PATH — nên phải THỬ
# CHẠY từng ứng viên, lấy cái đầu tiên import được. PYTHONUTF8 cho tiếng Việt (console
# Windows mặc định cp1252 sẽ vỡ khi in dấu).
PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "✗ không tìm thấy Python chạy được (thử python3/python/py)"; exit 1; }
export PYTHONUTF8=1
# Offline demo authority. Production must inject these values from SSO/ACL and
# the approval service; coverage.yml alone is intentionally not authoritative.
export PROJECT_KNOWLEDGE_ACTOR="${PROJECT_KNOWLEDGE_ACTOR:-local-demo}"
export PROJECT_KNOWLEDGE_ROLES="${PROJECT_KNOWLEDGE_ROLES:-project_member}"
export PROJECT_KNOWLEDGE_DEMO_MODE="${PROJECT_KNOWLEDGE_DEMO_MODE:-1}"
# Test state is isolated from the persistent production volume.  It must not
# live under derived/: the corpus and all derived indexes are a read-only input
# boundary for the query runtime.
export PROJECT_KNOWLEDGE_STATE_DIR="$PWD/.runtime/test-runtime"
if [ -z "${PROJECT_KNOWLEDGE_COVERAGE_GRANTS:-}" ]; then
  export PROJECT_KNOWLEDGE_COVERAGE_GRANTS='{"Đô":["project_knowledge:approve_coverage"]}'
fi
export PROJECT_KNOWLEDGE_APPROVAL_IDS="${PROJECT_KNOWLEDGE_APPROVAL_IDS:-nexus-demo-person-role-20260803,nexus-demo-person-task-20260803}"
echo "Python: $("$PY" --version 2>&1) ($PY)"

echo; echo "══ Gate 1 · TOÀN VẸN NGUỒN (sha256 originals/) ══"
"$PY" scripts/gate1_integrity.py

echo; echo "══ xoá tầng dựng lại được ══"
rm -rf derived; mkdir -p raw derived; touch raw/.gitkeep derived/.gitkeep
echo; echo "══ Stage 0/1 · INVENTORY & CANONICAL REVIEW ══"; "$PY" scripts/inventory.py

echo; echo "══ Stage 2 · EXTRACT (NEXUS PLAN · .xlsx) ══";  "$PY" scripts/extract_nexus.py
echo; echo "══ Stage 2 · EXTRACT (VĂN / OCR · opt-in) ══"; "$PY" scripts/extract_van.py
echo; echo "══ Stage 3 · STRUCTURE CONTRACT ══"; "$PY" scripts/structure_selftest.py
echo; echo "══ Stage 4 · WIKI PAGES (NEXUS) ══"; "$PY" scripts/build_nexus_wiki.py
echo; echo "══ Gate 3a · LINT ══";     "$PY" scripts/lint.py
echo; echo "══ Gate 2+4 · numeric_guard ══"; "$PY" scripts/numeric_guard.py
echo; echo "══ ACCESS CONTROL ══"; "$PY" scripts/access_control.py
echo; echo "══ Response style contract ══"; "$PY" scripts/response_style.py
echo; echo "══ Stage 6 · PUBLISH ══";  "$PY" scripts/build_db.py
echo; echo "══ Stage 5 · DERIVE · bậc 3 graph (typed links + DIMENSION) ══"; "$PY" scripts/build_graph.py
echo; echo "══ Stage 5 · DERIVE · BM25 + Chroma vector (Bậc 2, bắt buộc) ══"
if [ "${PROJECT_KNOWLEDGE_SKIP_VECTOR:-0}" = "1" ]; then
  echo "✗ PROJECT_KNOWLEDGE_SKIP_VECTOR đã bị loại bỏ; muốn chạy offline hãy dùng " \
       "PROJECT_KNOWLEDGE_EMBEDDING_BACKEND=hash" >&2
  exit 2
fi
"$PY" scripts/build_rag_indexes.py
echo; echo "══ RAG INDEX CONTRACT (offline) ══"; "$PY" scripts/rag_index_selftest.py
echo; echo "══ CORPUS VERSION / FRESHNESS ══"; "$PY" scripts/versioning.py build --summary
echo; echo "══ EVAL ══";               (cd scripts && "$PY" eval.py)
echo; echo "══ EXTENDED EVAL + STYLE ══"; "$PY" scripts/eval_extended.py
echo; echo "══ COVERAGE EVAL ══"; "$PY" scripts/eval_coverage.py
echo; echo "══ ONBOARDING EVAL ══"; "$PY" scripts/eval_onboarding.py
echo; echo "══ PRODUCTION BOUNDARY EVAL ══"; "$PY" scripts/eval_production.py
echo; echo "══ DEMO SHOWCASE CONTRACT ══"; "$PY" scripts/demo_showcase.py --check --no-cache
echo; echo "══ LONG-LIVED RUNTIME BENCHMARK ══"; "$PY" scripts/benchmark.py --iterations 1 --concurrency 2 --max-p95-ms 2000
echo; echo "══ ROUTER CONTRACT (offline) ══"; "$PY" scripts/router_selftest.py
echo; echo "══ VERSION/FRESHNESS (offline) ══"; "$PY" scripts/version_selftest.py
echo; echo "══ DOCUMENT LIFECYCLE (offline) ══"; "$PY" scripts/lifecycle_selftest.py
echo; echo "══ VERSIONED ARTIFACTS (offline) ══"; "$PY" scripts/versioned_artifact_selftest.py
echo; echo "══ RUNTIME ACCESS/CACHE/CONTEXT (offline) ══"; "$PY" scripts/runtime_selftest.py
echo; echo "══ READ-ONLY FILESYSTEM BOUNDARY (offline) ══"; "$PY" scripts/filesystem_boundary_selftest.py
echo; echo "══ GRAPH RETRIEVAL (offline) ══"; "$PY" scripts/graph_selftest.py
echo; echo "══ INVENTORY (offline) ══"; "$PY" scripts/inventory_selftest.py
echo; echo "══ AUTOMATIC FILE INTAKE (offline) ══"; "$PY" scripts/intake_selftest.py
echo; echo "══ GATE 3a HISTORY METADATA (offline) ══"; "$PY" scripts/lint_history_selftest.py
echo; echo "══ GATE 3b CONSENSUS CONTRACT (offline) ══"; "$PY" scripts/review_selftest.py
if [ "${PROJECT_KNOWLEDGE_RUN_SLACK_TESTS:-1}" = "1" ]; then
  echo; echo "══ SLACK HTTP BOUNDARY (offline) ══"; "$PY" adapters/slack/slack_http_selftest.py
  echo; echo "══ SLACK DURABLE QUEUE (offline) ══"; "$PY" adapters/slack/slack_queue_selftest.py
fi

# Gate 3b (LLM soát nội dung) — full rebuild vẫn OPT-IN vì tốn 1 lệnh `claude -p`
# mỗi trang (~1-2 phút) và không tất định. Luồng ingest worktree (`ingest_flow.py
# --run`) thì mặc định bắt buộc Gate 3b; chỉ fixture/offline mới dùng --no-review.
#   GATE3B=1 bash scripts/run_all.sh
if [ "${GATE3B:-0}" = "1" ]; then
  echo; echo "══ Gate 3b · LLM SOÁT NỘI DUNG (opt-in, đồng thuận K=3) ══"
  "$PY" scripts/review.py --all --log
fi
