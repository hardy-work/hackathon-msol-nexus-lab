"""Mint Google OAuth2 access token từ Service Account JSON key (JWT Bearer flow).

Chỉ dùng thư viện chuẩn Python — KHÔNG cài `cryptography`/`PyJWT`. Python
stdlib không có sẵn RSA signing (khác Node's `crypto` built-in), nên bước ký
RS256 (RSA PKCS#1 v1.5 + SHA-256) shell ra `openssl` CLI (cần có trong PATH)
thay vì tự cài thêm package — giữ đúng triết lý zero pip-install của các
skill khác trong repo (vốn đã dựa vào binary hệ thống như curl/node).
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_URL = "https://oauth2.googleapis.com/token"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_json(obj: dict) -> str:
    return b64url(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def build_signing_input(client_email: str, scope: str, now: int) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": client_email,
        "scope": scope,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    return f"{b64url_json(header)}.{b64url_json(claims)}"


def sign_rs256(signing_input: bytes, private_key_pem: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "key.pem"
        key_path.write_text(private_key_pem, encoding="utf-8")
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout


def build_jwt(client_email: str, private_key_pem: str, scope: str, now: int | None = None) -> str:
    now = now if now is not None else int(time.time())
    signing_input = build_signing_input(client_email, scope, now)
    signature = sign_rs256(signing_input.encode("ascii"), private_key_pem)
    return f"{signing_input}.{b64url(signature)}"


def mint_access_token(key_file_path: str, scope: str = "https://www.googleapis.com/auth/spreadsheets") -> str:
    """Đọc Service Account JSON key, ký JWT, đổi lấy access token thật (network call)."""
    with open(key_file_path, "r", encoding="utf-8") as f:
        key = json.load(f)

    jwt = build_jwt(key["client_email"], key["private_key"], scope)

    body = (
        "grant_type=" + urllib.parse.quote("urn:ietf:params:oauth:grant-type:jwt-bearer", safe="")
        + "&assertion=" + jwt
    )
    req = urllib.request.Request(
        TOKEN_URL,
        data=body.encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"mint_access_token failed: {e.code} {e.read().decode('utf-8')}") from e

    if "access_token" not in result:
        raise RuntimeError(f"mint_access_token failed: {result}")
    return result["access_token"]
