#!/usr/bin/env bash
# Ai phải report HÔM NAY — đọc từ tab "Resource plan" của Google Sheet logtime.
#
# Nguồn: bảng có header `Member | Slack ID | Slack name | Role`, kèm khối công
# "Thời gian làm việc mỗi ngày" (mỗi ngày 1 cột). Ô công của hôm nay trống / 0 /
# "P" / "nghỉ" => người đó NGHỈ hôm nay, KHÔNG nhắc.
#
# Mỗi Slack ID còn được ĐỐI CHIẾU với workspace qua users.info trước khi in ra:
# id không tồn tại thì bị loại thẳng, không tag. Lý do: Slack render <@Uxxx> lạ
# thành một pill TRỐNG — tin vẫn đăng, vẫn xanh, mà không ai nhận notification và
# không lỗi nào nổ ra. Đã dính thật ngày 06-08-2026: cả 6 id trong sheet là của
# workspace khác, tin 9:00 tag vào hư không.
#
# Vào  (env): LOGTIME_SHEET_LINK (hoặc GOOGLE_SHEETS_LINK), GOOGLE_SHEETS_API_KEY,
#             LOGTIME_SHEET_TAB (mặc định "Resource plan"),
#             REMINDER_TIMEZONE (mặc định Asia/Ho_Chi_Minh — dùng để biết "hôm nay"),
#             SLACK_BOT_TOKEN (tuỳ chọn — không có thì tự đọc channels.slack.botToken
#             trong openclaw.json; không lấy được nữa thì BỎ QUA bước đối chiếu,
#             giữ nguyên hành vi cũ chứ không loại oan ai)
#             EFFORT_TOLERANCE_H (mặc định 1 — thiếu dưới ngần này giờ thì bỏ qua,
#             khỏi hỏi ai vì 7,5 với 8)
# Tham số   : không có       -> JSON {date, found_day_column, people[], off[], no_id[], bad_id[]}
#             --mentions     -> một dòng "<@U...> <@U...>" của riêng people[], dán thẳng vào Slack
#             --effort-check -> JSON chia nhóm ai hôm nay log thiếu giờ so với công đăng ký
#
# Ô công của hôm nay là một CON SỐ (8 = ngày đủ công, 4 = nghỉ nửa buổi), không
# phải cờ có/không. `hours` giữ nguyên con số đó để --effort-check còn so được;
# PM sửa ô thành 4 là mốc tự thành 4, không cần luật riêng cho nghỉ nửa buổi.
#
# Exit code:
#   0  ok, có ít nhất 1 người phải report hôm nay
#   2  thiếu env / tham số sai
#   3  gọi Sheets API lỗi
#   4  không thấy header "Slack ID"
#   5  có header nhưng không có dòng người nào (sheet rỗng/sai tab), hoặc mọi
#      Slack ID đều không tồn tại trong workspace
#   6  có danh sách nhưng HÔM NAY cả đội nghỉ -> job phải SKIP im lặng, KHÔNG báo lỗi
set -uo pipefail

MODE="${1:-json}"
case "$MODE" in
  json | --mentions | --effort-check) ;;
  *) echo "tham số không hợp lệ: $MODE (chỉ nhận --mentions, --effort-check, hoặc bỏ trống)" >&2; exit 2 ;;
esac

# Sổ cái giờ đã log hôm nay. gg-sheet/scripts/sheet-task.sh ghi vào đây sau mỗi
# lần log thành công (nó tính đường dẫn y hệt, qua thư mục skill anh em), script
# này chỉ đọc. Tự dò thư mục của chính mình -> không phụ thuộc cwd, không cần env.
SKILL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
LEDGER="${EFFORT_LEDGER_FILE:-$SKILL_DIR/state/effort-today.json}"

TAB="${LOGTIME_SHEET_TAB:-Resource plan}"
LINK="${LOGTIME_SHEET_LINK:-${GOOGLE_SHEETS_LINK:-}}"

if [ -z "$LINK" ]; then
  echo "thiếu LOGTIME_SHEET_LINK (hoặc GOOGLE_SHEETS_LINK) trong env" >&2
  exit 2
fi
if [ -z "${GOOGLE_SHEETS_API_KEY:-}" ]; then
  echo "thiếu GOOGLE_SHEETS_API_KEY trong env" >&2
  exit 2
fi

