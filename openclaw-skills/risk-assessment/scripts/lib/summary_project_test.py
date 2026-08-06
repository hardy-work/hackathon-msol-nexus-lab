import unittest

from summary_project import find_sprint_end

HEADER = ["", "No", "Sprint", "Start date", "End date", "Re-est (h)", "Remaining Time (h)", "Progress", "Status"]


class FindSprintEndTest(unittest.TestCase):
    def test_parses_real_row(self):
        rows = [
            ["PROJECT SUMMARY"],
            [],
            HEADER,
            ["", "1", "Sprint 1", "2026/07/27（Thứ 2）", "2026/08/07（Thứ 6）", "292,00", "196,00", "32,88%", "In progress"],
        ]
        self.assertEqual(find_sprint_end(rows, "Sprint 1"), "2026-08-07")

    def test_sunday_end_date_rolls_back_to_friday(self):
        rows = [
            HEADER,
            ["", "1", "Sprint 1", "2026/07/27（Thứ 2）", "2026/08/09（Chủ nhật）", "292,00", "196,00", "32,88%", "In progress"],
        ]
        self.assertEqual(find_sprint_end(rows, "Sprint 1"), "2026-08-07")

    def test_sprint_not_found_returns_none(self):
        rows = [
            HEADER,
            ["", "1", "Sprint 1", "2026/07/27（Thứ 2）", "2026/08/07（Thứ 6）", "292,00", "196,00", "32,88%", "In progress"],
        ]
        self.assertIsNone(find_sprint_end(rows, "Sprint 2"))

    def test_no_header_returns_none(self):
        self.assertIsNone(find_sprint_end([["a", "b"]], "Sprint 1"))


if __name__ == "__main__":
    unittest.main()
