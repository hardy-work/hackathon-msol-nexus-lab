#!/usr/bin/env node
'use strict';

/**
 * Action 2: Apply Draft — ghi THẬT vào Risk management / Issue management /
 * Next Action Plan (gg-sheet) hoặc Jira, sau khi PM đã xác nhận trong chat.
 *
 * Agent vẫn là bên duy nhất diễn giải câu trả lời tự nhiên của PM (chọn
 * risk/issue nào, phương án nào) — script này chỉ làm phần cơ học: đọc input
 * quyết định (đã confirm) từ state/pending-apply.json, rồi thực thi ghi +
 * bookkeeping. Không tự suy diễn thêm gì ngoài input được đưa vào.
 *
 * Input là state/pending-apply.json (agent ghi bằng Write tool SAU KHI PM đã
 * xác nhận "có" ở preview cuối — KHÔNG nhận qua stdin/heredoc, để lệnh Bash
 * gọi apply.js luôn là 1 chuỗi cố định, không lẫn nội dung JSON thay đổi vào
 * command line — tránh vừa phải allow-list wildcard nguy hiểm vừa tránh dialog
 * xác nhận Bash hiện lại nội dung JSON trông như "hỏi lại lần 2"). Ví dụ nội
 * dung file:
 * {
 *   "draftDate": "2026-07-29",
 *   "appliedBy": "PM Kiên",
 *   "risks": [
 *     { "detectedFrom": "Sprint 1, No.1", "category": "Resource", "description": "...",
 *       "score": 6, "trend": "New", "chosenMitigation": "OT LongVN",
 *       "nextAction": { "description": "...", "owner": "LongVN", "due": "2026-08-01" } }
 *   ],
 *   "issues": [
 *     { "detectedFrom": "Sprint 1, No.3", "category": "Technical", "description": "...",
 *       "priority": "High" }
 *   ]
 * }
 *
 * In ra stdout 1 JSON: { ok, written: {risks,issues,nextActions}, auditLine }.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

const { loadEnv } = require('./lib/load-env.js');
loadEnv(path.join(ROOT, '.env'));

const { getValuesWithApiKey, getValuesWithToken, updateValues } = require('./lib/sheets-client.js');
const { getAccessToken } = require('./lib/google-auth.js');
const { createIssue, updateIssue } = require('./lib/jira-client.js');

const RISK_HEADER = ['Category', 'Description', 'Detected From', 'Probability', 'Impact', 'Score', 'Trend', 'Owner', 'Mitigation', 'Status', 'Source', 'Last Updated'];
const ISSUE_HEADER = ['Category', 'Description', 'Detected From', 'Priority', 'Score', 'Owner', 'Status', 'Raised Date', 'Source', 'Last Updated'];
const NEXT_ACTION_HEADER = ['Description', 'Owner', 'Due', 'Related Detected From', 'Status'];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function output(payload) {
  console.log(JSON.stringify(payload, null, 2));
}

const PENDING_APPLY_PATH = path.join(ROOT, 'state', 'pending-apply.json');

function loadConfig() {
  const configPath = path.join(ROOT, 'config.json');
  return JSON.parse(fs.readFileSync(configPath, 'utf8'));
}

function makeTabReader(fileId) {
  const apiKey = process.env.GOOGLE_SHEETS_API_KEY || null;
  let cachedToken = null;
  const getToken = async () => {
    if (cachedToken) return cachedToken;
    const keyFile = process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE
      ? path.resolve(ROOT, process.env.GOOGLE_SERVICE_ACCOUNT_KEY_FILE)
      : null;
    if (!keyFile) throw new Error('Thiếu GOOGLE_SERVICE_ACCOUNT_KEY_FILE trong .env để ghi sheet.');
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

/** Đọc tab hiện có; nếu trống hoàn toàn (chưa có header) → coi header cần tạo mới. */
async function ensureHeaderAndNextRow(tabReader, fileId, tabName, header, accessToken) {
  let rows = [];
  try {
    rows = (await tabReader.readTab(tabName)) || [];
  } catch (e) {
    rows = [];
  }
  if (rows.length === 0) {
    await updateValues(fileId, `${tabName}!A1`, [header], accessToken);
    return 2; // dòng dữ liệu đầu tiên sau header mới tạo
  }
  return rows.length + 1;
}

