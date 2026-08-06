import json
import unittest

from draft import build_draft


def make_passive(**overrides):
    item = {
        "layer": "Task",
        "rule": "T1",
        "description": "Sub-task X trễ",
        "detectedFrom": "X-1",
        "relatedAssigneeTask": "NguoiA / X-1",
        "nextAction": "Do Y",
        "nextActionOptions": ["Do Y"],
        "score": 3,
    }
    item.update(overrides)
    return item


def make_health(**overrides):
    health = {"sprintName": "Sprint 1", "totalBacklog": 100.0, "totalCapacity": 120.0, "onTrack": True}
    health.update(overrides)
    return health


class BuildDraftTest(unittest.TestCase):
    def test_empty_everything_shows_all_sections_with_placeholders(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("Chưa xử lý", out)
        self.assertIn("Đang xử lý", out)
        self.assertIn("Đánh giá", out)
        self.assertIn("Chưa phát hiện dấu hiệu nào", out)

    def test_header_includes_bold_project_title_and_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("**Test Nexus** — 2026-08-04", out)

    def test_no_sprint_health_omits_sprint_line_but_keeps_section(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertNotIn("KHÔNG kịp tiến độ", out)
        self.assertNotIn("Đang bám sát kế hoạch", out)

    def test_sprint_health_on_track_shows_surplus_and_maintain_message(self):
        health = make_health(onTrack=True, totalBacklog=100.0, totalCapacity=120.0)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=health,
        )
        self.assertIn("Sprint 1: **Đang bám sát kế hoạch**", out)
        self.assertIn("dư 20.0h", out)
        self.assertIn("Duy trì nhịp độ hiện tại", out)

    def test_sprint_health_off_track_shows_deficit_and_recommendation(self):
        health = make_health(onTrack=False, totalBacklog=198.0, totalCapacity=88.0)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=health,
        )
        self.assertIn("Sprint 1: **KHÔNG kịp tiến độ**", out)
        self.assertIn("thiếu 110.0h", out)
        self.assertIn("Đề xuất: rà soát scope", out)

    def test_p4_items_shown_as_person_deficit_list(self):
        items = [
            make_passive(rule="P4", detectedFrom="SơnBH, sprint Sprint 1", relatedAssigneeTask="SơnBH",
                         description="SơnBH, sprint Sprint 1: tồn đọng 32.0h ... (thiếu 8.0h)."),
            make_passive(rule="P4", detectedFrom="ĐôNT, sprint Sprint 1", relatedAssigneeTask="ĐôNT",
                         description="ĐôNT, sprint Sprint 1: tồn đọng 32.0h ... (thiếu 16.0h)."),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("Người có nguy cơ không kịp việc của mình:", out)
        self.assertIn("**SơnBH** (thiếu 8.0h)", out)
        self.assertIn("**ĐôNT** (thiếu 16.0h)", out)

    def test_m2_items_shown_as_category_lag_list(self):
        items = [
            make_passive(rule="M2", detectedFrom="Product Catalog & Search", relatedAssigneeTask="Product Catalog & Search",
                         description='Category "Product Catalog & Search" đang tụt hậu tiến độ so với deadline riêng: đã trôi qua 83% thời gian nhưng chỉ 42% sub-task hoàn thành.'),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("Category có nguy cơ không kịp deadline riêng:", out)
        self.assertIn("**Product Catalog & Search** (83% thời gian/42% xong)", out)

    def test_s1_item_shown_verbatim(self):
        items = [make_passive(rule="S1", description="Velocity giảm: Sprint 2 hoàn thành 40% so với Sprint 1 là 80%.")]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("Velocity giảm: Sprint 2 hoàn thành 40% so với Sprint 1 là 80%.", out)

    def test_non_assessment_rules_excluded_from_danh_gia_counted_in_detail_note(self):
        items = [make_passive(rule="T4", description="Sub-task PCS-9 bị nghi block")]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            sprint_health=None,
        )
        narrative = out.split("```json")[0]
        self.assertNotIn("Sub-task PCS-9 bị nghi block", narrative)
        self.assertIn("Ngoài ra còn 1 risk + 0 issue khác được phát hiện", narrative)
        self.assertIn("hỏi mình nếu muốn biết chi tiết", narrative)

    def test_no_detail_note_when_nothing_outside_assessment(self):
        items = [make_passive(rule="P4", description="X thiếu 8.0h")]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            sprint_health=None,
        )
        self.assertNotIn("Ngoài ra còn", out)

    def test_existing_open_lists_items_with_id(self):
        existing = [{"id": "R-000", "description": "SơnBH xin nghỉ", "nextAction": "Reschedule", "status": "Open"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing, existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("R-000", out)
        self.assertIn("SơnBH xin nghỉ", out)

    def test_existing_open_missing_next_action_flagged(self):
        existing = [{"id": "R-000", "description": "SơnBH xin nghỉ", "nextAction": "", "status": "Pending"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing, existing_in_progress=[], passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("chưa có Next Action", out)

    def test_existing_in_progress_shows_idle_days_unambiguously(self):
        existing = [{"id": "R-001", "description": "Test follow up", "nextAction": "x", "status": "In progress", "idleDays": 9}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=existing, passive_risks=[], passive_issues=[],
            sprint_health=None,
        )
        self.assertIn("(đã xử lý được 9 ngày, chưa xong)", out)

    def test_json_block_embeds_expected_fields(self):
        existing_open = [{"id": "R-000", "description": "x", "status": "Open"}]
        existing_ip = [{"id": "R-001", "description": "y", "status": "In progress", "idleDays": 3}]
        health = make_health()
        risks = [make_passive(rule="P4")]
        issues = [make_passive(rule="T1")]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing_open, existing_in_progress=existing_ip, passive_risks=risks, passive_issues=issues,
            sprint_health=health,
        )
        json_text = out.split("```json\n")[1].split("\n```")[0]
        parsed = json.loads(json_text)
        self.assertEqual(parsed["existingOpen"], existing_open)
        self.assertEqual(parsed["existingInProgress"], existing_ip)
        self.assertEqual(parsed["passiveRisks"], risks)
        self.assertEqual(parsed["passiveIssues"], issues)
        self.assertEqual(parsed["sprintHealth"], health)
        self.assertNotIn("resolvedRisks", parsed)
        self.assertNotIn("activeRisks", parsed)


if __name__ == "__main__":
    unittest.main()
