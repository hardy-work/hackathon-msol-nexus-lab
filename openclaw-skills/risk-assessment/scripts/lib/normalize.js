'use strict';

/**
 * Thuần hàm chuyển đổi dữ liệu thô (gg-sheet rows / Jira issues) sang task
 * item chuẩn hóa cho scripts/rule-engine.js. Không gọi network ở đây — xem
 * scripts/lib/sheets-client.js, scripts/lib/jira-client.js cho phần I/O.
 */

function colToIndex(letter) {
  let n = 0;
  for (const ch of letter.trim().toUpperCase()) {
    n = n * 26 + (ch.charCodeAt(0) - 64);
  }
  return n - 1;
}

// Sheet dùng format D-M-YYYY / DD-M-YYYY (không zero-pad tháng) — không dùng
// new Date(string) trực tiếp vì parser mặc định hiểu nhầm thành MM-DD-YYYY.
function parseDMYDate(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s) return null;
  const m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(s);
  if (!m) return null;
  const [, d, mo, y] = m;
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

// Số giờ đôi khi dùng dấu phẩy thập phân (vd dòng subtotal "240,0").
function parseHoursNumber(raw) {
  if (raw === null || raw === undefined) return null;
  const s = String(raw).trim();
  if (!s) return null;
  const n = Number(s.replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

// Header row (kể cả header nhiều tầng) không xác định được bằng số dòng cố
// định — nhận diện bằng cách so khớp giá trị cell với chính tên field trong
// `columns` (vd cell ở cột Task chứa đúng chữ "Task").
function looksLikeHeaderRow(row, idx, columns) {
  let matches = 0;
  for (const field of Object.keys(columns)) {
    const val = row[idx[field]];
    if (val && String(val).trim().toLowerCase() === field.trim().toLowerCase()) matches += 1;
  }
  return matches >= 2;
}

/**
 * @param {{rows: string[][], columns: object, tabName: string, statusDoneValues: string[]}} input
 * @returns {object[]} normalized task items
 */
function rowsToTasks({ rows, columns, tabName, statusDoneValues }) {
  const idx = {};
  for (const [field, letter] of Object.entries(columns)) idx[field] = colToIndex(letter);

  const get = (row, field) => {
    const i = idx[field];
    return i === undefined || i < 0 ? undefined : row[i];
  };

  const tasks = [];
  let lastCategory = null;

  (rows || []).forEach((row, i) => {
    const rowNumber = i + 1;
    const title = get(row, 'Task');
    if (!title || !String(title).trim()) return; // subtotal/blank row
    if (looksLikeHeaderRow(row, idx, columns)) return; // header row (kể cả header nhiều tầng)

    const category = get(row, 'Category');
    if (category && String(category).trim()) lastCategory = String(category).trim();

    const status = (get(row, 'Status') || '').toString().trim();
    const estimateHours = parseHoursNumber(get(row, 'Re-estimate(h)')) ?? parseHoursNumber(get(row, 'Estimate(h)'));

    // Ưu tiên dùng TaskID thật (vd "AU-3") làm detectedFrom nếu tab có mapping
    // cột này — ổn định qua việc thêm/xoá/sắp xếp lại dòng, khác hẳn "row N"
    // (vốn lệch ngay khi ai đó chèn thêm 1 dòng phía trên). Tab không có cột
    // TaskID (vd Jira, hoặc sheet cũ) thì fallback về kiểu cũ.
    const taskId = get(row, 'TaskID');
    const detectedFrom = taskId && String(taskId).trim() ? String(taskId).trim() : `${tabName}, row ${rowNumber}`;

    tasks.push({
      id: get(row, 'No.') || taskId || null,
      title: String(title).trim(),
      assignee: get(row, 'Assignee') ? String(get(row, 'Assignee')).trim() : null,
      status,
      isDone: (statusDoneValues || []).includes(status),
      planStart: parseDMYDate(get(row, 'Plan Start')),
      planEnd: parseDMYDate(get(row, 'Plan End')),
      estimateHours,
      actualHours: parseHoursNumber(get(row, 'Actual Effort(h)')),
      sprint: get(row, 'Sprint') ? String(get(row, 'Sprint')).trim() : tabName,
      category: lastCategory,
      // Priority của TASK (từ cột "Priority" trên sheet, vd "High") — khác với
      // `priority` (Critical/High/Medium/Low) mà rule-engine tự tính cho từng
      // risk/issue dựa theo Score. Đặt tên khác để khỏi lẫn 2 khái niệm.
      taskPriority: get(row, 'Priority') ? String(get(row, 'Priority')).trim() : null,
      lastUpdated: null, // điền bởi scripts/lib/status-log.js
      detectedFrom,
    });
  });

  return tasks;
}

function jiraIssuesToTasks(issues) {
  return (issues || []).map((issue) => {
    const f = issue.fields || {};
    const sprints = f.customfield_10020;
    const sprint = Array.isArray(sprints) && sprints.length ? sprints[sprints.length - 1].name : null;
    return {
      id: issue.key,
      title: f.summary || '',
      assignee: f.assignee ? f.assignee.displayName : null,
      status: f.status ? f.status.name : '',
      isDone: !!(f.status && f.status.statusCategory && f.status.statusCategory.key === 'done'),
      planStart: null,
      planEnd: f.duedate || null,
      estimateHours: typeof f.timeoriginalestimate === 'number' ? f.timeoriginalestimate / 3600 : null,
      actualHours: typeof f.timespent === 'number' ? f.timespent / 3600 : null,
      sprint,
      category: null,
      taskPriority: f.priority ? f.priority.name : null,
      lastUpdated: f.updated ? f.updated.slice(0, 10) : null,
      detectedFrom: issue.key,
    };
  });
}

module.exports = { colToIndex, parseDMYDate, parseHoursNumber, rowsToTasks, jiraIssuesToTasks };
