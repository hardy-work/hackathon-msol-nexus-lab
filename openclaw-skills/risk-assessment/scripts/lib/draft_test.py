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


class BuildDraftTest(unittest.TestCase):
    def test_empty_everything_shows_all_sections_with_placeholders(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Rủi ro chủ động", out)
        self.assertIn("Rủi ro bị động", out)
        self.assertIn("Hiện không có rủi ro bị động nào", out)
        self.assertIn("Rủi ro chưa được xử lý", out)
        self.assertIn("Không phát hiện rủi ro/issue bị động nào hôm nay", out)
        self.assertNotIn("Status=Pending", out)
        self.assertNotIn("In progress", out)

    def test_header_includes_bold_project_title_and_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("**Test Nexus** — 2026-08-04", out)

    def test_opening_summary_counts_items_and_urgent(self):
        items = [make_passive(layer="Person", rule="P4", score=9), make_passive(layer="Task", rule="T4", score=3)]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=items, passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Phát hiện 2 rủi ro/issue hôm nay, 1 mục cần chú ý ngay (⚠️)", out)

    def test_stale_in_progress_present_lists_id_description_and_idle_days(self):
        stale = [{"id": "R-002", "description": "SơnBH tồn đọng 32h", "idleDays": 2}]
        out = build_draft(
            today="2026-08-06", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=stale, resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("R-002", out)
        self.assertIn("SơnBH tồn đọng 32h", out)
        self.assertIn("(đã 2 ngày)", out)

    def test_no_previous_snapshot_hides_resolved_section_entirely(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertNotIn("Đã hết rủi ro", out)

    def test_has_previous_snapshot_but_nothing_resolved_shows_explicit_note_with_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date="2026-08-03",
            thresholds=THRESHOLDS,
        )
        self.assertIn("Đã hết rủi ro* (so với báo cáo ngày 2026-08-03)", out)
        self.assertIn("Không có rủi ro nào vừa hết so với báo cáo ngày 2026-08-03", out)

    def test_has_previous_snapshot_and_resolved_risks_lists_them_with_date(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=["AU-9"],
            previous_snapshot_date="2026-08-03",
            thresholds=THRESHOLDS,
        )
        self.assertIn("Đã hết rủi ro* (so với báo cáo ngày 2026-08-03)", out)
        self.assertIn("AU-9", out)

    def test_active_risks_present_lists_them_and_no_placeholder(self):
        active = [{"id": "R-005", "description": "SơnBH báo bị block", "nextAction": "Escalate"}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=active, passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("R-005", out)
        active_section = out.split("*Rủi ro chủ động*:")[1].split("🔁")[0]
        self.assertNotIn("Hiện không có.", active_section)

    def test_urgent_item_marked_inline_within_its_layer(self):
        urgent = make_passive(layer="Task", rule="T3", description="Task X trễ", score=9)
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[urgent], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("⚠️ Task X trễ", out)
        self.assertIn("[Task]", out)

    def test_active_risk_missing_next_action_flagged(self):
        active = {"id": "R-000", "description": "SơnBH nghỉ", "nextAction": ""}
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[active], passive_risks=[], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("chưa có Next Action", out)

    def test_json_block_embeds_all_five_lists(self):
        stale = [{"id": "R-002", "description": "x", "idleDays": 2}]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[], stale_in_progress=stale, resolved_risks=["AU-9"],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        json_text = out.split("```json\n")[1].split("\n```")[0]
        parsed = json.loads(json_text)
        self.assertEqual(parsed["resolvedRisks"], ["AU-9"])
        self.assertEqual(parsed["staleInProgress"], stale)

    def test_grouped_by_layer_in_fixed_order_person_before_category(self):
        items = [
            make_passive(layer="Module", rule="M1", description="Category bug"),
            make_passive(layer="Person", rule="P2", description="Person overload"),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=items, passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertLess(out.index("Person overload"), out.index("Category bug"))
        self.assertIn("[Category]", out)  # nhãn hiển thị, KHÔNG phải "[Module]"

    def test_next_action_shows_all_options_with_dash_separator(self):
        item = make_passive(
            layer="Person", rule="P2", description="X tồn đọng",
            nextActionOptions=["OT bù giờ", "San bớt task sang người khác", "Xin dời deadline sprint"],
        )
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[item], passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("— OT bù giờ / San bớt task sang người khác / Xin dời deadline sprint.", out)

    def test_single_item_of_groupable_rule_not_grouped(self):
        item = make_passive(layer="Task", rule="T1", description="Sub-task duy nhất trễ", detectedFrom="X-1", relatedAssigneeTask="NguoiA / X-1")
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=[item], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Sub-task duy nhất trễ", out)
        self.assertNotIn("sub-task đã trễ Plan End:", out)  # câu gộp nhóm KHÔNG xuất hiện khi chỉ có 1 item

    def test_two_t1_items_grouped_into_one_compact_line(self):
        items = [
            make_passive(layer="Task", rule="T1", description="Sub-task A trễ", detectedFrom="A-1", relatedAssigneeTask="NguoiA / A-1"),
            make_passive(layer="Task", rule="T1", description="Sub-task B trễ", detectedFrom="B-1", relatedAssigneeTask="NguoiB / B-1"),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[], passive_issues=items, stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        narrative = out.split("```json")[0]
        self.assertIn("2 sub-task đã trễ Plan End: `A-1`·NguoiA, `B-1`·NguoiB.", narrative)
        self.assertNotIn("Sub-task A trễ", narrative)  # description gốc từng item KHÔNG hiện riêng trong narrative khi đã gộp (vẫn còn trong JSON block)

    def test_t4_group_depersonalizes_next_action_name(self):
        items = [
            make_passive(
                layer="Task", rule="T4", detectedFrom="A-1", relatedAssigneeTask="KiênĐT / A-1",
                description="Sub-task A quá Plan Start", nextActionOptions=["Hỏi KiênĐT lý do chưa bắt đầu", "Dời Plan Start"],
            ),
            make_passive(
                layer="Task", rule="T4", detectedFrom="B-1", relatedAssigneeTask="SơnBH / B-1",
                description="Sub-task B quá Plan Start", nextActionOptions=["Hỏi SơnBH lý do chưa bắt đầu", "Dời Plan Start"],
            ),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=items, passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        narrative = out.split("```json")[0]
        self.assertIn("Hỏi từng người lý do chưa bắt đầu", narrative)
        self.assertNotIn("Hỏi KiênĐT", narrative)

    def test_two_p4_items_grouped_with_deficit_extracted_from_description(self):
        items = [
            make_passive(
                layer="Person", rule="P4", detectedFrom="SơnBH, sprint Sprint 1", relatedAssigneeTask="SơnBH",
                description="SơnBH, sprint Sprint 1: tồn đọng 32.0h trong khi capacity còn lại tới hết sprint chỉ 24.0h (thiếu 8.0h).",
            ),
            make_passive(
                layer="Person", rule="P4", detectedFrom="ĐôNT, sprint Sprint 1", relatedAssigneeTask="ĐôNT",
                description="ĐôNT, sprint Sprint 1: tồn đọng 32.0h trong khi capacity còn lại tới hết sprint chỉ 16.0h (thiếu 16.0h).",
            ),
        ]
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=items, passive_issues=[], stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("**SơnBH** thiếu **8.0h**", out)
        self.assertIn("**ĐôNT** thiếu **16.0h**", out)
        self.assertIn("người đều đang vượt capacity còn lại tới hết sprint", out)

    def test_tally_line_shows_risk_issue_and_resolved_counts(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[make_passive()], passive_issues=[make_passive(), make_passive()],
            stale_in_progress=[], resolved_risks=["AU-9"],
            previous_snapshot_date="2026-08-03",
            thresholds=THRESHOLDS,
        )
        self.assertIn("**1 risk + 2 issue** phát hiện hôm nay, **1** đã hết so với báo cáo ngày 2026-08-03.", out)

    def test_tally_line_without_previous_snapshot_omits_resolved_clause(self):
        out = build_draft(
            today="2026-08-04", project_title="Test Nexus",
            active_risks=[], passive_risks=[make_passive()], passive_issues=[],
            stale_in_progress=[], resolved_risks=[],
            previous_snapshot_date=None,
            thresholds=THRESHOLDS,
        )
        self.assertIn("Tổng: **1 risk + 0 issue** phát hiện hôm nay.", out)
        self.assertNotIn("đã hết so với", out)


if __name__ == "__main__":
    unittest.main()
