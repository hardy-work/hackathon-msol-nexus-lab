/**
 * sheet-task — Apps Script backend cho NexusBot_Schedule_v2.1
 *
 * Gắn trực tiếp vào file Google Sheet của dự án (container-bound), nên không
 * cần Service Account / Google Cloud. Deploy dạng Web App:
 *
 *   GET  ?action=tabs|ping|list|get|holidays|map|resolve       → đọc
 *   POST {action: update|reschedule|fillplan|map_set}          → ghi
 *
 * Agent chỉ cầm URL `.../exec` + API_TOKEN, không chạm tới credential Google.
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

/**
 * gid của tab backlog sprint (lấy từ URL: .../edit#gid=<số này>).
 *
 * Dùng gid chứ không dùng tên tab, vì file có nhiều tab cùng cấu trúc
 * (Config, Backlog_OLD, 2.2.Sprint 1, UAT, CR...) và tên tab thì đổi được,
 * còn gid thì không. Lấy tab đầu tiên là sai — tab đầu là `Config`.
 * Mọi action đều nhận `gid` để override mà không phải deploy lại.
 */
var SHEET_GID = 2050369208;

/**
 * Dòng đầu tiên chứa dữ liệu thật.
 * Tab sprint có layout: dòng 1 = ô chọn Sprint, dòng 2-3 trống, dòng 4-6 =
 * header (merged 3 dòng), dòng 7 = hàng filter, dòng 8 = hàng tổng
 * → dữ liệu bắt đầu từ dòng 9.
 */
var DATA_START_ROW = 9;

/**
 * Map cột → tên field, theo đúng thứ tự A→S.
 *
 * Khai báo tay thay vì đọc header, vì header merge qua 3 dòng và có nhóm cha
 * (PLAN / Actual) — parse tự động không đáng tin. Sheet đổi thứ tự cột thì
 * phải sửa mảng này.
 */
var COLUMNS = [
  'no',                  // A  công thức =ROW()-8
  'category',            // B  Category / Milestone
  'type',                // C  FE | BE | QC | Common | BrSE | Design
  'sprint',              // D
  'task',                // E
  'subtask_vi',          // F  Sub-task Vietnamese
  'assignee',            // G
  'plan_estimate_h',     // H  PLAN > Estimate (h)
  'plan_start',          // I  PLAN > Start Date
  'plan_end',            // J  PLAN > End Date
  'actual_reestimate_h', // K  Actual > Re-estimate (h)
  'actual_start',        // L  Actual > Start Date
  'actual_end',          // M  Actual > End Date
  'actual_effort_h',     // N  Actual > Actual Effort (h)
  'progress',            // O  công thức = Actual Effort ÷ Re-estimate
  '_progress_merge',     // P  ô merge của Progress, luôn rỗng
  'remaining_h',         // Q  công thức = Re-estimate − Actual Effort
  'status',              // R
  'note'                 // S
];

/**
 * Field bot được phép ghi, kèm kiểu để ép giá trị.
 *
 * Ba nhóm cố tình vắng mặt:
 *   - `no`, `progress`, `remaining_h` — là CÔNG THỨC. Ghi giá trị cứng lên sẽ
 *     xoá công thức vĩnh viễn, và sẽ không ai nhận ra cho tới khi số liệu đã
 *     sai một thời gian dài. Progress/Remaining tự tính từ Re-estimate và
 *     Actual Effort, chỉ cần ghi hai cột nguồn là đủ.
 *   - `task`, `subtask_vi`, `category`, `type`, `sprint` — là mốc định danh
 *     dòng. Cơ chế verify-before-write dựa vào chúng; cho sửa thì mất luôn khả
 *     năng phát hiện ghi nhầm dòng.
 *   - `plan_estimate_h` — ước lượng gốc của PM, giữ nguyên để còn so sánh được
 *     với Re-estimate. Task phình ra thì ghi vào Re-estimate.
 */
var WRITABLE = {
  assignee:            'text',
  plan_start:          'date',   // bot dồn lịch → được sửa
  plan_end:            'date',
  actual_reestimate_h: 'number',
  actual_start:        'date',
  actual_end:          'date',
  actual_effort_h:     'number',
  status:              'text',
  note:                'text'
};

/** Status hợp lệ, lấy từ tab `Config` của chính file này. */
var VALID_STATUS = [
  'Open', 'Study', 'Code done', 'Reviewing', 'Testing', 'Verify bug',
  'Done', 'In progress', 'N/A', 'ﾕｰﾄﾞﾑ様確認待ち', 'Pending',
  'Chờ KH phản hồi', 'Cancel'
];

/** Status coi như đã đóng — không xếp lịch, không đụng vào plan. */
var CLOSED_STATUS = ['Done', 'Cancel', 'N/A'];

var HOURS_PER_DAY = 8;

/**
 * Ngày nghỉ lễ khai TAY (dạng 'yyyy-MM-dd') — chỉ dùng để bổ sung.
 *
 * Nguồn chính là cột "Date" trong tab Config (đọc bằng holidaySet_). Mảng này
 * để trống trong điều kiện thường; chỉ điền khi cần thêm một ngày nghỉ đột
 * xuất không tiện đưa vào Config.
 */