function riskRow(r, today_) {
  return [
    r.category,
    r.description,
    r.detectedFrom,
    r.probability ?? '',
    r.impact ?? '',
    r.score ?? '',
    r.trend || 'New',
    r.owner || '',
    r.chosenMitigation || '',
    'Open',
    'AI',
    today_,
  ];
}

function issueRow(i, today_) {
  return [i.category, i.description, i.detectedFrom, i.priority, i.score ?? '', i.owner || '', 'Open', today_, 'AI', today_];
}

function nextActionRow(na, detectedFrom) {
  return [na.description, na.owner || '', na.due || '', detectedFrom, 'Open'];
}

async function applyGgSheet(config, decision) {
  const tabReader = makeTabReader(config.read.fileId);
  const accessToken = await tabReader.getToken();
  const todayStr = today();
  const written = { risks: 0, issues: 0, nextActions: 0 };

  const risks = decision.risks || [];
  const issues = decision.issues || [];

  if (risks.length) {
    let nextRow = await ensureHeaderAndNextRow(tabReader, config.read.fileId, config.output.riskTabName, RISK_HEADER, accessToken);
    const rowsToWrite = risks.map((r) => riskRow(r, todayStr));
    const range = `${config.output.riskTabName}!A${nextRow}:${String.fromCharCode(64 + RISK_HEADER.length)}${nextRow + rowsToWrite.length - 1}`;
    await updateValues(config.read.fileId, range, rowsToWrite, accessToken);
    written.risks = rowsToWrite.length;

    const nextActions = risks.filter((r) => r.nextAction).map((r) => nextActionRow(r.nextAction, r.detectedFrom));
    if (nextActions.length && config.output.nextActionTabName) {
      let naNextRow = await ensureHeaderAndNextRow(tabReader, config.read.fileId, config.output.nextActionTabName, NEXT_ACTION_HEADER, accessToken);
      const naRange = `${config.output.nextActionTabName}!A${naNextRow}:${String.fromCharCode(64 + NEXT_ACTION_HEADER.length)}${naNextRow + nextActions.length - 1}`;
      await updateValues(config.read.fileId, naRange, nextActions, accessToken);
      written.nextActions = nextActions.length;
    }
  }

  if (issues.length) {
    let nextRow = await ensureHeaderAndNextRow(tabReader, config.read.fileId, config.output.issueTabName, ISSUE_HEADER, accessToken);
    const rowsToWrite = issues.map((i) => issueRow(i, todayStr));
    const range = `${config.output.issueTabName}!A${nextRow}:${String.fromCharCode(64 + ISSUE_HEADER.length)}${nextRow + rowsToWrite.length - 1}`;
    await updateValues(config.read.fileId, range, rowsToWrite, accessToken);
    written.issues = rowsToWrite.length;
  }

  return written;
}

async function applyJira(config, decision) {
  const { JIRA_EMAIL, JIRA_API_TOKEN, JIRA_BASE_URL } = process.env;
  if (!JIRA_EMAIL || !JIRA_API_TOKEN || !JIRA_BASE_URL) {
    throw new Error('Thiếu JIRA_EMAIL/JIRA_API_TOKEN/JIRA_BASE_URL trong .env');
  }
  const written = { risks: 0, issues: 0, nextActions: 0 };
  for (const r of decision.risks || []) {
    await createIssue({
      baseUrl: JIRA_BASE_URL,
      email: JIRA_EMAIL,
      token: JIRA_API_TOKEN,
      projectKey: config.read.jiraProjectKey,
      issueType: config.output.riskIssueType,
      summary: r.description,
      description: `${r.description}\n\nDetected from: ${r.detectedFrom}\nMitigation: ${r.chosenMitigation || ''}`,
    });
    written.risks += 1;
  }
  for (const i of decision.issues || []) {
    await createIssue({
      baseUrl: JIRA_BASE_URL,
      email: JIRA_EMAIL,
      token: JIRA_API_TOKEN,
      projectKey: config.read.jiraProjectKey,
      issueType: config.output.issueIssueType,
      summary: i.description,
      description: `${i.description}\n\nDetected from: ${i.detectedFrom}`,
    });
    written.issues += 1;
  }
  return written;
}

