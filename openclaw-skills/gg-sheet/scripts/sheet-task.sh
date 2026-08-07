#!/usr/bin/env bash
# Log 1 dòng report của dev lên Google Sheet lịch trình, và ghi cảnh báo quá giờ
# sang tab "Risk management".
#
# Vì sao là script chứ không để bot tự curl: vị trí cột trong tab Sprint là
# header 2 tầng (PLAN/Actual), có tới 2 cột tên "Start Date" và 2 cột tên chứa
# "Estimate" — bot tự dò bằng mắt là ghi lệch khối PLAN, đè mất giờ plan của PM.
# Script tự đọc header, tự khớp cột, và TỰ CHẶN khi quá giờ (exit 9) nên cái
# chốt "vượt est thì không được log thẳng" là luật của code, không phải luật của
# prompt.
#
# Dùng cho Action 4 (log report task từ dev). Action 1/2/3 là PM thao tác bằng
# lời, không đi qua script này.
#
# Vào (env): GOOGLE_SHEETS_LINK (hoặc LOGTIME_SHEET_LINK), GOOGLE_SHEETS_API_KEY
#            (đọc), GOOGLE_SERVICE_ACCOUNT_KEY_FILE (ghi) — script tự gọi
#            scripts/get-token.sh cùng thư mục, không tự ký JWT.
#
# Lệnh:
#   sheet-task.sh find <TASKID>
#       -> JSON {task_id, tab, row, estimate, assignee, task, sub_task, status}
#
#   sheet-task.sh log <TASKID> --re-est X --start DD-MM-YYYY --end DD-MM-YYYY|"" \
#                              --actual X --status S [--note N] [--force] \
#                              [--slack-id U...] [--date YYYY-MM-DD]
#       -> ghi 6 ô khối Actual + Status + Note của ĐÚNG dòng task đó.
#          Actual Effort > Estimate HOẶC Re-estimate > Estimate mà không có
#          --force -> exit 9, KHÔNG ghi gì.
#          Status = Done mà Actual Effort != Re-estimate (Remaining sẽ khác 0)
#          mà không có --force -> exit 12, KHÔNG ghi gì.
#          Có --slack-id thì ghi thêm 1 dòng vào sổ cái effort-today.json (giờ
#          vừa bỏ thêm vào = actual mới - actual đang có trên sheet) để lượt
#          follow-up 16:30 so được với công đăng ký. Không có thì bỏ qua im lặng.
#          Có --slack-id (và parse được ngày từ --start) thì TRƯỚC KHI ghi còn
#          cộng dồn (qua sổ cái, không phải quét lại Actual Effort trên sheet —
#          số đó cộng dồn cả task, không phải giờ-hôm-nay) tổng giờ member đã
#          log hôm đó qua MỌI task, cộng thêm giờ task này -> so với giờ
#          allocate trong tab "Resource plan". LOG NHIỀU HƠN allocate mà không
#          có --force -> exit 13, KHÔNG ghi gì (bất thường bất kể giờ nào trong
#          ngày). LOG ÍT HƠN allocate KHÔNG bị chặn (bình thường giữa ngày) —
#          ghi bình thường, JSON kết quả có thêm field allocation_note.
#
#   sheet-task.sh risk --task <TASKID> --assignee <A> --diff <h> --reason <text> \
#                      [--next <hành động>] [--reporter <slack name>]
#       -> thêm 1 dòng vào tab "Risk management", tự sinh ID R-xx kế tiếp.
#
# Exit code:
#   0  ok
#   2  thiếu env / tham số sai
#   3  gọi Sheets API lỗi (đọc)
#   4  không tìm thấy cột bắt buộc trong tab (header đổi cấu trúc)
#   7  không có task id đó trong sheet
#   8  task id xuất hiện ở nhiều tab -> phải hỏi lại, không tự chọn
#   9  QUÁ GIỜ: Actual Effort > Estimate hoặc Re-estimate > Estimate, chưa ghi
#      gì cả (in JSON chi tiết ra stdout)
#  10  lấy access token thất bại (ghi)
#  11  ghi lên sheet lỗi / verify lại thấy không khớp
#  12  Status = Done nhưng Actual Effort != Re-estimate, chưa ghi gì cả (in
#      JSON chi tiết ra stdout)
#  13  Tổng giờ member đã log hôm đó (mọi task, qua sổ cái) NHIỀU HƠN giờ
#      allocate trong Resource plan, chưa ghi gì cả (in JSON chi tiết ra
#      stdout). Log ÍT HƠN allocate không dùng exit này — xem allocation_note.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