var HOLIDAYS = [];

/** Tên tab chứa danh mục lễ. */
var CONFIG_TAB_NAME = 'Config';

/**
 * true  = task không bao giờ được kéo lên sớm hơn ngày PM đã xếp.
 * false = tính lại thuần tuý theo giờ trống, có thể kéo lên sớm.
 *
 * Để true vì PM xếp một task vào tuần sau có thể do đang chờ thứ gì đó bên
 * ngoài (khách duyệt, task người khác xong). Kéo lên sớm là tự ý đổi kế hoạch
 * chứ không còn là dồn lịch do trễ nữa.
 */
var NEVER_EARLIER = true;

var TIMEZONE = 'Asia/Ho_Chi_Minh';

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

function doGet(e) {
  try {
    var params = (e && e.parameter) || {};
    if (!isAuthorized_(params.token)) return json_({ ok: false, error: 'unauthorized' });

    switch (params.action || 'list') {
      case 'tabs':
        // Không đụng SHEET_GID — luôn chạy được, kể cả khi gid cấu hình sai.
        return json_({ ok: true, tabs: listTabs_() });

      case 'ping':
        var sh = sheet_(params.gid);
        return json_({
          ok: true,
          sheet: sh.getName(),
          gid: sh.getSheetId(),
          sprint: sprintName_(params.gid),
          rows: countRows_(params.gid),
          writable: Object.keys(WRITABLE)
        });

      case 'get':
        return json_({ ok: true, task: getRow_(params.gid, Number(params.row)) });

      case 'list':
        return json_({
          ok: true,
          sprint: sprintName_(params.gid),
          tasks: listTasks_(params)
        });

      case 'holidays':
        // Trả danh sách ngày nghỉ backend đang dùng (Config + HOLIDAYS).
        return json_({ ok: true, holidays: Object.keys(holidaySet_()).sort() });

      case 'map':
        // Trả cả bảng SlackMap — để agent xem ai đã có ID, ai chưa.
        return json_({ ok: true, map: readSlackMap_() });

      case 'resolve':
        // Một slack_id → assignee. Trả null (kèm ok:true) nếu chưa map, để
        // agent biết cần HỎI chứ không phải lỗi hệ thống.
        var who = resolveAssignee_(params.slackId);
        return json_({ ok: true, slackId: params.slackId || '', assignee: who });

      default:
        return json_({ ok: false, error: 'unknown action: ' + params.action });
    }
  } catch (err) {
    return json_({ ok: false, error: errMsg_(err) });
  }
}

function doPost(e) {
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!isAuthorized_(body.token)) return json_({ ok: false, error: 'unauthorized' });

    switch (body.action || 'update') {
      case 'update':     return json_(update_(body));
      case 'reschedule': return guardReschedule_(body) || json_(reschedule_(body));
      case 'fillplan':   return requirePm_(body) || json_(fillplan_(body));
      case 'map_set':
        // Lưu một ánh xạ slack_id → assignee (khi agent vừa hỏi ra được).
        // role tùy chọn: "pm" để cấp quyền lập/dồn lịch.
        return json_({ ok: true, result: upsertSlackMap_(body.slackId, body.assignee, body.displayName, body.role) });
      default:           return json_({ ok: false, error: 'unknown action: ' + body.action });
    }
  } catch (err) {
    return json_({ ok: false, error: errMsg_(err) });
  }
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/**
 * So sánh token gửi lên với API_TOKEN lưu trong Script Properties.
 *
 * Web App deploy dạng "Anyone" thì URL là thứ duy nhất chặn người lạ — mà URL
 * lọt vào log, lịch sử shell, git rất dễ. Token này mới là hàng rào thật.
 */
function isAuthorized_(token) {
  var expected = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  if (!expected) throw new Error('API_TOKEN chưa được set trong Script Properties');
  return token === expected;
}

/**
 * Cổng cho `fillplan` — CHỈ PM. fillplan ghi đè toàn bộ kế hoạch (reset), chỉ
 * dùng đầu dự án hoặc khi PM chủ động làm lại. Dev không bao giờ được chạy.
 *
 * Trả response lỗi nếu không được phép, null nếu được (`requirePm_(body) || …`).
 *
 * Danh tính lấy từ `requesterSlackId` (bot điền = người gửi tin). Logic:
 *   - Không có requesterSlackId → cho qua (token-holder gọi trực tiếp, đã được
 *     token tin tưởng). Bot LUÔN điền nên dev không "bỏ trống để lách".
 *   - Chưa khai PM nào → cho qua (giai đoạn setup, không khoá chết).
 *   - Có → phải là PM.
 */
function requirePm_(body) {
  if (!body.requesterSlackId) return null;          // token-holder trực tiếp
  if (!hasAnyPm_()) return null;                    // chưa bật phân quyền
  if (isPm_(body.requesterSlackId)) return null;    // đúng PM

  return json_({
    ok: false,
    error: 'chỉ PM mới được lập lịch (fillplan ghi đè toàn bộ kế hoạch).',
    role_required: 'pm'
  });
}

