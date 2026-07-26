#!/usr/bin/env bash
#
# sheet.sh — gọi Apps Script Web App của sheet-task.
#
#   ./sheet.sh get  ping
#   ./sheet.sh get  list 'assignee=Duy'
#   ./sheet.sh get  get  'row=9'
#   ./sheet.sh post '{"action":"update","dryRun":true,"updates":[...]}'
#
# Token tự đọc từ .env, không bao giờ xuất hiện trên dòng lệnh hay trong log.
#
# ┌─ VÌ SAO CẦN SCRIPT NÀY THAY VÌ CURL TRỰC TIẾP ────────────────────────┐
# │ Apps Script trả 302 sang script.googleusercontent.com. Với POST,      │
# │ `curl -L` đi theo redirect NHƯNG gửi lại nguyên header                │
# │ `Content-Type: application/json` — Google từ chối, trả về trang HTML  │
# │ "Không tìm thấy trang". Nhìn hệt như backend hỏng, trong khi doPost    │
# │ đã chạy xong và kết quả đang nằm ở URL redirect.                      │
# │                                                                       │
# │ Nên POST phải làm hai bước: gửi không kèm -L để lấy `location`, rồi   │
# │ GET location đó KHÔNG kèm header nào.                                 │
# └───────────────────────────────────────────────────────────────────────┘

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DIR/.env"

[[ -f "$ENV_FILE" ]] || { echo "✗ Thiếu $ENV_FILE — copy từ .env.example" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

: "${SHEET_WEBHOOK_URL:?thiếu SHEET_WEBHOOK_URL trong .env}"
: "${SHEET_API_TOKEN:?thiếu SHEET_API_TOKEN trong .env}"

# URL mẫu trong .env.example dài 47 ký tự; URL thật khoảng 110-120.
if [[ ${#SHEET_WEBHOOK_URL} -lt 80 ]]; then
    echo "✗ SHEET_WEBHOOK_URL trông như chuỗi mẫu (${#SHEET_WEBHOOK_URL} ký tự)." >&2
    echo "  URL thật lấy ở Apps Script > Triển khai > Quản lý các lần triển khai." >&2
    exit 1
fi

TIMEOUT=90

usage() { sed -n '3,9p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 2; }

case "${1:-}" in
    get)
        action="${2:?thiếu action}"
        extra="${3:-}"
        url="$SHEET_WEBHOOK_URL?action=$action&token=$SHEET_API_TOKEN"
        [[ -n "$extra" ]] && url="$url&$extra"
        curl -s -L --max-time "$TIMEOUT" "$url"
        echo
        ;;

    post)
        payload="${2:?thiếu JSON body}"

        # `@file.json` = đọc body từ file. Dùng cách này khi payload có tiếng
        # Nhật/tiếng Việt — tránh hẳn khâu shell quoting.
        if [[ "$payload" == @* ]]; then
            src="${payload:1}"
            [[ -f "$src" ]] || { echo "✗ Không thấy file: $src" >&2; exit 1; }
            payload=$(cat "$src")
        fi

        # Nhét token vào body — nơi gọi không cần biết token là gì.
        #
        # Escape mọi ký tự ngoài ASCII thành \uXXXX. Bắt buộc trên Windows:
        # stdout của Git Bash không phải UTF-8, nên "ログイン" gửi thẳng sẽ
        # biến thành "????" và ghi dữ liệu hỏng vào sheet. Dạng \uXXXX vẫn là
        # JSON hợp lệ, Apps Script tự giải mã lại đúng.
        body=$(printf '%s' "$payload" | node -e '
let s="";
process.stdin.setEncoding("utf8");
process.stdin.on("data", c => s += c).on("end", () => {
  const d = JSON.parse(s);
  d.token = process.env.SHEET_API_TOKEN;
  process.stdout.write(
    JSON.stringify(d).replace(/[-￿]/g,
      ch => "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0"))
  );
});')

        # Bước 1: POST, KHÔNG -L, chỉ lấy header để đọc `location`.
        loc=$(curl -s -D - -o /dev/null --max-time "$TIMEOUT" \
                -X POST "$SHEET_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "$body" \
              | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')

        if [[ -z "$loc" ]]; then
            echo '{"ok":false,"error":"không nhận được redirect — kiểm tra deploy còn sống không"}'
            exit 1
        fi

        # Bước 2: GET kết quả, KHÔNG kèm header nào.
        curl -s --max-time "$TIMEOUT" "$loc"
        echo
        ;;

    *) usage ;;
esac
