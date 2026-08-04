import unittest

from rule_engine import (
    rule_T1_overdue,
    rule_T2_effort_overrun,
    rule_T3_stalled,
    rule_T4_not_started,
    rule_P1_leave_cascade,
    rule_P2_daily_overload,
    rule_P3_unassigned_near_deadline,
    rule_P4_sprint_backlog_overload,
    rule_S1_velocity_drop,
    rule_S2_sprint_at_risk,
    rule_M1_bug_trend_by_module,
    rule_M2_category_behind_own_deadline,
    apply_trend,
    run_rules,
)

THRESHOLDS = {
    "overdueGraceDays": 0,
    "stalledDays": 3,
    "estimateVarianceRatio": 1.5,
    "workHoursPerDay": 8,
    "highScoreThreshold": 6,
    "unassignedNearDeadlineDays": 2,
    "velocityDropMarginPct": 15,
    "notStartedGraceDays": 0,
}

TODAY = "2026-08-04"


def base_task(**overrides):
    t = {
        "id": "AU-1",
        "title": "Task mẫu",
        "taskName": None,
        "category": "Authentication",
        "role": "BE",
        "assignee": "LongVN",
        "priority": "Medium",
        "status": "In progress",
        "isDone": False,
        "planStart": None,
        "planEnd": None,
        "estimateHours": None,
        "actualHours": None,
        "remainingHours": None,
        "sprint": "Sprint 1",
        "lastUpdated": None,
        "detectedFrom": "AU-1",
    }
    t.update(overrides)
    return t


class RuleT1OverdueTest(unittest.TestCase):
    def test_overdue_not_done_fires(self):
        t = base_task(planEnd="2026-07-28", isDone=False)
        out = rule_T1_overdue([t], TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["layer"], "Task")
        self.assertEqual(out[0]["rule"], "T1")
        self.assertEqual(out[0]["detectedFrom"], "AU-1")

    def test_overdue_done_does_not_fire(self):
        t = base_task(planEnd="2026-07-28", isDone=True, status="Done")
        self.assertEqual(rule_T1_overdue([t], TODAY, THRESHOLDS), [])

    def test_not_yet_due_does_not_fire(self):
        t = base_task(planEnd="2026-08-10", isDone=False)
        self.assertEqual(rule_T1_overdue([t], TODAY, THRESHOLDS), [])


class RuleT2EffortOverrunTest(unittest.TestCase):
    def test_far_exceeds_estimate_fires(self):
        t = base_task(estimateHours=4, actualHours=10)
        out = rule_T2_effort_overrun([t], TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "T2")

    def test_within_variance_does_not_fire(self):
        t = base_task(estimateHours=8, actualHours=9)
        self.assertEqual(rule_T2_effort_overrun([t], TODAY, THRESHOLDS), [])


class RuleT3StalledTest(unittest.TestCase):
    def test_stale_5_days_fires(self):
        t = base_task(isDone=False, lastUpdated="2026-07-30")
        out = rule_T3_stalled([t], TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["layer"], "Task")
        self.assertEqual(out[0]["rule"], "T3")

    def test_updated_yesterday_does_not_fire(self):
        t = base_task(isDone=False, lastUpdated="2026-08-03")
        self.assertEqual(rule_T3_stalled([t], TODAY, THRESHOLDS), [])


class RuleT4NotStartedTest(unittest.TestCase):
    def test_past_start_no_actual_effort_fires(self):
        t = base_task(planStart="2026-08-01", actualHours=None)
        out = rule_T4_not_started([t], TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "T4")

    def test_has_actual_effort_does_not_fire(self):
        t = base_task(planStart="2026-08-01", actualHours=2)
        self.assertEqual(rule_T4_not_started([t], TODAY, THRESHOLDS), [])