/**
 * Cổng cho `reschedule` — việc THƯỜNG NGÀY sau dev report, KHÔNG khoá PM.
 *
 * Khác fillplan: reschedule chỉ dồn phần chưa xong theo thực tế, không reset.
 * Dev report cuối ngày là bot chạy reschedule cho chính người đó. Ràng buộc
 * duy nhất: dev chỉ dồn được lịch CỦA CHÍNH MÌNH — dồn người khác / cả team
 * mới cần PM.
 */
function guardReschedule_(body) {
  if (!body.requesterSlackId) return null;          // token-holder trực tiếp
  if (!hasAnyPm_()) return null;                    // chưa bật phân quyền
  if (isPm_(body.requesterSlackId)) return null;    // PM: dồn ai cũng được

  // Dev: chỉ được dồn chính mình.
  var me = resolveAssignee_(body.requesterSlackId);
  if (!me) {
    return json_({ ok: false, error: 'người gửi chưa có trong SlackMap', needMap: true });
  }
  var target = String(body.assignee || '').trim();
  if (!target) {
    return json_({
      ok: false, role_required: 'pm',
      error: 'Dev chỉ dồn được lịch của chính mình. Dồn cả team cần PM.'
    });
  }
  // Khớp lỏng: assignee trong sheet có tiền tố vai trò ([FE]HoangMv) còn target
  // thường là tên rút gọn (HoangMv) — chấp nhận chuỗi con hai chiều.
  if (norm_(me).indexOf(norm_(target)) === -1 && norm_(target).indexOf(norm_(me)) === -1) {
    return json_({
      ok: false, role_required: 'pm',
      error: 'Dev chỉ dồn được lịch của chính mình (' + me + '). Dồn người khác cần PM.'
    });
  }
  return null;
}

// ---------------------------------------------------------------------------
// Action: update — ghi giá trị vào ô
// ---------------------------------------------------------------------------

/**
 * Cập nhật nhiều dòng trong một request.
 *
 * Body:
 *   { token, action: "update", gid?, dryRun?,
 *     updates: [
 *       { row: 9,
 *         expect: { assignee: "[BrSE] Duy", task: "..." },   // BẮT BUỘC
 *         fields: { status: "In progress", actual_effort_h: 8 } }
 *     ] }
 *
 * `expect` chống ghi nhầm dòng: cột `No.` chỉ là công thức đếm theo vị trí
 * (=ROW()-8), nên chèn/xoá một dòng là mọi số bên dưới dịch hết. Trước khi
 * ghi, hàm đọc lại dòng và đối chiếu — lệch thì bỏ qua dòng đó.
 *
 * Không update nào thất bại âm thầm: mỗi phần tử trả về `ok` hoặc kèm `reason`.
 */
function update_(body) {
  var updates = body.updates || [];
  if (!updates.length) return { ok: false, error: 'updates rỗng' };

  // Chặn hai request ghi cùng lúc. Cuối ngày cả team report một loạt thì đây
  // không phải chuyện lý thuyết.
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'sheet đang bận, thử lại sau' };

  try {
    var sh = sheet_(body.gid);
    var dryRun = body.dryRun === true;
    var results = [];
    var applied = 0;

    for (var i = 0; i < updates.length; i++) {
      var r = applyOne_(sh, updates[i], dryRun);
      if (r.ok) applied++;
      results.push(r);
    }

    if (!dryRun) SpreadsheetApp.flush();
    return {
      ok: true, dryRun: dryRun,
      applied: applied, total: updates.length, results: results
    };
  } finally {
    lock.releaseLock();
  }
}

