'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { runRules } = require('./rule-engine.js');

const THRESHOLDS = {
  overdueGraceDays: 0,
  stalledDays: 3,
  estimateVarianceRatio: 1.5,
  workHoursPerDay: 8,
  highScoreThreshold: 6,
  unassignedNearDeadlineDays: 2,
  velocityDropMarginPct: 15,
  notStartedGraceDays: 0,
};

const TODAY = '2026-07-27';

function baseTask(overrides) {
  return {
    id: 'T1',
    title: 'Task mẫu',
    assignee: 'LongVN',
    status: 'In progress',
    isDone: false,
    planStart: null,
    planEnd: null,
    estimateHours: null,
    actualHours: null,
    sprint: 'Sprint 1',
    lastUpdated: null,
    detectedFrom: 'Sprint 1, No.1',
    ...overrides,
  };
}

test('rule 1: overdue task not done → issue, not risk', () => {
  const tasks = [
    baseTask({ id: 'T1', planEnd: '2026-07-20', isDone: false, detectedFrom: 'Sprint 1, No.1' }),
  ];
  const { risks, issues } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(issues.length, 1);
  assert.equal(issues[0].category, 'Schedule');
  assert.equal(issues[0].detectedFrom, 'Sprint 1, No.1');
  assert.equal(risks.length, 0);
});

test('rule 1: overdue task already Done → no issue', () => {
  const tasks = [baseTask({ planEnd: '2026-07-20', isDone: true, status: 'Done' })];
  const { issues } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(issues.length, 0);
});

