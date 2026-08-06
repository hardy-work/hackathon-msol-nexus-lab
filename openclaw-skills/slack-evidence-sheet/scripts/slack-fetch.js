// Đọc 1 thread Slack, lấy email người gửi, tải toàn bộ file đính kèm về máy.
// Dùng: node scripts/slack-fetch.js <threadUrl|channelId:ts> <outDir>
// Cần: SLACK_BOT_TOKEN (scope: channels:history hoặc groups:history, files:read,
//       users:read, users:read.email)
//
// Vì sao gọi thẳng Slack Web API thay vì dùng tool `slack` của OpenClaw: Slack chỉ
// đẩy file của message TAG bot tới bot, các file khác trong thread không truyền tới.
// Gọi conversations.replies thì lấy được đủ cả thread.
require('dotenv').config();
const fs = require('fs');
const path = require('path');
const https = require('https');

const [target, outDir = './downloads'] = process.argv.slice(2);
const TOKEN = process.env.SLACK_BOT_TOKEN;

if (!target || !TOKEN) {
  console.error('Dùng: node slack-fetch.js <threadUrl|channelId:ts> <outDir>  (cần SLACK_BOT_TOKEN)');
  process.exit(1);
}

// https://xxx.slack.com/archives/C0606MMATEV/p1785313275818529?thread_ts=1785313275.818529
function parseTarget(s) {
  if (/^[A-Z0-9]+:[0-9.]+$/.test(s)) {
    const [channel, ts] = s.split(':');
    return { channel, ts };
  }
  const m = s.match(/\/archives\/([A-Z0-9]+)\/p(\d+)/);
  if (!m) throw new Error('Không parse được link thread: ' + s);
  const u = new URL(s);
  const threadTs = u.searchParams.get('thread_ts');
  const raw = m[2];
  return {
    channel: m[1],
    ts: threadTs || `${raw.slice(0, raw.length - 6)}.${raw.slice(-6)}`,
  };
}

function slack(method, params) {
  const url = `https://slack.com/api/${method}?` + new URLSearchParams(params);
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { Authorization: `Bearer ${TOKEN}` } }, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => {
        const j = JSON.parse(d);
        if (!j.ok) reject(new Error(`${method}: ${j.error}`));
        else resolve(j);
      });
    }).on('error', reject);
  });
}

// url_private_download cần Bearer token; gọi trần sẽ trả về HTML trang login.
function download(url, dest, redirectsLeft = 5) {
  return new Promise((resolve, reject) => {
    https
      .get(url, { headers: { Authorization: `Bearer ${TOKEN}` } }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          if (!redirectsLeft) return reject(new Error('quá nhiều redirect'));
          res.resume();
          return resolve(download(res.headers.location, dest, redirectsLeft - 1));
        }
        if (res.statusCode !== 200) return reject(new Error(`tải file HTTP ${res.statusCode}`));
        const ct = res.headers['content-type'] || '';
        if (ct.includes('text/html')) {
          return reject(new Error('nhận về HTML — token thiếu scope files:read'));
        }
        const out = fs.createWriteStream(dest);
        res.pipe(out);
        out.on('finish', () => out.close(() => resolve(dest)));
        out.on('error', reject);
      })
      .on('error', reject);
  });
}

const vnTime = (ts) =>
  new Date(Number(ts) * 1000).toLocaleString('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour12: false,
  });

const safe = (s) => String(s).replace(/[^\p{L}\p{N}._-]+/gu, '_').slice(0, 60);