class RuleP1LeaveCascadeTest(unittest.TestCase):
    def test_leave_overlapping_task_produces_cascade_risk(self):
        tasks = [
            base_task(
                id="AU-5", detectedFrom="AU-5", assignee="SơnBH",
                planStart="2026-08-03", planEnd="2026-08-04",
                category="Authentication", isDone=False,
            ),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {
                "2026-08-03": 0.0, "2026-08-04": 0.0,
            }},
        ]
        out = rule_P1_leave_cascade(tasks, resource_plan, TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["layer"], "Person")
        self.assertEqual(out[0]["rule"], "P1")
        self.assertIn("AU-5", out[0]["description"])
        self.assertIn("Authentication", out[0]["description"])

    def test_leave_not_overlapping_any_task_produces_nothing(self):
        tasks = [
            base_task(
                id="AU-5", detectedFrom="AU-5", assignee="SơnBH",
                planStart="2026-08-10", planEnd="2026-08-10",
                category="Authentication", isDone=False,
            ),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {
                "2026-08-03": 0.0,
            }},
        ]
        out = rule_P1_leave_cascade(tasks, resource_plan, TODAY, THRESHOLDS)
        self.assertEqual(out, [])

    def test_none_hours_is_not_treated_as_leave(self):
        tasks = [
            base_task(
                id="AU-5", detectedFrom="AU-5", assignee="SơnBH",
                planStart="2026-08-03", planEnd="2026-08-03",
                category="Authentication", isDone=False,
            ),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {
                "2026-08-03": None,  # cuối tuần / chưa tới, KHÔNG phải nghỉ
            }},
        ]
        out = rule_P1_leave_cascade(tasks, resource_plan, TODAY, THRESHOLDS)
        self.assertEqual(out, [])


class RuleP2DailyOverloadTest(unittest.TestCase):
    def test_two_tasks_same_day_over_8h_fires(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="LongVN", planStart="2026-08-04", planEnd="2026-08-04", estimateHours=5),
            base_task(id="T2", detectedFrom="T2", assignee="LongVN", planStart="2026-08-04", planEnd="2026-08-04", estimateHours=6),
        ]
        out = rule_P2_daily_overload(tasks, TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "P2")

    def test_within_capacity_does_not_fire(self):
        tasks = [base_task(id="T1", detectedFrom="T1", assignee="LongVN", planStart="2026-08-04", planEnd="2026-08-04", estimateHours=4)]
        self.assertEqual(rule_P2_daily_overload(tasks, TODAY, THRESHOLDS), [])

    def test_single_task_alone_over_8h_does_not_fire(self):
        # Tái hiện bug thật (PCS-7, VinhNV, 03/8/2026): 1 task DUY NHẤT trong
        # ngày, tự nó estimate/re-estimate >8h (vd phát sinh vấn đề nên phải
        # sửa Re-estimate từ 8 lên 12) — đây KHÔNG phải bị xếp chồng lịch,
        # không phải việc của P2 (P4/S2 đã cover quá tải theo backlog rồi).
        tasks = [base_task(id="PCS-7", detectedFrom="PCS-7", assignee="VinhNV", planStart="2026-08-03", planEnd="2026-08-03", estimateHours=12)]
        self.assertEqual(rule_P2_daily_overload(tasks, TODAY, THRESHOLDS), [])


class RuleP3UnassignedNearDeadlineTest(unittest.TestCase):
    def test_unassigned_near_deadline_fires(self):
        t = base_task(assignee=None, planEnd="2026-08-05", isDone=False)
        out = rule_P3_unassigned_near_deadline([t], TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "P3")

    def test_unassigned_far_deadline_does_not_fire(self):
        t = base_task(assignee=None, planEnd="2026-09-01", isDone=False)
        self.assertEqual(rule_P3_unassigned_near_deadline([t], TODAY, THRESHOLDS), [])


class RuleP4SprintBacklogOverloadTest(unittest.TestCase):
    def test_backlog_exceeds_capacity_fires(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="SơnBH", sprint="Sprint 1", isDone=False, remainingHours=40),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {
                "2026-08-04": 8.0, "2026-08-05": 8.0,
            }},
        ]
        out = rule_P4_sprint_backlog_overload(tasks, resource_plan, TODAY, "2026-08-05", "Sprint 1", THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "P4")

    def test_backlog_within_capacity_does_not_fire(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="SơnBH", sprint="Sprint 1", isDone=False, remainingHours=8),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {
                "2026-08-04": 8.0, "2026-08-05": 8.0,
            }},
        ]
        out = rule_P4_sprint_backlog_overload(tasks, resource_plan, TODAY, "2026-08-05", "Sprint 1", THRESHOLDS)
        self.assertEqual(out, [])