function applyOne_(sh, u, dryRun) {
  // --- ĐỊNH DANH XẾP TẦNG ---
  // Tầng 1: có taskId (Developer Metadata) → tìm dòng theo ID. Bền nhất: dù
  //         dòng đã dịch chỗ hay tên task đã sửa, ID vẫn đi theo dòng.
  // Tầng 2: không có taskId → dùng row người gọi đưa, để expect đối chiếu.
  // Tầng 3: (bên dưới) expect lệch → từ chối ghi.
  var row;
  var relocated = false;

  if (u.taskId) {
    var byId = findRowByTaskId_(sh, u.taskId);
    if (!byId) {
      return { taskId: u.taskId, ok: false, reason: 'không tìm thấy dòng mang taskId này (có thể đã bị xoá)' };
    }
    // Nếu row người gọi đưa khác với row thật của ID → dòng đã dịch chỗ.
    // Không sao — tin ID, và báo lại để agent biết.
    if (u.row && Number(u.row) !== byId) relocated = true;
    row = byId;
  } else {
    row = Number(u.row);
    if (!row || row < DATA_START_ROW) {
      return { row: u.row, ok: false, reason: 'thiếu taskId và row không hợp lệ (phải >= ' + DATA_START_ROW + ')' };
    }
  }

  if (row > sh.getLastRow()) {
    return { row: row, ok: false, reason: 'row vượt quá dòng cuối của sheet' };
  }

  var current = rowToTask_(sh.getRange(row, 1, 1, COLUMNS.length).getValues()[0], row);

  // --- suy assignee từ slackId, rồi ĐỐI CHIẾU với dòng ---
  // Nếu update kèm slackId, tra SlackMap ra assignee và tự thêm vào expect.
  // Đây vừa là cách dev khỏi gõ tên, vừa là một lớp chống ghi nhầm: nếu người
  // gửi tin không phải người được giao dòng này, expect.assignee sẽ lệch và
  // bị chặn ngay bên dưới.
  var expect = u.expect || {};
  if (u.slackId) {
    var mapped = resolveAssignee_(u.slackId);
    if (!mapped) {
      return {
        row: row, ok: false, reason: 'slack_id "' + u.slackId + '" chưa có trong SlackMap',
        needMap: true
      };
    }
    if (expect.assignee && norm_(expect.assignee) !== norm_(mapped)) {
      return {
        row: row, ok: false,
        reason: 'người gửi (' + mapped + ') khác assignee yêu cầu (' + expect.assignee + ')'
      };
    }
    expect.assignee = mapped;
  }

  // --- đối chiếu trước khi ghi ---
  // Có taskId thì expect là tùy chọn: ID đã đảm bảo đúng dòng, khỏi cần khoá
  // văn bản. Không có taskId thì expect BẮT BUỘC — đó là lá chắn duy nhất.
  var keys = Object.keys(expect);
  if (!u.taskId && !keys.length) {
    return { row: row, ok: false, reason: 'thiếu cả taskId lẫn expect — không có gì bảo đảm đúng dòng' };
  }
  for (var k = 0; k < keys.length; k++) {
    var f = keys[k];
    if (norm_(current[f]) !== norm_(expect[f])) {
      return {
        row: row, ok: false,
        reason: 'dòng đã thay đổi — có thể ai đó đã chèn/xoá/sửa dòng',
        field: f, expected: expect[f], found: current[f]
      };
    }
  }

  // --- kiểm tra field ---
  var fields = u.fields || {};
  var names = Object.keys(fields);
  if (!names.length) return { row: row, ok: false, reason: 'fields rỗng' };

  var writes = [];
  for (var n = 0; n < names.length; n++) {
    var name = names[n];
    var kind = WRITABLE[name];

    if (!kind) {
      return {
        row: row, ok: false,
        reason: 'field "' + name + '" không được phép ghi (công thức hoặc mốc định danh)'
      };
    }
    if (name === 'status' && fields[name] && VALID_STATUS.indexOf(fields[name]) === -1) {
      return {
        row: row, ok: false,
        reason: 'status "' + fields[name] + '" không có trong tab Config',
        valid: VALID_STATUS
      };
    }

    var value = coerce_(fields[name], kind);
    if (value === undefined) {
      return {
        row: row, ok: false,
        reason: 'giá trị "' + fields[name] + '" sai kiểu cho ' + name + ' (cần ' + kind + ')'
      };
    }

    var col = COLUMNS.indexOf(name) + 1;

    // Chốt chặn cuối: dù WRITABLE đã lọc, vẫn kiểm tra ô đích có công thức
    // không. Để máy tự phát hiện thay vì tin vào danh sách khai tay — ai đó
    // gắn công thức vào cột Status chẳng hạn thì ta vẫn không phá.
    if (sh.getRange(row, col).getFormula() !== '') {
      return { row: row, ok: false, reason: 'ô ' + name + ' đang là công thức, không ghi đè' };
    }

    writes.push({ col: col, value: value, field: name });
  }

  // --- ghi ---
  var changed = {};
  for (var w = 0; w < writes.length; w++) {
    changed[writes[w].field] = { from: current[writes[w].field], to: fields[writes[w].field] };
    if (!dryRun) sh.getRange(row, writes[w].col).setValue(writes[w].value);
  }

  var res = { row: row, ok: true, task: label_(current), changed: changed };
  if (u.taskId) res.taskId = u.taskId;
  // relocated = dòng đã dịch chỗ so với row người gọi tưởng; ID vẫn tìm đúng.
  if (relocated) res.relocated = { expectedRow: Number(u.row), actualRow: row };
  return res;
}

// ---------------------------------------------------------------------------
// Action: reschedule — dồn lại lịch PLAN
// ---------------------------------------------------------------------------

/**
 * Tính lại cột PLAN cho một người (hoặc tất cả) theo quy tắc tích luỹ giờ.
 *
 * Body:
 *   { token, action: "reschedule", gid?,
 *     assignee: "Duy",          // bỏ trống = mọi người
 *     from: "2026-07-28",       // ngày đầu tiên còn trống giờ
 *     dryRun: true }            // mặc định true — phải chủ động tắt mới ghi
 *
 * QUY TẮC
 *   - Mỗi ngày HOURS_PER_DAY giờ, bỏ qua T7/CN và HOLIDAYS
 *   - Giờ chảy liên tục: task dư giờ tràn sang ngày sau, task kế tiếp bắt đầu
 *     ngay từ giờ trống còn lại của ngày đó (không đợi sang ngày mới)
 *   - Mỗi người một hàng đợi riêng, thứ tự theo thứ tự dòng trên sheet
 *   - Số giờ còn phải làm = (Re-estimate hoặc Estimate) − Actual Effort
 *   - Task đã đóng (Done/Cancel/N/A) hoặc hết giờ → không đụng tới
 *   - Task đang làm dở giữ nguyên plan_start (nó đã bắt đầu thật rồi),
 *     chỉ đẩy plan_end
 *
 * `from` là ngày đầu tiên còn trống giờ — thường là ngày làm việc kế tiếp sau
 * buổi report. Ví dụ Duy log 8h cho ngày 27-07 thì `from` = 28-07, vì ngày 27
 * đã bị số giờ đó tiêu hết.
 */