CMD="${1:-}"
case "$CMD" in
  find | log | risk) shift ;;
  *)
    echo "lệnh không hợp lệ: '${CMD}' (chỉ nhận find | log | risk)" >&2
    exit 2
    ;;
esac

LINK="${GOOGLE_SHEETS_LINK:-${LOGTIME_SHEET_LINK:-}}"
[ -n "$LINK" ] || { echo "thiếu GOOGLE_SHEETS_LINK (hoặc LOGTIME_SHEET_LINK) trong env" >&2; exit 2; }
[ -n "${GOOGLE_SHEETS_API_KEY:-}" ] || { echo "thiếu GOOGLE_SHEETS_API_KEY trong env" >&2; exit 2; }

FILE_ID=$(printf '%s' "$LINK" | sed -nE 's#.*/spreadsheets/d/([a-zA-Z0-9_-]+).*#\1#p')
if [ -z "$FILE_ID" ]; then
  case "$LINK" in
    */*) echo "không rút được fileId từ link: $LINK" >&2; exit 2 ;;
    *) FILE_ID="$LINK" ;;
  esac
fi

# Token chỉ cần cho lệnh ghi. Lấy sớm và tách hẳn stderr — stack trace của
# get-token.sh dài xấp xỉ token thật, gộp 2 luồng vào là "thành công giả".
ACCESS_TOKEN=""
if [ "$CMD" != "find" ]; then
  ACCESS_TOKEN=$(bash "$SKILL_DIR/scripts/get-token.sh" 2>/dev/null) || ACCESS_TOKEN=""
  case "$ACCESS_TOKEN" in
    ya29.*) ;;
    *)
      echo "không lấy được access token (Service Account). Chạy tay để xem lỗi:" >&2
      echo "  bash $SKILL_DIR/scripts/get-token.sh" >&2
      exit 10
      ;;
  esac
fi

# Sổ cái "hôm nay ai log bao nhiêu giờ", để lượt follow-up 16:30 so với công
# đăng ký trong Resource plan. Nằm bên skill reminder-followup vì đó là nơi đọc
# nó; hai skill là thư mục anh em trong workspace nên tính bằng ../ là ra, khỏi
# cần biến env hay đường dẫn tuyệt đối nào.
EFFORT_LEDGER_FILE="${EFFORT_LEDGER_FILE:-$SKILL_DIR/../reminder-followup/state/effort-today.json}"

export FILE_ID ACCESS_TOKEN CMD EFFORT_LEDGER_FILE
exec python3 - "$@" <<'PY'
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

API = "https://sheets.googleapis.com/v4/spreadsheets"
FILE_ID = os.environ["FILE_ID"]
KEY = os.environ["GOOGLE_SHEETS_API_KEY"]
TOKEN = os.environ.get("ACCESS_TOKEN", "")
CMD = os.environ["CMD"]
ARGV = sys.argv[1:]


def die(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        die(3, "Sheets API lỗi %s: %s" % (e.code, e.read().decode(errors="replace")[:400]))
    except OSError as e:
        die(3, "không gọi được Sheets API: %s" % e)


def post(url, payload, method="POST"):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        code = 11
        if e.code in (401, 403):
            body += "\n(403 ở bước ghi = Service Account chưa được share quyền Editor vào sheet)"
        die(code, "ghi lên sheet lỗi %s: %s" % (e.code, body))
    except OSError as e:
        die(11, "không gọi được Sheets API khi ghi: %s" % e)


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip().lower()


def today():
    tz = os.environ.get("REMINDER_TIMEZONE", "Asia/Ho_Chi_Minh")
    now = datetime.now(ZoneInfo(tz)) if ZoneInfo else datetime.now()
    return now


def to_number(raw):
    """'480,0' / '7.5' / '8h' -> float. None nếu không phải số."""
    if raw is None:
        return None
    s = str(raw).strip().rstrip("hH").strip()
    s = s.replace("%", "").replace(" ", "")
    if not s:
        return None
    # vi_VN: dấu . là phân cách nghìn, dấu , là thập phân
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_cell_number(raw):
    """Ghi số vào sheet locale vi_VN: 7.5 -> '7,5'. Không phải số thì giữ nguyên."""
    n = to_number(raw)
    if n is None:
        return str(raw)
    txt = ("%g" % n)
    return txt.replace(".", ",")


EMPTY_END = {"", "-", "--", "x", "?", "n/a", "na", "chưa", "chua", "chưa xong", "tbd"}


# ---------------------------------------------------------------- đọc cấu trúc
def list_tabs():
    d = get("%s/%s?fields=sheets.properties(title,sheetId)&key=%s" % (API, FILE_ID, KEY))
    return [(s["properties"]["title"], s["properties"]["sheetId"]) for s in d.get("sheets", [])]


def batch_get(ranges):
    q = "&".join("ranges=" + urllib.parse.quote(r, safe="") for r in ranges)
    d = get("%s/%s/values:batchGet?%s&key=%s" % (API, FILE_ID, q, KEY))
    return d.get("valueRanges", [])


def headers_of(rows):
    """Header 2 tầng -> {chỉ số cột: 'nhóm/tên'}. Nhóm ở dòng 1 là ô merge nên
    chỉ ô đầu có chữ -> phải forward-fill sang phải."""
    r1 = rows[0] if len(rows) > 0 else []
    r2 = rows[1] if len(rows) > 1 else []
    width = max(len(r1), len(r2))
    out = {}
    group = ""
    for i in range(width):
        top = norm(r1[i]) if i < len(r1) else ""
        sub = norm(r2[i]) if i < len(r2) else ""
        if top:
            group = top
        if sub:
            out[i] = (group, sub)
        else:
            out[i] = (group if top else group, "")
            if top:
                out[i] = (top, "")
    return out


def resolve_columns(hdr):
    """Khớp cột theo ngữ nghĩa, KHÔNG theo vị trí cứng."""
    col = {}
    for i, (group, sub) in hdr.items():
        full = sub or group
        if full == "taskid" or full == "task id":
            col.setdefault("task_id", i)
        elif full == "assignee":
            col.setdefault("assignee", i)
        elif full == "task":
            col.setdefault("task", i)
        elif full in ("sub-task", "sub task", "subtask", "sub-task (vn)"):
            col.setdefault("sub_task", i)
        elif full == "status" and not group.startswith("plan") and not group.startswith("actual"):
            col.setdefault("status", i)
        elif full in ("note", "notes") and not group.startswith("actual"):
            col.setdefault("note", i)
        if group.startswith("plan") and "estimate" in sub and "re-estimate" not in sub:
            col.setdefault("estimate", i)
        elif group.startswith("actual"):
            if "estimate" in sub:
                col.setdefault("re_est", i)
            elif "start" in sub:
                col.setdefault("start", i)
            elif "end" in sub:
                col.setdefault("end", i)
            elif "effort" in sub:
                col.setdefault("actual", i)
    return col


REQUIRED = ["task_id", "estimate", "re_est", "start", "end", "actual", "status"]

# Tab "Risk management" header 1 tầng. Khớp theo TÊN, không theo vị trí: PM chèn
# thêm cột vào giữa (đã xảy ra: cột 'Task' xen giữa 'Related Assignee' và
# 'Next Action') là mọi ô sau đó lệch sang phải, không exit code nào nổ ra.
RISK_ALIASES = {
    "id": ("id",),
    "date": ("date detected", "date"),
    "desc": ("description", "mô tả"),
    "prio": ("priority",),
    "assignee": ("related assignee", "assignee"),
    "task": ("task", "related task"),
    "next": ("next action", "action"),
    "status": ("status",),
    "notes": ("notes", "note"),
}


def resolve_risk_columns(hdr):
    """['ID','Date Detected',...] (đã norm) -> {tên cột: chỉ số}."""
    col = {}
    for key, names in RISK_ALIASES.items():
        for n in names:
            if n in hdr:
                col[key] = hdr.index(n)
                break
    return col


def find_task(task_id):
    want = norm(task_id)
    tabs = list_tabs()
    names = [t for t, _ in tabs]
    # 1 lệnh lấy header 2 dòng của mọi tab
    heads = batch_get(["%s!A1:BZ2" % t for t in names])
    cand = []
    for name, vr in zip(names, heads):
        hdr = headers_of(vr.get("values", []))
        col = resolve_columns(hdr)
        if "task_id" in col:
            cand.append((name, hdr, col))
    if not cand:
        die(4, "không tab nào có cột 'TaskID' — sheet đổi cấu trúc rồi?")

    # 1 lệnh lấy nguyên cột TaskID của các tab ứng viên
    id_cols = batch_get(
        ["%s!%s1:%s2000" % (n, col_letter(c["task_id"]), col_letter(c["task_id"])) for n, _, c in cand]
    )
    hits = []
    for (name, hdr, col), vr in zip(cand, id_cols):
        for idx, row in enumerate(vr.get("values", []), start=1):
            if row and norm(row[0]) == want:
                hits.append((name, hdr, col, idx))

    if not hits:
        die(7, json.dumps({"error": "not_found", "task_id": task_id}, ensure_ascii=False))
    if len(hits) > 1:
        die(
            8,
            json.dumps(
                {"error": "ambiguous", "task_id": task_id, "tabs": [h[0] for h in hits]},
                ensure_ascii=False,
            ),
        )

    name, hdr, col, row = hits[0]
    missing = [k for k in REQUIRED if k not in col]
    if missing:
        die(4, "tab '%s' thiếu cột: %s" % (name, ", ".join(missing)))

    last = max(col.values())
    vr = batch_get(["%s!A%d:%s%d" % (name, row, col_letter(last), row)])[0]
    vals = (vr.get("values") or [[]])[0]

    def cell(key):
        i = col.get(key)
        return vals[i] if i is not None and i < len(vals) else ""

    return {
        "task_id": cell("task_id") or task_id,
        "tab": name,
        "row": row,
        "estimate": to_number(cell("estimate")),
        "estimate_raw": cell("estimate"),
        # Giờ đang có TRƯỚC khi ghi. Cần để tính delta = giờ vừa bỏ thêm vào hôm
        # nay: "Actual Effort" trên sheet là số CỘNG DỒN của cả task, cộng thẳng
        # các dòng report lại là ra tổng của cả sprint chứ không phải của 1 ngày.
        "actual_before": to_number(cell("actual")),
        "assignee": cell("assignee"),
        "task": cell("task"),
        "sub_task": cell("sub_task"),
        "status": cell("status"),
        "_col": col,
    }


# ------------------------------------------------------------------ tham số CLI
def parse_flags(argv, known):
    pos, flags = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:]
            if k not in known:
                die(2, "tham số lạ: %s" % a)
            if known[k] == "bool":
                flags[k] = True
                i += 1
            else:
                if i + 1 >= len(argv):
                    die(2, "%s thiếu giá trị" % a)
                flags[k] = argv[i + 1]
                i += 2
        else:
            pos.append(a)
            i += 1
    return pos, flags


# ------------------------------------------------------------------------- sổ cái
def write_ledger(slack_id, date_str, entry):
    """Ghi thêm 1 dòng vào sổ cái giờ-log-hôm-nay. Trả về mô tả ngắn để in kèm.

    KHÔNG có --slack-id thì bỏ qua im lặng: log lên sheet vẫn là log thành công,
    thiếu sổ cái chỉ làm lượt 16:30 kém thông tin hơn. Và mọi lỗi ghi sổ đều bị
    nuốt — không đời nào để một task đã ghi đúng lên sheet bị báo là thất bại
    chỉ vì cái file phụ này hỏng.
    """
    if not slack_id:
        return "skip (khong co --slack-id)"
    path = os.environ.get("EFFORT_LEDGER_FILE") or ""
    if not path:
        return "skip (khong biet duong dan)"
    try:
        day = (date_str or "").strip() or time.strftime("%Y-%m-%d")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, encoding="utf-8") as fh:
                book = json.load(fh)
        except Exception:
            book = {}
        entries = book.get("entries") or []
        # Chỉ giữ 7 ngày gần nhất, khỏi để file phình mãi.
        keep = sorted({e.get("date") for e in entries if e.get("date")} | {day})[-7:]
        entries = [e for e in entries if e.get("date") in keep]
        entries.append(dict(entry, date=day, slack_id=slack_id, at=int(time.time())))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"entries": entries}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return "ok (%s, delta %s)" % (day, entry.get("delta"))
    except Exception as ex:
        print("khong ghi duoc so cai effort: %s" % ex, file=sys.stderr)
        return "loi: %s" % ex


# ------------------------------------------------------- allocation cross-check
def parse_ddmmyyyy(raw):
    """'07-08-2026' hoặc '7-8-2026' -> date. None nếu không parse được."""
    m = re.match(r"^\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$", raw or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d).date()
    except ValueError:
        return None


MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def ledger_logged_today(slack_id, date_key, current_task_id=None, current_task_live_before=None):
    """Tổng giờ member đã log HÔM NAY, cộng dồn qua MỌI task họ report trong
    ngày — đọc sổ cái effort-today.json (cùng file reminder-followup dùng cho
    lượt follow-up 16:30), KHÔNG quét lại 'Actual Effort' trên sheet Sprint.

    Lý do bắt buộc phải qua sổ cái: 'Actual Effort (h)' trên sheet là số CỘNG
    DỒN của riêng từng task tính từ ngày task đó bắt đầu, không phải 'số giờ
    làm hôm nay' — 1 task chạy nhiều ngày mà cộng thẳng cột đó vào là tính sai
    ngay cả với 1 task, chưa nói tới cộng nhiều task.

    Với MỖI task, KHÔNG cộng thô mọi `delta` đã ghi trong ngày — nếu ai đó
    reset thẳng ô Actual Effort trên sheet (không qua `log`) rồi report lại,
    delta của lần report sau được tính từ giá trị đã bị reset (đúng tại lúc
    đó), nhưng sổ cái vẫn còn delta CŨ từ trước khi reset -> cộng thô 2 delta
    lại là phồng lên gấp đôi dù sheet thật chỉ còn giá trị mới. Thay vào đó,
    lấy đúng 2 mốc: `actual` của lần log ĐẦU TIÊN hôm nay cho task đó (trừ đi
    delta của chính lần đó ra `baseline` = giá trị trước khi ngày hôm nay bắt
    đầu report) và `actual` của lần log GẦN NHẤT — chênh lệch 2 mốc này luôn
    đúng bằng đúng giờ đã thay đổi thật trong ngày cho task đó, bất kể ở giữa
    có bị reset bao nhiêu lần. Entry cũ thiếu field `actual` (ghi trước khi
    field này tồn tại) thì fallback về cộng thô `delta` như cũ.

    Vẫn còn 1 khoảng trống: nếu sheet bị reset SAU lần log gần nhất trong
    ledger (chưa có lần log nào sau đó để "thấy" việc reset) thì lịch sử ledger
    của đúng task đang log lúc này (`current_task_id`) đã stale — không cách
    nào biết được nếu chỉ nhìn ledger. Vì vậy bên gọi phải truyền thêm
    `current_task_id` + `current_task_live_before` (giá trị Actual Effort đọc
    SỐNG từ sheet ngay trước khi ghi lần này, tức `before` ở cmd log) — nếu nó
    lệch với `actual` của entry gần nhất trong ledger cho đúng task đó, coi
    lịch sử ledger của RIÊNG task đó là không đáng tin (bỏ qua hoàn toàn, không
    cộng vào), vì sheet đã đổi ngoài kiểm soát của ledger kể từ lần log đó."""
    path = os.environ.get("EFFORT_LEDGER_FILE") or ""
    if not path or not slack_id:
        return 0.0, []
    try:
        with open(path, encoding="utf-8") as fh:
            book = json.load(fh)
    except Exception:
        return 0.0, []
    per_task = {}
    for e in book.get("entries") or []:
        if e.get("slack_id") == slack_id and e.get("date") == date_key:
            per_task.setdefault(e.get("task_id"), []).append(e)
    total = 0.0
    for task_id, es in per_task.items():
        if task_id == current_task_id:
            last_known_actual = es[-1].get("actual")
            live_before = 0.0 if current_task_live_before is None else float(current_task_live_before)
            if last_known_actual is not None and abs(float(last_known_actual) - live_before) > 0.01:
                # Sheet đã đổi ngoài script kể từ lần log gần nhất cho đúng
                # task này (reset tay, sửa tay...) -> lịch sử ledger của task
                # này không còn phản ánh đúng sheet, bỏ hẳn, không cộng.
                continue
        first, last = es[0], es[-1]
        first_actual, last_actual = first.get("actual"), last.get("actual")
        if first_actual is None or last_actual is None:
            total += sum(float(e.get("delta") or 0) for e in es)
        else:
            baseline = float(first_actual) - float(first.get("delta") or 0)
            total += float(last_actual) - baseline
    return round(total, 2), list(per_task.keys())


def read_resource_plan_allocation(slack_id, target_date):
    """Giờ allocate của 1 member đúng 1 ngày, đọc từ tab 'Resource plan', khối
    'Thời gian làm việc mỗi ngày' (cột U+). Trả (allocated_hours|None, lý_do)."""
    names = [t for t, _ in list_tabs()]
    if "Resource plan" not in names:
        return None, "khong co tab Resource plan"
    vr = batch_get(["'Resource plan'!U1:DZ40"])[0]
    rows = vr.get("values", [])
    if len(rows) < 4:
        return None, "khong doc duoc header Resource plan"
    hdr_month, hdr_day = rows[2], rows[3]
    width = max(len(hdr_month), len(hdr_day))
    col_idx, cur_month = None, None
    for i in range(5, width):
        m = norm(hdr_month[i]) if i < len(hdr_month) else ""
        if m in MONTHS_EN:
            cur_month = MONTHS_EN[m]
        day_num = to_number(hdr_day[i]) if i < len(hdr_day) else None
        if cur_month is not None and day_num is not None:
            if (cur_month, int(day_num)) == (target_date.month, target_date.day):
                col_idx = i
                break
    if col_idx is None:
        return None, "ngay %s ngoai pham vi Resource plan" % target_date.isoformat()
    for row in rows[4:]:
        sid = (row[2] if len(row) > 2 else "").strip()
        if sid and sid == slack_id.strip():
            return to_number(row[col_idx] if col_idx < len(row) else ""), "ok"
    return None, "khong tim thay slack_id trong Resource plan"


# ------------------------------------------------------------------------ find
if CMD == "find":
    if len(ARGV) != 1:
        die(2, "dùng: sheet-task.sh find <TASKID>")
    info = find_task(ARGV[0])
    info.pop("_col")
    print(json.dumps(info, ensure_ascii=False))
    sys.exit(0)

# ------------------------------------------------------------------------- log
if CMD == "log":
    known = {
        "re-est": "v", "start": "v", "end": "v", "actual": "v",
        "status": "v", "note": "v", "force": "bool",
        "slack-id": "v", "date": "v",
    }
    pos, f = parse_flags(ARGV, known)
    if len(pos) != 1:
        die(2, "dùng: sheet-task.sh log <TASKID> --re-est .. --start .. --end .. --actual .. --status ..")
    for req in ("re-est", "start", "actual", "status"):
        if not f.get(req):
            die(2, "thiếu --%s" % req)

    info = find_task(pos[0])
    col = info.pop("_col")
    est = info["estimate"]
    act = to_number(f["actual"])

    if act is None:
        die(2, "Actual Effort không phải số: %r" % f["actual"])

    re_est_val = to_number(f["re-est"])
    if re_est_val is None:
        die(2, "Re-estimate không phải số: %r" % f["re-est"])

    # Actual vượt Estimate = đã thực sự tốn nhiều giờ hơn kế hoạch. Re-estimate
    # vượt Estimate = dev tự nhận định tổng effort sẽ vượt kế hoạch, dù Actual
    # (số giờ đã làm tới lúc report) chưa chắc đã vượt — vẫn là tín hiệu sớm cần
    # hỏi lý do, không chờ tới lúc Actual thực sự vượt mới hỏi.
    over_actual = est is not None and act > est
    over_re_est = est is not None and re_est_val > est
    over = over_actual or over_re_est
    if over and not f.get("force"):
        print(json.dumps({
            "error": "overtime",
            "task_id": info["task_id"], "tab": info["tab"], "row": info["row"],
            "assignee": info["assignee"], "task": info["task"], "sub_task": info["sub_task"],
            "estimate": est, "actual": act, "re_estimate": re_est_val,
            "over_actual": over_actual, "over_re_estimate": over_re_est,
            "diff": round(max(act - est, re_est_val - est), 2),
        }, ensure_ascii=False))
        sys.exit(9)

    # Status = Done ngụ ý Remaining = Re-estimate - Actual phải bằng 0 (Progress
    # 100%) — dev report Done nhưng Actual còn thấp hơn Re-estimate là dữ liệu tự
    # mâu thuẫn (task "xong" mà vẫn còn giờ chưa log), khác hẳn case "quá giờ" ở
    # trên. Không tự đoán số nào đúng (Actual thiếu, hay Re-estimate còn thừa) —
    # chặn lại hỏi dev.
    status_val = f["status"].strip()
    done_mismatch = (
        status_val.lower() == "done"
        and re_est_val is not None
        and abs(act - re_est_val) > 0.01
    )
    if done_mismatch and not f.get("force"):
        print(json.dumps({
            "error": "done_mismatch",
            "task_id": info["task_id"], "tab": info["tab"], "row": info["row"],
            "assignee": info["assignee"], "task": info["task"], "sub_task": info["sub_task"],
            "actual": act, "re_estimate": re_est_val,
            "diff": round(re_est_val - act, 2),
        }, ensure_ascii=False))
        sys.exit(12)

    # Giờ MỚI thêm vào task này ở lần log này — không phải "Actual Effort" thô
    # (số đó cộng dồn cả task, có thể đã tích luỹ từ nhiều ngày trước). Dùng
    # delta này (không phải act) để cộng vào tổng-giờ-hôm-nay của member.
    before = info.get("actual_before")
    delta = round(act - (before if before is not None else 0), 2)

    # Chỉ CHẶN khi log NHIỀU hơn allocate (gap âm) — bất thường bất kể giờ nào
    # trong ngày, vì không thể làm nhiều hơn giờ thực có. Log ÍT hơn allocate
    # (gap dương) là trạng thái BÌNH THƯỜNG trong phần lớn ngày làm việc (chưa
    # ai log đủ 8h lúc 10h sáng cả) — KHÔNG chặn, chỉ đính kèm ghi chú vào
    # response sau khi ghi thành công; hỏi "có thực sự thiếu giờ" là việc của
    # lượt cuối ngày (reminder-followup --effort-check, 16:30), không lặp lại
    # ở đây. Chỉ chạy được khi có --slack-id (khớp đúng dòng member ở Resource
    # plan qua Slack ID, không qua tên/nickname) và parse được ngày từ --start;
    # thiếu 1 trong 2 thì bỏ qua im lặng, không suy đoán.
    allocation_note = None
    target_date = parse_ddmmyyyy(f["start"])
    slack_id = f.get("slack-id")
    if slack_id and target_date is not None and not f.get("force"):
        ledger_date = (f.get("date") or "").strip() or time.strftime("%Y-%m-%d")
        logged_before_this, other_tasks = ledger_logged_today(
            slack_id, ledger_date, current_task_id=info["task_id"], current_task_live_before=before,
        )
        total_logged_today = round(logged_before_this + delta, 2)
        allocated, _reason = read_resource_plan_allocation(slack_id, target_date)
        if allocated is not None:
            gap = round(allocated - total_logged_today, 2)
            payload = {
                "task_id": info["task_id"], "tab": info["tab"], "row": info["row"],
                "assignee": info["assignee"], "task": info["task"], "sub_task": info["sub_task"],
                "date": target_date.isoformat(),
                "this_task_delta": delta,
                "other_tasks_logged_today": other_tasks,
                "logged_before_this_hours": logged_before_this,
                "total_logged_today_hours": total_logged_today,
                "allocated_hours": allocated,
                "gap": gap,
            }
            if gap < -0.01:
                print(json.dumps(dict(payload, error="allocation_mismatch"), ensure_ascii=False))
                sys.exit(13)
            elif gap > 0.01:
                allocation_note = payload

    end_raw = (f.get("end") or "").strip()
    end_val = "" if norm(end_raw) in EMPTY_END else end_raw

    tab = info["tab"]
    row = info["row"]
    data = [
        {"range": "%s!%s%d" % (tab, col_letter(col["re_est"]), row), "values": [[to_cell_number(f["re-est"])]]},
        {"range": "%s!%s%d" % (tab, col_letter(col["start"]), row), "values": [[f["start"].strip()]]},
        {"range": "%s!%s%d" % (tab, col_letter(col["end"]), row), "values": [[end_val]]},
        {"range": "%s!%s%d" % (tab, col_letter(col["actual"]), row), "values": [[to_cell_number(f["actual"])]]},
        {"range": "%s!%s%d" % (tab, col_letter(col["status"]), row), "values": [[f["status"].strip()]]},
    ]
    if "note" in col and f.get("note") is not None:
        data.append({"range": "%s!%s%d" % (tab, col_letter(col["note"]), row), "values": [[f.get("note", "")]]})

    post("%s/%s/values:batchUpdate" % (API, FILE_ID), {"valueInputOption": "USER_ENTERED", "data": data})

    # Verify: đọc lại đúng dòng đó, so Actual Effort. Ghi xong không kiểm là
    # không biết USER_ENTERED có nuốt mất dấu thập phân hay không.
    vr = batch_get(["%s!A%d:%s%d" % (tab, row, col_letter(max(col.values())), row)])[0]
    back = (vr.get("values") or [[]])[0]

    def cell(key):
        i = col.get(key)
        return back[i] if i is not None and i < len(back) else ""

    got = to_number(cell("actual"))
    if got is None or abs(got - act) > 0.01:
        die(11, "ghi xong nhưng đọc lại không khớp: Actual Effort trên sheet = %r, cần %s" % (cell("actual"), act))

    ledger_note = write_ledger(f.get("slack-id"), f.get("date"), {
        "task_id": info["task_id"], "tab": tab,
        "delta": delta, "actual": act, "status": f["status"].strip(),
    })

    result = {
        "ok": True, "task_id": info["task_id"], "tab": tab, "row": row,
        "assignee": info["assignee"],
        "written": {
            "re_estimate": cell("re_est"), "start": cell("start"), "end": cell("end"),
            "actual_effort": cell("actual"), "status": cell("status"), "note": cell("note"),
        },
        "estimate": est, "overtime": bool(over),
        "actual_before": before, "delta": delta, "ledger": ledger_note,
    }
    if allocation_note is not None:
        result["allocation_note"] = allocation_note
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)

# ------------------------------------------------------------------------ risk
if CMD == "risk":
    known = {
        "task": "v", "assignee": "v", "diff": "v", "reason": "v",
        "next": "v", "reporter": "v", "priority": "v",
    }
    pos, f = parse_flags(ARGV, known)
    for req in ("task", "diff", "reason"):
        if not f.get(req):
            die(2, "thiếu --%s" % req)

    tabs = [t for t, _ in list_tabs()]
    risk_tab = next((t for t in tabs if norm(t) == "risk management"), None)
    if not risk_tab:
        die(4, "không thấy tab 'Risk management' trong sheet")

    vr = batch_get(["%s!A1:Z500" % risk_tab])[0]
    rows = vr.get("values", [])
    hdr = [norm(c) for c in (rows[0] if rows else [])]
    for need in ("id", "date detected", "description", "priority"):
        if need not in hdr:
            die(4, "tab '%s' thiếu cột '%s'" % (risk_tab, need))

    rcol = resolve_risk_columns(hdr)

    last_row = len(rows)
    max_n = 0
    for r in rows[1:]:
        m = re.match(r"^\s*R-(\d+)", r[0] if r else "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    new_id = "R-%02d" % (max_n + 1)

    diff = to_number(f["diff"]) or 0
    prio = f.get("priority") or ("High" if diff >= 4 else "Medium")
    assignee = f.get("assignee") or ""
    desc = "%s vượt %sh ở task %s: %s" % (
        assignee or "Dev", ("%g" % diff), f["task"], f["reason"].strip(),
    )
    # Có cột 'Task' riêng thì Related Assignee chỉ để tên người, cho khớp với
    # các dòng PM tự nhập tay. Không có thì mới gộp 'Tên/TaskID' như trước.
    if "task" in rcol:
        related = assignee
    else:
        related = ("%s/%s" % (assignee, f["task"])) if assignee else f["task"]
    nxt = f.get("next") or "PM review giờ vượt"
    notes = "Ghi tự động từ report Slack ngày %s%s" % (
        today().strftime("%d-%m-%Y"),
        (", người report %s" % f["reporter"]) if f.get("reporter") else "",
    )
    vals = {
        "id": new_id, "date": today().strftime("%d-%m-%Y"), "desc": desc,
        "prio": prio, "assignee": related, "task": f["task"], "next": nxt,
        "status": "Open", "notes": notes,
    }
    width = max(len(hdr), max(rcol.values()) + 1 if rcol else 1)
    row_vals = [""] * width
    for key, i in rcol.items():
        row_vals[i] = vals[key]
    new_row = last_row + 1
    post(
        "%s/%s/values/%s?valueInputOption=USER_ENTERED"
        % (API, FILE_ID, urllib.parse.quote(
            "%s!A%d:%s%d" % (risk_tab, new_row, col_letter(width - 1), new_row), safe="")),
        {"values": [row_vals]},
        method="PUT",
    )
    print(json.dumps({
        "ok": True, "risk_id": new_id, "tab": risk_tab, "row": new_row,
        "description": desc, "priority": prio, "related": related,
        "columns": {k: col_letter(i) for k, i in sorted(rcol.items(), key=lambda kv: kv[1])},
    }, ensure_ascii=False))
    sys.exit(0)
PY
