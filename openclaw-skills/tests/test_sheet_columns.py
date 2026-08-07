#!/usr/bin/env python3
"""Test offline cho phần dễ vỡ âm thầm nhất của gg-sheet/scripts/sheet-task.sh:
khớp cột theo header 2 tầng (PLAN/Actual), đọc số theo locale vi_VN, và sổ cái
effort.

Vì sao cần: tab Sprint có HAI cột tên "Start Date" và HAI cột chứa chữ
"Estimate". Khớp nhầm là ghi đè giờ plan của PM — hỏng dữ liệu gốc chứ không
phải hỏng dòng report, và không có exit code nào nổ ra để biết.

Không cần mạng, không cần API key, không đụng sheet thật: chỉ nạp các hàm thuần
trong script rồi cho ăn header giả.

    python3 openclaw-skills/tests/test_sheet_columns.py
"""
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "gg-sheet" / "scripts" / "sheet-task.sh"


def load_pure_functions():
    """Nạp các hàm thuần của sheet-task.sh mà không chạy phần dispatch CLI.

    Python nằm trong heredoc của bash nên không import được. Cắt từ dòng import
    đầu tiên tới ngay trước khối `if CMD == "find"` — phần đó toàn def, không
    gọi mạng, không đọc argv.
    """
    src = SCRIPT.read_text(encoding="utf-8")
    start = src.index("import json, os, re, sys")
    end = src.index('# ------------------------------------------------------------------------ find')
    ns = {"__name__": "sheet_task_pure"}
    for k, v in (("FILE_ID", "x"), ("ACCESS_TOKEN", ""), ("CMD", "find"),
                 ("GOOGLE_SHEETS_API_KEY", "test-key")):
        os.environ.setdefault(k, v)
    exec(compile(src[start:end], str(SCRIPT), "exec"), ns)
    return ns


FAILED = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s\n       got  = %r\n       want = %r" % (name, got, want))
        FAILED.append(name)


# --------------------------------------------------------------- header 2 tầng
# Đúng hình dạng thật của tab "Sprint 1" trong sheet Nexus Lab.
SPRINT_HEADER = [
    ["Category\nMilestone", "Task", "TaskID", "Sub-task", "Role", "Assignee", "Priority",
     "PLAN", "", "", "Actual", "", "", "", "", "", "Remaining (h)", "Status", "Note"],
    ["", "", "", "", "", "", "",
     "Estimate (h)", "Start Date", "End Date",
     "Re-estimate (h)", "Start Date", "End Date", "Actual Effort (h)", "Progress"],
]


def test_columns(ns):
    print("khop cot theo header 2 tang")
    hdr = ns["headers_of"](SPRINT_HEADER)
    col = ns["resolve_columns"](hdr)

    # Cái bẫy chính: 2 cột "Start Date" (H của PLAN, L của Actual) và 2 cột chứa
    # "Estimate" (H = Estimate của PLAN, K = Re-estimate của Actual).
    check("estimate -> khoi PLAN (H, index 7)", col.get("estimate"), 7)
    check("re_est   -> khoi Actual (K, index 10)", col.get("re_est"), 10)
    check("start    -> khoi Actual (L, index 11)", col.get("start"), 11)
    check("end      -> khoi Actual (M, index 12)", col.get("end"), 12)
    check("actual   -> Actual Effort (N, index 13)", col.get("actual"), 13)
    check("status   -> index 17", col.get("status"), 17)
    check("note     -> index 18", col.get("note"), 18)
    check("task_id  -> index 2", col.get("task_id"), 2)

    # PM chèn 1 cột vào giữa -> mọi cột phía sau dịch 1, script phải theo kịp.
    shifted = [r[:] for r in SPRINT_HEADER]
    shifted[0].insert(3, "Epic")
    shifted[1].insert(3, "")
    col2 = ns["resolve_columns"](ns["headers_of"](shifted))
    check("chen 1 cot -> estimate dich sang 8", col2.get("estimate"), 8)
    check("chen 1 cot -> actual dich sang 14", col2.get("actual"), 14)


def test_numbers(ns):
    print("doc so theo locale vi_VN")
    to_number = ns["to_number"]
    check("7,5 -> 7.5 (phay la thap phan)", to_number("7,5"), 7.5)
    check("7.5 -> 7.5", to_number("7.5"), 7.5)
    check("8 -> 8.0", to_number("8"), 8.0)
    check("480,0 -> 480.0", to_number("480,0"), 480.0)
    check("o trong -> None", to_number(""), None)
    check("chu -> None", to_number("chua xong"), None)


