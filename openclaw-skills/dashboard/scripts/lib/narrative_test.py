import unittest

from narrative import build_narrative

SPRINT = {"sprint": "Sprint 1", "status": "In progress", "remainingHours": 152.0, "progressPct": 68.85}
RISK_TALLY = {"open": 2, "inProgress": 1, "closed": 3}
ISSUE_TALLY = {"open": 1, "inProgress": 0, "closed": 0}
TOP_RISKS = [{"id": "R-01", "relatedAssigneeTask": "HoàngMV / NEX-40", "description": "vượt 4h"}]


class BuildNarrativeTest(unittest.TestCase):
    def test_includes_bold_sprint_values(self):
        text = build_narrative(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS)
        self.assertIn("**Sprint 1**", text)
        self.assertIn("**68,85%**", text)
        self.assertIn("**152h**", text)
        self.assertIn("**In progress**", text)

    def test_includes_risk_and_issue_tally(self):
        text = build_narrative(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS)
        self.assertIn("**2** chưa xử lý, **1** đang xử lý", text)
        self.assertIn("**1** chưa xử lý, **0** đang xử lý", text)

    def test_lists_top_risks(self):
        text = build_narrative(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS)
        self.assertIn("**R-01**", text)
        self.assertIn("HoàngMV / NEX-40", text)

    def test_no_top_risks_message(self):
        text = build_narrative(SPRINT, RISK_TALLY, ISSUE_TALLY, [])
        self.assertIn("Không có risk ưu tiên cao nào đang mở.", text)

    def test_no_sprint_message(self):
        text = build_narrative(None, RISK_TALLY, ISSUE_TALLY, [])
        self.assertIn("Không tìm thấy sprint nào đang **In progress**", text)

    def test_no_emoji(self):
        text = build_narrative(SPRINT, RISK_TALLY, ISSUE_TALLY, TOP_RISKS)
        for ch in text:
            self.assertLess(ord(ch), 0x2190, f"unexpected symbol/emoji char: {ch!r}")


if __name__ == "__main__":
    unittest.main()
