// Chạy 1 lần để lấy refresh token. Mở URL in ra, bấm Đồng ý, xong.
// Dùng: node scripts/oauth-setup.js [clientJson] [outTokenJson]
// Mặc định đọc GOOGLE_OAUTH_CLIENT_FILE / GOOGLE_OAUTH_TOKEN_FILE từ env.
const fs = require('fs');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const clientPath = process.argv[2] || process.env.GOOGLE_OAUTH_CLIENT_FILE;
const outPath = process.argv[3] || process.env.GOOGLE_OAUTH_TOKEN_FILE || './oauth-token.json';
const PORT = Number(process.env.OAUTH_PORT || 53682);
const REDIRECT = `http://localhost:${PORT}`;

// drive.file = chỉ đụng được file do chính app tạo ra. Đủ cho skill này và
// không đọc được phần còn lại trong Drive của người dùng.
const SCOPES = [
  'https://www.googleapis.com/auth/drive.file',
  'https://www.googleapis.com/auth/spreadsheets',
].join(' ');

if (!clientPath) {
  console.error('Thiếu client JSON. Đặt GOOGLE_OAUTH_CLIENT_FILE hoặc truyền tham số 1.');
  process.exit(1);
}

const conf = JSON.parse(fs.readFileSync(clientPath, 'utf8'));
const { client_id, client_secret } = conf.installed || conf.web;

const authUrl =
  'https://accounts.google.com/o/oauth2/v2/auth?' +
  new URLSearchParams({
    client_id,
    redirect_uri: REDIRECT,
    response_type: 'code',
    scope: SCOPES,
    access_type: 'offline',
    prompt: 'consent',
  });

function exchange(code) {
  const body = new URLSearchParams({
    code,
    client_id,
    client_secret,
    redirect_uri: REDIRECT,
    grant_type: 'authorization_code',
  }).toString();
  return new Promise((resolve, reject) => {
    const req = https.request(
      'https://oauth2.googleapis.com/token',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        let d = '';
        res.on('data', (c) => (d += c));
        res.on('end', () => resolve({ status: res.statusCode, body: d }));
      }
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, REDIRECT);
  const err = u.searchParams.get('error');
  const code = u.searchParams.get('code');
  if (err) {
    res.end('Bi tu choi: ' + err);
    console.error('Người dùng từ chối:', err);
    server.close();
    return;
  }
  if (!code) {
    res.end('waiting');
    return;
  }
  const tok = await exchange(code);
  const parsed = JSON.parse(tok.body);
  if (!parsed.refresh_token) {
    res.end('That bai — xem terminal.');
    console.error('Đổi code thất bại:', tok.status, tok.body);
    server.close();
    return;
  }
  fs.writeFileSync(
    outPath,
    JSON.stringify({ client_id, client_secret, refresh_token: parsed.refresh_token }, null, 2)
  );
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end('<h2>Xong. Quay lai terminal.</h2>');
  console.log('Đã lưu refresh token ->', outPath);
  server.close();
});

server.listen(PORT, () => {
  console.log('Mở link này trên trình duyệt, đăng nhập bằng tài khoản sẽ SỞ HỮU các file evidence:\n');
  console.log(authUrl.toString());
  console.log('\nĐang chờ...');
});
