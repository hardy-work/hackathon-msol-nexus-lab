'use strict';

/**
 * Rule engine cho skill risk-assessment — thuần deterministic, KHÔNG có LLM.
 * SKILL.md chỉ gọi runRules() qua Bash rồi diễn giải kết quả bằng tiếng Việt.
 *
 * Input task item chuẩn hóa (do Source Adapter trong SKILL.md tạo ra, từ
 * Sprint tabs gg-sheet hoặc Jira issues):
 *   {
 *     id: string,                 // "No." (gg-sheet) hoặc issue key (jira)
 *     title: string,
 *     assignee: string|null,
 *     status: string,             // nguyên văn: "Open"|"In progress"|"Done"|...
 *     isDone: boolean,
 *     planStart: string|null,     // "YYYY-MM-DD"
 *     planEnd: string|null,       // "YYYY-MM-DD" (Plan End hoặc duedate)
 *     estimateHours: number|null,
 *     actualHours: number|null,
 *     sprint: string|null,
 *     lastUpdated: string|null,   // "YYYY-MM-DD" — lần cuối status/progress đổi
 *     detectedFrom: string,       // vd "Sprint 1, No.28" hoặc "NEX-123"
 *   }
 *
 * Phân loại Risk vs Issue theo quy ước PM cổ điển:
 *   Issue = sự thật đã xảy ra rồi (task ĐÃ trễ, effort ĐÃ vượt nhiều so với estimate)
 *   Risk  = dấu hiệu cảnh báo sớm, CHƯA chắc thành vấn đề (quá tải, đứng yên,
 *           chưa gán người gần hạn, xu hướng xấu, velocity giảm)
 */

const DEFAULT_THRESHOLDS = {
  overdueGraceDays: 0,
  stalledDays: 3,
  estimateVarianceRatio: 1.5,
  workHoursPerDay: 8,
  highScoreThreshold: 6,
  unassignedNearDeadlineDays: 2,
  velocityDropMarginPct: 15,
};

function daysBetween(fromIso, toIso) {
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  return Math.round((new Date(toIso) - new Date(fromIso)) / MS_PER_DAY);
}

function priorityFromScore(score, th) {
  if (score >= th.highScoreThreshold) return 'Critical';
  if (score >= th.highScoreThreshold - 2) return 'High';
  if (score >= 2) return 'Medium';
  return 'Low';
}

function makeIssue({ category, description, detectedFrom, probability, impact, today, th }) {
  const score = probability * impact;
  return {
    issueId: null,
    category,
    description,
    detectedFrom,
    relatedRiskId: null,
    priority: priorityFromScore(score, th),
    score,
    owner: null,
    status: 'Open',
    raisedDate: today,
    targetResolution: null,
    resolutionNotes: null,
    source: 'AI',
    lastUpdated: today,
  };
}

function makeRisk({ category, description, detectedFrom, probability, impact, mitigationOptions, today }) {
  const score = probability * impact;
  return {
    riskId: null,
    category,
    description,
    detectedFrom,
    probability,
    impact,
    score,
    trend: 'New',
    owner: null,
    mitigationOptions: mitigationOptions || [],
    status: 'Open',
    source: 'AI',
    lastUpdated: today,
  };
}

// --- Rule 1: task quá hạn, chưa Done → Issue ---------------------------------
function ruleOverdue(tasks, today, th) {
  const out = [];
  for (const t of tasks) {
    if (t.isDone || !t.planEnd) continue;
    const daysLate = daysBetween(t.planEnd, today);
    if (daysLate > th.overdueGraceDays) {
      const impact = daysLate >= 7 ? 3 : daysLate >= 3 ? 2 : 1;
      out.push(
        makeIssue({
          category: 'Schedule',
          description: `Task "${t.title}" (${t.assignee || 'chưa gán người'}) đã trễ ${daysLate} ngày so với Plan End.`,
          detectedFrom: t.detectedFrom,
          probability: 3,
          impact,
          today,
          th,
        })
      );
    }
  }
  return out;
}

