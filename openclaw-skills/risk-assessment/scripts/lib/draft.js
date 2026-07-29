'use strict';

function isHighlighted(item, thresholds) {
  const th = thresholds || {};
  const score = item.score;
  const trend = item.trend; // chỉ risk mới có trend
  return score >= (th.highScoreThreshold || 6) || trend === 'Increasing';
}

function riskLine(r) {
  const opts = (r.mitigationOptions || []).map((o) => `Đề xuất: ${o}`).join('; ');
  return `- ${r.description}${opts ? ` — ${opts}` : ''} (Detected from: ${r.detectedFrom})`;
}

function issueLine(i) {
  return `- [${i.priority}] ${i.description} (Detected from: ${i.detectedFrom})`;
}

/**
 * Xây phần tường thuật tiếng Việt từ kết quả runRules(), theo đúng giọng văn
 * mẫu trong SKILL.md — risk/issue nổi bật (Score cao hoặc Trend=Increasing)
 * nêu riêng lên đầu, không liệt kê ngang hàng với risk Stable/Low.
 */
function buildNarrative({ risks = [], issues = [], resolvedRisks = [], thresholds = {}, projectName = 'dự án' } = {}) {
  const today = new Date().toISOString().slice(0, 10);
  const highlighted = [...risks, ...issues].filter((it) => isHighlighted(it, thresholds));
  const normalRisks = risks.filter((r) => !isHighlighted(r, thresholds));
  const normalIssues = issues.filter((i) => !isHighlighted(i, thresholds));

  const lines = [`📋 Báo cáo rủi ro ${projectName} — ${today}`, ''];

  if (highlighted.length) {
    lines.push('⚠️ Cần chú ý ngay:');
    for (const it of highlighted) lines.push('riskId' in it ? riskLine(it) : issueLine(it));
    lines.push('');
  }

  if (normalRisks.length) {
    lines.push('📈 Risk khác (Stable/Low):');
    for (const r of normalRisks) lines.push(riskLine(r));
    lines.push('');
  }

  if (normalIssues.length) {
    lines.push('🐞 Issue khác:');
    for (const i of normalIssues) lines.push(issueLine(i));
    lines.push('');
  }

  if (resolvedRisks.length) {
    lines.push('✅ Đã hết rủi ro (so với báo cáo hôm qua):');
    for (const ref of resolvedRisks) lines.push(`- ${ref}`);
    lines.push('');
  }

  if (!highlighted.length && !normalRisks.length && !normalIssues.length) {
    lines.push('Không phát hiện risk/issue mới nào hôm nay.');
  }

  return lines.join('\n').trimEnd() + '\n';
}

function buildDraftFile(narrative, result) {
  return `${narrative}\n\`\`\`json\n${JSON.stringify(result, null, 2)}\n\`\`\`\n`;
}

/** Loại các item đã có sẵn trong Risk/Issue management thật (trùng category+detectedFrom). */
function dedupeAgainstExisting(items, existingKeys) {
  if (!existingKeys || existingKeys.size === 0) return items;
  return items.filter((it) => !existingKeys.has(`${it.category}__${it.detectedFrom}`));
}

module.exports = { buildNarrative, buildDraftFile, dedupeAgainstExisting };
