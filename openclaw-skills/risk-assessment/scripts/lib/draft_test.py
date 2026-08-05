import json
import unittest

from draft import build_draft

THRESHOLDS = {"highScoreThreshold": 6, "inProgressReminderDays": 1}


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
        "trend": "New",
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
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Chưa xử lý", out)
        self.assertIn("Đang xử lý", out)
        self.assertIn("Rủi ro mới phát hiện", out)
        self.assertIn("Hiện không có rủi ro/issue mới nào", out)

    def test_header_includes_bold_project_title_and_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("**Test Nexus** — 2026-08-04", out)

    def test_no_sprint_health_hides_section(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertNotIn("Sức khỏe", out)

    def test_sprint_health_on_track_shows_surplus_and_maintain_message(self):
        health = make_health(onTrack=True, totalBacklog=100.0, totalCapacity=120.0)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=health,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Sức khỏe Sprint 1", out)
        self.assertIn("Đang bám sát kế hoạch", out)
        self.assertIn("dư 20.0h", out)
        self.assertIn("Duy trì nhịp độ hiện tại", out)

    def test_sprint_health_off_track_shows_deficit_and_action_options(self):
        health = make_health(onTrack=False, totalBacklog=198.0, totalCapacity=88.0)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=health,
            thresholds=THRESHOLDS,
        )
        self.assertIn("KHÔNG kịp tiến độ", out)
        self.assertIn("thiếu 110.0h", out)
        self.assertIn("cắt bớt task ưu tiên thấp", out)

    def test_existing_open_lists_items_with_id(self):
        existing = [{"id": "R-000", "description": "SơnBH xin nghỉ", "nextAction": "Reschedule", "status": "Open"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing, existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("R-000", out)
        self.assertIn("SơnBH xin nghỉ", out)

    def test_existing_open_missing_next_action_flagged(self):
        existing = [{"id": "R-000", "description": "SơnBH xin nghỉ", "nextAction": "", "status": "Pending"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing, existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("chưa có Next Action", out)

    def test_existing_in_progress_shows_idle_days(self):
        existing = [{"id": "R-001", "description": "Test follow up", "nextAction": "x", "status": "In progress", "idleDays": 9}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=existing, passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("(đã xử lý được 9 ngày, chưa xong)", out)

    def test_no_previous_snapshot_hides_resolved_section_entirely(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertNotIn("Đã hết rủi ro", out)

    def test_has_previous_snapshot_and_resolved_risks_lists_them_with_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=[],
            resolved_risks=["AU-9"], previous_snapshot_date="2026-08-03", sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Đã hết rủi ro* (so với báo cáo ngày 2026-08-03)", out)
        self.assertIn("AU-9", out)

    def test_urgent_and_non_urgent_split_into_separate_groups_not_by_layer(self):
        urgent = make_passive(layer="Person", rule="P4", description="Urgent item", score=9, detectedFrom="P-1", relatedAssigneeTask="A / P-1")
        normal = make_passive(layer="Task", rule="T3", description="Normal item", score=2, detectedFrom="T-1", relatedAssigneeTask="B / T-1")
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[urgent], passive_issues=[normal],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Cần chú ý ngay", out)
        self.assertIn("Còn lại", out)
        self.assertLess(out.index("Urgent item"), out.index("Còn lại"))
        self.assertNotIn("[Person]", out)
        self.assertNotIn("[Task]", out)

    def test_only_urgent_present_omits_con_lai_heading(self):
        urgent = make_passive(score=9)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[urgent], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Cần chú ý ngay", out)
        self.assertNotIn("Còn lại", out)

    def test_next_action_shows_all_options_with_dash_separator(self):
        item = make_passive(
            description="X tồn đọng",
            nextActionOptions=["OT bù giờ", "San bớt task sang người khác", "Xin dời deadline sprint"],
        )
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[item], passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("— OT bù giờ / San bớt task sang người khác / Xin dời deadline sprint.", out)

    def test_two_t1_items_grouped_into_one_compact_line(self):
        items = [
            make_passive(rule="T1", description="Sub-task A trễ", detectedFrom="A-1", relatedAssigneeTask="NguoiA / A-1"),
            make_passive(rule="T1", description="Sub-task B trễ", detectedFrom="B-1", relatedAssigneeTask="NguoiB / B-1"),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[], passive_issues=items,
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        narrative = out.split("```json")[0]
        self.assertIn("2 sub-task đã trễ Plan End: `A-1`·NguoiA, `B-1`·NguoiB.", narrative)
        self.assertNotIn("Sub-task A trễ", narrative)

    def test_t4_group_depersonalizes_next_action_name(self):
        items = [
            make_passive(
                rule="T4", detectedFrom="A-1", relatedAssigneeTask="KiênĐT / A-1",
                description="Sub-task A quá Plan Start", nextActionOptions=["Hỏi KiênĐT lý do chưa bắt đầu", "Dời Plan Start"],
            ),
            make_passive(
                rule="T4", detectedFrom="B-1", relatedAssigneeTask="SơnBH / B-1",
                description="Sub-task B quá Plan Start", nextActionOptions=["Hỏi SơnBH lý do chưa bắt đầu", "Dời Plan Start"],
            ),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        narrative = out.split("```json")[0]
        self.assertIn("Hỏi từng người lý do chưa bắt đầu", narrative)
        self.assertNotIn("Hỏi KiênĐT", narrative)

    def test_two_p4_items_grouped_with_deficit_extracted_from_description(self):
        items = [
            make_passive(
                rule="P4", detectedFrom="SơnBH, sprint Sprint 1", relatedAssigneeTask="SơnBH",
                description="SơnBH, sprint Sprint 1: tồn đọng 32.0h trong khi capacity còn lại tới hết sprint chỉ 24.0h (thiếu 8.0h).",
            ),
            make_passive(
                rule="P4", detectedFrom="ĐôNT, sprint Sprint 1", relatedAssigneeTask="ĐôNT",
                description="ĐôNT, sprint Sprint 1: tồn đọng 32.0h trong khi capacity còn lại tới hết sprint chỉ 16.0h (thiếu 16.0h).",
            ),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("**SơnBH** thiếu **8.0h**", out)
        self.assertIn("**ĐôNT** thiếu **16.0h**", out)
        self.assertIn("người đều đang vượt capacity còn lại tới hết sprint", out)

    def test_rule_order_is_fixed_not_input_order(self):
        # Đưa vào theo thứ tự M2 trước P3 -- output phải theo _RULE_ORDER (P
        # trước M), không theo thứ tự list đầu vào.
        items = [
            make_passive(rule="M2", description="Category tụt hậu", score=9),
            make_passive(rule="P3", description="Chưa gán người", score=9),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=items, passive_issues=[],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertLess(out.index("Chưa gán người"), out.index("Category tụt hậu"))

    def test_json_block_embeds_new_field_names(self):
        existing_open = [{"id": "R-000", "description": "x", "status": "Open"}]
        existing_ip = [{"id": "R-001", "description": "y", "status": "In progress", "idleDays": 3}]
        health = make_health()
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=existing_open, existing_in_progress=existing_ip, passive_risks=[], passive_issues=[],
            resolved_risks=["AU-9"], previous_snapshot_date=None, sprint_health=health,
            thresholds=THRESHOLDS,
        )
        json_text = out.split("```json\n")[1].split("\n```")[0]
        parsed = json.loads(json_text)
        self.assertEqual(parsed["existingOpen"], existing_open)
        self.assertEqual(parsed["existingInProgress"], existing_ip)
        self.assertEqual(parsed["resolvedRisks"], ["AU-9"])
        self.assertEqual(parsed["sprintHealth"], health)

    def test_tally_and_new_detected_count_shown_in_section_header(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            existing_open=[], existing_in_progress=[], passive_risks=[make_passive()], passive_issues=[make_passive(), make_passive()],
            resolved_risks=[], previous_snapshot_date=None, sprint_health=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Rủi ro mới phát hiện* (1 risk + 2 issue)", out)


if __name__ == "__main__":
    unittest.main()