function reschedule_(body) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'sheet đang bận, thử lại sau' };

  try {
    var sh = sheet_(body.gid);
    var dryRun = body.dryRun !== false;          // mặc định KHÔNG ghi
    var filter = body.assignee || '';
    var from = body.from ? parseDate_(body.from) : todayLocal_();
    if (!from) return { ok: false, error: 'from phải dạng yyyy-MM-dd' };

    var lastRow = sh.getLastRow();
    if (lastRow < DATA_START_ROW) return { ok: false, error: 'sheet không có dòng dữ liệu' };

    var values = sh
      .getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, COLUMNS.length)
      .getValues();

    var cursors = {};
    var changes = [];
    var skipped = [];

    for (var i = 0; i < values.length; i++) {
      var t = rowToTask_(values[i], DATA_START_ROW + i);
      if (!t.task || !t.assignee) continue;                       // dòng trống / tổng nhóm
      if (filter && !contains_(t.assignee, filter)) continue;

      if (CLOSED_STATUS.indexOf(t.status) !== -1) {
        skipped.push({ row: t.row, reason: 'status = ' + t.status });
        continue;
      }

      var total = Number(t.actual_reestimate_h) > 0
        ? Number(t.actual_reestimate_h)
        : Number(t.plan_estimate_h);
      var done = Number(t.actual_effort_h) || 0;
      var left = total - done;

      if (!(total > 0)) { skipped.push({ row: t.row, reason: 'không có số giờ' }); continue; }
      if (left <= 0)    { skipped.push({ row: t.row, reason: 'đã đủ giờ, chờ đổi status' }); continue; }

      if (!cursors[t.assignee]) {
        cursors[t.assignee] = { day: workingDayOnOrAfter_(from), used: 0 };
      }
      var span = consume_(cursors[t.assignee], left);

      // Task đang làm dở thì ngày bắt đầu là sự thật đã xảy ra, không dời.
      var inProgress = done > 0;
      var newStart = inProgress && t.plan_start ? parseDate_(t.plan_start) : span.start;

      // Không kéo lên sớm hơn kế hoạch gốc của PM.
      if (NEVER_EARLIER && !inProgress && t.plan_start) {
        var planned = parseDate_(t.plan_start);
        if (planned && planned > newStart) {
          cursors[t.assignee] = { day: workingDayOnOrAfter_(planned), used: 0 };
          span = consume_(cursors[t.assignee], left);
          newStart = span.start;
        }
      }

      var oldStart = t.plan_start, oldEnd = t.plan_end;
      var nextStart = fmt_(newStart), nextEnd = fmt_(span.end);
      if (oldStart === nextStart && oldEnd === nextEnd) continue;  // không đổi thì bỏ qua

      changes.push({
        row: t.row, assignee: t.assignee, task: label_(t), hours_left: left,
        plan_start: { from: oldStart, to: nextStart },
        plan_end:   { from: oldEnd,   to: nextEnd }
      });
    }

    if (!dryRun) {
      for (var c = 0; c < changes.length; c++) {
        var ch = changes[c];
        var colS = COLUMNS.indexOf('plan_start') + 1;
        var colE = COLUMNS.indexOf('plan_end') + 1;

        if (sh.getRange(ch.row, colS).getFormula() !== '' ||
            sh.getRange(ch.row, colE).getFormula() !== '') {
          ch.skipped = 'ô PLAN đang là công thức, không ghi đè';
          continue;
        }
        sh.getRange(ch.row, colS).setValue(parseDate_(ch.plan_start.to));
        sh.getRange(ch.row, colE).setValue(parseDate_(ch.plan_end.to));
      }
      SpreadsheetApp.flush();
    }

    return {
      ok: true, dryRun: dryRun, from: fmt_(workingDayOnOrAfter_(from)),
      changes: changes, skipped: skipped
    };
  } finally {
    lock.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// Action: fillplan — lập lịch PLAN từ đầu theo cột Estimate
// ---------------------------------------------------------------------------

/**
 * Lập lịch cột PLAN (I/J) cho cả sprint dựa trên Estimate — dùng khi PM lên
 * kế hoạch đầu sprint, khác với reschedule (điều chỉnh khi thực tế lệch).
 *
 * Body:
 *   { token, action: "fillplan", gid?,
 *     assignee: "Duy",             // bỏ trống = mọi người
 *     from: "2026-08-03",          // ngày bắt đầu; bỏ trống = hôm nay
 *     preferReestimate: false,     // true = ưu tiên Re-estimate nếu có
 *     dryRun: true }               // mặc định true
 *
 * Khác reschedule ở ba điểm: dùng nguyên Estimate (không trừ Actual Effort),
 * không giữ plan_start của task đang làm dở (lập lại từ đầu), không áp
 * NEVER_EARLIER (đây là kế hoạch mới nên được xếp bất kỳ ngày nào từ `from`).
 * Vẫn né T7/CN + lễ (chung isWorkingDay_).
 */
function fillplan_(body) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'sheet đang bận, thử lại sau' };

  try {
    var sh = sheet_(body.gid);
    var dryRun = body.dryRun !== false;                 // mặc định KHÔNG ghi
    var filter = body.assignee || '';
    var preferRe = body.preferReestimate === true;
    var from = body.from ? parseDate_(body.from) : todayLocal_();
    if (!from) return { ok: false, error: 'from phải dạng yyyy-MM-dd' };

    var lastRow = sh.getLastRow();
    if (lastRow < DATA_START_ROW) return { ok: false, error: 'sheet không có dòng dữ liệu' };

    var values = sh
      .getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, COLUMNS.length)
      .getValues();

    var cursors = {};
    var changes = [];
    var skipped = [];

    for (var i = 0; i < values.length; i++) {
      var t = rowToTask_(values[i], DATA_START_ROW + i);
      if (!t.task || !t.assignee) continue;             // dòng trống / tổng nhóm
      if (filter && !contains_(t.assignee, filter)) continue;

      var hours = Number(t.plan_estimate_h);
      if (preferRe && Number(t.actual_reestimate_h) > 0) hours = Number(t.actual_reestimate_h);
      if (!(hours > 0)) { skipped.push({ row: t.row, reason: 'không có số giờ' }); continue; }

      if (!cursors[t.assignee]) {
        cursors[t.assignee] = { day: workingDayOnOrAfter_(from), used: 0 };
      }
      var span = consume_(cursors[t.assignee], hours);

      var nextStart = fmt_(span.start), nextEnd = fmt_(span.end);
      if (t.plan_start === nextStart && t.plan_end === nextEnd) continue;

      changes.push({
        row: t.row, assignee: t.assignee, task: label_(t), hours: hours,
        plan_start: { from: t.plan_start, to: nextStart },
        plan_end:   { from: t.plan_end,   to: nextEnd }
      });
    }

    if (!dryRun) {
      var colS = COLUMNS.indexOf('plan_start') + 1;
      var colE = COLUMNS.indexOf('plan_end') + 1;
      for (var c = 0; c < changes.length; c++) {
        var ch = changes[c];
        if (sh.getRange(ch.row, colS).getFormula() !== '' ||
            sh.getRange(ch.row, colE).getFormula() !== '') {
          ch.skipped = 'ô PLAN đang là công thức, không ghi đè';
          continue;
        }
        sh.getRange(ch.row, colS).setValue(parseDate_(ch.plan_start.to));
        sh.getRange(ch.row, colE).setValue(parseDate_(ch.plan_end.to));
      }
      SpreadsheetApp.flush();
    }

    return {
      ok: true, dryRun: dryRun, from: fmt_(workingDayOnOrAfter_(from)),
      source: preferRe ? 'Re-estimate (thiếu → Estimate)' : 'Estimate',
      changes: changes, skipped: skipped
    };
  } finally {
    lock.releaseLock();
  }
}

