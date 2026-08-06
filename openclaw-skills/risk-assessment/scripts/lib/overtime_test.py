import unittest

from overtime import build_ot_by_assignee_code, parse_overtime

# Dữ liệu mẫu THẬT đọc từ tab "Overtime" (session 2026-08-05).
REAL_SAMPLE_ROWS = [
    ["#", "Member", "Slack ID", "Slack name", "Role", "July", "", "", "", "", "August"],
    ["", "", "", "", "", "27", "28", "29", "30", "31", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
    ["1", "Bùi Hồng Sơn", "U09QRTUHX24", "Bùi Hồng Sơn", "BE"],
    ["2", "Nguyễn Thành Đô", "U0APQSSGKTM", "Nguyễn Thành Đô", "BE"],
    ["3", "Văn Ngọc Long", "U09PXK5SCP4", "Văn Ngọc Long", "BE"],
    ["4", "Nguyễn Văn Vinh", "U0A2PDFHHL7", "Nguyễn Văn Vinh", "FE", "", "", "", "", "", "", "", "4"],
    ["5", "Mai Việt Hoàng", "U08FT511ZEF", "Mai Việt Hoàng", "FE"],
    ["6", "Đỗ Trung Kiên", "U08GQJRUT3Q", "Đỗ Trung Kiên", "FE"],
]

RESOURCE_PLAN_PEOPLE = [
    {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "slackId": "U09QRTUHX24", "dailyHours": {}},
    {"member": "Nguyễn Văn Vinh", "assigneeCode": "VinhNV", "slackId": "U0A2PDFHHL7", "dailyHours": {}},
]


class ParseOvertimeTest(unittest.TestCase):
    def test_finds_all_six_people(self):
        result = parse_overtime(REAL_SAMPLE_ROWS, year=2026)
        self.assertEqual(len(result), 6)

    def test_reads_slack_id(self):
        result = parse_overtime(REAL_SAMPLE_ROWS, year=2026)
        vinh = next(p for p in result if p["member"] == "Nguyễn Văn Vinh")
        self.assertEqual(vinh["slackId"], "U0A2PDFHHL7")

    def test_builds_correct_iso_date_for_ot_hours(self):
        result = parse_overtime(REAL_SAMPLE_ROWS, year=2026)
        vinh = next(p for p in result if p["member"] == "Nguyễn Văn Vinh")
        self.assertEqual(vinh["dailyHours"]["2026-08-03"], 4.0)

    def test_no_ot_days_are_none(self):
        result = parse_overtime(REAL_SAMPLE_ROWS, year=2026)
        son = next(p for p in result if p["member"] == "Bùi Hồng Sơn")
        self.assertIsNone(son["dailyHours"]["2026-08-03"])
        self.assertIsNone(son["dailyHours"]["2026-07-27"])


class BuildOtByAssigneeCodeTest(unittest.TestCase):
    def test_joins_via_slack_id_to_assignee_code(self):
        overtime_people = parse_overtime(REAL_SAMPLE_ROWS, year=2026)
        result = build_ot_by_assignee_code(overtime_people, RESOURCE_PLAN_PEOPLE)
        self.assertEqual(result["VinhNV"]["2026-08-03"], 4.0)

    def test_person_without_matching_slack_id_excluded(self):
        overtime_people = [{"member": "Người lạ", "slackId": "U_UNKNOWN", "dailyHours": {"2026-08-03": 5.0}}]
        result = build_ot_by_assignee_code(overtime_people, RESOURCE_PLAN_PEOPLE)
        self.assertEqual(result, {})

    def test_person_missing_slack_id_in_overtime_excluded(self):
        overtime_people = [{"member": "Ai đó", "slackId": None, "dailyHours": {"2026-08-03": 5.0}}]
        result = build_ot_by_assignee_code(overtime_people, RESOURCE_PLAN_PEOPLE)
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
