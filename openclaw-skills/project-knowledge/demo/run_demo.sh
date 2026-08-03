#!/usr/bin/env bash
# One-command, offline-safe demo for the Project Knowledge skill.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f derived/facts.duckdb ]; then
  echo "[demo] dựng corpus Nexus và index (offline-safe)"
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 bash scripts/run_all.sh
fi

echo "[demo] gate kiểm tra"
python3 scripts/lint.py >/dev/null
python3 scripts/numeric_guard.py >/dev/null
python3 scripts/response_style.py >/dev/null
python3 scripts/skill_selftest.py
python3 scripts/versioning.py check --summary
python3 scripts/graph_selftest.py
python3 scripts/eval.py | tail -n 12
python3 scripts/eval_extended.py | tail -n 3
python3 scripts/eval_coverage.py | tail -n 3

echo
echo "[demo] project-knowledge skill"
queries=(
  "ĐôNT làm vai trò gì trong dự án Nexus?"
  "Task API Login trong Sprint 1 do ai phụ trách?"
  "ĐôNT đã bỏ ra bao nhiêu giờ trong Sprint 1?"
  "Sprint đầu tiên bắt đầu ngày nào?"
  "Tổng số task của Sprint 1 là bao nhiêu?"
  "Re-est của Sprint 1 là bao nhiêu giờ?"
  "TùngDV có task nào trong Sprint 1 không?"
  "Có issue nào trong Issue management không?"
  "Liệt kê các task thuộc Authentication"
  "Những người liên quan đến Authentication là ai?"
)
for query in "${queries[@]}"; do
  echo
  echo "### $query"
  python3 scripts/run.py --project nexus --query "$query"
done
