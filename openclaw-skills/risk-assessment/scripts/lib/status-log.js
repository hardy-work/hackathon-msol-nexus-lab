'use strict';

const fs = require('fs');

/**
 * Sprint tabs (gg-sheet) không có cột lưu ngày status đổi lần cuối, nên suy ra
 * "lastUpdated" bằng cách so sánh status hôm nay với lần đọc gần nhất, lưu ở
 * state/task-status-log.json: { "<detectedFrom>": { status, since } }.
 */

function loadStatusLog(filePath) {
  if (!fs.existsSync(filePath)) return {};
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (e) {
    return {};
  }
}

function saveStatusLog(filePath, log) {
  fs.writeFileSync(filePath, JSON.stringify(log, null, 2), 'utf8');
}

/**
 * @returns {{tasks: object[], log: object}} tasks with lastUpdated filled in,
 * plus the updated log to persist via saveStatusLog.
 */
function applyStatusLog(tasks, log, today) {
  const newLog = { ...log };
  const tasksWithLastUpdated = tasks.map((t) => {
    const prev = newLog[t.detectedFrom];
    const since = prev && prev.status === t.status ? prev.since : today;
    newLog[t.detectedFrom] = { status: t.status, since };
    return { ...t, lastUpdated: since };
  });
  return { tasks: tasksWithLastUpdated, log: newLog };
}

module.exports = { loadStatusLog, saveStatusLog, applyStatusLog };
