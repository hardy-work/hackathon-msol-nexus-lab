import unittest

from parse import find_current_sprint_row, parse_number, read_status_tab


class ParseNumberTest(unittest.TestCase):
    def test_comma_decimal(self):
        self.assertEqual(parse_number("344,00"), 344.0)

    def test_percent_suffix(self):
        self.assertEqual(parse_number("68,85%"), 68.85)

    def test_none_for_empty(self):
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number(None))

    def test_none_for_non_numeric(self):
        self.assertIsNone(parse_number("chưa rõ"))


SUMMARY_ROWS = [
    ["PROJECT SUMMARY"],
    [],
    ["", "No", "Sprint", "Start date", "End date", "Re-est (h)", "Remaining Time (h)", "Progress", "Status", "Link Weekly  Report", "Note"],
    ["", "1", "Sprint 1", "2026/08/03（Thứ 2）", "2026/08/14（Thứ 6）", "344,00", "152,00", "68,85%", "In progress"],
    ["", "2", "Sprint 2", "2026/08/17（Thứ 2）", "2026/08/28（Thứ 6）", "320,00", "320,00", "0,00%", "Not started"],
]


class FindCurrentSprintRowTest(unittest.TestCase):
    def test_finds_in_progress_sprint(self):
        result = find_current_sprint_row(SUMMARY_ROWS)
        self.assertIsNotNone(result)
        self.assertEqual(result["sprint"], "Sprint 1")
        self.assertEqual(result["status"], "In progress")
        self.assertEqual(result["remainingHours"], 152.0)
        self.assertEqual(result["progressPct"], 68.85)

    def test_none_when_no_in_progress_sprint(self):
        rows = [SUMMARY_ROWS[2], SUMMARY_ROWS[4]]  # chỉ còn Sprint 2 (Not started)
        self.assertIsNone(find_current_sprint_row(rows))

    def test_none_when_header_missing(self):
        self.assertIsNone(find_current_sprint_row([["x", "y"]]))


RISK_ROWS_SEPARATE_COLS = [
    ["ID", "Date Detected", "Description", "Priority", "Related Assignee", "Related Task", "Next Action", "Status"],
    ["R-01", "11-8-2026", "HoàngMV vượt 4h ở task NEX-40", "High", "HoàngMV", "NEX-40", "PM review giờ vượt", "Open"],
    ["R-02", "11-8-2026", "LongVN vượt 4h ở task NEX-41", "High", "LongVN", "NEX-41", "PM review giờ vượt", "In progress"],
    ["R-03", "10-8-2026", "Đã xử lý xong", "Medium", "SonBH", "NEX-30", "", "Done"],
]

ISSUE_ROWS_COMBINED_COL = [
    ["ID", "Date Detected", "Description", "Priority", "Related Assignee/Task", "Next Action", "Status"],
    ["I-01", "9-8-2026", "Thiếu API key staging", "Medium", "VinhNV / NEX-20", "Xin key mới", "Pending"],
]


class ReadStatusTabTest(unittest.TestCase):
    def test_reads_separate_assignee_task_columns(self):
        items = read_status_tab(RISK_ROWS_SEPARATE_COLS)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["id"], "R-01")
        self.assertEqual(items[0]["priority"], "High")
        self.assertEqual(items[0]["status"], "Open")
        self.assertEqual(items[0]["relatedAssigneeTask"], "HoàngMV / NEX-40")

    def test_reads_combined_column(self):
        items = read_status_tab(ISSUE_ROWS_COMBINED_COL)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["relatedAssigneeTask"], "VinhNV / NEX-20")

    def test_empty_rows(self):
        self.assertEqual(read_status_tab([]), [])

    def test_skips_rows_without_id(self):
        rows = [RISK_ROWS_SEPARATE_COLS[0], ["", "11-8-2026", "no id row", "High", "X", "Y", "Z", "Open"]]
        self.assertEqual(read_status_tab(rows), [])


if __name__ == "__main__":
    unittest.main()
