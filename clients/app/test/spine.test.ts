// The spine (ADR-0054): where a mission is, from its state and held_from only.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PRESENTATION } from '../src/state/presentation.ts';
import { present } from '../src/state/present.ts';
import { SPINE } from '../src/state/spineTable.ts';
import { spineOf } from '../src/state/spine.ts';

const STATES = Object.keys(PRESENTATION.mission);
const TOTAL = SPINE.stations.length;
const HOLDS = ['BLOCKED', 'PAUSED'];
const STATION_STATES = STATES.filter((s) => SPINE.states[s as keyof typeof SPINE.states].kind === 'current');
const letters = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean);

test('every mission state of the presentation table has a position, and the table has no other', () => {
  assert.deepEqual(Object.keys(SPINE.states).sort(), [...STATES].sort());
  for (const s of STATES) {
    const x = spineOf(s, null);
    assert.equal(x.marks.length, TOTAL, s);
    assert.ok(x.text.length > 0, s);
  }
});

test('the six stations are named by a word Core uses for the state they sit on', () => {
  assert.equal(TOTAL, 6);
  SPINE.stations.forEach((st, i) => {
    const on = SPINE.states[st.anchor as keyof typeof SPINE.states] as { kind: string; station?: number };
    assert.deepEqual([on.kind, on.station], ['current', i + 1], st.label);
    assert.ok(present('mission', st.anchor).label.toLowerCase().includes(st.label.toLowerCase()), st.label);
  });
});

test('a held mission sits on the station of held_from, whichever state it held from', () => {
  for (const hold of HOLDS) {
    for (const from of STATION_STATES) {
      const x = spineOf(hold, from);
      const at = spineOf(from, null).marks.indexOf('current') + 1;
      assert.equal(x.at, at, `${hold} from ${from}`);
      assert.equal(x.marks.filter((m) => m === 'held').length, 1);
      assert.equal(x.marks[at - 1], 'held');
      assert.ok(x.marks.slice(0, at - 1).every((m) => m === 'passed'));
      assert.ok(x.marks.slice(at).every((m) => m === 'ahead'));
      assert.equal(x.look?.cls, present('mission', hold).cls);
    }
  }
  assert.deepEqual(spineOf('BLOCKED', 'EXECUTING').marks, ['passed', 'passed', 'passed', 'held', 'ahead', 'ahead']);
  assert.equal(spineOf('BLOCKED', 'EXECUTING').text, 'Blocked at step 4 of 6 (Executing).');
  assert.equal(spineOf('PAUSED', 'EXECUTING').text, 'Paused at step 4 of 6 (Executing).');
});

test('never guess: a hold without a held_from that names a station has no position', () => {
  for (const hold of HOLDS) {
    for (const bad of [undefined, null, '', 'NOT_A_STATE', 'COMPLETED', 'APPROVED', 'BLOCKED', 'CREATED', 'executing', 7, {}, [], '__proto__', 'constructor', 'toString']) {
      const x = spineOf(hold, bad);
      assert.deepEqual(x.marks, Array(TOTAL).fill('unknown'), `${hold} ${String(bad)}`);
      assert.equal(x.at, null);
      assert.equal(x.look, null);
      assert.equal(x.text, `${present('mission', hold).label}, position unknown.`);
    }
  }
  assert.deepEqual(spineOf('RESUMED', undefined).marks, Array(TOTAL).fill('unknown'));
  assert.equal(spineOf('RESUMED', 'REASONING').at, 1);
});

test('a station state ignores held_from', () => {
  for (const s of STATION_STATES) assert.deepEqual(spineOf(s, 'VERIFYING'), spineOf(s, null), s);
  assert.deepEqual(spineOf('FAILED', 'VERIFYING'), spineOf('FAILED', null));
});

