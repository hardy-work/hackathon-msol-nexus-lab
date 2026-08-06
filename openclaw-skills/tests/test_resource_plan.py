#!/usr/bin/env python3
"""Test offline cho reminder-followup/scripts/resource-plan-members.sh: dò cột
ngày của hôm nay, đọc công đăng ký, và chia nhóm thiếu giờ.

Vì sao cần: dò cột ngày là logic "sai âm thầm" điển hình — dò trượt thì script
vẫn exit 0, vẫn in ra danh sách, chỉ là nhắc nhầm người nghỉ hoặc bỏ sót người
đi làm. Không ai biết cho tới khi có người kêu.

Chạy hoàn toàn offline: bơm payload Sheets API giả qua MOCK_SHEET_RESPONSE_FILE,
ghim "hôm nay" bằng LOGTIME_TODAY, và trỏ OPENCLAW_STATE_DIR vào chỗ không tồn
tại để bỏ qua bước đối chiếu users.info (cần mạng).

    python3 openclaw-skills/tests/test_resource_plan.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "reminder-followup" / "scripts" / "resource-plan-members.sh"

FAILED = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s\n       got  = %r\n       want = %r" % (name, got, want))
        FAILED.append(name)


# Đúng hình dạng thật của khối "Thời gian làm việc mỗi ngày" trong tab
# "Resource plan": hàng tên tháng, hàng dưới là số ngày, ô giá trị là SỐ GIỜ
# (8 = đủ công, 4 = nghỉ nửa buổi, trống = T7/CN).
def sheet(rows):
    return {"values": rows}


BASE = [
    ["Thời gian làm việc mỗi ngày"],
    ["#", "Member", "Slack ID", "Slack name", "Role", "July", "", "August"],
    ["", "", "", "", "", "30", "31", "1", "2", "3", "4", "5", "6"],
    ["1", "An", "U0000000001", "an", "BE", "8", "8", "", "", "8", "8", "8", "4"],
    ["2", "Bình", "U0000000002", "binh", "FE", "8", "8", "", "", "8", "8", "0", "8"],
    ["3", "Chi", "U0000000003", "chi", "FE", "8", "8", "", "", "8", "8", "8", "8"],
    ["4", "Dũng", "", "dung", "BE", "8", "8", "", "", "8", "8", "8", "8"],
]


def run(mode, today, ledger=None, mock=None, tol=None):
    with tempfile.TemporaryDirectory() as d:
        mockfile = os.path.join(d, "resp.json")
        pathlib.Path(mockfile).write_text(
            json.dumps(sheet(mock if mock is not None else BASE)), encoding="utf-8")
        env = dict(os.environ)
        env.update({
            "MOCK_SHEET_RESPONSE_FILE": mockfile,
            "LOGTIME_TODAY": today,
            "LOGTIME_SHEET_LINK": "https://docs.google.com/spreadsheets/d/FAKEID/edit",
            "GOOGLE_SHEETS_API_KEY": "test-key",
            "LOGTIME_SHEET_TAB": "Resource plan",
            # Không có token -> bỏ qua users.info, khỏi cần mạng.
            "OPENCLAW_STATE_DIR": os.path.join(d, "no-such-state"),
            "SLACK_BOT_TOKEN": "",
            "EFFORT_LEDGER_FILE": ledger or os.path.join(d, "empty-ledger.json"),
        })
        if tol is not None:
            env["EFFORT_TOLERANCE_H"] = str(tol)
        args = ["bash", str(SCRIPT)] + ([mode] if mode else [])
        p = subprocess.run(args, capture_output=True, text=True, env=env)
        return p.returncode, p.stdout


def test_day_column():
    print("do cot ngay cua hom nay")
    # 05-08 (thu Tu): cot ngay "5" -> An 8h, Binh 0 (nghi ca ngay), Chi 8h.
    code, out = run(None, "2026-08-05")
    d = json.loads(out)
    check("exit 0", code, 0)
    check("tim thay cot ngay", d["found_day_column"], True)
    check("nguoi phai report", [p["name"] for p in d["people"]], ["An", "Chi"])
    check("nguoi nghi", [p["name"] for p in d["off"]], ["Bình"])
    check("An dang ky 8h", d["people"][0]["hours"], 8.0)
    check("thieu Slack ID van bao ten", d["no_id"], ["Dũng"])

    # 06-08: An nghi NUA BUOI -> van phai report, nhung moc chi con 4h.
    d = json.loads(run(None, "2026-08-06")[1])
    an = [p for p in d["people"] if p["name"] == "An"][0]
    check("nghi nua buoi van phai report", an["name"], "An")
    check("nghi nua buoi -> hours = 4", an["hours"], 4.0)

    # 01-08 la thu Bay: ca doi trong o -> exit 6, KHONG phai loi doc sheet.
    code, _ = run(None, "2026-08-01")
    check("T7 ca doi nghi -> exit 6", code, 6)

    # Thang khac cung so ngay: 30-07 phai lay cot July/30, khong lay August.
    d = json.loads(run(None, "2026-07-30")[1])
    check("30-07 lay dung cot July", d["found_day_column"], True)
    check("30-07 ca 3 nguoi di lam", len(d["people"]), 3)

    # Ngay chua co cot trong sheet -> khong doan bua, coi nhu di lam het.
    d = json.loads(run(None, "2026-09-15")[1])
    check("chua co cot cho hom nay", d["found_day_column"], False)
    check("chua co cot -> hours = None", d["people"][0]["hours"], None)
    check("chua co cot -> van nhac ca 3", len(d["people"]), 3)


def ledger_file(d, entries):
    p = os.path.join(d, "ledger.json")
    pathlib.Path(p).write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return p


def test_effort_check():
    print("chia nhom thieu gio")
    day = "2026-08-05"

    with tempfile.TemporaryDirectory() as d:
        # An:  3h Done + 5h Done          = 8/8  -> du gio (case "xong som roi
        #      nhay task khac", tuyet doi khong duoc canh bao gi)
        # Chi: 4h, task VAN In progress   = 4/8  -> hoi ly do + ghi Risk
        led = ledger_file(d, [
            {"date": day, "slack_id": "U0000000001", "task_id": "NEX-1", "delta": 3, "status": "Done"},
            {"date": day, "slack_id": "U0000000001", "task_id": "NEX-2", "delta": 5, "status": "Done"},
            {"date": day, "slack_id": "U0000000003", "task_id": "NEX-9", "delta": 4, "status": "In progress"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("est 8 lam 3 roi nhay task khac -> du gio", r["du_gio"], ["U0000000001"])
        check("con In progress -> nhom hoi ly do", [x["id"] for x in r["thieu_gio_con_dang_lam"]], ["U0000000003"])
        check("thieu 4h", r["thieu_gio_con_dang_lam"][0]["missing"], 4.0)
        check("keo theo id task dang lam", r["thieu_gio_con_dang_lam"][0]["in_progress"], ["NEX-9"])
        check("nhom Done rong", r["thieu_gio_da_xong_het"], [])

    with tempfile.TemporaryDirectory() as d:
        # Chi: 5h nhung DA DONE HET -> khong phai risk, chi hoi nhe.
        led = ledger_file(d, [
            {"date": day, "slack_id": "U0000000003", "task_id": "NEX-9", "delta": 5, "status": "Done"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("Done het ma thieu gio -> nhom hoi nhe", [x["id"] for x in r["thieu_gio_da_xong_het"]], ["U0000000003"])
        check("Done het -> KHONG vao nhom risk", r["thieu_gio_con_dang_lam"], [])
        check("khong log gi -> chua_log", r["chua_log"], ["U0000000001"])

    with tempfile.TemporaryDirectory() as d:
        # Status Done viet kieu Viet + emoji van phai tinh la xong.
        led = ledger_file(d, [
            {"date": day, "slack_id": "U0000000003", "task_id": "N1", "delta": 2, "status": "đã hoàn thành"},
            {"date": day, "slack_id": "U0000000003", "task_id": "N2", "delta": 2, "status": "done ✅"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("'đã hoàn thành' / 'done ✅' = Done", [x["id"] for x in r["thieu_gio_da_xong_het"]], ["U0000000003"])

        # ... nhung "hoàn thành 90%" thi KHONG phai Done.
        led = ledger_file(d, [
            {"date": day, "slack_id": "U0000000003", "task_id": "N1", "delta": 4, "status": "hoàn thành 90%"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("'hoàn thành 90%' KHONG phai Done", [x["id"] for x in r["thieu_gio_con_dang_lam"]], ["U0000000003"])

    with tempfile.TemporaryDirectory() as d:
        # Dung sai: thieu 0,5h thi im, dung hoi ai vi 7,5 voi 8.
        led = ledger_file(d, [
            {"date": day, "slack_id": "U0000000003", "task_id": "N1", "delta": 7.5, "status": "In progress"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("thieu 0,5h -> trong dung sai, im", "U0000000003" in r["du_gio"], True)

        # So cai cua HOM KHAC khong duoc tinh vao hom nay.
        led = ledger_file(d, [
            {"date": "2026-08-04", "slack_id": "U0000000003", "task_id": "N1", "delta": 8, "status": "Done"},
        ])
        r = json.loads(run("--effort-check", day, ledger=led)[1])
        check("so cai ngay khac -> khong tinh", r["chua_log"], ["U0000000001", "U0000000003"])

    # So cai chua ton tai -> khong phai loi, moi nguoi vao chua_log.
    r = json.loads(run("--effort-check", day, ledger="/nonexistent/ledger.json")[1])
    check("chua co so cai -> khong crash", sorted(r["chua_log"]), ["U0000000001", "U0000000003"])


def main():
    test_day_column()
    test_effort_check()
    print()
    if FAILED:
        print("FAIL: %d case hong -> %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("tat ca pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