def test_ledger(ns):
    print("so cai effort")
    write_ledger = ns["write_ledger"]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state", "effort-today.json")
        os.environ["EFFORT_LEDGER_FILE"] = path

        # Khong co --slack-id -> bo qua im lang, KHONG duoc bao loi.
        r = write_ledger(None, "2026-08-06", {"task_id": "NEX-1", "delta": 8})
        check("khong co slack-id -> skip", r.startswith("skip"), True)
        check("khong co slack-id -> khong tao file", os.path.exists(path), False)

        write_ledger("U1", "2026-08-06", {"task_id": "NEX-1", "delta": 3, "status": "Done"})
        write_ledger("U1", "2026-08-06", {"task_id": "NEX-2", "delta": 5, "status": "In progress"})
        write_ledger("U2", "2026-08-06", {"task_id": "NEX-3", "delta": 8, "status": "Done"})
        book = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        rows = book["entries"]
        check("ghi du 3 dong", len(rows), 3)
        check("tong gio cua U1 = 8", sum(e["delta"] for e in rows if e["slack_id"] == "U1"), 8)

        # Dev khai lai THAP HON lan truoc -> delta am, tong ngay phai giam.
        write_ledger("U2", "2026-08-06", {"task_id": "NEX-3", "delta": -3, "status": "Done"})
        rows = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["entries"]
        check("delta am -> tong U2 giam con 5", sum(e["delta"] for e in rows if e["slack_id"] == "U2"), 5)

        # Chi giu 7 ngay gan nhat.
        for day in range(1, 12):
            write_ledger("U9", "2026-07-%02d" % day, {"task_id": "OLD", "delta": 1})
        rows = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["entries"]
        check("chi giu <= 7 ngay", len({e["date"] for e in rows}) <= 7, True)


# ------------------------------------------------ ledger_logged_today (exit 13)
def test_ledger_reset_drift(ns):
    """Bug thật gặp trên server: 1 task bị reset thẳng Actual Effort trên sheet
    (không qua `log`) giữa 2 lần report cùng ngày -> cộng thô delta cũ + delta
    mới bị phồng gấp đôi dù sheet thật chỉ còn giá trị mới nhất."""
    print("ledger_logged_today: reset giua chung cung 1 task")
    write_ledger = ns["write_ledger"]
    ledger_logged_today = ns["ledger_logged_today"]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state", "effort-today.json")
        os.environ["EFFORT_LEDGER_FILE"] = path

        # Log binh thuong, khong reset: 2 task khac nhau, cong dung tong.
        write_ledger("U1", "2026-08-07", {"task_id": "NEX-1", "delta": 3, "actual": 3, "status": "In progress"})
        write_ledger("U1", "2026-08-07", {"task_id": "NEX-2", "delta": 5, "actual": 5, "status": "Done"})
        total, tasks = ledger_logged_today("U1", "2026-08-07")
        check("2 task khac nhau -> cong dung 8", total, 8)
        check("2 task khac nhau -> du 2 task_id", sorted(tasks), ["NEX-1", "NEX-2"])

        # Cung 1 task, log 2 lan lien tuc KHONG reset: 4h roi len 8h -> dung la 8h
        # (khong phai 4+8=12), vi lay actual dau/cuoi chu khong cong delta tho.
        write_ledger("U2", "2026-08-07", {"task_id": "NEX-3", "delta": 4, "actual": 4, "status": "In progress"})
        write_ledger("U2", "2026-08-07", {"task_id": "NEX-3", "delta": 4, "actual": 8, "status": "Done"})
        total2, _ = ledger_logged_today("U2", "2026-08-07")
        check("1 task log 2 lan lien tuc, khong reset -> 8", total2, 8)

        # Dung bug that: log 8h (actual=8), AI DO RESET sheet ve 0 ngoai script,
        # roi log lai 4h (actual=4, delta tinh tu 0 la dung 4 tai thoi diem do).
        # Cong tho delta se ra 8+4=12 (SAI). Phai ra 4 (dung, khop sheet that).
        write_ledger("U3", "2026-08-07", {"task_id": "NEX-55", "delta": 8, "actual": 8, "status": "In progress"})
        write_ledger("U3", "2026-08-07", {"task_id": "NEX-55", "delta": 4, "actual": 4, "status": "In progress"})
        total3, tasks3 = ledger_logged_today("U3", "2026-08-07")
        check("reset giua chung -> lay actual cuoi (4), KHONG cong tho (12)", total3, 4)
        check("reset giua chung -> van chi 1 task_id", tasks3, ["NEX-55"])

        # Entry cu thieu field 'actual' (ghi truoc khi field nay ton tai) ->
        # fallback cong tho delta nhu cu, khong duoc crash.
        write_ledger("U4", "2026-08-07", {"task_id": "OLD-1", "delta": 3, "status": "Done"})
        total4, _ = ledger_logged_today("U4", "2026-08-07")
        check("entry cu thieu 'actual' -> fallback cong tho", total4, 3)

        # Reset xay ra SAU lan log cuoi cung trong ledger (khac voi case tren,
        # noi reset nam GIUA 2 lan log da ghi) -> ledger khong the tu biet vi
        # khong co lan log nao sau do de "thay". Ben goi phai tu doi chieu
        # bang cach truyen current_task_id + current_task_live_before (doc
        # song tu sheet ngay truoc lan ghi nay) -> lech voi 'actual' cuoi cung
        # trong ledger thi bo hoan toan lich su cua RIENG task do.
        write_ledger("U5", "2026-08-07", {"task_id": "NEX-55", "delta": 8, "actual": 8, "status": "Done"})
        write_ledger("U5", "2026-08-07", {"task_id": "NEX-60", "delta": 3, "actual": 3, "status": "In progress"})
        # Sheet thuc te NEX-55 da bi reset thang ve rong (None) SAU khi ledger
        # ghi actual=8 o tren -> live_before = None luc goi lan nay.
        total5, tasks5 = ledger_logged_today(
            "U5", "2026-08-07", current_task_id="NEX-55", current_task_live_before=None)
        check("reset SAU lan log cuoi -> bo lich su NEX-55, chi con NEX-60 (3)", total5, 3)
        check("reset SAU lan log cuoi -> van liet ke du 2 task_id", sorted(tasks5), ["NEX-55", "NEX-60"])

        # Doi chieu khop (khong bi reset sau do) -> giu nguyen lich su nhu cu.
        total6, _ = ledger_logged_today(
            "U5", "2026-08-07", current_task_id="NEX-55", current_task_live_before=8)
        check("doi chieu khop (khong reset) -> giu nguyen 8+3=11", total6, 11)


