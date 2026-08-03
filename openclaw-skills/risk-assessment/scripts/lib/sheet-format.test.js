'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { toDMY, nextSequentialId, formatId, relatedAssigneeTask, notesTrace, parseNotesTrace } = require('./sheet-format.js');

test('toDMY: converts ISO date to no-zero-pad D-M-YYYY', () => {
  assert.equal(toDMY('2026-08-03'), '3-8-2026');
  assert.equal(toDMY('2026-07-27'), '27-7-2026');
  assert.equal(toDMY('2026-12-05'), '5-12-2026');
});

test('formatId: pads to 3 digits with prefix', () => {
  assert.equal(formatId('R', 1), 'R-001');
  assert.equal(formatId('I', 42), 'I-042');
  assert.equal(formatId('R', 1000), 'R-1000');
});

test('nextSequentialId: starts at 1 when no existing IDs match prefix', () => {
  const rows = [['ID', 'Date Detected'], ['I-001', '27-7-2026']];
  assert.equal(nextSequentialId(rows, 'R'), 1);
});

test('nextSequentialId: increments from max existing ID with matching prefix', () => {
  const rows = [
    ['ID', 'Date Detected'],
    ['R-000', '27-7-2026'], // sample/template row — still counts, doesn't break max logic
    ['R-001', '28-7-2026'],
    ['R-003', '29-7-2026'],
    ['I-005', '29-7-2026'], // different prefix, ignored
  ];
  assert.equal(nextSequentialId(rows, 'R'), 4);
  assert.equal(nextSequentialId(rows, 'I'), 6);
});

test('nextSequentialId: empty tab (only header) starts at 1', () => {
  assert.equal(nextSequentialId([['ID', 'Date Detected']], 'R'), 1);
});

test('relatedAssigneeTask: combines owner and detectedFrom', () => {
  assert.equal(relatedAssigneeTask({ owner: 'SơnBH', detectedFrom: 'AU-3' }), 'SơnBH / AU-3');
});

test('relatedAssigneeTask: falls back to "Chưa gán" when no owner', () => {
  assert.equal(relatedAssigneeTask({ owner: '', detectedFrom: 'AU-3' }), 'Chưa gán / AU-3');
  assert.equal(relatedAssigneeTask({ detectedFrom: 'AU-3' }), 'Chưa gán / AU-3');
});

test('notesTrace + parseNotesTrace: round-trips detectedFrom and category', () => {
  const item = { detectedFrom: 'AU-3', category: 'Schedule' };
  const notes = notesTrace(item);
  const parsed = parseNotesTrace(notes);
  assert.deepEqual(parsed, { detectedFrom: 'AU-3', category: 'Schedule' });
});

test('parseNotesTrace: returns null for unrelated text', () => {
  assert.equal(parseNotesTrace('Sample row for template reference, can be deleted'), null);
  assert.equal(parseNotesTrace(''), null);
  assert.equal(parseNotesTrace(undefined), null);
});
