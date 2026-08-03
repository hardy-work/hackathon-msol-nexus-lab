'use strict';

/**
 * Hàm thuần phục vụ việc ghi vào format Risk/Issue management chính thức
 * (ID | Date Detected | Description | Priority | Related Assignee/Task |
 * Next Action | Status | Notes). Tách riêng khỏi scripts/apply.js để có test
 * — đây đúng loại logic (parse ID, convert ngày) đã từng gây lỗi vặt khi để
 * agent tự viết lại mỗi lần.
 */

// Sheet dùng format D-M-YYYY không zero-pad (vd "27-7-2026") — ngược lại với
// scripts/lib/normalize.js's parseDMYDate (parse chiều D-M-YYYY -> ISO).
function toDMY(isoDate) {
  const [y, m, d] = isoDate.split('-');
  return `${parseInt(d, 10)}-${parseInt(m, 10)}-${y}`;
}

/** Quét cột ID (cột đầu tiên) tìm số lớn nhất theo prefix (vd "R" hoặc "I"), trả về số tiếp theo. */
function nextSequentialId(rows, prefix) {
  let max = 0;
  const re = new RegExp(`^${prefix}-(\\d+)$`, 'i');
  for (const row of (rows || []).slice(1)) {
    const m = re.exec((row[0] || '').toString().trim());
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return max + 1;
}

function formatId(prefix, n) {
  return `${prefix}-${String(n).padStart(3, '0')}`;
}

/** "<owner hoặc 'Chưa gán'> / <detectedFrom>" — khớp giọng văn mẫu PM đã dựng trên sheet thật. */
function relatedAssigneeTask(item) {
  return `${item.owner || 'Chưa gán'} / ${item.detectedFrom}`;
}

const NOTES_TRACE_RE = /Detected from:\s*([^|]+?)\s*\|\s*Category:\s*(.+)$/i;

/**
 * Nhét trace máy-đọc-được vào cột Notes để scan.js dedupe lại được — format
 * chính thức không có cột Category/Detected From riêng nên phải giấu ở đây.
 */
function notesTrace(item) {
  return `Detected from: ${item.detectedFrom} | Category: ${item.category}`;
}

/** Parse ngược lại trace đã nhét bằng notesTrace() — dùng trong scan.js lúc dedupe. */
function parseNotesTrace(notes) {
  const m = NOTES_TRACE_RE.exec((notes || '').toString());
  if (!m) return null;
  return { detectedFrom: m[1].trim(), category: m[2].trim() };
}

module.exports = { toDMY, nextSequentialId, formatId, relatedAssigneeTask, notesTrace, parseNotesTrace };
