#!/usr/bin/env bash
# Chạy toàn bộ test offline của các skill. Không cần mạng, không cần API key,
# không đụng vào sheet thật.
#
#   bash openclaw-skills/tests/run.sh
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
FAIL=0

for t in "$HERE"/test_*.py; do
  echo "=== $(basename "$t") ==="
  python3 "$t" || FAIL=1
  echo
done

if [ "$FAIL" -ne 0 ]; then
  echo "CO TEST HONG"
  exit 1
fi
echo "TAT CA TEST PASS"