/**
 * Trừ `hours` giờ vào con trỏ của một người, trả về ngày bắt đầu và kết thúc.
 *
 * Đây là chỗ thể hiện quy tắc "task sau tính từ giờ còn trống": con trỏ KHÔNG
 * nhảy sang ngày mới sau mỗi task — nó chỉ nhảy khi ngày hiện tại đã dùng đủ
 * 8h. Nên task 4h kết thúc ở giờ 5 thì task sau vào ngay giờ 6 cùng ngày.
 */
function consume_(cursor, hours) {
  if (cursor.used >= HOURS_PER_DAY) {
    cursor.day = nextWorkingDay_(cursor.day);
    cursor.used = 0;
  }

  var start = cursor.day;
  var left = hours;

  while (left > 0) {
    var take = Math.min(HOURS_PER_DAY - cursor.used, left);
    cursor.used += take;
    left -= take;
    if (left > 0) {
      cursor.day = nextWorkingDay_(cursor.day);
      cursor.used = 0;
    }
  }

  return { start: start, end: cursor.day };
}

// ---------------------------------------------------------------------------
// Ngày làm việc
// ---------------------------------------------------------------------------

function workingDayOnOrAfter_(d) {
  return isWorkingDay_(d) ? d : nextWorkingDay_(d);
}

function nextWorkingDay_(d) {
  var next = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
  while (!isWorkingDay_(next)) {
    next = new Date(next.getFullYear(), next.getMonth(), next.getDate() + 1);
  }
  return next;
}

function isWorkingDay_(d) {
  var dow = d.getDay();
  if (dow === 0 || dow === 6) return false;              // CN, T7
  return !holidaySet_()[fmt_(d)];
}

