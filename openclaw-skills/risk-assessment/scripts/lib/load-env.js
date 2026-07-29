'use strict';

/**
 * Loader .env tối giản (không cài package ngoài, cùng chủ trương với
 * google-auth.js tự ký JWT bằng crypto). Chỉ set biến CHƯA có sẵn trong
 * process.env (không override env thật của shell/CI).
 */

const fs = require('fs');

function loadEnv(envPath) {
  if (!fs.existsSync(envPath)) return;

  const content = fs.readFileSync(envPath, 'utf8');
  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;

    const eqIdx = line.indexOf('=');
    if (eqIdx === -1) continue;

    const key = line.slice(0, eqIdx).trim();
    let value = line.slice(eqIdx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (key && !(key in process.env)) {
      process.env[key] = value;
    }
  }
}

module.exports = { loadEnv };