class RuleS1VelocityDropTest(unittest.TestCase):
    def test_drop_between_two_sprints_fires(self):
        tasks = [
            base_task(id="A", detectedFrom="A", sprint="Sprint 1", isDone=True),
            base_task(id="B", detectedFrom="B", sprint="Sprint 1", isDone=True),
            base_task(id="C", detectedFrom="C", sprint="Sprint 2", isDone=False),
            base_task(id="D", detectedFrom="D", sprint="Sprint 2", isDone=False),
        ]
        out = rule_S1_velocity_drop(tasks, TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "S1")

    def test_stable_velocity_does_not_fire(self):
        tasks = [
            base_task(id="A", detectedFrom="A", sprint="Sprint 1", isDone=True),
            base_task(id="B", detectedFrom="B", sprint="Sprint 1", isDone=False),
            base_task(id="C", detectedFrom="C", sprint="Sprint 2", isDone=True),
            base_task(id="D", detectedFrom="D", sprint="Sprint 2", isDone=False),
        ]
        self.assertEqual(rule_S1_velocity_drop(tasks, TODAY, THRESHOLDS), [])

    def test_only_one_sprint_present_does_not_fire(self):
        tasks = [base_task(id="A", detectedFrom="A", sprint="Sprint 1", isDone=False)]
        self.assertEqual(rule_S1_velocity_drop(tasks, TODAY, THRESHOLDS), [])


class RuleS2SprintAtRiskTest(unittest.TestCase):
    def test_team_backlog_exceeds_team_capacity_fires(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="SơnBH", sprint="Sprint 1", isDone=False, remainingHours=40),
            base_task(id="T2", detectedFrom="T2", assignee="VinhNV", sprint="Sprint 1", isDone=False, remainingHours=40),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {"2026-08-04": 8.0}},
            {"member": "Nguyễn Văn Vinh", "assigneeCode": "VinhNV", "dailyHours": {"2026-08-04": 8.0}},
        ]
        out = rule_S2_sprint_at_risk(tasks, resource_plan, TODAY, "2026-08-04", "Sprint 1", THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "S2")

    def test_team_capacity_sufficient_does_not_fire(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="SơnBH", sprint="Sprint 1", isDone=False, remainingHours=4),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {"2026-08-04": 8.0}},
        ]
        out = rule_S2_sprint_at_risk(tasks, resource_plan, TODAY, "2026-08-04", "Sprint 1", THRESHOLDS)
        self.assertEqual(out, [])


class RuleM1BugTrendByModuleTest(unittest.TestCase):
    def test_counts_verify_bug_per_module_separately(self):
        tasks = [
            base_task(id="A1", detectedFrom="A1", category="Authentication", status="Verify bug"),
            base_task(id="A2", detectedFrom="A2", category="Authentication", status="Verify bug"),
            base_task(id="P1", detectedFrom="P1", category="Profile", status="Verify bug"),
            base_task(id="A3", detectedFrom="A3", category="Authentication", status="Done", isDone=True),
        ]
        out = rule_M1_bug_trend_by_module(tasks, TODAY, THRESHOLDS)
        by_module = {o["relatedAssigneeTask"]: o for o in out}
        self.assertEqual(len(out), 2)
        self.assertIn("Authentication", by_module)
        self.assertIn("Profile", by_module)
        self.assertIn("A1", by_module["Authentication"]["description"])
        self.assertIn("A2", by_module["Authentication"]["description"])
        self.assertNotIn("P1", by_module["Authentication"]["description"])

    def test_no_verify_bug_produces_nothing(self):
        tasks = [base_task(id="A1", detectedFrom="A1", category="Authentication", status="Open")]
        self.assertEqual(rule_M1_bug_trend_by_module(tasks, TODAY, THRESHOLDS), [])


