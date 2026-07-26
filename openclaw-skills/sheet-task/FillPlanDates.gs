/**
 * FillPlanDates.gs — script chạy MỘT LẦN trong editor Apps Script.
 *
 * Không cần deploy, không cần web app, không cần token. Dán vào editor của
 * chính file Sheet, chọn hàm `fillPlanDates` rồi bấm Run.
 *
 * Việc nó làm: tính lại cột PLAN Start Date (I) và End Date (J) cho từng
 * người, theo quy tắc tích luỹ giờ liên tục.
 *
 * ┌─ QUY TẮC ────────────────────────────────────────────────────────────┐
 * │ - Mỗi ngày công 8h                                                   │
 * │ - Giờ chảy liên tục: task dư giờ thì tràn sang ngày sau, task kế tiếp │
 * │   bắt đầu ngay từ giờ trống còn lại của ngày đó (không đợi ngày mới)  │
 * │ - Mỗi người một hàng đợi riêng, các người chạy song song              │
 * │ - Thứ tự trong hàng đợi = thứ tự dòng trên sheet                      │
 * │ - Bỏ qua T7, CN và ngày lễ (đọc từ tab Config, xem Code.gs)           │
 * └──────────────────────────────────────────────────────────────────────┘
 *
 * DÙNG CHUNG với Code.gs: isWorkingDay_, nextWorkingDay_, consume_, fmt_,
 * holidaySet_, HOURS_PER_DAY, TIMEZONE. Mọi file .gs chia sẻ global scope nên
 * file này KHÔNG định nghĩa lại chúng — tránh hai bản đè nhau. Cần Code.gs có
 * mặt trong cùng project (luôn đúng).
 *
 * MẶC ĐỊNH LÀ DRY RUN — chạy lần đầu chỉ in kết quả ra Nhật ký (Logs), không
 * sửa gì. Xem thấy đúng rồi mới đổi DRY_RUN = false và chạy lại để ghi thật.
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

/** true = chỉ in ra Logs, không ghi. Đổi thành false khi đã xem và đồng ý. */
var DRY_RUN = true;

/** gid của tab cần tính (lấy từ URL: .../edit#gid=<số này>). */
var TARGET_GID = 2050369208;

/** Dòng đầu tiên có dữ liệu thật (dòng 1-8 là tiêu đề, filter, hàng tổng). */
var FIRST_DATA_ROW = 9;

/**
 * Ngày làm việc đầu tiên, dạng yyyy-MM-dd.
 * 25-07-2026 là thứ Bảy nên mốc bắt đầu là thứ Hai 27-07-2026.
 * Nếu để rỗng '' thì script tự lấy ngày làm việc kế tiếp tính từ hôm nay.
 */
var START_DATE = '2026-07-27';

// HOURS_PER_DAY, HOLIDAYS, TIMEZONE, isWorkingDay_, nextWorkingDay_, consume_,
// fmt_, holidaySet_ — dùng chung từ Code.gs (né lễ đọc từ tab Config).

/**
 * false = luôn dùng cột Estimate (H).
 * true  = ưu tiên Re-estimate (K) nếu ô đó có số, chưa có mới lấy Estimate.
 *
 * Để false cho khớp yêu cầu "tính theo cột est". Bật true khi muốn lịch phản
 * ánh ước lượng dev đã sửa lại.
 */
var PREFER_REESTIMATE = false;

// Chỉ số cột (A = 1)
var COL_NO         = 1;   // A  công thức — không đụng
var COL_TASK       = 5;   // E
var COL_SUBTASK    = 6;   // F
var COL_ASSIGNEE   = 7;   // G
var COL_ESTIMATE   = 8;   // H
var COL_PLAN_START = 9;   // I  ← ghi
var COL_PLAN_END   = 10;  // J  ← ghi
var COL_REESTIMATE = 11;  // K
var LAST_COL       = 19;  // S

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function fillPlanDates() {
  var sh = sheetByGid_(TARGET_GID);
  var lastRow = sh.getLastRow();
  if (lastRow < FIRST_DATA_ROW) {
    Logger.log('Tab "%s" không có dòng dữ liệu nào.', sh.getName());
    return;
  }

  var values = sh
    .getRange(FIRST_DATA_ROW, 1, lastRow - FIRST_DATA_ROW + 1, LAST_COL)
    .getValues();

  // Mỗi người một con trỏ thời gian riêng.
  var cursors = {};
  var plan = [];
  var skipped = [];

  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var rowNum = FIRST_DATA_ROW + i;

    var assignee = String(row[COL_ASSIGNEE - 1] || '').trim();
    var task = String(row[COL_TASK - 1] || '').trim();
    var hours = pickHours_(row);

    if (!assignee || !task) continue;             // dòng trống / dòng tổng nhóm
    if (!hours || hours <= 0) {
      skipped.push('dòng ' + rowNum + ': không có số giờ');
      continue;
    }

    if (!cursors[assignee]) {
      cursors[assignee] = { day: firstWorkingDay_(), used: 0 };
    }

    var span = consume_(cursors[assignee], hours);
    plan.push({
      row: rowNum,
      assignee: assignee,
      task: task,
      hours: hours,
      start: span.start,
      end: span.end
    });
  }

  report_(sh, plan, skipped);
  if (!DRY_RUN) write_(sh, plan);
}

