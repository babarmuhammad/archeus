import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spineOf, spineText, isOpenMission, STATIONS } from '../spine-model.js';
import { WORDS, present } from '../core-words.js';

const MISSION_STATES = Object.keys(WORDS.machines.mission);
const stationStates = { UNDERSTANDING: 1, CONTEXT_GATHERING: 1, REASONING: 1, PLANNING: 2, REPLANNING: 2, APPROVAL_REQUIRED: 3, APPROVED: 3, EXECUTING: 4, VERIFYING: 5, REVIEWING: 6 };

test('every Core mission state has a spine and a sentence', () => {
  assert.equal(MISSION_STATES.length, 17);
  for (const s of MISSION_STATES) {
    const r = spineOf(s, s === 'BLOCKED' || s === 'PAUSED' ? 'EXECUTING' : null);
    assert.ok(r.text.length > 3, s);
    assert.ok(r.marks.length === 6, s);
  }
});

test('each station name is a word Core itself uses for its anchor state', () => {
  const anchors = ['UNDERSTANDING', 'PLANNING', 'APPROVAL_REQUIRED', 'EXECUTING', 'VERIFYING', 'REVIEWING'];
  anchors.forEach((a, i) => assert.ok(present('mission', a).label.toLowerCase().includes(STATIONS[i].toLowerCase()), STATIONS[i]));
});

test('station states put the current mark on their station and everything before it passed', () => {
  for (const [s, n] of Object.entries(stationStates)) {
    if (s === 'APPROVED') continue;
    const r = spineOf(s);
    assert.equal(r.station, n);
    r.marks.forEach((m, i) => assert.equal(m.kind, i + 1 < n ? 'passed' : i + 1 === n ? 'current' : 'ahead', s + ' ' + i));
  }
  const ap = spineOf('APPROVED');
  assert.deepEqual(ap.marks.map((m) => m.kind), ['passed', 'passed', 'passed', 'ahead', 'ahead', 'ahead']);
  assert.match(ap.text, /3 of 6 steps passed/);
});

test('BLOCKED and PAUSED sit on the station of held_from, and say so in words', () => {
  const b = spineOf('BLOCKED', 'EXECUTING');
  assert.equal(b.station, 4); assert.equal(b.marks[3].cls, 'blocked');
  assert.equal(b.text, 'Blocked at step 4 of 6 (Executing).');
  assert.equal(spineOf('PAUSED', 'EXECUTING').marks[3].cls, 'paused');
  assert.equal(spineOf('BLOCKED', 'UNDERSTANDING').station, 1);
});

test('never guess: a hold with no valid held_from draws every station unknown', () => {
  for (const held of [null, undefined, '', 'COMPLETED', 'CANCELLED', 'NOPE', 'BLOCKED']) {
    const r = spineOf('BLOCKED', held);
    assert.equal(r.unknown, true, String(held));
    assert.ok(r.marks.every((m) => m.kind === 'unknown'));
    assert.equal(r.text, 'Blocked, position unknown.');
    assert.ok(r.segments.every((x) => x === 'dotted'));
  }
  assert.equal(spineOf('PAUSED', null).text, 'Paused, position unknown.');
});

test('only COMPLETED is all passed and done; CANCELLED ignores a left-over held_from', () => {
  for (const s of MISSION_STATES) {
    const r = spineOf(s, 'EXECUTING');
    assert.equal(r.done, s === 'COMPLETED', s);
    if (s !== 'COMPLETED') assert.ok(!r.marks.every((m) => m.kind === 'passed'), s);
  }
  const c = spineOf('CANCELLED', 'EXECUTING');
  assert.equal(c.text, 'Cancelled.'); assert.ok(c.marks.every((m) => m.kind === 'none'));
  assert.equal(spineOf('FAILED').station, 4);
  assert.equal(spineOf('FAILED').marks[3].cls, 'failed');
  assert.equal(spineOf('CREATED').text, present('mission', 'CREATED').label + ', not started.');
});

test('a state this client does not know draws its own word and no stations', () => {
  const r = spineOf('SOMETHING_NEW');
  assert.equal(r.marks.length, 0); assert.equal(r.text, 'SOMETHING_NEW');
});

test('replanning shows the later stations ahead again', () => {
  const r = spineOf('REPLANNING');
  assert.deepEqual(r.marks.map((m) => m.kind), ['passed', 'current', 'ahead', 'ahead', 'ahead', 'ahead']);
});

test('terminal form matches the ADR-0054 table, unicode and ascii', () => {
  const cases = [
    ['EXECUTING', null, '\u2713\u2713\u2713\u25cf\u25cb\u25cb Executing', '+++*oo Executing'],
    ['BLOCKED', 'EXECUTING', '\u2713\u2713\u2713\u25a0\u25cb\u25cb Blocked', '+++#oo Blocked'],
    ['PAUSED', 'EXECUTING', '\u2713\u2713\u2713\u2016\u25cb\u25cb Paused', '+++=oo Paused'],
    ['APPROVAL_REQUIRED', null, '\u2713\u2713\u25c6\u25cb\u25cb\u25cb Approval', '++!ooo Approval'],
    ['BLOCKED', null, '?????? Blocked', '?????? Blocked'],
    ['COMPLETED', null, '\u2713\u2713\u2713\u2713\u2713\u2713 Done', '++++++ Done'],
    ['CREATED', null, '\u25cb\u25cb\u25cb\u25cb\u25cb\u25cb Created', 'oooooo Created'],
    ['CANCELLED', null, '\u2013\u2013\u2013\u2013\u2013\u2013 Cancelled', '------ Cancelled']
  ];
  for (const [st, held, uni, asc] of cases) { assert.equal(spineText(st, held, false), uni, st); assert.equal(spineText(st, held, true), asc, st); }
});

test('isOpenMission: COMPLETED, CANCELLED and FAILED are over; every other Core state is open', () => {
  for (const s of MISSION_STATES) assert.equal(isOpenMission({ state: s }), !['COMPLETED', 'CANCELLED', 'FAILED'].includes(s), s);
  assert.equal(isOpenMission({ state: 'DONE' }), true);
});
