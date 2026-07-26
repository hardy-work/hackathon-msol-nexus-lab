/**
 * SlackMap.gs — "danh bạ" nối người Slack với assignee trong sheet.
 *
 * Google Sheet không có danh bạ người dùng như Jira (Jira tra @tên → accountId
 * qua API user/search). Sheet chỉ có chuỗi tự do "[BrSE] Duy". Tab SlackMap này
 * là bản thay thế thủ công: nối slack_user_id → assignee, lập một lần dùng mãi.
 *
 * Luồng khi chạy thật:
 *   Duy nhắn "1 | xong | 3h"  (KHÔNG gõ tên)
 *     → bot đọc thread, thấy người gửi (id U01ABC HOẶC tên MH_Duy)
 *     → resolveAssignee_(<định danh>)  → "[BrSE] Duy"
 *     → ghi đúng dòng
 *
 * KHỚP LINH HOẠT: chưa chốt runtime OpenClaw đưa cho agent `slack_id` (U0123…)
 * hay tên hiển thị (MH_VinhNV). Nên tab có CẢ HAI cột và hàm khớp thử cả hai
 * (matchSlackRow_). Mai test trong Slack thấy cái nào đúng thì điền cột đó.
 *
 * Cột: slack_id | assignee | role | slack_display_name
 *
 * ┌─ SETUP (một lần) ─────────────────────────────────────────────────────┐
 * │ 1. Chạy `createSlackMapTab` → tạo tab, mồi sẵn tên từ cột PIC Config.  │
 * │ 2. Điền slack_id VÀ/HOẶC slack_display_name cho từng người.            │
 * │ 3. Điền "pm" vào cột role cho ai được lập/dồn lịch.                    │
 * └───────────────────────────────────────────────────────────────────────┘
 */

var SLACKMAP_TAB = 'SlackMap';

/** Tên tab Config và vị trí cột PIC (để mồi danh sách người). */
var CONFIG_TAB = 'Config';
var CONFIG_PIC_HEADER = 'PIC';

// ---------------------------------------------------------------------------
// Setup — chạy tay một lần
// ---------------------------------------------------------------------------

/**
 * Tạo tab SlackMap, mồi sẵn danh sách assignee từ cột PIC của tab Config.
 * Cột slack_id để trống — điền tay sau.
 * Chạy lại nhiều lần an toàn: không ghi đè tab đã có.
 */
function createSlackMapTab() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  if (ss.getSheetByName(SLACKMAP_TAB)) {
    Logger.log('Tab "%s" đã tồn tại — không tạo lại.', SLACKMAP_TAB);
    return;
  }

  var sh = ss.insertSheet(SLACKMAP_TAB);
  sh.getRange(1, 1, 1, 4).setValues([['slack_id', 'assignee', 'role', 'slack_display_name']]);
  sh.getRange(1, 1, 1, 4).setFontWeight('bold');
  sh.setFrozenRows(1);

  var people = knownAssignees_();
  if (people.length) {
    // role để trống = dev. Điền "pm" cho người được lập/dồn lịch.
    var rows = people.map(function (name) { return ['', name, '', '']; });
    sh.getRange(2, 1, rows.length, 4).setValues(rows);
  }

  sh.setColumnWidth(1, 160);
  sh.setColumnWidth(2, 160);
  sh.setColumnWidth(3, 60);
  sh.setColumnWidth(4, 200);

  Logger.log('✓ Tạo tab "%s" với %s người từ cột PIC.', SLACKMAP_TAB, people.length);
  Logger.log('→ Giờ điền cột slack_id cho từng người. Lấy ID bằng action=collect.');
}

/** Lấy danh sách assignee đã biết từ cột PIC của tab Config. */
function knownAssignees_() {
  var cfg = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG_TAB);
  if (!cfg) return [];

  var data = cfg.getDataRange().getValues();
  // Tìm cột có header "PIC".
  var picCol = -1;
  for (var r = 0; r < Math.min(data.length, 5); r++) {
    for (var c = 0; c < data[r].length; c++) {
      if (String(data[r][c]).trim() === CONFIG_PIC_HEADER) { picCol = c; break; }
    }
    if (picCol !== -1) { var headerRow = r; break; }
  }
  if (picCol === -1) return [];

  var seen = {};
  var out = [];
  for (var i = headerRow + 1; i < data.length; i++) {
    var v = String(data[i][picCol] || '').trim();
    if (v && !seen[v]) { seen[v] = true; out.push(v); }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Đọc bảng + tra cứu
// ---------------------------------------------------------------------------

/**
 * Đọc tab SlackMap thành mảng dòng {id, assignee, role, name}.
 *
 * `id`   = cột slack_id (dạng U0123…, nếu runtime đưa id thật)
 * `name` = cột slack_display_name (dạng MH_VinhNV, nếu runtime đưa tên hiển thị)
 *
 * Chưa chốt runtime đưa cái nào, nên giữ CẢ HAI cột và khớp linh hoạt (xem
 * matchSlackRow_). Mai test trong Slack thấy cái nào đúng thì dùng cột đó.
 */
function readSlackRows_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SLACKMAP_TAB);
  if (!sh || sh.getLastRow() < 2) return [];

  var vals = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
  var out = [];
  for (var i = 0; i < vals.length; i++) {
    var assignee = String(vals[i][1] || '').trim();
    if (!assignee) continue;
    out.push({
      id:       String(vals[i][0] || '').trim(),
      assignee: assignee,
      role:     String(vals[i][2] || '').trim().toLowerCase(),
      name:     String(vals[i][3] || '').trim()
    });
  }
  return out;
}

