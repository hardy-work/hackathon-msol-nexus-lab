#!/usr/bin/env bash
# Mint 1 OAuth2 access token cho Service Account (scope spreadsheets).
# Dùng: ACCESS_TOKEN=$(bash "$SKILL_DIR/scripts/get-token.sh")
#       (SKILL_DIR tính theo mục "Đường dẫn" trong SKILL.md — đừng gõ /home/<user>/… tay)
# Cần: GOOGLE_SERVICE_ACCOUNT_KEY_FILE trỏ tới file JSON credentials của Service
#      Account. Ghi TƯƠNG ĐỐI được (script tự tính từ thư mục skill, xem dưới),
#      ghi tuyệt đối cũng được — nhận cả hai.
#
# Viết bằng python3 (thư viện `cryptography`), KHÔNG dùng Node. Lý do — bản Node
# trên máy này (v14.16.0, đúng bản Gateway ghim trong PATH) dính 2 lỗi liên tiếp:
#   1. encoding 'base64url' chỉ có từ Node 15.7 -> ERR_UNKNOWN_ENCODING
#   2. sửa xong lỗi trên thì crypto.sign() chết ở tầng OpenSSL:
#      "DSO support routines:dlfcn_load:could not load the shared library"
# Cả hai đều làm $ACCESS_TOKEN rỗng dù credentials hoàn toàn đúng, và triệu
# chứng nhìn y hệt lỗi thiếu quyền. Root-caused 2026-08-05.
set -euo pipefail

# Script tự tìm thư mục skill của chính nó (theo symlink về repo thật), nên KHÔNG
# phụ thuộc cwd và KHÔNG cần hardcode đường dẫn máy nào. Nhờ vậy
# GOOGLE_SERVICE_ACCOUNT_KEY_FILE được phép ghi tương đối trong .env, và file
# .env commit/copy sang máy khác vẫn chạy.
SKILL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

KEY_FILE="${GOOGLE_SERVICE_ACCOUNT_KEY_FILE:-service-account.json}"
case "$KEY_FILE" in
  /*) ;;                                   # tuyệt đối -> dùng nguyên
  *) KEY_FILE="$SKILL_DIR/${KEY_FILE#./}" ;;  # tương đối -> tính từ thư mục skill
esac

[ -f "$KEY_FILE" ] || {
  echo "khong tim thay file credentials: $KEY_FILE" >&2
  echo "(GOOGLE_SERVICE_ACCOUNT_KEY_FILE='${GOOGLE_SERVICE_ACCOUNT_KEY_FILE:-<chua set>}', SKILL_DIR='$SKILL_DIR')" >&2
  exit 1
}
export GOOGLE_SERVICE_ACCOUNT_KEY_FILE="$KEY_FILE"

exec python3 - <<'PY'
import base64, json, os, sys, time, urllib.parse, urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


path = os.environ["GOOGLE_SERVICE_ACCOUNT_KEY_FILE"]
with open(path, encoding="utf-8") as fh:
    key = json.load(fh)

for field in ("client_email", "private_key"):
    if not key.get(field):
        sys.exit(f"file credentials thieu truong {field}: {path}")

now = int(time.time())
segments = [
    b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode()),
    b64url(
        json.dumps(
            {
                "iss": key["client_email"],
                "scope": "https://www.googleapis.com/auth/spreadsheets",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now,
                "exp": now + 3600,
            },
            separators=(",", ":"),
        ).encode()
    ),
]
unsigned = ".".join(segments).encode()

private_key = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
signature = private_key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
jwt = unsigned.decode() + "." + b64url(signature)

body = urllib.parse.urlencode(
    {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}
).encode()
req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)

try:
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
except urllib.error.HTTPError as err:
    sys.exit(err.read().decode(errors="replace"))
except OSError as err:
    sys.exit(f"khong goi duoc oauth2.googleapis.com: {err}")

token = data.get("access_token")
if not token:
    sys.exit(json.dumps(data))
print(token)
PY