function updateSnapshotWithApplied(decision, todayStr) {
  const snapshotPath = path.join(ROOT, 'state', `risk-snapshot-${todayStr}.json`);
  const snapshot = fs.existsSync(snapshotPath) ? JSON.parse(fs.readFileSync(snapshotPath, 'utf8')) : { risks: [], issues: [] };
  const appliedKeys = new Set((decision.risks || []).map((r) => `${r.category}__${r.detectedFrom}`));
  for (const r of snapshot.risks || []) {
    if (appliedKeys.has(`${r.category}__${r.detectedFrom}`)) r.status = 'Confirmed';
  }
  fs.writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2), 'utf8');
}

function markDraftApplied(draftDate) {
  const draftPath = path.join(ROOT, 'drafts', `draft-${draftDate}.md`);
  const appliedPath = path.join(ROOT, 'drafts', `draft-${draftDate}.applied.md`);
  if (fs.existsSync(draftPath)) fs.renameSync(draftPath, appliedPath);
}

function appendAuditLog(config, written, appliedBy) {
  const line = `[${new Date().toISOString().replace('T', ' ').slice(0, 19)}] ACTION=apply SOURCE=${config.source} NEW=${written.risks + written.issues} UPDATED=0 BY="${appliedBy || 'PM'}" CHANGES="ghi ${written.risks} risk, ${written.issues} issue, ${written.nextActions} next action"`;
  fs.appendFileSync(path.join(ROOT, 'risk-assessment-audit.log'), `${line}\n`, 'utf8');
  return line;
}

async function main() {
  if (!fs.existsSync(PENDING_APPLY_PATH)) {
    output({
      ok: false,
      reason: 'no_pending_apply',
      message: `Không tìm thấy ${path.relative(ROOT, PENDING_APPLY_PATH)} — ghi quyết định đã PM xác nhận vào file này (qua Write tool) trước khi chạy apply.js.`,
    });
    process.exitCode = 1;
    return;
  }
  let decision;
  try {
    decision = JSON.parse(fs.readFileSync(PENDING_APPLY_PATH, 'utf8'));
  } catch (e) {
    output({ ok: false, reason: 'invalid_input', message: `${path.relative(ROOT, PENDING_APPLY_PATH)} không phải JSON hợp lệ` });
    process.exitCode = 1;
    return;
  }

  const config = loadConfig();
  if (!config || !config.source) {
    output({ ok: false, reason: 'no_config' });
    process.exitCode = 1;
    return;
  }

  const todayStr = today();
  let written;
  if (config.source === 'gg-sheet') {
    written = await applyGgSheet(config, decision);
  } else if (config.source === 'jira') {
    written = await applyJira(config, decision);
  } else {
    output({ ok: false, reason: 'unknown_source', source: config.source });
    process.exitCode = 1;
    return;
  }

  updateSnapshotWithApplied(decision, todayStr);
  if (decision.draftDate) markDraftApplied(decision.draftDate);
  const auditLine = appendAuditLog(config, written, decision.appliedBy);
  fs.unlinkSync(PENDING_APPLY_PATH); // tránh áp dụng nhầm lại quyết định cũ ở lần chạy sau

  output({ ok: true, written, auditLine });
}

main().catch((e) => {
  output({ ok: false, reason: 'error', message: e.message });
  process.exitCode = 1;
});
