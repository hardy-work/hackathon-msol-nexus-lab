#!/usr/bin/env node
'use strict';

/**
 * Action 1: Scan — gộp toàn bộ Source Adapter + rule-engine + ghi draft/snapshot
 * thành 1 lệnh Bash duy nhất (thay vì nhiều bước curl/node -e rời rạc), để
 * agent chỉ cần 1 lần gọi `node scripts/scan.js` cho mỗi lần quét.
 *
 * KHÔNG BAO GIỜ ghi vào Sheet/Jira thật ở đây — chỉ đọc + ghi file local
 * (drafts/, state/). Xem scripts/apply.js cho phần ghi thật (Action 2).
 *
 * In ra stdout duy nhất 1 JSON: { ok, ...}. Khi ok=false, `reason` cho biết
 * bước tiếp theo (vd hỏi PM nguồn dữ liệu) thay vì crash.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

const { loadEnv } = require('./lib/load-env.js');
loadEnv(path.join(ROOT, '.env'));

const { runRules, DEFAULT_THRESHOLDS } = require('./rule-engine.js');
const { rowsToTasks, jiraIssuesToTasks } = require('./lib/normalize.js');
const { loadStatusLog, saveStatusLog, applyStatusLog } = require('./lib/status-log.js');
const { buildNarrative, buildDraftFile, dedupeAgainstExisting } = require('./lib/draft.js');
const { getValuesWithApiKey, getValuesWithToken } = require('./lib/sheets-client.js');
const { getAccessToken } = require('./lib/google-auth.js');
const { searchIssues } = require('./lib/jira-client.js');
const { parseNotesTrace } = require('./lib/sheet-format.js');

function today() {
  return new Date().toISOString().slice(0, 10);
}

function shiftDate(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function output(payload) {
  console.log(JSON.stringify(payload, null, 2));
}

function loadConfig() {
  const configPath = path.join(ROOT, 'config.json');
  if (!fs.existsSync(configPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (e) {
    return null;
  }
}

/** Đọc 1 tab, tự fallback API key -> service-account token khi 403/không có API key. */
function makeTabReader(fileId) {
  const apiKey = process.env.GOOGLE_SHEETS_API_KEY || null;
  let cachedToken = null;
  const getToken = async () => {
    if (cachedToken) return cachedToken;
    const keyFile = process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE
      ? path.resolve(ROOT, process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE)
      : null;
    if (!keyFile) throw new Error('Thiếu GOOGLE_SERVICE_ACCOUNT_KEY_FILE trong .env để đọc sheet private.');
    cachedToken = await getAccessToken(keyFile);
    return cachedToken;
  };
  const readTab = async (tabName) => {
    if (apiKey) {
      const rows = await getValuesWithApiKey(fileId, tabName, apiKey);
      if (rows !== null) return rows;
    }
    return getValuesWithToken(fileId, tabName, await getToken());
  };
  return { readTab, getToken };
}

async function readGgSheetTasks(config, tabReader) {
  const tasks = [];
  for (const tab of config.read.sprintTabs) {
    const rows = await tabReader.readTab(tab.name);
    tasks.push(
      ...rowsToTasks({
        rows,
        columns: tab.columns,
        tabName: tab.name,
        statusDoneValues: config.read.statusDoneValues || ['Done'],
      })
    );
  }
  return tasks;
}

async function readJiraTasks(config) {
  const { JIRA_EMAIL, JIRA_API_TOKEN, JIRA_BASE_URL } = process.env;
  if (!JIRA_EMAIL || !JIRA_API_TOKEN || !JIRA_BASE_URL) {
    throw new Error('Thiếu JIRA_EMAIL/JIRA_API_TOKEN/JIRA_BASE_URL trong .env');
  }
  const issues = await searchIssues({
    baseUrl: JIRA_BASE_URL,
    email: JIRA_EMAIL,
    token: JIRA_API_TOKEN,
    projectKey: config.read.jiraProjectKey,
  });
  return jiraIssuesToTasks(issues);
}

/**
 * Bước 4 (SKILL.md): đọc Risk/Issue management THẬT để loại đề xuất trùng
 * detectedFrom+category. Format chính thức của 2 tab này (ID | Date Detected
 * | Description | Priority | Related Assignee/Task | Next Action | Status |
 * Notes) không có cột Category/Detected From riêng — scripts/apply.js đã
 * nhét trace máy-đọc-được vào cột Notes lúc ghi (xem notesTrace() trong
 * scripts/lib/sheet-format.js), ở đây parse lại đúng trace đó để tái tạo key
 * dedupe.
 */