/**
 * Tập ngày nghỉ = cột "Date" trong tab Config + mảng HOLIDAYS khai tay.
 *
 * Cache trong một lần chạy (reschedule gọi isWorkingDay_ rất nhiều lần, không
 * đọc lại Config mỗi lần). PM sửa lễ trong tab Config là bot dùng ngay lần
 * chạy sau, không cần đụng code.
 */
var _holidayCache = null;

function holidaySet_() {
  if (_holidayCache) return _holidayCache;

  var set = {};
  for (var i = 0; i < HOLIDAYS.length; i++) set[HOLIDAYS[i]] = true;

  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG_TAB_NAME);
  if (sh && sh.getLastRow() > 0) {
    var data = sh.getDataRange().getValues();

    // Tìm cột có header "Date" (nằm dưới nhóm "2. Holiday" trong Config).
    var dateCol = -1, headerRow = -1;
    for (var r = 0; r < Math.min(data.length, 6) && dateCol === -1; r++) {
      for (var c = 0; c < data[r].length; c++) {
        if (String(data[r][c]).trim() === 'Date') { dateCol = c; headerRow = r; break; }
      }
    }

    if (dateCol !== -1) {
      for (var k = headerRow + 1; k < data.length; k++) {
        var v = data[k][dateCol];
        if (v instanceof Date && v.getFullYear() >= 2000 && v.getFullYear() <= 2100) {
          set[fmt_(v)] = true;
        }
      }
    }
  }

  _holidayCache = set;
  return set;
}

function todayLocal_() {
  var n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

/** Chỉ nhận yyyy-MM-dd — sheet dùng lẫn dd-MM-yyyy và d/M/yyyy, đoán sai sẽ
 *  ghi nhầm ngày mà không ai biết. */
function parseDate_(s) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s).trim());
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function fmt_(d) {
  return Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd');
}

// ---------------------------------------------------------------------------
// Chọn tab
// ---------------------------------------------------------------------------

function sheet_(gid) {
  var want = Number(gid || SHEET_GID);
  var sheets = SpreadsheetApp.getActiveSpreadsheet().getSheets();

  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === want) return sheets[i];
  }

  // Kèm luôn danh sách tab vào lỗi — một lần gọi là đủ biết phải điền gid nào.
  throw new Error(
    'Không tìm thấy tab có gid = ' + want + '. Các tab hiện có: ' +
    JSON.stringify(listTabs_())
  );
}

function listTabs_() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function (sh) {
    return { name: sh.getName(), gid: sh.getSheetId(), lastRow: sh.getLastRow() };
  });
}

/** Tên sprint nằm ở B1 của các tab sprint. */
function sprintName_(gid) {
  return normalize_(sheet_(gid).getRange('B1').getValue());
}

function countRows_(gid) {
  return Math.max(0, sheet_(gid).getLastRow() - DATA_START_ROW + 1);
}

// ---------------------------------------------------------------------------
// Đọc dữ liệu
// ---------------------------------------------------------------------------

function getRow_(gid, row) {
  var sh = sheet_(gid);
  if (!row || row < DATA_START_ROW || row > sh.getLastRow()) {
    throw new Error('row không hợp lệ: ' + row);
  }
  var task = rowToTask_(sh.getRange(row, 1, 1, COLUMNS.length).getValues()[0], row);
  task.taskId = getRowTaskId_(sh, row);
  return task;
}

// ---------------------------------------------------------------------------
// Developer Metadata — ID bền cho từng dòng (xem Backfill.gs)
// ---------------------------------------------------------------------------

var TASKID_KEY = 'taskId';

/** Đọc taskId gắn trên một dòng. '' nếu chưa có. */
function getRowTaskId_(sh, row) {
  var md = sh.getRange(row + ':' + row).getDeveloperMetadata();
  for (var i = 0; i < md.length; i++) {
    if (md[i].getKey() === TASKID_KEY) return md[i].getValue();
  }
  return '';
}

/** Gắn taskId vào một dòng (ghi đè nếu đã có). */
function setRowTaskId_(sh, row, id) {
  var range = sh.getRange(row + ':' + row);
  var md = range.getDeveloperMetadata();
  for (var i = 0; i < md.length; i++) {
    if (md[i].getKey() === TASKID_KEY) { md[i].setValue(id); return; }
  }
  range.addDeveloperMetadata(TASKID_KEY, id);
}

/**
 * Tìm số dòng mang taskId này. null nếu không thấy.
 *
 * Đây là trái tim của định danh bền: dù dòng đã dịch chỗ do chèn/xoá, hay tên
 * task đã bị sửa, metadata vẫn đi theo dòng nên vẫn tìm đúng.
 */
function findRowByTaskId_(sh, taskId) {
  if (!taskId) return null;
  var found = sh.createDeveloperMetadataFinder()
    .withKey(TASKID_KEY).withValue(taskId).find();
  if (!found.length) return null;

  var loc = found[0].getLocation().getRow();   // Range của dòng
  return loc ? loc.getRow() : null;
}