FILE_ID=$(printf '%s' "$LINK" | sed -nE 's#.*/spreadsheets/d/([a-zA-Z0-9_-]+).*#\1#p')
if [ -z "$FILE_ID" ]; then
  # link có thể đã là fileId trần
  case "$LINK" in
    */*) echo "không rút được fileId từ LOGTIME_SHEET_LINK: $LINK" >&2; exit 2 ;;
    *) FILE_ID="$LINK" ;;
  esac
fi

RANGE_ENC=$(TAB="$TAB" python3 -c '
import os, urllib.parse
print(urllib.parse.quote(os.environ["TAB"] + "!A1:CZ300", safe=""))
')

if [ -n "${MOCK_SHEET_RESPONSE_FILE:-}" ]; then
  # Chỗ cắm cho test offline: đưa sẵn payload của Sheets API, khỏi cần mạng/API
  # key. CHỈ đọc file, không đổi hành vi gì khác. Cron không bao giờ set biến này.
  RESP=$(cat "$MOCK_SHEET_RESPONSE_FILE") || { echo "không đọc được MOCK_SHEET_RESPONSE_FILE" >&2; exit 3; }
else
  RESP=$(curl -sS --max-time 30 \
    "https://sheets.googleapis.com/v4/spreadsheets/${FILE_ID}/values/${RANGE_ENC}?key=${GOOGLE_SHEETS_API_KEY}") || {
    echo "gọi Google Sheets API lỗi (curl)" >&2
    exit 3
  }
fi

printf '%s' "$RESP" | TAB="$TAB" MODE="$MODE" LEDGER="$LEDGER" python3 -c '
import json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("Sheets API trả về không phải JSON: " + raw[:300], file=sys.stderr)
    sys.exit(3)

if "error" in data:
    err = data["error"]
    print("Sheets API lỗi %s: %s" % (err.get("code"), err.get("message")), file=sys.stderr)
    sys.exit(3)

rows = data.get("values") or []


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


# --- Header: dòng đầu tiên có ô "Slack ID". Không hardcode số dòng/cột, sheet
# --- chèn thêm dòng/cột phía trên vẫn chạy đúng.
head_i = head = None
for i, row in enumerate(rows):
    if any(norm(c) in ("slack id", "slackid", "slack_id") for c in row):
        head_i, head = i, [norm(c) for c in row]
        break

if head is None:
    print(
        "không tìm thấy cột \"Slack ID\" trong tab %r — kiểm tra lại tên tab / header của sheet"
        % os.environ.get("TAB"),
        file=sys.stderr,
    )
    sys.exit(4)


def col(*names):
    for n in names:
        if n in head:
            return head.index(n)
    return None


c_id = col("slack id", "slackid", "slack_id")
c_name = col("member", "tên nhân sự", "ten nhan su", "name", "họ tên", "ho ten")
c_slack_name = col("slack name", "slackname", "slack_name")
c_role = col("role", "vai trò", "vai tro")

# --- Hôm nay theo múi giờ của team, không theo giờ máy chạy Gateway.
tz_name = os.environ.get("REMINDER_TIMEZONE") or "Asia/Ho_Chi_Minh"
now = None
# LOGTIME_TODAY=YYYY-MM-DD: chỉ để soi lỗi bằng tay ("hôm T7 bot có nhắc nhầm
# không?"). Cron KHÔNG BAO GIỜ set biến này.
override = os.environ.get("LOGTIME_TODAY")
if override:
    try:
        now = datetime.strptime(override.strip(), "%Y-%m-%d")
    except ValueError:
        print("LOGTIME_TODAY phải dạng YYYY-MM-DD, đang là %r" % override, file=sys.stderr)
        sys.exit(2)
if now is None and ZoneInfo is not None:
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = None
if now is None:
    now = datetime.now()

# --- Cột công của hôm nay: dòng header mang tên tháng (July / August / Tháng 8),
# --- dòng ngay dưới mang số ngày. Ghép tháng gần nhất bên trái + số ngày, so
# --- khớp đúng ngày hôm nay -> khỏi phải suy ra năm (sheet không ghi năm).
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def month_of(cell):
    t = norm(cell)
    if not t:
        return None
    if t in MONTHS:
        return MONTHS[t]
    m = re.fullmatch(r"th[aá]ng\s*(\d{1,2})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return None


day_row = rows[head_i + 1] if head_i + 1 < len(rows) else []
today_col = None
cur_month = None
for c in range(max(len(head), len(day_row))):
    mth = month_of(head[c]) if c < len(head) else None
    if mth is not None:
        cur_month = mth
    cell = str(day_row[c]).strip() if c < len(day_row) else ""
    if not re.fullmatch(r"\d{1,2}", cell):
        continue
    day = int(cell)
    if cur_month == now.month and day == now.day:
        today_col = c
        break

found_day_column = today_col is not None

OFF_WORDS = {"", "-", "--", "0", "0.0", "0,0", "x", "p", "off", "nghỉ", "nghi", "nghỉ phép", "nghi phep"}


def to_hours(cell):
    """Ô công -> số giờ đăng ký hôm nay. Không đọc được thì None."""
    t = norm(cell).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def is_off(cell):
    t = norm(cell)
    if t in OFF_WORDS:
        return True
    n = t.replace(",", ".")
    try:
        return float(n) <= 0
    except ValueError:
        # Không hiểu ô này ghi gì -> coi như đi làm. Thà nhắc thừa 1 người còn
        # hơn im lặng bỏ sót người phải report.
        return False


ID_RE = re.compile(r"^[UW][A-Z0-9]{6,}$")
people, off, no_id, seen = [], [], [], set()

for row in rows[head_i + 1 :]:
    def cell(idx):
        return str(row[idx]).strip() if idx is not None and idx < len(row) else ""

    uid = cell(c_id)
    name = cell(c_name)
    if not ID_RE.match(uid):
        # Có tên người thật nhưng thiếu Slack ID -> không tag được, phải nói ra.
        if name and not month_of(name) and name.lower() not in ("member", "sum", "grand total"):
            no_id.append(name)
        continue
    if uid in seen:
        continue
    seen.add(uid)

    person = {
        "id": uid,
        "name": name or cell(c_slack_name) or uid,
        "slack_name": cell(c_slack_name),
        "role": cell(c_role),
        # Công đăng ký hôm nay, giữ nguyên con số trong ô. None = chưa có cột
        # cho hôm nay, hoặc ô ghi chữ lạ -> --effort-check bỏ qua người này chứ
        # không lấy 8 làm mặc định (đoán mốc rồi đi hỏi người ta là nhắc oan).
        "hours": to_hours(cell(today_col)) if found_day_column else None,
    }
    if found_day_column and is_off(cell(today_col)):
        off.append(person)
    else:
        people.append(person)

# --- Đối chiếu từng id với workspace. Đúng cú pháp <@U...> KHÔNG có nghĩa là
# --- người đó có thật: Slack im lặng render id lạ thành pill trống.
def slack_token():
    t = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if t:
        return t
    state = os.environ.get("OPENCLAW_STATE_DIR") or os.path.expanduser("~/.openclaw")
    try:
        with open(os.path.join(state, "openclaw.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        return str(((cfg.get("channels") or {}).get("slack") or {}).get("botToken") or "").strip()
    except Exception:
        return ""


def user_exists(token, uid):
    """True/False, hoặc None = CHƯA KẾT LUẬN ĐƯỢC (mạng lỗi, thiếu scope, rate limit).
    None thì giữ lại người đó — thà tag một id đáng ngờ còn hơn im lặng bỏ sót
    người phải report chỉ vì bot đang hỏng mạng."""
    req = urllib.request.Request(
        "https://slack.com/api/users.info?" + urllib.parse.urlencode({"user": uid}),
        headers={"Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if d.get("ok"):
        # Đã nghỉ việc (deleted) thì cũng không tag nữa.
        return not (d.get("user") or {}).get("deleted")
    # Chỉ đúng lỗi này mới dám kết luận là id sai. invalid_auth / missing_scope /
    # ratelimited là bot hỏng, không phải sheet sai -> None.
    return False if d.get("error") == "user_not_found" else None


bad_id, id_checked = [], False
token = slack_token()
if token and people:
    id_checked = True
    kept = []
    for p in people:
        if user_exists(token, p["id"]) is False:
            bad_id.append(p)
        else:
            kept.append(p)
    people = kept

if bad_id:
    # Ra stderr, KHÔNG ra stdout: stdout của --mentions được dán thẳng vào tin
    # Slack, thêm dòng vào đó là đăng rác cho cả kênh đọc.
    print(
        "bỏ qua %d Slack ID không tồn tại trong workspace: %s"
        % (len(bad_id), ", ".join("%s (%s)" % (p["name"], p["id"]) for p in bad_id)),
        file=sys.stderr,
    )

if bad_id and not people:
    print(
        "tab %r: KHÔNG id nào tồn tại trong workspace này — cột Slack ID nhiều khả "
        "năng là của workspace khác, nhờ PM sửa lại" % os.environ.get("TAB"),
        file=sys.stderr,
    )
    sys.exit(5)

if not people and not off:
    print(
        "tab %r có cột Slack ID nhưng không có dòng nào chứa user id hợp lệ"
        % os.environ.get("TAB"),
        file=sys.stderr,
    )
    sys.exit(5)

notices = []
if not found_day_column:
    notices.append(
        "(Bảng công trong sheet chưa có cột cho hôm nay, nhờ PM kéo dài giúp mình nhé.)"
    )
if no_id:
    notices.append(
        "(Chưa có Id Slack nên mình không tag được: %s)" % ", ".join(no_id)
    )

if os.environ.get("MODE") == "--effort-check":
    # --- Ai hôm nay log ÍT GIỜ HƠN công đã đăng ký.
    #
    # Chia 2 nhóm vì cùng một triệu chứng nhưng khác hẳn hậu quả:
    #   - còn task In progress -> task CHƯA XONG mà giờ bỏ vào cũng chưa đủ:
    #     tiến độ đang trôi thật -> hỏi lý do rồi ghi Risk management.
    #   - mọi task đều Done     -> xong sớm hơn plan, chuyện tốt. KHÔNG ghi risk,
    #     chỉ hỏi một câu xem có phải quên log dòng nữa / nghỉ nửa buổi không.
    # Trộn 2 nhóm này làm một là biến "làm nhanh hơn plan" thành rủi ro dự án.
    DONE_WORDS = {
        "done", "completed", "finished", "xong",
        "hoàn thành", "hoan thanh", "hoàn tất", "hoan tat",
    }

    def is_done(s):
        # Cùng bộ chữ với template/log-task-rules.md mục "Thế nào là Status Done".
        # Sửa một bên thì phải sửa bên kia — đây là 2 bản dùng cho 2 việc khác
        # nhau (bên kia chấm format, bên này hỏi tiến độ) nên không gộp được.
        t = re.sub(r"[^0-9a-zà-ỹ\s]", "", norm(s)).strip()
        t = re.sub(r"^đã\s+", "", t).strip()
        return t in DONE_WORDS

    try:
        tol = float(os.environ.get("EFFORT_TOLERANCE_H") or 1)
    except ValueError:
        tol = 1.0

    today_key = now.strftime("%Y-%m-%d")
    logged = {}
    try:
        with open(os.environ["LEDGER"], encoding="utf-8") as fh:
            for e in (json.load(fh).get("entries") or []):
                if e.get("date") != today_key:
                    continue
                b = logged.setdefault(e.get("slack_id"), {"h": 0.0, "open": [], "n": 0})
                b["h"] += float(e.get("delta") or 0)
                b["n"] += 1
                if not is_done(e.get("status") or ""):
                    tid = e.get("task_id")
                    if tid and tid not in b["open"]:
                        b["open"].append(tid)
    except FileNotFoundError:
        pass          # chưa ai log hôm nay -> mọi người vào chua_log, không phải lỗi
    except Exception as ex:
        print("sổ cái effort hỏng (%s), bỏ qua bước so giờ" % ex, file=sys.stderr)

    dang_lam, da_xong, du_gio, chua_log = [], [], [], []
    for p in people:
        h = p.get("hours")
        b = logged.get(p["id"])
        if b is None or not b["n"]:
            # Chưa log gì cả -> họ đã nằm trong nhóm CHUA_REPORT của Job B rồi.
            # Tag thêm lần nữa vì cùng một chuyện là phiền người ta 2 lần.
            chua_log.append(p["id"])
            continue
        if h is None or h <= 0:
            du_gio.append(p["id"])     # không có mốc để so -> im, đừng đoán
            continue
        missing = round(h - b["h"], 2)
        if missing <= tol:
            du_gio.append(p["id"])
            continue
        item = {
            "id": p["id"], "name": p["name"],
            "hours": h, "logged": round(b["h"], 2), "missing": missing,
        }
        if b["open"]:
            item["in_progress"] = b["open"]
            dang_lam.append(item)
        else:
            da_xong.append(item)

    json.dump(
        {
            "date": now.strftime("%d-%m-%Y"),
            "tolerance_h": tol,
            "thieu_gio_con_dang_lam": dang_lam,
            "thieu_gio_da_xong_het": da_xong,
            "du_gio": du_gio,
            "chua_log": chua_log,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()
    sys.exit(0 if people else 6)

if os.environ.get("MODE") == "--mentions":
    # Dòng 1 = chuỗi mention. Các dòng sau (nếu có) = dòng phụ dán vào CUỐI tin.
    if people:
        print(" ".join("<@%s>" % m["id"] for m in people))
        for n in notices:
            print(n)
else:
    json.dump(
        {
            "date": now.strftime("%d-%m-%Y"),
            "found_day_column": found_day_column,
            "people": people,
            "off": off,
            "no_id": no_id,
            "bad_id": bad_id,
            "id_checked": id_checked,
            "notices": notices,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()

# Cả đội nghỉ hôm nay -> caller phải SKIP im lặng, KHÔNG coi là lỗi đọc sheet.
sys.exit(0 if people else 6)
'
