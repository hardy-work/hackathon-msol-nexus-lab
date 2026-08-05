// Upload ảnh lên Drive + tạo Google Sheet log evidence từ manifest của slack-fetch.js
// Dùng: node scripts/build-sheet.js <manifest.json> <config.json> [--dry-run]
// Cần: GOOGLE_OAUTH_TOKEN_FILE (xem scripts/oauth-setup.js)
require('dotenv').config();
const fs = require('fs');
const https = require('https');

const [manifestPath, configPath, ...flags] = process.argv.slice(2);
const DRY = flags.includes('--dry-run');

// Editor trên Windows hay lưu JSON kèm BOM -> JSON.parse sẽ vỡ, cắt bỏ trước.
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));

const manifest = readJson(manifestPath);
const config = readJson(configPath);

// Nạp muộn: --dry-run không đụng tới Google nên không đòi credentials.
function oauthConf() {
  const p = process.env.GOOGLE_OAUTH_TOKEN_FILE;
  if (!p) throw new Error('Thiếu GOOGLE_OAUTH_TOKEN_FILE — chạy scripts/oauth-setup.js trước.');
  return readJson(p);
}

const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Ho_Chi_Minh' });
const fill = (s) => String(s || '').replace('{date}', today);

function request(url, opt = {}) {
  return new Promise((resolve, reject) => {
    const h = { ...(opt.headers || {}) };
    if (opt.body) h['Content-Length'] = Buffer.byteLength(opt.body);
    const req = https.request(url, { method: opt.method || 'GET', headers: h }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () =>
        resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() })
      );
    });
    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error('HTTP request timeout (30s)'));
    });
    if (opt.body) req.write(opt.body);
    req.end();
  });
}

async function accessToken() {
  const oauth = oauthConf();
  const body = new URLSearchParams({
    client_id: oauth.client_id,
    client_secret: oauth.client_secret,
    refresh_token: oauth.refresh_token,
    grant_type: 'refresh_token',
  }).toString();
  const res = await request('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const j = JSON.parse(res.body);
  if (!j.access_token) throw new Error('Đổi refresh token thất bại: ' + res.body);
  return j.access_token;
}

let TOKEN;
async function api(url, method = 'GET', payload = null) {
  const res = await request(url, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      ...(payload ? { 'Content-Type': 'application/json' } : {}),
    },
    body: payload ? JSON.stringify(payload) : null,
  });
  if (res.status >= 400) throw new Error(`${method} ${url}\nHTTP ${res.status}\n${res.body.slice(0, 600)}`);
  try {
    return JSON.parse(res.body);
  } catch {
    return res.body;
  }
}

