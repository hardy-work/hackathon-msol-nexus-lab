#!/usr/bin/env bash
# Đổi refresh token (OAuth user) lấy 1 access token sống 1 giờ.
# Dùng: ACCESS_TOKEN=$(bash openclaw-skills/slack-evidence-sheet/scripts/get-token.sh)
# Cần: GOOGLE_OAUTH_TOKEN_FILE trỏ tới file JSON sinh ra bởi scripts/oauth-setup.js
#
# Khác với gg-sheet (Service Account tự ký JWT): skill này phải TẠO file mới trên
# Drive, mà Service Account không có storage quota nên không tạo được — xem README.
set -euo pipefail

node -e "
const fs = require('fs');
const https = require('https');

const conf = JSON.parse(fs.readFileSync(process.env.GOOGLE_OAUTH_TOKEN_FILE, 'utf8'));
const body = new URLSearchParams({
  client_id: conf.client_id,
  client_secret: conf.client_secret,
  refresh_token: conf.refresh_token,
  grant_type: 'refresh_token',
}).toString();

const req = https.request('https://oauth2.googleapis.com/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(body) },
}, (res) => {
  let data = '';
  res.on('data', (c) => (data += c));
  res.on('end', () => {
    const json = JSON.parse(data);
    if (json.access_token) console.log(json.access_token);
    else { console.error(data); process.exit(1); }
  });
});
req.write(body);
req.end();
"
