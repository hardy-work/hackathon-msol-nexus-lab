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
echo "Python: $("$PY" --version 2>&1) ($PY)"

echo; echo "══ Gate 1 · TOÀN VẸN NGUỒN (sha256 originals/) ══"
"$PY" scripts/gate1_integrity.py

echo; echo "══ xoá tầng dựng lại được ══"
rm -rf raw derived; mkdir -p raw derived; touch raw/.gitkeep derived/.gitkeep
echo; echo "══ Stage 0/1 · INVENTORY & CANONICAL REVIEW ══"; "$PY" scripts/inventory.py

echo; echo "══ Stage 2 · EXTRACT (NEXUS PLAN · .xlsx) ══";  "$PY" scripts/extract_nexus.py
echo; echo "══ Stage 4 · WIKI PAGES (NEXUS) ══"; "$PY" scripts/build_nexus_wiki.py
echo; echo "══ Gate 3a · LINT ══";     "$PY" scripts/lint.py
echo; echo "══ Gate 2+4 · numeric_guard ══"; "$PY" scripts/numeric_guard.py
echo; echo "══ Response style contract ══"; "$PY" scripts/response_style.py
echo; echo "══ Stage 6 · PUBLISH ══";  "$PY" scripts/build_db.py
echo; echo "══ Stage 5 · DERIVE · bậc 3 graph (typed links + DIMENSION) ══"; "$PY" scripts/build_graph.py
echo; echo "══ Stage 5 · DERIVE · vector wiki (bge-m3) ══"
"$PY" scripts/embed_index.py 2>&1 | grep -v "Warning\|Loading weights\|HF_TOKEN\|Batches" \
  || echo "  (bỏ qua — thiếu model/thư viện; bậc 2 vector sẽ tự tắt, keyword vẫn chạy)"
echo; echo "══ CORPUS VERSION / FRESHNESS ══"; "$PY" scripts/versioning.py build --summary
echo; echo "══ EVAL ══";               (cd scripts && "$PY" eval.py)
echo; echo "══ EXTENDED EVAL + STYLE ══"; "$PY" scripts/eval_extended.py
echo; echo "══ COVERAGE EVAL ══"; "$PY" scripts/eval_coverage.py
echo; echo "══ ROUTER CONTRACT (offline) ══"; "$PY" scripts/router_selftest.py
echo; echo "══ VERSION/FRESHNESS (offline) ══"; "$PY" scripts/version_selftest.py
echo; echo "══ GRAPH RETRIEVAL (offline) ══"; "$PY" scripts/graph_selftest.py
echo; echo "══ INVENTORY (offline) ══"; "$PY" scripts/inventory_selftest.py
echo; echo "══ SLACK HTTP BOUNDARY (offline) ══"; "$PY" adapters/slack/slack_http_selftest.py

# Gate 3b (LLM soát nội dung) — OPT-IN. Tốn 1 lệnh `claude -p` mỗi trang (~1-2 phút) và
# KHÔNG tất định, nên KHÔNG bật mặc định (demo cần nhanh + lặp lại được). Bật khi cần:
#   GATE3B=1 bash scripts/run_all.sh
if [ "${GATE3B:-0}" = "1" ]; then
  echo; echo "══ Gate 3b · LLM SOÁT NỘI DUNG (opt-in, đồng thuận K=3) ══"
  "$PY" scripts/review.py --all --log
fi
