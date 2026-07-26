/**
 * Backfill.gs — gắn ID bền cho từng dòng bằng Developer Metadata.
 *
 * Chạy MỘT LẦN trong editor Apps Script (chọn `backfillTaskIds` → Run).
 * Phạm vi: CHỈ tab sprint schedule (SHEET_GID trong Code.gs). Không đụng
 * Backlog_OLD, UAT, CR.
 *
 * ┌─ VÌ SAO CẦN ─────────────────────────────────────────────────────────┐
 * │ Khoá 4 cột (assignee+category+task+subtask) hỏng khi ai sửa tên task,  │
 * │ và không phân biệt được hai dòng giống hệt. Developer Metadata là một │
 * │ ID vô hình gắn vào CHÍNH DÒNG — đi theo dòng khi chèn/xoá/kéo thả,    │
 * │ không phải văn bản người gõ nên sửa tên task không ảnh hưởng.         │
 * │                                                                       │
 * │ Người dùng KHÔNG thấy ID này: không phải cột, không hiện trên sheet,  │
 * │ không in ra, không xuất CSV. Hoàn toàn ẩn.                            │
 * └───────────────────────────────────────────────────────────────────────┘
 *
 * An toàn chạy lại nhiều lần: dòng đã có ID thì bỏ qua.
 *
 * TASKID_KEY, getRowTaskId_, setRowTaskId_ định nghĩa trong Code.gs (mọi file
 * .gs dùng chung global scope).
 */

function backfillTaskIds() {
    var sh = sheet_(); // dùng SHEET_GID trong Code.gs
    var lastRow = sh.getLastRow();
    if (lastRow < DATA_START_ROW) {
        Logger.log('Tab "%s" không có dòng dữ liệu.', sh.getName());
        return;
    }

    var values = sh
        .getRange(
            DATA_START_ROW,
            1,
            lastRow - DATA_START_ROW + 1,
            COLUMNS.length,
        )
        .getValues();

    var added = 0,
        skipped = 0,
        blank = 0;

    for (var i = 0; i < values.length; i++) {
        var rowNum = DATA_START_ROW + i;
        var t = rowToTask_(values[i], rowNum);

        // Bỏ dòng trống và dòng subtotal (có category nhưng không có task/assignee).
        if (!t.task && !t.assignee) {
            blank++;
            continue;
        }

        if (getRowTaskId_(sh, rowNum)) {
            skipped++;
            continue;
        }

        setRowTaskId_(sh, rowNum, Utilities.getUuid());
        added++;
    }

    SpreadsheetApp.flush();

    Logger.log('=== Backfill xong: tab "%s" ===', sh.getName());
    Logger.log("  Gắn ID mới : %s dòng", added);
    Logger.log("  Đã có ID   : %s dòng (bỏ qua)", skipped);
    Logger.log("  Dòng trống : %s (không gắn)", blank);
}

/** Xoá toàn bộ taskId trong tab (nếu cần làm lại từ đầu). Cẩn thận. */
function clearAllTaskIds() {
    var sh = sheet_();
    var md = sh.createDeveloperMetadataFinder().withKey(TASKID_KEY).find();
    for (var i = 0; i < md.length; i++) md[i].remove();
    SpreadsheetApp.flush();
    Logger.log('Đã xoá %s taskId khỏi tab "%s".', md.length, sh.getName());
}
