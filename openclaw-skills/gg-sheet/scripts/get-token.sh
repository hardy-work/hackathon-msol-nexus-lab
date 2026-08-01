#!/usr/bin/env bash
# Mint 1 OAuth2 access token cho Service Account (dùng crypto sẵn có của Node, không cần cài package).
# Dùng: ACCESS_TOKEN=$(bash openclaw-skills/gg-sheet/scripts/get-token.sh)
# Cần: GOOGLE_SERVICE_ACCOUNT_KEY_FILE trỏ tới file JSON credentials của Service Account.
set -euo pipefail

node -e "
const fs = require('fs');
const crypto = require('crypto');
const https = require('https');

const key = JSON.parse(fs.readFileSync(process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE, 'utf8'));
const now = Math.floor(Date.now() / 1000);
const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
const header = { alg: 'RS256', typ: 'JWT' };
const claims = {
  iss: key.client_email,
  scope: 'https://www.googleapis.com/auth/spreadsheets',
  aud: 'https://oauth2.googleapis.com/token',
  iat: now,
  exp: now + 3600,
};
const unsigned = \`\${b64url(header)}.\${b64url(claims)}\`;
const signature = crypto.createSign('RSA-SHA256').update(unsigned).sign(key.private_key, 'base64url');
const jwt = \`\${unsigned}.\${signature}\`;

const body = 'grant_type=' + encodeURIComponent('urn:ietf:params:oauth:grant-type:jwt-bearer') + '&assertion=' + jwt;
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
