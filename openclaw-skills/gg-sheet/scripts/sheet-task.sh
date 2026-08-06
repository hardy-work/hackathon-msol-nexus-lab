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
#                              --actual X --status S [--note N] [--force]
#       -> ghi 6 ô khối Actual + Status + Note của ĐÚNG dòng task đó.
#          Actual Effort > Estimate mà không có --force -> exit 9, KHÔNG ghi gì.
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
#   9  QUÁ GIỜ: Actual Effort > Estimate, chưa ghi gì cả (in JSON chi tiết ra stdout)
#  10  lấy access token thất bại (ghi)
#  11  ghi lên sheet lỗi / verify lại thấy không khớp
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

export FILE_ID ACCESS_TOKEN CMD
exec python3 - "$@" <<'PY'
import json, os, re, sys, urllib.parse, urllib.request
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

    over = est is not None and act > est
    if over and not f.get("force"):
        print(json.dumps({
            "error": "overtime",
            "task_id": info["task_id"], "tab": info["tab"], "row": info["row"],
            "assignee": info["assignee"], "task": info["task"], "sub_task": info["sub_task"],
            "estimate": est, "actual": act, "diff": round(act - est, 2),
        }, ensure_ascii=False))
        sys.exit(9)

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

    print(json.dumps({
        "ok": True, "task_id": info["task_id"], "tab": tab, "row": row,
        "assignee": info["assignee"],
        "written": {
            "re_estimate": cell("re_est"), "start": cell("start"), "end": cell("end"),
            "actual_effort": cell("actual"), "status": cell("status"), "note": cell("note"),
        },
        "estimate": est, "overtime": bool(over),
    }, ensure_ascii=False))
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

    vr = batch_get(["%s!A1:H500" % risk_tab])[0]
    rows = vr.get("values", [])
    hdr = [norm(c) for c in (rows[0] if rows else [])]
    for need in ("id", "date detected", "description", "priority"):
        if need not in hdr:
            die(4, "tab '%s' thiếu cột '%s'" % (risk_tab, need))

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
    related = ("%s/%s" % (assignee, f["task"])) if assignee else f["task"]
    nxt = f.get("next") or "PM review giờ vượt"
    notes = "Ghi tự động từ report Slack ngày %s%s" % (
        today().strftime("%d-%m-%Y"),
        (", người report %s" % f["reporter"]) if f.get("reporter") else "",
    )
    new_row = last_row + 1
    post(
        "%s/%s/values/%s?valueInputOption=USER_ENTERED"
        % (API, FILE_ID, urllib.parse.quote("%s!A%d:H%d" % (risk_tab, new_row, new_row), safe="")),
        {"values": [[new_id, today().strftime("%d-%m-%Y"), desc, prio, related, nxt, "Open", notes]]},
        method="PUT",
    )
    print(json.dumps({
        "ok": True, "risk_id": new_id, "tab": risk_tab, "row": new_row,
        "description": desc, "priority": prio, "related": related,
    }, ensure_ascii=False))
    sys.exit(0)
PY
