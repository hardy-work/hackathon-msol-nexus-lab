'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { colToIndex, parseDMYDate, parseHoursNumber, rowsToTasks, jiraIssuesToTasks } = require('./normalize.js');

test('colToIndex: single and double letter columns', () => {
  assert.equal(colToIndex('A'), 0);
  assert.equal(colToIndex('C'), 2);
  assert.equal(colToIndex('Q'), 16);
  assert.equal(colToIndex('AA'), 26);
});

test('parseDMYDate: no zero-pad D-M-YYYY parses correctly', () => {
  assert.equal(parseDMYDate('3-8-2026'), '2026-08-03');
  assert.equal(parseDMYDate('27-7-2026'), '2026-07-27');
});

test('parseDMYDate: empty/invalid → null', () => {
  assert.equal(parseDMYDate(''), null);
  assert.equal(parseDMYDate(null), null);
  assert.equal(parseDMYDate('not a date'), null);
});

test('parseHoursNumber: comma decimal handled', () => {
  assert.equal(parseHoursNumber('240,0'), 240);
  assert.equal(parseHoursNumber('4.5'), 4.5);
  assert.equal(parseHoursNumber(''), null);
  assert.equal(parseHoursNumber(null), null);
});

const COLUMNS = {
  'No.': 'A',
  Sprint: 'B',
  Category: 'C',
  Task: 'D',
  Assignee: 'E',
  'Estimate(h)': 'F',
  'Plan Start': 'G',
  'Plan End': 'H',
  'Re-estimate(h)': 'I',
  'Actual Effort(h)': 'J',
  Status: 'K',
};

test('rowsToTasks: skips header/subtotal rows with empty Task column', () => {
  const rows = [
    ['No.', 'Sprint', 'Category', 'Task', 'Assignee', 'Estimate(h)', 'Plan Start', 'Plan End', 'Re-estimate(h)', 'Actual Effort(h)', 'Status'],
    ['', '', '', '', '', '240,0', '', '', '', '', ''], // subtotal row
    ['1', 'Sprint 1', 'Backend', 'Build API', 'LongVN', '8', '3-8-2026', '5-8-2026', '', '', 'In progress'],
  ];
  const tasks = rowsToTasks({ rows, columns: COLUMNS, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks.length, 1);
  assert.equal(tasks[0].detectedFrom, 'Sprint 1, row 3');
  assert.equal(tasks[0].title, 'Build API');
  assert.equal(tasks[0].planStart, '2026-08-03');
  assert.equal(tasks[0].planEnd, '2026-08-05');
  assert.equal(tasks[0].category, 'Backend');
});

test('rowsToTasks: forward-fills merged Category column', () => {
  const rows = [
    ['No.', 'Sprint', 'Category', 'Task', 'Assignee', 'Estimate(h)', 'Plan Start', 'Plan End', 'Re-estimate(h)', 'Actual Effort(h)', 'Status'],
    ['1', 'Sprint 1', 'Backend', 'Task A', 'LongVN', '8', '', '', '', '', 'Open'],
    ['2', 'Sprint 1', '', 'Task B', 'LongVN', '8', '', '', '', '', 'Open'],
  ];
  const tasks = rowsToTasks({ rows, columns: COLUMNS, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks[0].category, 'Backend');
  assert.equal(tasks[1].category, 'Backend');
});

test('rowsToTasks: Re-estimate(h) takes precedence over Estimate(h)', () => {
  const rows = [
    ['1', 'Sprint 1', 'Backend', 'Task A', 'LongVN', '8', '', '', '12', '', 'Open'],
  ];
  const tasks = rowsToTasks({ rows, columns: COLUMNS, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks[0].estimateHours, 12);
});

test('rowsToTasks: reads taskPriority when Priority column mapped', () => {
  const columnsWithPriority = {
    'No.': 'A',
    Sprint: 'B',
    Category: 'C',
    Task: 'D',
    Priority: 'E',
    Assignee: 'F',
    'Estimate(h)': 'G',
    'Plan Start': 'H',
    'Plan End': 'I',
    'Re-estimate(h)': 'J',
    'Actual Effort(h)': 'K',
    Status: 'L',
  };
  const rows = [['1', 'Sprint 1', 'Backend', 'Task A', 'High', 'LongVN', '8', '', '', '', '', 'Open']];
  const tasks = rowsToTasks({ rows, columns: columnsWithPriority, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks[0].taskPriority, 'High');
});

test('rowsToTasks: taskPriority is null when Priority column not mapped', () => {
  const rows = [['1', 'Sprint 1', 'Backend', 'Task A', 'LongVN', '8', '', '', '', '', 'Open']];
  const tasks = rowsToTasks({ rows, columns: COLUMNS, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks[0].taskPriority, null);
});

test('rowsToTasks: isDone true only when Status in statusDoneValues', () => {
  const rows = [
    ['1', 'Sprint 1', 'Backend', 'Task A', 'LongVN', '8', '', '', '', '', 'Done'],
    ['2', 'Sprint 1', 'Backend', 'Task B', 'LongVN', '8', '', '', '', '', 'In progress'],
  ];
  const tasks = rowsToTasks({ rows, columns: COLUMNS, tabName: 'Sprint 1', statusDoneValues: ['Done'] });
  assert.equal(tasks[0].isDone, true);
  assert.equal(tasks[1].isDone, false);
});

test('jiraIssuesToTasks: maps core fields', () => {
  const issues = [
    {
      key: 'NEX-1',
      fields: {
        summary: 'Fix bug',
        assignee: { displayName: 'LongVN' },
        status: { name: 'In Progress', statusCategory: { key: 'indeterminate' } },
        duedate: '2026-08-01',
        timeoriginalestimate: 3600 * 4,
        timespent: 3600 * 2,
        updated: '2026-07-27T10:00:00.000+0000',
        customfield_10020: [{ name: 'Sprint 1' }],
      },
    },
  ];
  const tasks = jiraIssuesToTasks(issues);
  assert.equal(tasks[0].id, 'NEX-1');
  assert.equal(tasks[0].isDone, false);
  assert.equal(tasks[0].estimateHours, 4);
  assert.equal(tasks[0].actualHours, 2);
  assert.equal(tasks[0].sprint, 'Sprint 1');
  assert.equal(tasks[0].detectedFrom, 'NEX-1');
});