class RuleM2CategoryBehindOwnDeadlineTest(unittest.TestCase):
    def test_time_elapsed_far_exceeds_done_pct_fires(self):
        # Category chạy 27/7 -> 04/8 (9 ngày), hôm nay 04/8 = 100% thời gian
        # trôi qua, nhưng chỉ 1/2 task Done (50%) -> lệch 50 điểm % >= 15
        tasks = [
            base_task(id="A1", detectedFrom="A1", category="Authentication", planStart="2026-07-27", planEnd="2026-08-04", isDone=True),
            base_task(id="A2", detectedFrom="A2", category="Authentication", planStart="2026-07-27", planEnd="2026-08-04", isDone=False),
        ]
        out = rule_M2_category_behind_own_deadline(tasks, TODAY, THRESHOLDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rule"], "M2")

    def test_on_track_does_not_fire(self):
        tasks = [
            base_task(id="A1", detectedFrom="A1", category="Authentication", planStart="2026-07-27", planEnd="2026-08-04", isDone=True),
            base_task(id="A2", detectedFrom="A2", category="Authentication", planStart="2026-07-27", planEnd="2026-08-04", isDone=True),
        ]
        self.assertEqual(rule_M2_category_behind_own_deadline(tasks, TODAY, THRESHOLDS), [])


class ApplyTrendTest(unittest.TestCase):
    def test_new_when_absent_from_snapshot(self):
        risks = [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 4}]
        risks, resolved = apply_trend(risks, None)
        self.assertEqual(risks[0]["trend"], "New")
        self.assertEqual(resolved, [])

    def test_increasing_when_score_went_up(self):
        risks = [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 6}]
        snapshot = {"risks": [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 4}]}
        risks, _ = apply_trend(risks, snapshot)
        self.assertEqual(risks[0]["trend"], "Increasing")

    def test_decreasing_when_score_went_down(self):
        risks = [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 2}]
        snapshot = {"risks": [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 4}]}
        risks, _ = apply_trend(risks, snapshot)
        self.assertEqual(risks[0]["trend"], "Decreasing")

    def test_stable_when_score_unchanged(self):
        risks = [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 4}]
        snapshot = {"risks": [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-1", "score": 4}]}
        risks, _ = apply_trend(risks, snapshot)
        self.assertEqual(risks[0]["trend"], "Stable")

    def test_resolved_risks_lists_snapshot_entries_no_longer_present(self):
        risks = []
        snapshot = {"risks": [{"layer": "Task", "rule": "T3", "detectedFrom": "AU-9", "score": 4}]}
        _, resolved = apply_trend(risks, snapshot)
        self.assertEqual(resolved, ["AU-9"])


class RunRulesTest(unittest.TestCase):
    def test_combines_issues_and_risks_without_resource_plan(self):
        tasks = [
            base_task(id="A1", detectedFrom="A1", planEnd="2026-07-28", isDone=False),  # T1 overdue
            base_task(id="A2", detectedFrom="A2", estimateHours=4, actualHours=10),  # T2 overrun
        ]
        result = run_rules(tasks=tasks, thresholds=THRESHOLDS, today=TODAY)
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(result["risks"], [])
        self.assertEqual(result["resolvedRisks"], [])

    def test_includes_person_and_sprint_rules_when_resource_plan_given(self):
        tasks = [
            base_task(id="T1", detectedFrom="T1", assignee="SơnBH", sprint="Sprint 1", isDone=False, remainingHours=40),
        ]
        resource_plan = [
            {"member": "Bùi Hồng Sơn", "assigneeCode": "SơnBH", "dailyHours": {"2026-08-04": 8.0}},
        ]
        result = run_rules(
            tasks=tasks,
            resource_plan_people=resource_plan,
            sprint_end="2026-08-04",
            sprint_name="Sprint 1",
            thresholds=THRESHOLDS,
            today=TODAY,
        )
        rules_fired = {r["rule"] for r in result["risks"]}
        self.assertIn("P4", rules_fired)
        self.assertIn("S2", rules_fired)


if __name__ == "__main__":
    unittest.main()
