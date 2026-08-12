import unittest

from dashboard_rows import build_dashboard_rows

SPRINT = {"sprint": "Sprint 1", "status": "In progress", "remainingHours": 152.0, "progressPct": 68.85}
RISK_TALLY = {"open": 2, "inProgress": 0, "closed": 3}
ISSUE_TALLY = {"open": 0, "inProgress": 0, "closed": 0}
TOP_RISKS = [{"id": "R-01", "relatedAssigneeTask": "HoàngMV / NEX-40", "description": "vượt 4h"}]


class BuildDashboardRowsTest(unittest.TestCase):
    def test_includes_title_and_timestamp(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS, "2026-08-11 10:00")
        self.assertEqual(rows[0], ["NexusBot Dashboard"])
        self.assertEqual(rows[1], ["Cập nhật lúc: 2026-08-11 10:00"])

    def test_includes_sprint_fields(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS, "now")
        self.assertIn(["Sprint hiện tại", "Sprint 1"], rows)
        self.assertIn(["Tiến độ (%)", 68.85], rows)
        self.assertIn(["Còn lại (giờ)", 152.0], rows)
        self.assertIn(["Trạng thái sprint", "In progress"], rows)

    def test_includes_risk_issue_tally(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS, "now")
        self.assertIn(["Risk chưa xử lý", 2], rows)
        self.assertIn(["Issue chưa xử lý", 0], rows)

    def test_includes_top_risk_rows(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS, "now")
        self.assertIn(["R-01", "HoàngMV / NEX-40", "vượt 4h"], rows)

    def test_no_sprint_fallback(self):
        rows = build_dashboard_rows(None, RISK_TALLY, ISSUE_TALLY, [], "now")
        self.assertIn(["Sprint hiện tại", "Không có sprint nào đang In progress"], rows)

    def test_no_top_risks_placeholder(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, [], "now")
        self.assertIn(["(không có)", "", ""], rows)

    def test_all_rows_are_lists(self):
        rows = build_dashboard_rows(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS, "now")
        for row in rows:
            self.assertIsInstance(row, list)


if __name__ == "__main__":
    unittest.main()