async function readExistingKeys(config, tabReader) {
  const keys = new Set();
  const tabNames = [config.output.riskTabName, config.output.issueTabName].filter(Boolean);
  for (const tabName of tabNames) {
    let rows;
    try {
      rows = await tabReader.readTab(tabName);
    } catch (e) {
      continue; // tab lỗi/không đọc được -> bỏ qua dedupe cho tab này, không chặn scan
    }
    if (!rows || rows.length < 2) continue; // trống hoặc chỉ có header/không có header
    const header = rows[0].map((h) => (h || '').toString().trim());
    const notesIdx = header.findIndex((h) => /notes/i.test(h));
    if (notesIdx === -1) continue;
    for (const row of rows.slice(1)) {
      const trace = parseNotesTrace(row[notesIdx]);
      if (trace) keys.add(`${trace.category}__${trace.detectedFrom}`);
    }
  }
  return keys;
}

async function main() {
  const config = loadConfig();
  if (!config || !config.source) {
    output({
      ok: false,
      reason: 'no_config',
      askPm: 'Dự án này bạn đang theo dõi tiến độ bằng Google Sheet hay Jira? Mình sẽ cấu hình risk-assessment theo đúng nguồn đó.',
    });
    process.exitCode = 1;
    return;
  }

  const todayStr = today();
  let tasks;
  let existingKeys = new Set();

  if (config.source === 'gg-sheet') {
    const tabReader = makeTabReader(config.read.fileId);
    tasks = await readGgSheetTasks(config, tabReader);

    const statusLogPath = path.join(ROOT, 'state', 'task-status-log.json');
    const log = loadStatusLog(statusLogPath);
    const applied = applyStatusLog(tasks, log, todayStr);
    tasks = applied.tasks;
    saveStatusLog(statusLogPath, applied.log);

    try {
      existingKeys = await readExistingKeys(config, tabReader);
    } catch (e) {
      existingKeys = new Set(); // lỗi dedupe không chặn scan
    }
  } else if (config.source === 'jira') {
    tasks = await readJiraTasks(config);
  } else {
    output({ ok: false, reason: 'unknown_source', source: config.source });
    process.exitCode = 1;
    return;
  }

  // Chỉ phân tích risk/issue cho sprint hiện tại — task ở sprint khác (vd
  // sprint tương lai chưa bắt đầu) không đưa vào rule engine. Nếu PM chưa
  // set `currentSprint` nhưng config chỉ có ĐÚNG 1 sprint tab → tự động coi
  // tab đó là sprint hiện tại, không cần hỏi (chỉ hỏi khi có >1 tab, xem
  // SKILL.md mục Config). Lưu ý: ruleVelocityDrop cần task của ≥2 sprint để
  // so sánh nên sẽ không bao giờ bắn khi bị scope về đúng 1 sprint hiện tại
  // — đây là đánh đổi chấp nhận được, không phải bug.
  const currentSprint =
    config.read.currentSprint ||
    (config.source === 'gg-sheet' && config.read.sprintTabs && config.read.sprintTabs.length === 1
      ? config.read.sprintTabs[0].name
      : null);
  if (currentSprint) {
    tasks = tasks.filter((t) => t.sprint === currentSprint);
  }

  const yesterdaySnapshotPath = path.join(ROOT, 'state', `risk-snapshot-${shiftDate(todayStr, -1)}.json`);
  const snapshot = fs.existsSync(yesterdaySnapshotPath)
    ? JSON.parse(fs.readFileSync(yesterdaySnapshotPath, 'utf8'))
    : null;

  const thresholds = { ...DEFAULT_THRESHOLDS, ...(config.thresholds || {}) };
  const result = runRules({ tasks, snapshot, thresholds, today: todayStr });
  result.risks = dedupeAgainstExisting(result.risks, existingKeys);
  result.issues = dedupeAgainstExisting(result.issues, existingKeys);

  const narrative = buildNarrative({ ...result, thresholds });
  const draftContent = buildDraftFile(narrative, result);
  const draftPath = path.join(ROOT, 'drafts', `draft-${todayStr}.md`);
  fs.writeFileSync(draftPath, draftContent, 'utf8');

  const snapshotPath = path.join(ROOT, 'state', `risk-snapshot-${todayStr}.json`);
  fs.writeFileSync(snapshotPath, JSON.stringify({ risks: result.risks, issues: result.issues }, null, 2), 'utf8');

  output({
    ok: true,
    draftPath: path.relative(ROOT, draftPath),
    narrative,
    summary: { risks: result.risks.length, issues: result.issues.length, resolved: result.resolvedRisks.length },
  });
}

main().catch((e) => {
  output({ ok: false, reason: 'error', message: e.message });
  process.exitCode = 1;
});