function uploadFile(name, parentId, filePath, mimetype) {
  const boundary = 'nexus' + Date.now();
  const meta = JSON.stringify({ name, parents: [parentId] });
  const data = fs.readFileSync(filePath);
  const body = Buffer.concat([
    Buffer.from(
      `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${meta}\r\n` +
        `--${boundary}\r\nContent-Type: ${mimetype || 'image/png'}\r\n\r\n`
    ),
    data,
    Buffer.from(`\r\n--${boundary}--`),
  ]);
  return new Promise((resolve, reject) => {
    const req = https.request(
      'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink',
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${TOKEN}`,
          'Content-Type': `multipart/related; boundary=${boundary}`,
          'Content-Length': body.length,
        },
      },
      (res) => {
        let d = '';
        res.on('data', (c) => (d += c));
        res.on('end', () =>
          res.statusCode >= 400
            ? reject(new Error(`upload ${name} HTTP ${res.statusCode}\n${d.slice(0, 400)}`))
            : resolve(JSON.parse(d))
        );
      }
    );
    req.on('error', reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error(`Upload ${name} timeout (30s)`));
    });
    req.write(body);
    req.end();
  });
}

// Tên hiển thị của ảnh trong sheet: tên file gốc từ Slack thường dài
// ("Screenshot 2026-07-29 at 15.18.55.png") nên rút gọn thành "ảnh N".
const fileLabel = (f, i) => `ảnh ${i + 1}`;

// Chế độ "image": 1 ô chỉ chứa được 1 =IMAGE nên cột nở ra nhiều ô.
// Chế độ "link": gom mọi ảnh vào ĐÚNG 1 ô, mỗi ảnh 1 dòng. Không dùng
// =HYPERLINK được (chỉ 1 link/ô) -> ghi text nhiều dòng rồi gắn link vào
// từng dòng bằng textFormatRuns ở bước updateCells phía dưới.
function imageCells(files, slots) {
  const mode = config.imageDisplay || 'link';
  if (mode !== 'image') {
    return [files.map(fileLabel).join('\n')];
  }
  return Array.from({ length: slots }, (_, i) => {
    const f = files[i];
    return f ? `=IMAGE("https://drive.google.com/thumbnail?id=${f.driveId}&sz=w400")` : '';
  });
}

// 1 run cho mỗi dòng trong ô, mỗi run trỏ tới 1 ảnh
function linkRuns(files) {
  const runs = [];
  let offset = 0;
  files.forEach((f, i) => {
    runs.push({
      startIndex: offset,
      format: { link: { uri: f.webViewLink }, underline: true },
    });
    offset += fileLabel(f, i).length + 1; // +1 cho ký tự xuống dòng
  });
  return runs;
}

(async () => {
  const people = manifest.people || [];
  const cols = config.columns || [];

  if (DRY) {
    const totalFiles = people.reduce((sum, p) => sum + p.files.length, 0);
    const missingEmails = people.filter((p) => !p.email).map((p) => p.name);
    const sheetTitle = fill(config.sheetTitle) || `Evidence log ${today}`;
    const viewers = (config.viewers || []).length > 0 ? config.viewers.join(', ') : 'chỉ mình bạn';
    const sharingMode = config.imageSharing === 'anyone'
      ? 'anyone (ai có link cũng xem được)'
      : 'restricted (chỉ viewers xem được)';

    console.log(`Sắp tạo sheet "${sheetTitle}" từ thread #${manifest.channel}:`);
    console.log('─────────────────────────────────────────');
    console.log(`• Số người có evidence : ${people.length}`);
    console.log(`• Tổng số ảnh          : ${totalFiles}`);
    if (missingEmails.length > 0) {
      console.log(`• Thiếu email          : ${missingEmails.join(', ')}`);
    }
    console.log(`• Chế độ chia sẻ ảnh   : ${sharingMode}`);
    console.log(`• Người được share     : ${viewers}`);
    console.log('─────────────────────────────────────────');
    return;
  }

  TOKEN = await accessToken();

  const folder = await api(
    'https://www.googleapis.com/drive/v3/files?fields=id,name,webViewLink',
    'POST',
    { name: fill(config.folderName) || `Evidence ${today}`, mimeType: 'application/vnd.google-apps.folder' }
  );
  console.log(`Folder: ${folder.name}`);
  if (!DRY) console.log(`  Link: ${folder.webViewLink}`);

  // Ảnh nằm trong folder con riêng để file sheet không lẫn giữa hàng chục ảnh.
  const imgFolder = await api(
    'https://www.googleapis.com/drive/v3/files?fields=id,name',
    'POST',
    {
      name: config.imageFolderName || 'Ảnh evidence',
      mimeType: 'application/vnd.google-apps.folder',
      parents: [folder.id],
    }
  );

  let uploaded = 0;
  for (const p of people) {
    for (let i = 0; i < p.files.length; i++) {
      const f = p.files[i];
      const up = await uploadFile(`${p.name} — ảnh ${i + 1}`, imgFolder.id, f.path, f.mimetype);
      f.driveId = up.id;
      f.webViewLink = up.webViewLink;
      uploaded++;
    }
  }
  console.log(`Đã upload ${uploaded} ảnh`);

  // Chế độ chia sẻ ảnh: "anyone" bắt buộc nếu muốn =IMAGE() render được,
  // vì máy chủ Sheets tải ảnh ẩn danh. "restricted" thì chỉ viewers xem được.
  if (config.imageSharing === 'anyone') {
    await api(`https://www.googleapis.com/drive/v3/files/${folder.id}/permissions`, 'POST', {
      role: 'reader',
      type: 'anyone',
    });
    console.log('Folder: anyone-with-link');
  }

  const sheet = await api('https://www.googleapis.com/drive/v3/files?fields=id,name', 'POST', {
    name: fill(config.sheetTitle) || `Evidence log ${today}`,
    mimeType: 'application/vnd.google-apps.spreadsheet',
    parents: [folder.id],
  });

  // Sheet tạo qua API mặc định locale vi_VN + Etc/GMT: công thức nhiều tham số
  // sẽ lỗi #ERROR! (vi_VN dùng ';' ngăn tham số) và hàm ngày giờ lệch 7 tiếng.
  await api(`https://sheets.googleapis.com/v4/spreadsheets/${sheet.id}:batchUpdate`, 'POST', {
    requests: [
      {
        updateSpreadsheetProperties: {
          properties: { locale: 'en_US', timeZone: 'Asia/Ho_Chi_Minh' },
          fields: 'locale,timeZone',
        },
      },
    ],
  });

  const imgSlots =
    (config.imageDisplay || 'link') === 'image'
      ? Math.max(1, ...people.map((p) => p.files.length))
      : 1;
  const imgColIndex = (() => {
    let n = 0;
    for (const c of cols) {
      if (c.key === 'images') return n;
      n++;
    }
    return -1;
  })();

  // Trải config.columns thành danh sách cột thật của sheet (cột images nở ra imgSlots ô)
  const flatCols = [];
  for (const c of cols) {
    if (c.key === 'images') {
      for (let i = 0; i < imgSlots; i++) {
        flatCols.push({
          ...c,
          header: imgSlots > 1 ? `${c.header} ${i + 1}` : c.header,
        });
      }
    } else {
      flatCols.push(c);
    }
  }

  const rows = [flatCols.map((c) => c.header)];
  people.forEach((p, i) => {
    const row = [];
    for (const c of cols) {
      switch (c.key) {
        case 'stt':
          row.push(i + 1);
          break;
        case 'name':
          row.push(p.name);
          break;
        case 'email':
          row.push(p.email || '');
          break;
        case 'sentAt':
          row.push(p.sentAt);
          break;
        case 'images':
          row.push(...imageCells(p.files, imgSlots));
          break;
        default:
          row.push('');
      }
    }
    rows.push(row);
  });

  await api(
    `https://sheets.googleapis.com/v4/spreadsheets/${sheet.id}/values/A1?valueInputOption=USER_ENTERED`,
    'PUT',
    { values: rows }
  );

  const reqs = [
    {
      repeatCell: {
        range: { sheetId: 0, startRowIndex: 0, endRowIndex: 1 },
        cell: {
          userEnteredFormat: {
            textFormat: { bold: true },
            backgroundColor: { red: 0.85, green: 0.9, blue: 0.97 },
          },
        },
        fields: 'userEnteredFormat(textFormat,backgroundColor)',
      },
    },
    { updateSheetProperties: { properties: { sheetId: 0, gridProperties: { frozenRowCount: 1 } }, fields: 'gridProperties.frozenRowCount' } },
  ];
  flatCols.forEach((c, i) => {
    if (!c.width) return;
    reqs.push({
      updateDimensionProperties: {
        range: { sheetId: 0, dimension: 'COLUMNS', startIndex: i, endIndex: i + 1 },
        properties: { pixelSize: c.width },
        fields: 'pixelSize',
      },
    });
  });
  if (config.imageDisplay === 'image') {
    reqs.push({
      updateDimensionProperties: {
        range: { sheetId: 0, dimension: 'ROWS', startIndex: 1, endIndex: rows.length },
        properties: { pixelSize: 120 },
        fields: 'pixelSize',
      },
    });
  } else if (imgColIndex >= 0) {
    // Ô nhiều dòng -> bật wrap để hiện đủ, rồi gắn link cho từng dòng
    reqs.push({
      repeatCell: {
        range: {
          sheetId: 0,
          startRowIndex: 1,
          endRowIndex: rows.length,
          startColumnIndex: imgColIndex,
          endColumnIndex: imgColIndex + 1,
        },
        cell: { userEnteredFormat: { wrapStrategy: 'WRAP', verticalAlignment: 'TOP' } },
        fields: 'userEnteredFormat(wrapStrategy,verticalAlignment)',
      },
    });
    people.forEach((p, i) => {
      if (!p.files.length) return;
      reqs.push({
        updateCells: {
          rows: [{ values: [{ textFormatRuns: linkRuns(p.files) }] }],
          fields: 'textFormatRuns',
          start: { sheetId: 0, rowIndex: i + 1, columnIndex: imgColIndex },
        },
      });
    });
  }
  await api(`https://sheets.googleapis.com/v4/spreadsheets/${sheet.id}:batchUpdate`, 'POST', {
    requests: reqs,
  });

  for (const email of config.viewers || []) {
    try {
      await api(`https://www.googleapis.com/drive/v3/files/${folder.id}/permissions`, 'POST', {
        role: 'reader',
        type: 'user',
        emailAddress: email,
      });
      console.log(`Đã share cho ${email}`);
    } catch (e) {
      console.error(`! Không share được cho ${email}: ${e.message.slice(0, 200)}`);
    }
  }

  const sheetTitle = fill(config.sheetTitle) || `Evidence log ${today}`;
  console.log(`\n✓ Đã tạo sheet "${sheetTitle}" với ${people.length} dòng.`);
  // URL trần, không bọc <> — đây là log cho model đọc, không phải mrkdwn gửi
  // thẳng lên Slack. Cách gửi lên Slack quy định ở Response Format trong SKILL.md.
  console.log(`Sheet: https://docs.google.com/spreadsheets/d/${sheet.id}/edit`);
  console.log(`Folder: ${folder.webViewLink}`);
})().catch((e) => {
  console.error('LỖI:\n' + e.message);
  process.exit(1);
});
