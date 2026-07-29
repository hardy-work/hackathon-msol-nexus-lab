'use strict';

const https = require('https');

function request(method, urlStr, headers, jsonBody) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const body = jsonBody !== undefined ? JSON.stringify(jsonBody) : undefined;
    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname + url.search,
        method,
        headers: { ...headers, ...(body ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } : {}) },
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => resolve({ status: res.statusCode, body: data }));
      }
    );
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

/** Đọc 1 tab bằng API key (chỉ đọc được sheet public). Trả về null nếu 403 (caller tự fallback sang token). */
async function getValuesWithApiKey(fileId, tabName, apiKey) {
  const range = encodeURIComponent(tabName);
  const res = await request('GET', `https://sheets.googleapis.com/v4/spreadsheets/${fileId}/values/${range}?key=${apiKey}`, {});
  if (res.status === 200) return JSON.parse(res.body).values || [];
  if (res.status === 403) return null;
  throw new Error(`Sheets API error đọc "${tabName}" (${res.status}): ${res.body}`);
}

async function getValuesWithToken(fileId, tabName, accessToken) {
  const range = encodeURIComponent(tabName);
  const res = await request('GET', `https://sheets.googleapis.com/v4/spreadsheets/${fileId}/values/${range}`, {
    Authorization: `Bearer ${accessToken}`,
  });
  if (res.status !== 200) throw new Error(`Sheets API error đọc "${tabName}" (${res.status}): ${res.body}`);
  return JSON.parse(res.body).values || [];
}

/** Ghi đè 1 range tường minh (KHÔNG dùng values:append — xem lý do trong SKILL.md). */
async function updateValues(fileId, range, values, accessToken) {
  const encRange = encodeURIComponent(range);
  const res = await request(
    'PUT',
    `https://sheets.googleapis.com/v4/spreadsheets/${fileId}/values/${encRange}?valueInputOption=USER_ENTERED`,
    { Authorization: `Bearer ${accessToken}` },
    { values }
  );
  if (res.status !== 200) throw new Error(`Sheets write error "${range}" (${res.status}): ${res.body}`);
  return JSON.parse(res.body);
}

/** Xóa toàn bộ nội dung 1 range (dùng để reset tab về trạng thái trống hoàn toàn). */
async function clearValues(fileId, range, accessToken) {
  const encRange = encodeURIComponent(range);
  const res = await request('POST', `https://sheets.googleapis.com/v4/spreadsheets/${fileId}/values/${encRange}:clear`, {
    Authorization: `Bearer ${accessToken}`,
  });
  if (res.status !== 200) throw new Error(`Sheets clear error "${range}" (${res.status}): ${res.body}`);
  return JSON.parse(res.body);
}

module.exports = { getValuesWithApiKey, getValuesWithToken, updateValues, clearValues };
