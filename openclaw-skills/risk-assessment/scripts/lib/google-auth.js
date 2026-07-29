'use strict';

const crypto = require('crypto');
const https = require('https');
const fs = require('fs');

function base64url(buf) {
  return Buffer.from(buf)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function signServiceAccountJWT(keyFile, scope) {
  const key = JSON.parse(fs.readFileSync(keyFile, 'utf8'));
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'RS256', typ: 'JWT' };
  const tokenUri = key.token_uri || 'https://oauth2.googleapis.com/token';
  const payload = { iss: key.client_email, scope, aud: tokenUri, iat: now, exp: now + 3600 };
  const unsigned = `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(payload))}`;
  const signature = crypto.createSign('RSA-SHA256').update(unsigned).sign(key.private_key);
  return { jwt: `${unsigned}.${base64url(signature)}`, tokenUri };
}

function postForm(urlStr, form) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const body = new URLSearchParams(form).toString();
    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname + url.search,
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(body) },
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(JSON.parse(data));
          else reject(new Error(`Google token request failed ${res.statusCode}: ${data}`));
        });
      }
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

/** Đổi service-account JSON key lấy access token OAuth2 (JWT-bearer grant), không cần package ngoài. */
async function getAccessToken(keyFile, scope = 'https://www.googleapis.com/auth/spreadsheets') {
  const { jwt, tokenUri } = signServiceAccountJWT(keyFile, scope);
  const res = await postForm(tokenUri, {
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: jwt,
  });
  return res.access_token;
}

module.exports = { getAccessToken };
