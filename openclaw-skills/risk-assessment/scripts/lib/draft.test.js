'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildNarrative, buildDraftFile, dedupeAgainstExisting } = require('./draft.js');

const THRESHOLDS = { highScoreThreshold: 6 };

test('buildNarrative: high-score risk goes under "Cần chú ý ngay"', () => {
  const risks = [{ riskId: null, category: 'Resource', description: 'Quá tải', detectedFrom: 'Sprint 1, No.1', score: 6, trend: 'Stable', mitigationOptions: ['OT'] }];
  const text = buildNarrative({ risks, issues: [], resolvedRisks: [], thresholds: THRESHOLDS });
  assert.match(text, /Cần chú ý ngay/);
  assert.match(text, /Quá tải/);
  assert.doesNotMatch(text, /Risk khác \(Stable\/Low\)/);
});

test('buildNarrative: low-score risk goes under "Risk khác"', () => {
  const risks = [{ riskId: null, category: 'Resource', description: 'Nhẹ thôi', detectedFrom: 'Sprint 1, No.2', score: 2, trend: 'Stable', mitigationOptions: [] }];
  const text = buildNarrative({ risks, issues: [], resolvedRisks: [], thresholds: THRESHOLDS });
  assert.match(text, /Risk khác \(Stable\/Low\)/);
  assert.doesNotMatch(text, /Cần chú ý ngay/);
});

test('buildNarrative: Increasing trend highlighted even with low score', () => {
  const risks = [{ riskId: null, category: 'Quality', description: 'Bug tăng', detectedFrom: 'x', score: 2, trend: 'Increasing', mitigationOptions: [] }];
  const text = buildNarrative({ risks, issues: [], resolvedRisks: [], thresholds: THRESHOLDS });
  assert.match(text, /Cần chú ý ngay/);
});

test('buildNarrative: resolved risks listed separately', () => {
  const text = buildNarrative({ risks: [], issues: [], resolvedRisks: ['Sprint 1, No.9'], thresholds: THRESHOLDS });
  assert.match(text, /Đã hết rủi ro/);
  assert.match(text, /Sprint 1, No.9/);
});

test('buildNarrative: nothing detected → explicit "no risk" message', () => {
  const text = buildNarrative({ risks: [], issues: [], resolvedRisks: [], thresholds: THRESHOLDS });
  assert.match(text, /Không phát hiện risk\/issue mới/);
});

test('buildDraftFile: appends JSON block after narrative', () => {
  const result = { risks: [], issues: [], resolvedRisks: [] };
  const content = buildDraftFile('Narrative text', result);
  assert.match(content, /^Narrative text/);
  assert.match(content, /```json/);
  assert.match(content, /"risks": \[\]/);
});

test('dedupeAgainstExisting: filters items already present in real tabs', () => {
  const items = [
    { category: 'Schedule', detectedFrom: 'Sprint 1, No.1' },
    { category: 'Resource', detectedFrom: 'Sprint 1, No.2' },
  ];
  const existing = new Set(['Schedule__Sprint 1, No.1']);
  const result = dedupeAgainstExisting(items, existing);
  assert.equal(result.length, 1);
  assert.equal(result[0].detectedFrom, 'Sprint 1, No.2');
});

test('dedupeAgainstExisting: empty existing set → no filtering', () => {
  const items = [{ category: 'Schedule', detectedFrom: 'Sprint 1, No.1' }];
  assert.equal(dedupeAgainstExisting(items, new Set()).length, 1);
});
