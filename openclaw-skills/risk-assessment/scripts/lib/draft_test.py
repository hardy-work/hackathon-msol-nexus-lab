import json
import unittest

from draft import build_draft

THRESHOLDS = {"highScoreThreshold": 6}


class BuildDraftTest(unittest.TestCase):
    def test_empty_everything_shows_active_and_passive_sections_with_note(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Rủi ro chủ động", out)
        self.assertIn("Hiện không có rủi ro chủ động nào", out)
        self.assertIn("Rủi ro bị động", out)
        self.assertIn("Hiện không có rủi ro bị động nào", out)

    def test_no_previous_snapshot_hides_resolved_section_entirely(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertNotIn("Đã hết rủi ro", out)

    def test_has_previous_snapshot_but_nothing_resolved_shows_explicit_note_with_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], resolved_risks=[],
            previous_snapshot_date="2026-08-03",
            thresholds=THRESHOLDS,
        )
        self.assertIn("Đã hết rủi ro (so với báo cáo ngày 2026-08-03)", out)
        self.assertIn("Không có rủi ro nào vừa hết so với báo cáo ngày 2026-08-03", out)

    def test_has_previous_snapshot_and_resolved_risks_lists_them_with_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], resolved_risks=["AU-9"],
            previous_snapshot_date="2026-08-03",
            thresholds=THRESHOLDS,
        )
        self.assertIn("Đã hết rủi ro (so với báo cáo ngày 2026-08-03)", out)
        self.assertIn("AU-9", out)

    def test_active_risks_present_lists_them_and_no_placeholder(self):
        active = [{"id": "R-005", "description": "SơnBH báo bị block", "nextAction": "Escalate"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=active, passive_risks=[], passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("R-005", out)
        self.assertNotIn("Hiện không có rủi ro chủ động nào", out)

    def test_urgent_item_marked_inline_within_its_layer(self):
        urgent = {"layer": "Task", "rule": "T1", "description": "Task X trễ", "nextAction": "Do Y", "nextActionOptions": ["Do Y"], "score": 9, "trend": "New"}
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[urgent], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("⚠️ Task X trễ", out)
        self.assertIn("[Task]", out)

    def test_active_risk_missing_next_action_flagged(self):
        active = {"id": "R-000", "description": "SơnBH nghỉ", "nextAction": ""}
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[active], passive_risks=[], passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("chưa có Next Action", out)

    def test_json_block_embeds_all_four_lists(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], resolved_risks=["AU-9"],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        json_text = out.split("```json\n")[1].split("\n```")[0]
        parsed = json.loads(json_text)
        self.assertEqual(parsed["resolvedRisks"], ["AU-9"])

    def test_grouped_by_layer_in_fixed_order_person_before_category(self):
        items = [
            {"layer": "Module", "rule": "M1", "description": "Category bug", "nextAction": "x", "nextActionOptions": ["x"], "score": 3, "trend": "New"},
            {"layer": "Person", "rule": "P2", "description": "Person overload", "nextAction": "x", "nextActionOptions": ["x"], "score": 3, "trend": "New"},
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=items, passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertLess(out.index("Person overload"), out.index("Category bug"))
        self.assertIn("[Category]", out)  # nhãn hiển thị, KHÔNG phải "[Module]"

    def test_next_action_shows_all_options_not_just_first(self):
        item = {
            "layer": "Person", "rule": "P4", "description": "X tồn đọng",
            "nextAction": "OT bù giờ",
            "nextActionOptions": ["OT bù giờ", "San bớt task sang người khác", "Xin dời deadline sprint"],
            "score": 6, "trend": "New",
        }
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[item], passive_issues=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("OT bù giờ / San bớt task sang người khác / Xin dời deadline sprint", out)


if __name__ == "__main__":
    unittest.main()
