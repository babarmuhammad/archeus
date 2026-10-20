// P19.5 R6: the thread's T1 form (ADR-0026 §1, design system §2, rulebook §20,
// §21 A-05). Mutation-verified by tools/mutate_p19_5.py (N140 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MOTIONS } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { lineBetween, linksOf, messageHeard, targetOf, threadWords } from '../src/state/thread.ts';

test('the thread travel is a built CSS motion: 600 ms, once, one at a time', () => {
  const m = MOTIONS['thread-travel'];
  assert.equal(m.status, 'built');
  assert.equal(m.runs_on, 'css');
  assert.deepEqual([...(m.css ?? [])], ['thread-draw']);
  assert.ok(m.max_ms <= 600);
  assert.equal(m.cap, 1);
  assert.equal(m.over_cap, 'refuse');
  assert.equal(MOTIONS['activity-chip'].status, 'approved', 'the chip stays deferred');
});

test('a message\'s links are the objects they name, in order, each once; nothing is guessed', () => {
  assert.deepEqual(
    linksOf([
      { ref: { kind: 'mission', id: 'm1' } },
      { ref: { kind: 'project', id: 'p1' } },
      { ref: { kind: 'mission', id: 'm1' } },
      { ref: { kind: 'mission' } },
      { kind: 'mission', id: 'm2' },
      null,
      'mission:m3',
    ]),
    [
      { kind: 'mission', id: 'm1' },
      { kind: 'project', id: 'p1' },
    ],
  );
});

test('only a message.created frame with a seq, about a message, says a message arrived', () => {
  const f = (id: number | undefined, event = 'message.created', kind = 'message') => ({ id, event, data: { subject: { kind, id: 'msg_1' } } });
  assert.equal(messageHeard(f(7)), 'msg_1');
  assert.equal(messageHeard(f(undefined)), null);
  assert.equal(messageHeard(f(7, 'mission.updated')), null);
  assert.equal(messageHeard(f(7, 'message.created', 'mission')), null);
  assert.equal(messageHeard({ event: 'resync' }), null);
});

test('the line goes to the first linked object whose row is on screen, and nowhere when none is', () => {
  const links = [
    { kind: 'mission', id: 'off' },
    { kind: 'mission', id: 'on' },
    { kind: 'project', id: 'on2' },
  ];
  assert.deepEqual(targetOf(links, (r) => r.id.startsWith('on')), { kind: 'mission', id: 'on' });
  assert.equal(targetOf(links, () => false), null);
});

test('the announcement names what Archeus touched (rulebook §20)', () => {
  assert.equal(threadWords(['mission Alpha']), 'Archeus updated mission Alpha');
  assert.equal(threadWords(['mission Alpha', 'project Atlas']), 'Archeus updated mission Alpha, project Atlas');
});

test('the line leaves the message on the side facing the row and ends on the row\'s near side', () => {
  const msg = { left: 600, top: 100, right: 900, bottom: 140 };
  const row = { left: 20, top: 300, right: 500, bottom: 320 };
  const l = lineBetween(msg, row);
  assert.deepEqual([l.x, l.y], [600, 120], 'leaves the message on its left, at its middle');
  assert.equal(Math.round(l.length), Math.round(Math.hypot(500 - 600, 310 - 120)), 'ends at the row\'s right side, at its middle');
  assert.ok(Math.abs(l.angle - Math.atan2(190, -100)) < 1e-9);
  const right = lineBetween(row, msg);
  assert.deepEqual([right.x, right.y], [500, 310], 'and the other way round');
});

test('one travel at a time, never twice for one message, never under reduced motion', () => {
  const t = new Timeline();
  assert.equal(t.start('thread-travel', 'message:a', 10, 0, false), true);
  assert.equal(t.start('thread-travel', 'message:b', 11, 100, false), false, 'a second while one travels is dropped');
  assert.equal(t.start('thread-travel', 'message:a', 10, 5000, false), false, 'the same event never travels again');
  assert.equal(t.start('thread-travel', 'message:c', 12, 5000, true), false, 'reduced motion: no travel');
  assert.equal(t.start('thread-travel', 'message:c', 12, 6000, false), false, 'and none later for it');
  assert.equal(t.start('thread-travel', 'message:d', 13, 6000, false), true);
});

test('Now handles each message once and draws only for an Archeus message with links', () => {
  const now = readFileSync(new URL('../src/surfaces/Now.tsx', import.meta.url), 'utf8');
  assert.match(now, /if \(id && !handled\.has\(id\)\) heard\.set\(id, f\.id!\);/);
  assert.match(now, /const links = m\.author === 'archeus' \? linksOf\(m\.links\) : \[\];/);
});