// --- Rule 2: Assignee quá tải trong 1 ngày → Risk ----------------------------
function ruleAssigneeOverload(tasks, today, th) {
  const byAssigneeDay = new Map();
  for (const t of tasks) {
    if (t.isDone || !t.assignee || !t.planStart || t.planStart !== t.planEnd || !t.estimateHours) continue;
    const key = `${t.assignee}__${t.planStart}`;
    const entry = byAssigneeDay.get(key) || { assignee: t.assignee, day: t.planStart, hours: 0, tasks: [] };
    entry.hours += t.estimateHours;
    entry.tasks.push(t.detectedFrom);
    byAssigneeDay.set(key, entry);
  }
  const out = [];
  for (const { assignee, day, hours, tasks: taskRefs } of byAssigneeDay.values()) {
    if (hours > th.workHoursPerDay) {
      out.push(
        makeRisk({
          category: 'Resource',
          description: `${assignee} bị xếp ${hours}h task trong ngày ${day}, vượt quá ${th.workHoursPerDay}h/ngày.`,
          detectedFrom: taskRefs[0],
          probability: 3,
          impact: 2,
          mitigationOptions: [`OT ${assignee}`, `Dời bớt task sang ngày làm việc kế tiếp`],
          today,
        })
      );
    }
  }
  return out;
}

// --- Rule 3: Actual Effort vượt xa Estimate → Issue --------------------------
function ruleEffortOverrun(tasks, today, th) {
  const out = [];
  for (const t of tasks) {
    if (!t.estimateHours || !t.actualHours || t.estimateHours <= 0) continue;
    const ratio = t.actualHours / t.estimateHours;
    if (ratio > th.estimateVarianceRatio) {
      out.push(
        makeIssue({
          category: 'Technical',
          description: `Task "${t.title}" đã tốn ${t.actualHours}h thực tế so với ${t.estimateHours}h ước tính (x${ratio.toFixed(1)}).`,
          detectedFrom: t.detectedFrom,
          probability: 2,
          impact: ratio > th.estimateVarianceRatio * 1.5 ? 3 : 2,
          today,
          th,
        })
      );
    }
  }
  return out;
}

// --- Rule 4: Task đứng yên quá N ngày → Risk ---------------------------------
function ruleStalledTask(tasks, today, th) {
  const out = [];
  for (const t of tasks) {
    if (t.isDone || !t.lastUpdated) continue;
    const idleDays = daysBetween(t.lastUpdated, today);
    if (idleDays >= th.stalledDays) {
      out.push(
        makeRisk({
          category: 'Schedule',
          description: `Task "${t.title}" đứng yên (status không đổi) đã ${idleDays} ngày.`,
          detectedFrom: t.detectedFrom,
          probability: 2,
          impact: 2,
          mitigationOptions: [`Hỏi ${t.assignee || 'người phụ trách'} về tiến độ`, `Xem xét reassign task`],
          today,
        })
      );
    }
  }
  return out;
}

// --- Rule 5: Task chưa gán người, gần hạn → Risk -----------------------------
function ruleUnassignedNearDeadline(tasks, today, th) {
  const out = [];
  for (const t of tasks) {
    if (t.isDone || t.assignee || !t.planEnd) continue;
    const daysLeft = daysBetween(today, t.planEnd);
    if (daysLeft <= th.unassignedNearDeadlineDays) {
      out.push(
        makeRisk({
          category: 'Resource',
          description: `Task "${t.title}" còn ${daysLeft} ngày tới hạn nhưng chưa có assignee/người phụ trách.`,
          detectedFrom: t.detectedFrom,
          probability: 3,
          impact: 2,
          mitigationOptions: [`Gán người ngay`, `Dời Plan End sang sau`],
          today,
        })
      );
    }
  }
  return out;
}

// --- Rule 7: Velocity sprint giảm → Risk -------------------------------------
function sprintNumber(name) {
  const m = /(\d+)/.exec(name || '');
  return m ? parseInt(m[1], 10) : null;
}