/** Bảng { định-danh: assignee } cho action=map — gộp cả id lẫn tên hiển thị. */
function readSlackMap_() {
  var rows = readSlackRows_();
  var map = {};
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].id) map[rows[i].id] = rows[i].assignee;
    if (rows[i].name) map[rows[i].name] = rows[i].assignee;
  }
  return map;
}

/**
 * Khớp một định danh với một dòng SlackMap — thử CẢ slack_id LẪN tên hiển thị,
 * không phân biệt hoa thường. Nhờ vậy chạy được dù runtime đưa `U0123…` hay
 * `MH_VinhNV`. Trả null nếu không thấy.
 */
function matchSlackRow_(identifier) {
  if (!identifier) return null;
  var want = String(identifier).trim().toLowerCase();
  var rows = readSlackRows_();
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].id.toLowerCase() === want || rows[i].name.toLowerCase() === want) {
      return rows[i];
    }
  }
  return null;
}

/**
 * Định danh (slack_id hoặc tên hiển thị) → assignee. Trả null nếu chưa map —
 * để agent HỎI thay vì đoán bừa, đúng nguyên tắc "thà hỏi còn hơn ghi nhầm".
 */
function resolveAssignee_(identifier) {
  var row = matchSlackRow_(identifier);
  return row ? row.assignee : null;
}

/**
 * Định danh có phải PM không (cột role = "pm"). Khớp cả id lẫn tên hiển thị.
 * Dùng để chặn action ghi PLAN (fillplan/reschedule) — chỉ PM được lập lịch.
 */
function isPm_(identifier) {
  var row = matchSlackRow_(identifier);
  return row ? row.role === 'pm' : false;
}

/** Có ít nhất một PM được khai trong SlackMap chưa? (để biết đã bật phân quyền) */
function hasAnyPm_() {
  var rows = readSlackRows_();
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].role === 'pm') return true;
  }
  return false;
}

/**
 * Ghi một ánh xạ mới vào SlackMap (khi agent vừa hỏi ra được ai là ai).
 * Cập nhật nếu slack_id đã có, thêm dòng nếu chưa.
 * Cột: slack_id | assignee | role | slack_display_name.
 * `role` chỉ ghi khi được truyền (để không xoá role đang có).
 */
function upsertSlackMap_(slackId, assignee, displayName, role) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SLACKMAP_TAB);
  if (!sh) { createSlackMapTab(); sh = ss.getSheetByName(SLACKMAP_TAB); }

  slackId = String(slackId).trim();
  var last = sh.getLastRow();

  // Đã có slack_id này chưa?
  if (last >= 2) {
    var ids = sh.getRange(2, 1, last - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (String(ids[i][0]).trim() === slackId) {
        var row = 2 + i;
        if (assignee) sh.getRange(row, 2).setValue(assignee);
        if (role) sh.getRange(row, 3).setValue(role);
        if (displayName) sh.getRange(row, 4).setValue(displayName);
        return { row: row, updated: true };
      }
    }
  }

  // Có dòng nào đã điền assignee nhưng trống slack_id không? (mồi từ Config)
  if (last >= 2) {
    var pairs = sh.getRange(2, 1, last - 1, 2).getValues();
    for (var j = 0; j < pairs.length; j++) {
      if (!String(pairs[j][0]).trim() &&
          String(pairs[j][1]).trim() === String(assignee).trim()) {
        var r2 = 2 + j;
        sh.getRange(r2, 1).setValue(slackId);
        if (role) sh.getRange(r2, 3).setValue(role);
        if (displayName) sh.getRange(r2, 4).setValue(displayName);
        return { row: r2, updated: true };
      }
    }
  }

  sh.appendRow([slackId, assignee, role || '', displayName || '']);
  return { row: sh.getLastRow(), updated: false };
}