# ------------------------------------------------------- cột tab Risk management
def test_risk_columns(ns):
    """PM chèn cột 'Task' vào giữa -> ghi theo vị trí là lệch hết sang phải."""
    print("resolve_risk_columns")
    norm, resolve = ns["norm"], ns["resolve_risk_columns"]

    # Layout MỚI (có cột Task ở F), đúng như sheet hiện tại.
    new = [norm(c) for c in ["ID", "Date Detected", "Description", "Priority",
                             "Related Assignee", "Task", "Next Action", "Status", "Notes"]]
    col = resolve(new)
    check("layout moi: next action -> G", col["next"], 6)
    check("layout moi: status -> H", col["status"], 7)
    check("layout moi: notes -> I", col["notes"], 8)
    check("layout moi: task -> F", col["task"], 5)

    # Layout CŨ (không có cột Task) vẫn phải chạy đúng, không lệch.
    old = [norm(c) for c in ["ID", "Date Detected", "Description", "Priority",
                             "Related Assignee", "Next Action", "Status", "Notes"]]
    col = resolve(old)
    check("layout cu: next action -> F", col["next"], 5)
    check("layout cu: status -> G", col["status"], 6)
    check("layout cu: khong co cot task", "task" in col, False)

    # 'Task' KHÔNG được cướp chỗ của 'Related Assignee' và ngược lại.
    check("layout moi: assignee -> E", resolve(new)["assignee"], 4)

    # Chèn thêm cột lạ ở đầu: mọi thứ dịch phải, vẫn phải khớp đúng.
    shifted = [norm("STT")] + new
    col = resolve(shifted)
    check("chen cot la o dau: status dich phai", col["status"], 8)


def main():
    ns = load_pure_functions()
    test_columns(ns)
    test_numbers(ns)
    test_risk_columns(ns)
    test_ledger(ns)
    test_ledger_reset_drift(ns)
    print()
    if FAILED:
        print("FAIL: %d case hong -> %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("tat ca pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
