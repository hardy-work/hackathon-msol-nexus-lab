/**
 * Test.gs — kiểm tra Code.gs hoạt động, KHÔNG cần deploy Web App.
 *
 * Dán file này vào cùng project Apps Script với Code.gs, chọn hàm
 * `runAllTests` rồi bấm Run. Xem kết quả ở Nhật ký (Logs).
 *
 * AN TOÀN: mọi phép ghi đều chạy dryRun — sheet không bị sửa gì.
 * Chỉ có test số 6 đụng vào sheet thật, và nó bị tắt sẵn.
 */

function runAllTests() {
  var pass = 0, fail = 0;

  function check(name, cond, detail) {
    if (cond) { pass++; log_('  ✓ ' + name); }
    else      { fail++; log_('  ✗ ' + name + (detail ? '  →  ' + detail : '')); }
  }

  log_('══════════════════════════════════════════════');
  log_(' TEST sheet-task backend');
  log_('══════════════════════════════════════════════');

  // ---------------------------------------------------------------------
  log_('');
  log_('[1] Chọn đúng tab');
  var sh;
  try {
    sh = sheet_();
    log_('  tab: "' + sh.getName() + '" · gid ' + int_(sh.getSheetId()) +
         ' · sprint B1 = "' + sprintName_() + '"');
    check('tìm được tab theo SHEET_GID', true);
    check('không phải tab Config', sh.getName().toLowerCase().indexOf('config') === -1,
          'đang trỏ vào tab Config — sai gid');
  } catch (e) {
    check('tìm được tab theo SHEET_GID', false, e.message);
    log_('');
    log_('DỪNG — không có tab thì không test tiếp được.');
    return;
  }

  // ---------------------------------------------------------------------
  log_('');
  log_('[2] Đọc dữ liệu');
  var tasks = listTasks_({});
  check('đọc được ít nhất 1 task', tasks.length > 0, 'không có dòng nào');
  log_('  đọc được ' + int_(tasks.length) + ' task');

  if (!tasks.length) { log_(''); log_('DỪNG — sheet rỗng.'); return; }

  var t0 = tasks[0];
  log_('  dòng đầu: ' + label_(t0));
  log_('    assignee="' + t0.assignee + '" est=' + t0.plan_estimate_h +
       'h plan=' + t0.plan_start + '→' + t0.plan_end + ' status="' + t0.status + '"');

  check('dòng đầu đúng vị trí DATA_START_ROW', t0.row === DATA_START_ROW,
        'row=' + t0.row + ' nhưng DATA_START_ROW=' + DATA_START_ROW);
  check('có cột status (map A→S đúng)', 'status' in t0);
  check('có cột note (cột cuối S)', 'note' in t0);
  check('ngày dạng yyyy-MM-dd hoặc rỗng',
        t0.plan_start === '' || /^\d{4}-\d{2}-\d{2}$/.test(t0.plan_start),
        'plan_start = "' + t0.plan_start + '"');

  // Đếm số người — dùng cho test dồn lịch bên dưới.
  var people = {};
  for (var i = 0; i < tasks.length; i++) people[tasks[i].assignee] = true;
  log_('  ' + int_(Object.keys(people).length) + ' người: ' + Object.keys(people).join(', '));

  // ---------------------------------------------------------------------
  log_('');
  log_('[3] Chặn ghi sai — đây là phần quan trọng nhất');

  // 3a. expect khớp → cho ghi (dryRun nên không sửa gì)
  var okRes = update_({
    dryRun: true,
    updates: [{
      row: t0.row,
      expect: { assignee: t0.assignee, task: t0.task },
      fields: { note: 'TEST — dryRun, không ghi thật' }
    }]
  });
  check('expect khớp → chấp nhận', okRes.results[0].ok,
        okRes.results[0].reason);

  // 3b. expect sai → phải từ chối. Đây là lá chắn chống ghi nhầm dòng khi
  //     có người chèn/xoá dòng giữa lúc đọc và lúc ghi.
  var badRes = update_({
    dryRun: true,
    updates: [{
      row: t0.row,
      expect: { assignee: 'người không tồn tại' },
      fields: { note: 'không được ghi' }
    }]
  });
  check('expect sai → từ chối', !badRes.results[0].ok, 'đã cho ghi — NGUY HIỂM');
  log_('    lý do: ' + badRes.results[0].reason);

  // 3c. thiếu expect → phải từ chối
  var noExpect = update_({
    dryRun: true,
    updates: [{ row: t0.row, fields: { note: 'x' } }]
  });
  check('thiếu expect → từ chối', !noExpect.results[0].ok, 'đã cho ghi — NGUY HIỂM');

  // 3d. ghi vào cột công thức → phải từ chối
  var formulaCols = ['no', 'progress', 'remaining_h'];
  for (var f = 0; f < formulaCols.length; f++) {
    var fields = {};
    fields[formulaCols[f]] = 999;
    var r = update_({
      dryRun: true,
      updates: [{ row: t0.row, expect: { assignee: t0.assignee }, fields: fields }]
    });
    check('chặn ghi vào cột công thức "' + formulaCols[f] + '"', !r.results[0].ok,
          'đã cho ghi — sẽ phá công thức cả cột');
  }

  // 3e. ghi vào mốc định danh → phải từ chối
  var idRes = update_({
    dryRun: true,
    updates: [{ row: t0.row, expect: { assignee: t0.assignee }, fields: { task: 'đổi tên' } }]
  });
  check('chặn sửa cột task (mốc định danh)', !idRes.results[0].ok);

  // 3f. status ngoài danh sách Config → phải từ chối
  var stRes = update_({
    dryRun: true,
    updates: [{ row: t0.row, expect: { assignee: t0.assignee }, fields: { status: 'Xong hết rồi' } }]
  });
  check('chặn status không có trong tab Config', !stRes.results[0].ok);

  // 3g. ngày sai định dạng → phải từ chối. Sheet dùng lẫn dd-MM-yyyy và
  //     d/M/yyyy nên đoán sai sẽ ghi nhầm ngày mà không ai biết.
  var dtRes = update_({
    dryRun: true,
    updates: [{ row: t0.row, expect: { assignee: t0.assignee }, fields: { actual_start: '27-07-2026' } }]
  });
  check('chặn ngày sai định dạng (phải yyyy-MM-dd)', !dtRes.results[0].ok);

  // 3h. row ngoài vùng dữ liệu → phải từ chối
  var rowRes = update_({
    dryRun: true,
    updates: [{ row: 1, expect: { assignee: 'x' }, fields: { note: 'y' } }]
  });
  check('chặn row nằm ngoài vùng dữ liệu', !rowRes.results[0].ok);

  // ---------------------------------------------------------------------
  log_('');
  log_('[4] Dồn lịch (dryRun)');
  var who = Object.keys(people)[0];
  var re = reschedule_({ assignee: who, from: '2026-07-28' });

  check('chạy được', re.ok === true, re.error);
  check('KHÔNG ghi gì (dryRun mặc định true)', re.dryRun === true,
        'dryRun không bật mặc định — NGUY HIỂM');

  if (re.ok) {
    log_('  người: ' + who + ' · from ' + re.from);
    log_('  ' + int_(re.changes.length) + ' dòng đổi, ' + int_(re.skipped.length) + ' dòng bỏ qua');
    for (var c = 0; c < Math.min(re.changes.length, 8); c++) {
      var ch = re.changes[c];
      log_('    dòng ' + int_(ch.row) + ' | còn ' + ch.hours_left + 'h | ' +
           ch.plan_start.from + '→' + ch.plan_end.from + '  ⇒  ' +
           ch.plan_start.to + '→' + ch.plan_end.to);
    }
    if (re.changes.length > 8) log_('    ... còn ' + int_(re.changes.length - 8) + ' dòng nữa');
    for (var s = 0; s < Math.min(re.skipped.length, 5); s++) {
      log_('    bỏ qua dòng ' + int_(re.skipped[s].row) + ': ' + re.skipped[s].reason);
    }
  }

  // ---------------------------------------------------------------------
  log_('');
  log_('[5] Đường HTTP đầy đủ (doGet + kiểm tra token)');
  var token = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  if (!token) {
    log_('  ⚠ BỎ QUA — chưa chạy setupToken(). Chạy hàm đó trước khi deploy.');
  } else {
    var good = JSON.parse(doGet({ parameter: { action: 'ping', token: token } }).getContent());
    check('doGet ping với token đúng', good.ok === true, good.error);
    log_('    sheet="' + good.sheet + '" sprint="' + good.sprint + '" rows=' + int_(good.rows));

    var bad = JSON.parse(doGet({ parameter: { action: 'ping', token: 'sai-token' } }).getContent());
    check('doGet với token sai → unauthorized', bad.ok === false && bad.error === 'unauthorized',
          'token sai vẫn lọt — NGUY HIỂM');

    var none = JSON.parse(doGet({ parameter: { action: 'ping' } }).getContent());
    check('doGet không token → unauthorized', none.ok === false);

    var post = JSON.parse(doPost({ postData: { contents: JSON.stringify({
      token: token, action: 'update', dryRun: true,
      updates: [{ row: t0.row, expect: { assignee: t0.assignee }, fields: { note: 'test' } }]
    }) } }).getContent());
    check('doPost update qua đường HTTP', post.ok === true, post.error);
  }

  // ---------------------------------------------------------------------
  log_('');
  log_('══════════════════════════════════════════════');
  log_(' ' + int_(pass) + ' pass · ' + int_(fail) + ' fail');
  log_('══════════════════════════════════════════════');
  if (fail === 0) log_(' Backend chạy đúng. Sheet KHÔNG bị sửa gì.');
  else            log_(' Có test fail — xem dấu ✗ ở trên.');
}

/**
 * [6] Ghi THẬT một ô — tắt sẵn.
 *
 * Bỏ dòng `return` đầu hàm rồi Run nếu muốn kiểm chứng script ghi được thật.
 * Nó ghi một dòng chữ vào cột Note của dòng đầu tiên. Xoá tay sau khi xem.
 */
function testWriteForReal() {
  return log_('Test này đang tắt. Xoá dòng `return` ở đầu hàm nếu thực sự muốn ghi.');

  /* eslint-disable no-unreachable */
  var t = listTasks_({})[0];
  var res = update_({
    dryRun: false,
    updates: [{
      row: t.row,
      expect: { assignee: t.assignee, task: t.task },
      fields: { note: 'sheet-task test ' + new Date().toISOString() }
    }]
  });
  log_(JSON.stringify(res, null, 2));
  log_('→ Kiểm tra cột Note dòng ' + t.row + ' trên sheet, rồi xoá đi.');
}

// ---------------------------------------------------------------------------

function log_(s) { Logger.log(s); }

/** Apps Script coi mọi số là double nên Logger in ra "9.0", "2.05E9". */
function int_(v) { return Number(v).toFixed(0); }