/** Lấy số giờ của một dòng theo cấu hình PREFER_REESTIMATE. */
function pickHours_(row) {
  if (PREFER_REESTIMATE) {
    var re = Number(row[COL_REESTIMATE - 1]);
    if (re > 0) return re;
  }
  var est = Number(row[COL_ESTIMATE - 1]);
  return est > 0 ? est : 0;
}

// ---------------------------------------------------------------------------
// Ghi
// ---------------------------------------------------------------------------

function write_(sh, plan) {
  var written = 0;
  var blocked = [];

  for (var i = 0; i < plan.length; i++) {
    var p = plan[i];

    // Không bao giờ ghi đè công thức. Cột I/J lẽ ra là ngày nhập tay, nhưng
    // nếu ai đó gắn công thức vào thì ghi giá trị cứng lên sẽ xoá mất công
    // thức đó vĩnh viễn — để máy tự phát hiện thay vì tin vào giả định.
    if (sh.getRange(p.row, COL_PLAN_START).getFormula() !== '' ||
        sh.getRange(p.row, COL_PLAN_END).getFormula() !== '') {
      blocked.push('dòng ' + p.row + ': ô PLAN đang là công thức, bỏ qua');
      continue;
    }

    sh.getRange(p.row, COL_PLAN_START).setValue(p.start);
    sh.getRange(p.row, COL_PLAN_END).setValue(p.end);
    written++;
  }

  SpreadsheetApp.flush();

  Logger.log('');
  Logger.log('=== ĐÃ GHI ' + num_(written) + '/' + num_(plan.length) + ' dòng ===');
  for (var b = 0; b < blocked.length; b++) Logger.log('  ⚠ ' + blocked[b]);
}

// ---------------------------------------------------------------------------
// Ngày làm việc
// ---------------------------------------------------------------------------

function firstWorkingDay_() {
  var d;
  if (START_DATE) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(START_DATE);
    if (!m) throw new Error('START_DATE phải dạng yyyy-MM-dd, đang là: ' + START_DATE);
    d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  } else {
    var now = new Date();
    d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }
  return isWorkingDay_(d) ? d : nextWorkingDay_(d);   // isWorkingDay_/nextWorkingDay_ từ Code.gs
}

// ---------------------------------------------------------------------------
// Báo cáo
// ---------------------------------------------------------------------------

function report_(sh, plan, skipped) {
  // Logger.log('%s', <số>) in ra kiểu float ("9.0", "2.050369208E9") vì Apps
  // Script coi mọi số là double. Ghép chuỗi bằng num_() để log đọc được —
  // đây là màn hình dùng để duyệt trước khi ghi, khó đọc là dễ bỏ sót.
  Logger.log('=== ' + (DRY_RUN ? 'DRY RUN — CHƯA GHI GÌ' : 'CHUẨN BỊ GHI') + ' ===');
  Logger.log('Tab: ' + sh.getName() + ' (gid ' + num_(TARGET_GID) + ') | ' +
    num_(HOURS_PER_DAY) + 'h/ngày | bắt đầu ' + fmt_(firstWorkingDay_()));
  Logger.log('Nguồn giờ: %s', PREFER_REESTIMATE ? 'Re-estimate (K), thiếu thì Estimate (H)' : 'Estimate (H)');
  Logger.log('');

  var byPerson = {};
  for (var i = 0; i < plan.length; i++) {
    var p = plan[i];
    if (!byPerson[p.assignee]) byPerson[p.assignee] = [];
    byPerson[p.assignee].push(p);
  }

  Object.keys(byPerson).forEach(function (name) {
    var rows = byPerson[name];
    var total = rows.reduce(function (s, r) { return s + r.hours; }, 0);

    Logger.log('--- ' + name + ' — ' + num_(total) + 'h, xong ' +
      fmt_(rows[rows.length - 1].end) + ' ---');
    for (var j = 0; j < rows.length; j++) {
      var r = rows[j];
      Logger.log('  dòng ' + num_(r.row) + ' | ' + num_(r.hours) + 'h | ' +
        fmt_(r.start) + ' → ' + fmt_(r.end) + ' | ' + truncate_(r.task, 45));
    }
    Logger.log('');
  });

  for (var s = 0; s < skipped.length; s++) Logger.log('  bỏ qua: %s', skipped[s]);

  if (DRY_RUN) {
    Logger.log('');
    Logger.log('>> Đây là DRY RUN. Đổi DRY_RUN = false rồi chạy lại để ghi thật.');
  }
}

/** Tên task trong sheet có xuống dòng (ô wrap nhiều dòng) — gộp lại 1 dòng. */
function truncate_(s, n) {
  var flat = String(s).replace(/\s*[\r\n]+\s*/g, ' ').trim();
  return flat.length > n ? flat.slice(0, n - 1) + '…' : flat;
}

/** In số nguyên không có đuôi ".0" và không chuyển sang ký hiệu mũ. */
function num_(v) {
  var n = Number(v);
  return Number.isInteger(n) ? n.toFixed(0) : String(n);
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function sheetByGid_(gid) {
  var sheets = SpreadsheetApp.getActiveSpreadsheet().getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === gid) return sheets[i];
  }

  var names = sheets.map(function (s) {
    return s.getName() + '(' + s.getSheetId() + ')';
  }).join(', ');
  throw new Error('Không tìm thấy tab gid=' + gid + '. Các tab: ' + names);
}