test('rule 2: assignee overload on a single day → risk', () => {
  const tasks = [
    baseTask({ id: 'T1', assignee: 'LongVN', planStart: '2026-07-27', planEnd: '2026-07-27', estimateHours: 5, detectedFrom: 'Sprint 1, No.1' }),
    baseTask({ id: 'T2', assignee: 'LongVN', planStart: '2026-07-27', planEnd: '2026-07-27', estimateHours: 6, detectedFrom: 'Sprint 1, No.2' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const overload = risks.find((r) => r.category === 'Resource');
  assert.ok(overload, 'expected a Resource overload risk');
  assert.match(overload.description, /LongVN/);
});

test('rule 2: assignee within capacity → no overload risk', () => {
  const tasks = [
    baseTask({ id: 'T1', assignee: 'LongVN', planStart: '2026-07-27', planEnd: '2026-07-27', estimateHours: 4 }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => r.category === 'Resource').length, 0);
});

test('rule 3: actual effort far exceeds estimate → issue', () => {
  const tasks = [
    baseTask({ estimateHours: 4, actualHours: 10, detectedFrom: 'Sprint 1, No.3' }),
  ];
  const { issues } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const overrun = issues.find((i) => i.category === 'Technical');
  assert.ok(overrun, 'expected a Technical effort-overrun issue');
});

test('rule 4: task not done, stale for 5 days → risk', () => {
  const tasks = [
    baseTask({ isDone: false, lastUpdated: '2026-07-22', detectedFrom: 'Sprint 1, No.4' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const stalled = risks.find((r) => r.category === 'Schedule' && /đứng yên|stalled/i.test(r.description));
  assert.ok(stalled, 'expected a stalled-task risk');
});

test('rule 4: task updated yesterday → no stalled risk', () => {
  const tasks = [baseTask({ isDone: false, lastUpdated: '2026-07-26' })];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => /đứng yên|stalled/i.test(r.description)).length, 0);
});

test('rule 5: unassigned task near deadline → risk', () => {
  const tasks = [
    baseTask({ assignee: null, planEnd: '2026-07-28', isDone: false, detectedFrom: 'Sprint 1, No.5' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const gap = risks.find((r) => r.category === 'Resource' && /chưa.*(assignee|người)/i.test(r.description));
  assert.ok(gap, 'expected an unassigned-near-deadline risk');
});

test('rule 5: unassigned task far from deadline → no risk', () => {
  const tasks = [baseTask({ assignee: null, planEnd: '2026-08-15', isDone: false })];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => /chưa.*(assignee|người)/i.test(r.description)).length, 0);
});

test('rule 6: risk trend — New when absent from snapshot', () => {
  const tasks = [baseTask({ assignee: null, planEnd: '2026-07-28', isDone: false, detectedFrom: 'Sprint 1, No.5' })];
  const { risks } = runRules({ tasks, snapshot: null, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks[0].trend, 'New');
});

test('rule 6: risk trend — Increasing when score went up vs snapshot', () => {
  const tasks = [
    baseTask({ id: 'T1', assignee: 'LongVN', planStart: '2026-07-27', planEnd: '2026-07-27', estimateHours: 12, detectedFrom: 'Sprint 1, No.1' }),
  ];
  const snapshot = {
    risks: [
      { category: 'Resource', detectedFrom: 'Sprint 1, No.1', score: 2 },
    ],
  };
  const { risks } = runRules({ tasks, snapshot, thresholds: THRESHOLDS, today: TODAY });
  const r = risks.find((x) => x.detectedFrom === 'Sprint 1, No.1');
  assert.ok(r.score > 2);
  assert.equal(r.trend, 'Increasing');
});

test('rule 6: resolvedRisks lists snapshot risks no longer detected', () => {
  const tasks = [baseTask({ isDone: true, detectedFrom: 'Sprint 1, No.9' })];
  const snapshot = {
    risks: [{ category: 'Schedule', detectedFrom: 'Sprint 1, No.9', score: 4 }],
  };
  const { resolvedRisks } = runRules({ tasks, snapshot, thresholds: THRESHOLDS, today: TODAY });
  assert.deepEqual(resolvedRisks, ['Sprint 1, No.9']);
});

test('rule 7: velocity drop between two sprints → risk', () => {
  const tasks = [
    baseTask({ id: 'A', sprint: 'Sprint 1', isDone: true, detectedFrom: 'Sprint 1, No.1' }),
    baseTask({ id: 'B', sprint: 'Sprint 1', isDone: true, detectedFrom: 'Sprint 1, No.2' }),
    baseTask({ id: 'C', sprint: 'Sprint 2', isDone: false, detectedFrom: 'Sprint 2, No.1' }),
    baseTask({ id: 'D', sprint: 'Sprint 2', isDone: false, detectedFrom: 'Sprint 2, No.2' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const velocity = risks.find((r) => r.category === 'Schedule' && /velocity/i.test(r.description));
  assert.ok(velocity, 'expected a velocity-drop risk');
});

test('rule 7: stable velocity across sprints → no risk', () => {
  const tasks = [
    baseTask({ id: 'A', sprint: 'Sprint 1', isDone: true, detectedFrom: 'Sprint 1, No.1' }),
    baseTask({ id: 'B', sprint: 'Sprint 1', isDone: false, detectedFrom: 'Sprint 1, No.2' }),
    baseTask({ id: 'C', sprint: 'Sprint 2', isDone: true, detectedFrom: 'Sprint 2, No.1' }),
    baseTask({ id: 'D', sprint: 'Sprint 2', isDone: false, detectedFrom: 'Sprint 2, No.2' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => /velocity/i.test(r.description)).length, 0);
});

test('score = probability × impact, and highScoreThreshold marks High', () => {
  const tasks = [baseTask({ planEnd: '2026-07-10', isDone: false, detectedFrom: 'Sprint 1, No.1' })];
  const { issues } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(issues[0].priority, 'Critical');
});

test('rule 8: task past Plan Start with no actual effort logged → risk', () => {
  const tasks = [
    baseTask({ planStart: '2026-07-20', actualHours: null, isDone: false, detectedFrom: 'Sprint 1, No.6' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const blocked = risks.find((r) => r.detectedFrom === 'Sprint 1, No.6');
  assert.ok(blocked, 'expected a not-started-on-time risk');
  assert.equal(blocked.category, 'Schedule');
});

test('rule 8: task past Plan Start but has actual effort logged → no risk', () => {
  const tasks = [
    baseTask({ planStart: '2026-07-20', actualHours: 4, isDone: false, detectedFrom: 'Sprint 1, No.7' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => r.detectedFrom === 'Sprint 1, No.7').length, 0);
});

test('rule 8: Plan Start not reached yet → no risk', () => {
  const tasks = [
    baseTask({ planStart: '2026-07-28', actualHours: null, isDone: false, detectedFrom: 'Sprint 1, No.8' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => r.detectedFrom === 'Sprint 1, No.8').length, 0);
});

test('rule 8: task already Done → no risk even if past Plan Start with no effort', () => {
  const tasks = [
    baseTask({ planStart: '2026-07-20', actualHours: null, isDone: true, detectedFrom: 'Sprint 1, No.9' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => r.detectedFrom === 'Sprint 1, No.9').length, 0);
});

test('rule 9: tasks in "Verify bug" status → bug-trend risk', () => {
  const tasks = [
    baseTask({ id: 'B1', status: 'Verify bug', detectedFrom: 'Sprint 1, No.10' }),
    baseTask({ id: 'B2', status: 'Verify bug', detectedFrom: 'Sprint 1, No.11' }),
  ];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  const bugRisk = risks.find((r) => r.category === 'Quality');
  assert.ok(bugRisk, 'expected a Quality bug-trend risk');
  assert.match(bugRisk.description, /2 task/);
});

test('rule 9: no tasks in "Verify bug" status → no bug-trend risk', () => {
  const tasks = [baseTask({ status: 'Open' })];
  const { risks } = runRules({ tasks, thresholds: THRESHOLDS, today: TODAY });
  assert.equal(risks.filter((r) => r.category === 'Quality').length, 0);
});

test('rule 9: bug count trend — Increasing when count went up vs snapshot', () => {
  const tasks = [
    baseTask({ id: 'B1', status: 'Verify bug', detectedFrom: 'Sprint 1, No.10' }),
    baseTask({ id: 'B2', status: 'Verify bug', detectedFrom: 'Sprint 1, No.11' }),
    baseTask({ id: 'B3', status: 'Verify bug', detectedFrom: 'Sprint 1, No.12' }),
  ];
  const snapshot = {
    risks: [{ category: 'Quality', detectedFrom: 'Toàn dự án (Verify bug)', score: 3 }],
  };
  const { risks } = runRules({ tasks, snapshot, thresholds: THRESHOLDS, today: TODAY });
  const bugRisk = risks.find((r) => r.category === 'Quality');
  assert.equal(bugRisk.trend, 'Increasing');
});

test('rule 9: bug-trend risk resolved when no more "Verify bug" tasks vs snapshot', () => {
  const tasks = [baseTask({ status: 'Done', isDone: true })];
  const snapshot = {
    risks: [{ category: 'Quality', detectedFrom: 'Toàn dự án (Verify bug)', score: 3 }],
  };
  const { resolvedRisks } = runRules({ tasks, snapshot, thresholds: THRESHOLDS, today: TODAY });
  assert.deepEqual(resolvedRisks, ['Toàn dự án (Verify bug)']);
});