/** Filter tuỳ chọn: ?assignee=Duy&status=Done&type=BE */
function listTasks_(params) {
  var sh = sheet_(params.gid);
  var lastRow = sh.getLastRow();
  if (lastRow < DATA_START_ROW) return [];

  var values = sh
    .getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, COLUMNS.length)
    .getValues();

  var out = [];
  for (var i = 0; i < values.length; i++) {
    var task = rowToTask_(values[i], DATA_START_ROW + i);

    // Bỏ dòng trống (sheet thường thừa vài dòng rỗng ở cuối) và dòng subtotal
    // của từng nhóm (có category nhưng không có task/assignee).
    if (!task.task && !task.assignee) continue;

    if (!contains_(task.assignee, params.assignee)) continue;
    if (!contains_(task.status, params.status)) continue;
    if (!contains_(task.type, params.type)) continue;

    // Lọc "task của một ngày" (giao việc buổi sáng): chỉ task có
    // plan_start <= day <= plan_end. So sánh chuỗi yyyy-MM-dd = so ngày.
    // Task chưa có plan (rỗng) không lọt vào ngày nào.
    if (params.day && !activeOn_(task, params.day)) continue;

    // taskId để agent ghi nhớ từ buổi sáng, dùng lại khi ghi buổi tối — bền
    // hơn row nếu có người chèn/xoá dòng giữa chừng.
    task.taskId = getRowTaskId_(sh, task.row);
    out.push(task);
  }
  return out;
}

function rowToTask_(row, rowNum) {
  var task = { row: rowNum };
  var errors = [];

  for (var c = 0; c < COLUMNS.length; c++) {
    var field = COLUMNS[c];
    if (field.charAt(0) === '_') continue;      // ô merge, bỏ qua

    if (isErrorCell_(row[c])) {
      // Sheet có sẵn vài ô #REF! do công thức gãy. Trả rỗng nhưng ghi lại để
      // agent biết ô đó hỏng, thay vì im lặng coi như chưa có dữ liệu.
      task[field] = '';
      errors.push(field + '=' + row[c]);
    } else {
      task[field] = normalize_(row[c]);
    }
  }

  if (errors.length) task.cell_errors = errors;
  return task;
}

/** Nhãn hiển thị cho người đọc: ghép category + task + sub-task.
 *  Cần cả ba vì sheet có nhiều dòng trùng `task` — ví dụ LAN có 3 dòng
 *  "Write Testcase", chỉ khác nhau ở category (tên màn hình). */
function label_(t) {
  var parts = [t.category, t.task, t.subtask_vi].filter(function (s) { return s; });
  return parts.join(' — ');
}

function contains_(value, filter) {
  if (!filter) return true;
  return String(value).toLowerCase().indexOf(String(filter).toLowerCase()) !== -1;
}

/** Task có chạy trong ngày `day` (yyyy-MM-dd) không: plan_start <= day <= plan_end. */
function activeOn_(task, day) {
  day = String(day).trim();
  return !!task.plan_start && !!task.plan_end &&
         task.plan_start <= day && day <= task.plan_end;
}

/** Ô lỗi công thức: #REF!, #N/A, #VALUE!, #DIV/0!... */
function isErrorCell_(value) {
  return typeof value === 'string' && /^#[A-Z\/0-9]+[!?]?$/.test(value.trim());
}

/**
 * Chuẩn hoá giá trị ô về dạng JSON gửi đi được.
 *
 * Ngày trống trong sheet hiện ra là 30-12-1899 — mốc 0 của Sheets, tức ô rỗng
 * chứ không phải ngày thật. Sheet cũng có ô rác 29-12-4420. Cả hai đều trả ""
 * để agent không tưởng task bắt đầu từ năm 1899 hay 4420.
 */
function normalize_(value) {
  if (value === null || value === undefined || value === '') return '';

  if (value instanceof Date) {
    var y = value.getFullYear();
    if (y < 2000 || y > 2100) return '';
    return Utilities.formatDate(value, TIMEZONE, 'yyyy-MM-dd');
  }

  if (typeof value === 'string') return value.trim();
  return value;
}

/** So sánh nới tay: bỏ khoảng trắng thừa và không phân biệt hoa thường.
 *  Sheet có ô "Review test case " với dấu cách cuối — so sánh thô là trượt. */
function norm_(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/\s+/g, ' ').trim().toLowerCase();
}

function coerce_(value, kind) {
  if (value === '' || value === null || value === undefined) return '';

  if (kind === 'number') {
    var num = Number(value);
    return isNaN(num) ? undefined : num;
  }
  if (kind === 'date') {
    var d = parseDate_(value);
    return d === null ? undefined : d;
  }
  return String(value);
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function errMsg_(err) {
  return String(err && err.message ? err.message : err);
}

/**
 * Chạy tay 1 lần trong editor Apps Script để sinh token.
 * Xem kết quả ở Nhật ký (Logs), rồi copy vào .env.
 */
function setupToken() {
  var token = Utilities.getUuid().replace(/-/g, '');
  PropertiesService.getScriptProperties().setProperty('API_TOKEN', token);
  Logger.log('API_TOKEN = ' + token);
  return token;
}
