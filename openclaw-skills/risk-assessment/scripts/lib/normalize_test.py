import unittest

from normalize import normalize_sprint_rows, parse_date, parse_hours

COLUMNS = {
    "Category Milestone": "A",
    "Task": "B",
    "TaskID": "C",
    "Sub-task": "D",
    "Role": "E",
    "Assignee": "F",
    "Priority": "G",
    "Estimate(h)": "H",
    "Plan Start": "I",
    "Plan End": "J",
    "Re-estimate(h)": "K",
    "Actual Effort(h)": "N",
    "Remaining(h)": "Q",
    "Status": "R",
}

STATUS_DONE = ["Done"]


class ParseDateTest(unittest.TestCase):
    def test_d_m_yyyy_no_zero_pad(self):
        self.assertEqual(parse_date("27-7-2026"), "2026-07-27")

    def test_dd_m_yyyy(self):
        self.assertEqual(parse_date("03-8-2026"), "2026-08-03")

    def test_none_for_empty(self):
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date(None))

    def test_none_for_wrong_format(self):
        self.assertIsNone(parse_date("2026-07-27"))


class ParseHoursTest(unittest.TestCase):
    def test_plain_int_string(self):
        self.assertEqual(parse_hours("8"), 8.0)

    def test_comma_decimal(self):
        self.assertEqual(parse_hours("480,0"), 480.0)

    def test_percent_suffix(self):
        self.assertEqual(parse_hours("32,88%"), 32.88)

    def test_none_for_empty(self):
        self.assertIsNone(parse_hours(""))
        self.assertIsNone(parse_hours(None))


class NormalizeSprintRowsTest(unittest.TestCase):
    def test_real_sample_row_maps_all_fields(self):
        rows = [
            ["Authentication", "Login", "AU-1", "API Login & Token Generation (JWT)", "BE", "SơnBH", "Highest", "8", "27-7-2026", "27-7-2026", "8", "27-7-2026", "27-7-2026", "8", "100%", "", "0,0", "Done"],
        ]
        tasks = normalize_sprint_rows(rows, COLUMNS, "Sprint 1", STATUS_DONE, "Sprint 1", start_row=5)
        self.assertEqual(len(tasks), 1)
        t = tasks[0]
        self.assertEqual(t["detectedFrom"], "AU-1")
        self.assertEqual(t["id"], "AU-1")
        self.assertEqual(t["title"], "API Login & Token Generation (JWT)")
        self.assertEqual(t["taskName"], "Login")
        self.assertEqual(t["category"], "Authentication")
        self.assertEqual(t["role"], "BE")
        self.assertEqual(t["assignee"], "SơnBH")
        self.assertEqual(t["priority"], "Highest")
        self.assertEqual(t["estimateHours"], 8.0)  # Re-estimate(h) ưu tiên, ở đây trùng Estimate
        self.assertEqual(t["actualHours"], 8.0)
        self.assertEqual(t["remainingHours"], 0.0)
        self.assertEqual(t["planStart"], "2026-07-27")
        self.assertEqual(t["planEnd"], "2026-07-27")
        self.assertEqual(t["status"], "Done")
        self.assertTrue(t["isDone"])

    def test_skips_blank_and_subtotal_rows(self):
        rows = [
            [],  # dòng trống
            ["", "", "", "", "", "", "", "480,0", "27-7-2026", "07-8-2026"],  # subtotal, không TaskID/Sub-task
            ["Authentication", "Login", "AU-1", "API Login", "BE", "SơnBH", "Highest", "8", "27-7-2026", "27-7-2026", "8", "", "", "", "", "", "0,0", "Open"],
        ]
        tasks = normalize_sprint_rows(rows, COLUMNS, "Sprint 1", STATUS_DONE, "Sprint 1", start_row=4)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["detectedFrom"], "AU-1")

    def test_forward_fills_category_across_group(self):
        rows = [
            ["Authentication", "Login", "AU-1", "API Login", "BE", "SơnBH", "Highest", "8", "27-7-2026", "27-7-2026"],
            ["", "", "AU-2", "API Logout", "BE", "SơnBH", "High", "8", "28-7-2026", "28-7-2026"],
        ]
        tasks = normalize_sprint_rows(rows, COLUMNS, "Sprint 1", STATUS_DONE, "Sprint 1", start_row=5)
        self.assertEqual(tasks[1]["category"], "Authentication")

    def test_fallback_detected_from_when_no_task_id(self):
        columns_no_id = dict(COLUMNS)
        del columns_no_id["TaskID"]
        rows = [
            ["Authentication", "Login", "IGNORED", "API Login", "BE", "SơnBH", "Highest", "8", "27-7-2026", "27-7-2026"],
        ]
        tasks = normalize_sprint_rows(rows, columns_no_id, "Sprint 1", STATUS_DONE, "Sprint 1", start_row=5)
        self.assertEqual(tasks[0]["detectedFrom"], "Sprint 1, row 5")

    def test_status_defaults_to_open_when_blank(self):
        rows = [
            ["Authentication", "Login", "AU-1", "API Login", "BE", "SơnBH", "Highest", "8", "27-7-2026", "27-7-2026"],
        ]
        tasks = normalize_sprint_rows(rows, COLUMNS, "Sprint 1", STATUS_DONE, "Sprint 1", start_row=5)
        self.assertEqual(tasks[0]["status"], "Open")
        self.assertFalse(tasks[0]["isDone"])


if __name__ == "__main__":
    unittest.main()
