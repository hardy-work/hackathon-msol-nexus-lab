#!/usr/bin/env bash
# One-command, offline-safe showcase for the Project Knowledge skill.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || {
  echo "[demo] không tìm thấy Python chạy được (đã thử python3/python/py)" >&2
  exit 1
}

export PYTHONUTF8=1
export PROJECT_KNOWLEDGE_ACTOR="${PROJECT_KNOWLEDGE_ACTOR:-local-demo}"
export PROJECT_KNOWLEDGE_ROLES="${PROJECT_KNOWLEDGE_ROLES:-project_member}"
export PROJECT_KNOWLEDGE_DEMO_MODE="${PROJECT_KNOWLEDGE_DEMO_MODE:-1}"
export PROJECT_KNOWLEDGE_STATE_DIR="${PROJECT_KNOWLEDGE_STATE_DIR:-$ROOT/.runtime/demo}"
# The showcase is a deterministic fixture, so do not inherit production or
# runner-wide approval variables. Production runtime injects these separately.
export PROJECT_KNOWLEDGE_COVERAGE_GRANTS='{"Đô":["project_knowledge:approve_coverage"]}'
export PROJECT_KNOWLEDGE_APPROVAL_IDS='nexus-demo-person-role-20260803,nexus-demo-person-task-20260803'

needs_build=0
if [ ! -f derived/facts.duckdb ]; then
  needs_build=1
elif ! "$PY" scripts/versioning.py check --summary >/dev/null 2>&1; then
  needs_build=1
fi

if [ "$needs_build" = "1" ]; then
  echo "[demo] corpus thiếu hoặc stale; dựng lại offline-safe"
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    PROJECT_KNOWLEDGE_EMBEDDING_BACKEND=hash \
    bash scripts/run_all.sh
fi

echo "[demo] Python: $("$PY" --version 2>&1) ($PY)"
echo "[demo] kiểm tra nhanh ingest/retrieval contract"
"$PY" scripts/lint.py >/dev/null
"$PY" scripts/numeric_guard.py >/dev/null
"$PY" scripts/response_style.py >/dev/null
"$PY" scripts/skill_selftest.py >/dev/null
"$PY" scripts/graph_selftest.py >/dev/null
"$PY" scripts/versioning.py check --summary

if [[ "${PROJECT_KNOWLEDGE_LLM:-0}" =~ ^(1|true|yes|on)$ ]]; then
  echo "[demo] kiểm tra live Haiku router + Sonnet answer"
  "$PY" scripts/llm_routing_selftest.py
else
  echo "[demo] LLM routing check bỏ qua; đặt PROJECT_KNOWLEDGE_LLM=1 để chạy live"
fi

echo
"$PY" scripts/demo_showcase.py