test('CANCELLED draws no stations and ignores a leftover held_from', () => {
  const plain = spineOf('CANCELLED', null);
  assert.deepEqual(plain.marks, Array(TOTAL).fill('none'));
  for (const from of [...STATION_STATES, 'COMPLETED', 'garbage']) assert.deepEqual(spineOf('CANCELLED', from), plain);
  assert.equal(plain.text, 'Cancelled.');
  assert.equal(plain.done, false);
});

test('only COMPLETED is all passed and Done', () => {
  for (const s of STATES) {
    for (const from of [null, 'EXECUTING']) {
      const x = spineOf(s, from);
      assert.equal(x.done, s === 'COMPLETED', s);
      assert.equal(x.marks.every((m) => m === 'passed'), s === 'COMPLETED', s);
    }
  }
  assert.equal(spineOf('COMPLETED', null).text, 'Done — verified and reviewed, all 6 steps passed.');
  assert.deepEqual(spineOf('APPROVED', null).marks, ['passed', 'passed', 'passed', 'ahead', 'ahead', 'ahead']);
  assert.equal(spineOf('APPROVED', null).text, 'Approved — not started, 3 of 6 steps passed.');
});

test('a station state shows itself current, the stations before it passed and after it ahead', () => {
  const want: Record<string, number> = {
    UNDERSTANDING: 1, CONTEXT_GATHERING: 1, REASONING: 1, PLANNING: 2, REPLANNING: 2, APPROVAL_REQUIRED: 3,
    EXECUTING: 4, VERIFYING: 5, REVIEWING: 6,
  };
  for (const [s, n] of Object.entries(want)) {
    const x = spineOf(s, null);
    assert.equal(x.at, n, s);
    assert.deepEqual(x.marks, Array.from({ length: TOTAL }, (_, i) => (i + 1 < n ? 'passed' : i + 1 === n ? 'current' : 'ahead')), s);
    assert.equal(x.text, `${present('mission', s).label}, step ${n} of 6.`);
  }
  assert.equal(spineOf('APPROVAL_REQUIRED', null).look?.glyph, '◆');
  assert.equal(spineOf('FAILED', null).text, 'Failed at step 4 of 6 (Executing).');
  assert.equal(spineOf('FAILED', null).marks[3], 'failed');
  assert.equal(spineOf('CREATED', null).text, 'Created, not started.');
  assert.deepEqual(spineOf('CREATED', null).marks, Array(TOTAL).fill('ahead'));
});

test('Verifying comes before Reviewing, and a replan puts the later stations ahead again', () => {
  assert.equal(spineOf('VERIFYING', null).at, 5);
  assert.equal(spineOf('REVIEWING', null).at, 6);
  assert.deepEqual(spineOf('REPLANNING', null).marks.slice(2), ['ahead', 'ahead', 'ahead', 'ahead']);
});

test('a state this client does not know draws its own word and no stations', () => {
  assert.deepEqual(spineOf('FROM_A_NEWER_CORE', 'EXECUTING'), { marks: [], at: null, done: false, look: null, text: 'FROM_A_NEWER_CORE' });
});

test('every sentence is Core\'s state word, a station word or the spine\'s few fixed words: none is invented', () => {
  const fixed = new Set(['step', 'of', 'steps', 'passed', 'at', 'position', 'unknown', 'not', 'started', 'all']);
  const stations = new Set(SPINE.stations.flatMap((s) => letters(s.label)));
  const cases: [string, unknown][] = [];
  for (const s of STATES) cases.push([s, null]);
  for (const h of HOLDS) for (const from of STATION_STATES) cases.push([h, from]);
  cases.push(['RESUMED', 'EXECUTING'], ['BLOCKED', null]);
  for (const [s, from] of cases) {
    const word = new Set(letters(present('mission', s).label));
    for (const w of letters(spineOf(s, from).text)) {
      assert.ok(word.has(w) || stations.has(w) || fixed.has(w) || /^\d+$/.test(w), `${s}/${String(from)}: "${w}"`);
    }
  }
});