(async () => {
  const { channel, ts } = parseTarget(target);

  // Thư mục riêng cho từng thread. PM có thể tag bot ở 2 thread khác nhau cùng
  // lúc — đó là 2 lượt gọi độc lập, không lượt nào biết lượt nào, nên nếu dùng
  // chung 1 thư mục thì manifest bị đè và sheet ra dữ liệu của thread kia.
  // Tên lấy từ chính danh tính thread nên không thể trùng nhau.
  const dir = path.join(outDir, `${channel}-${ts}`);
  fs.mkdirSync(dir, { recursive: true });

  // Tên kênh dễ đọc hơn mã kênh, dùng cho preview và tên folder trên Drive.
  // Cần scope channels:read/groups:read — không có thì lùi về mã kênh.
  let channelName = channel;
  try {
    const info = await slack('conversations.info', { channel });
    if (info.channel && info.channel.name) channelName = info.channel.name;
  } catch (e) {
    console.error(`  ! conversations.info: ${e.message} — dùng mã kênh thay tên`);
  }

  // Gom toàn bộ reply (có phân trang khi thread dài)
  let messages = [];
  let cursor;
  do {
    const page = await slack('conversations.replies', {
      channel,
      ts,
      limit: 200,
      ...(cursor ? { cursor } : {}),
    });
    messages = messages.concat(page.messages || []);
    cursor = page.response_metadata && page.response_metadata.next_cursor;
  } while (cursor);

  const userCache = new Map();
  async function userInfo(id) {
    if (userCache.has(id)) return userCache.get(id);
    let info = { id, name: id, email: '' };
    try {
      const r = await slack('users.info', { user: id });
      const p = r.user.profile || {};
      info = {
        id,
        name: p.display_name || p.real_name || r.user.real_name || r.user.name || id,
        email: p.email || '',
      };
    } catch (e) {
      console.error(`  ! users.info ${id}: ${e.message}`);
    }
    userCache.set(id, info);
    return info;
  }

  // Một người có thể gửi nhiều message trong thread -> gộp về 1 dòng
  const byUser = new Map();
  // File tải hỏng phải đi vào manifest, không chỉ in ra màn hình: nếu chỉ in thì
  // build-sheet.js không biết mà cảnh báo, PM thấy "17 ảnh" và tưởng là đủ.
  const failedFiles = [];
  for (const m of messages) {
    if (!m.user || !m.files || !m.files.length) continue;
    const u = await userInfo(m.user);
    if (!byUser.has(m.user)) {
      byUser.set(m.user, { ...u, sentAt: vnTime(m.ts), firstTs: Number(m.ts), files: [] });
    }
    const row = byUser.get(m.user);
    for (const f of m.files) {
      const src = f.url_private_download || f.url_private;
      if (!src) continue;
      const ext = path.extname(f.name || '') || '.png';
      const dest = path.join(dir, `${safe(u.name)}__${f.id}${ext}`);
      try {
        await download(src, dest);
        row.files.push({ id: f.id, name: f.name, path: dest, mimetype: f.mimetype });
        console.log(`  ✓ ${u.name} — ${f.name}`);
      } catch (e) {
        console.error(`  ! ${u.name} — ${f.name}: ${e.message}`);
        failedFiles.push({ person: u.name, name: f.name, id: f.id, reason: e.message });
      }
    }
  }

  const people = [...byUser.values()].sort((a, b) => a.firstTs - b.firstTs);
  const manifest = {
    channel,
    channelName,
    threadTs: ts,
    fetchedAt: new Date().toISOString(),
    failedFiles,
    people: people.map(({ firstTs, ...p }) => p),
  };
  const manifestPath = path.join(dir, 'manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  const totalFiles = people.reduce((n, p) => n + p.files.length, 0);
  // Dòng tổng kết phải nói cả phần hỏng: "5 người, 17 file" đọc như mọi thứ trọn vẹn.
  const failNote = failedFiles.length ? `, ! ${failedFiles.length} file TẢI LỖI` : '';
  console.log(`\n${people.length} người, ${totalFiles} file${failNote} -> ${manifestPath}`);

  // Ai gửi ảnh mà hỏng sạch thì lọt vào manifest với files rỗng — nêu tên ra,
  // nếu không build-sheet dựng cho họ một dòng trống và PM đọc thành "chưa nộp".
  const allFailed = people.filter((p) => p.files.length === 0).map((p) => p.name);
  if (allFailed.length) {
    console.log(`! Hỏng TOÀN BỘ ảnh (đã gửi nhưng không lấy được): ${allFailed.join(', ')}`);
  }
})().catch((e) => {
  console.error('LỖI: ' + e.message);
  process.exit(1);
});