function ruleVelocityDrop(tasks, today, th) {
  const bySprint = new Map();
  for (const t of tasks) {
    if (!t.sprint) continue;
    const entry = bySprint.get(t.sprint) || { total: 0, done: 0 };
    entry.total += 1;
    if (t.isDone) entry.done += 1;
    bySprint.set(t.sprint, entry);
  }
  const sprints = [...bySprint.keys()]
    .filter((s) => sprintNumber(s) !== null)
    .sort((a, b) => sprintNumber(a) - sprintNumber(b));
  if (sprints.length < 2) return [];

  const prevName = sprints[sprints.length - 2];
  const currName = sprints[sprints.length - 1];
  const prev = bySprint.get(prevName);
  const curr = bySprint.get(currName);
  const prevRate = prev.total ? (prev.done / prev.total) * 100 : 0;
  const currRate = curr.total ? (curr.done / curr.total) * 100 : 0;

  if (prevRate - currRate >= th.velocityDropMarginPct) {
    return [
      makeRisk({
        category: 'Schedule',
        description: `Velocity giảm: ${currName} hoàn thành ${currRate.toFixed(0)}% so với ${prevName} là ${prevRate.toFixed(0)}%.`,
        detectedFrom: currName,
        probability: 2,
        impact: 3,
        mitigationOptions: [`Rà soát scope ${currName}`, `Bổ sung người hỗ trợ`],
        today,
      }),
    ];
  }
  return [];
}

// --- Rule 6: Trend — so risk hiện tại với snapshot ngày trước ----------------
function applyTrend(risks, snapshot) {
  const prevByKey = new Map();
  const prevKeysSeen = new Set();
  if (snapshot && Array.isArray(snapshot.risks)) {
    for (const r of snapshot.risks) {
      prevByKey.set(`${r.category}__${r.detectedFrom}`, r);
    }
  }
  for (const r of risks) {
    const key = `${r.category}__${r.detectedFrom}`;
    const prev = prevByKey.get(key);
    if (!prev) {
      r.trend = 'New';
    } else {
      prevKeysSeen.add(key);
      if (r.score > prev.score) r.trend = 'Increasing';
      else if (r.score < prev.score) r.trend = 'Decreasing';
      else r.trend = 'Stable';
    }
  }
  const currentKeys = new Set(risks.map((r) => `${r.category}__${r.detectedFrom}`));
  const resolvedRisks = [];
  if (snapshot && Array.isArray(snapshot.risks)) {
    for (const r of snapshot.risks) {
      const key = `${r.category}__${r.detectedFrom}`;
      if (!currentKeys.has(key)) resolvedRisks.push(r.detectedFrom);
    }
  }
  return { risks, resolvedRisks };
}

/**
 * @param {{ tasks: object[], snapshot?: {risks: object[]}|null, thresholds?: object, today?: string }} input
 * @returns {{ risks: object[], issues: object[], resolvedRisks: string[] }}
 */
function runRules({ tasks = [], snapshot = null, thresholds = {}, today = new Date().toISOString().slice(0, 10) } = {}) {
  const th = { ...DEFAULT_THRESHOLDS, ...thresholds };

  const issues = [...ruleOverdue(tasks, today, th), ...ruleEffortOverrun(tasks, today, th)];

  const risksRaw = [
    ...ruleAssigneeOverload(tasks, today, th),
    ...ruleStalledTask(tasks, today, th),
    ...ruleUnassignedNearDeadline(tasks, today, th),
    ...ruleVelocityDrop(tasks, today, th),
  ];

  const { risks, resolvedRisks } = applyTrend(risksRaw, snapshot);

  return { risks, issues, resolvedRisks };
}

module.exports = {
  runRules,
  DEFAULT_THRESHOLDS,
  // exported for targeted testing / reuse if needed later
  ruleOverdue,
  ruleAssigneeOverload,
  ruleEffortOverrun,
  ruleStalledTask,
  ruleUnassignedNearDeadline,
  ruleVelocityDrop,
};
