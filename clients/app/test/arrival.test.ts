// P19.5: A-08 attention arrival (rulebook §17, §20, §21; §46.2).
// Mutation-verified by tools/mutate_p19_5.py (N294 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MOTIONS } from '../src/state/motion.ts';
import { MOTION } from '../src/state/tokens.ts';
import { Timeline } from '../src/state/timeline.ts';
import { Arrival, needsYou, tabTitle } from '../src/state/arrival.ts';

const src = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');

function rig(reduced = false) {
  let now = 0;
  const said: string[] = [];
  const flags = { reduced };
  const tl = new Timeline();
  const a = new Arrival(tl, { now: () => now, reduced: () => flags.reduced, announce: (t) => said.push(t) });
  let heard = 0;
  a.subscribe(() => heard++);
  return { a, tl, flags, said, tick: (ms: number) => void (now += ms), heard: () => heard };
}

test('attention arrival is a built CSS motion with the approved budget, bound to the badge', () => {
  const m = MOTIONS['attention-arrival'];
  assert.equal(m.status, 'built');
  assert.equal(m.runs_on, 'css');
  assert.deepEqual(m.css, ['attention-arrival']);
  assert.equal(m.max_ms, 240);
  assert.equal(MOTION.pulse, 240);
  assert.equal(m.cap, 1);
  const css = src('../src/styles/app.css');
  assert.match(css, /\.badge\[data-arrival\] \{\s*animation: attention-arrival var\(--dur-pulse\) var\(--ease\) 1;/);
});

test('the first read sets the baseline; a rise at a newer seq pulses once and is announced', () => {
  const r = rig();
  r.a.read(2, 10);
  assert.equal(r.a.current(), 0, 'the first read never pulses');
  assert.deepEqual(r.said, []);
  r.a.read(3, 11);
  assert.equal(r.a.current(), 11);
  assert.equal(r.heard(), 1);
  assert.deepEqual(r.said, ['3 things need you']);
});

test('the same count, a fall, or a read no newer than the one held is not an arrival', () => {
  const r = rig();
  r.a.read(2, 10);
  r.a.read(2, 12);
  r.a.read(1, 13);
  assert.equal(r.a.current(), 0, 'no rise, no pulse');
  r.a.read(5, 13);
  r.a.read(5, 9);
  assert.equal(r.a.current(), 0, 'a read at or below the held seq changes nothing');
  r.a.read(2, 14);
  assert.equal(r.a.current(), 14, 'a rise from the last count held (1 → 2), not from the highest ever');
  assert.deepEqual(r.said, ['2 things need you']);
});

test('no replay: the same read heard again after a reconnect or remount starts nothing', () => {
  const r = rig();
  r.a.read(0, 1);
  r.a.read(1, 2);
  r.tick(1000);
  r.a.read(1, 2);
  assert.equal(r.heard(), 1);
  assert.equal(r.said.length, 1);
});

test('reduced motion: no pulse, the announcement still happens', () => {
  const r = rig(true);
  r.a.read(0, 1);
  r.a.read(1, 2);
  assert.equal(r.a.current(), 0);
  assert.deepEqual(r.said, ['1 thing needs you']);
});

test('a read with no seq is ignored', () => {
  const r = rig();
  r.a.read(0, 1);
  r.a.read(4, undefined);
  assert.equal(r.a.current(), 0);
  assert.deepEqual(r.said, []);
});

test('the tab name and the badge label carry the count', () => {
  assert.equal(tabTitle(0), 'Archeus');
  assert.equal(tabTitle(3), '(3) Archeus');
  assert.equal(needsYou(1), '1 thing needs you');
  const app = src('../src/App.tsx');
  assert.match(app, /document\.title = tabTitle\(count\)/);
  assert.match(app, /<span key=\{arrived\} className="badge" data-arrival=\{arrived \|\| undefined\} aria-label=\{needsYou\(count\)\}>/);
});
