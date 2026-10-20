// P19.5 R5: the execution pulse on rows (ADR-0024 §5-6, rulebook §21 A-02).
// A frame names an execution; Core's read says its mission and whether it is
// live; that mission's row on screen pulses once, at most once per 2 s, never
// again for an event it presented, never under reduced motion or while frames
// run slow. Mutation-verified by tools/mutate_p19_5.py (N120 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MOTIONS } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { ROW_PULSE_EVERY_MS, RowPulses, pulseSubject, type PulseFrame } from '../src/state/rowpulse.ts';
import { Loop, framesSlow } from '../src/graph/loop.ts';
import { fakeHost } from './motion-harness.ts';

const frame = (id: number | undefined, ex = 'ex_a', event = 'execution.progress'): PulseFrame => ({
  id,
  event,
  data: { subject: { kind: 'execution', id: ex } },
});

function rig(over: { reduced?: boolean; degraded?: boolean; state?: string } = {}) {
  let now = 0;
  const flags = { reduced: !!over.reduced, degraded: !!over.degraded };
  const missions: Record<string, string> = { ex_a: 'mi_a', ex_b: 'mi_b' };
  const reads: string[] = [];
  const p = new RowPulses(new Timeline(), {
    now: () => now,
    reduced: () => flags.reduced,
    degraded: () => flags.degraded,
    read: async (id) => {
      reads.push(id);
      if (!(id in missions)) throw new Error('no such execution');
      return { mission_id: missions[id], state: over.state ?? 'RUNNING' };
    },
  });
  let heard = 0;
  p.subscribe(() => heard++);
  return { p, reads, flags, tick: (ms: number) => void (now += ms), heard: () => heard };
}

test('the row pulse is a registered, built CSS motion with the approved budget', () => {
  const m = MOTIONS['row-pulse'];
  assert.equal(m.status, 'built');
  assert.equal(m.runs_on, 'css');
  assert.deepEqual([...(m.css ?? [])], ['row-pulse']);
  assert.equal(m.max_ms, MOTIONS['execution-pulse'].max_ms);
  assert.equal(ROW_PULSE_EVERY_MS, 2000);
  assert.equal(MOTIONS['activity-chip'].status, 'approved', 'the chip is not built in R5');
});

test('only an execution.* frame with a seq, about an execution, can pulse a row', () => {
  assert.equal(pulseSubject(frame(5)), 'ex_a');
  assert.equal(pulseSubject(frame(undefined)), null, 'no seq: nothing to mark as presented');
  assert.equal(pulseSubject(frame(5, 'ex_a', 'mission.state_changed')), null);
  assert.equal(pulseSubject({ id: 5, event: 'execution.progress', data: { subject: { kind: 'task', id: 't' } } }), null);
  assert.equal(pulseSubject({ id: 5, event: 'resync' }), null);
});

test('a frame pulses exactly the row of the mission Core says the execution belongs to', async () => {
  const r = rig();
  r.p.show('mi_a');
  r.p.show('mi_b');
  await r.p.frame(frame(10, 'ex_a'));
  assert.deepEqual(r.reads, ['ex_a'], 'the execution is read again from Core');
  assert.equal(r.p.seq('mi_a'), 10);
  assert.equal(r.p.seq('mi_b'), 0, 'another mission\'s row');
  assert.equal(r.heard(), 1, 'exactly one pulse');
});

test('a row not on screen pulses nothing, and nothing on screen reads nothing', async () => {
  const r = rig();
  await r.p.frame(frame(10, 'ex_a'));
  assert.deepEqual(r.reads, []);
  const off = r.p.show('mi_b');
  await r.p.frame(frame(11, 'ex_a'));
  assert.equal(r.p.seq('mi_a'), 0);
  off();
  await r.p.frame(frame(12, 'ex_b'));
  assert.equal(r.heard(), 0);
});

test('an execution Core reads as not live pulses nothing; a failed read pulses nothing and the next frame still works', async () => {
  const ended = rig({ state: 'ENDED_OK' });
  ended.p.show('mi_a');
  await ended.p.frame(frame(10));
  assert.equal(ended.heard(), 0);
  const r = rig();
  r.p.show('mi_a');
  await r.p.frame(frame(10, 'ex_gone'));
  await r.p.frame(frame(11, 'ex_a'));
  assert.equal(r.p.seq('mi_a'), 11);
});

test('at most one pulse per row every 2 s', async () => {
  const r = rig();
  r.p.show('mi_a');
  r.p.show('mi_b');
  await r.p.frame(frame(10));
  r.tick(ROW_PULSE_EVERY_MS - 1);
  await r.p.frame(frame(11));
  assert.equal(r.p.seq('mi_a'), 10, 'inside the interval');
  await r.p.frame(frame(12, 'ex_b'));
  assert.equal(r.p.seq('mi_b'), 12, 'the interval is per row');
  r.tick(1);
  await r.p.frame(frame(13));
  assert.equal(r.p.seq('mi_a'), 13, 'once the interval has passed');
  assert.equal(r.heard(), 3);
});

test('an event already presented never pulses again: the same seq, an older one, a resync', async () => {
  const r = rig();
  r.p.show('mi_a');
  await r.p.frame(frame(10));
  r.tick(10_000);
  await r.p.frame(frame(10));
  await r.p.frame(frame(9));
  await r.p.frame({ event: 'resync' });
  await r.p.frame({ event: 'stream-open' });
  assert.equal(r.p.seq('mi_a'), 10);
  assert.equal(r.heard(), 1);
});

test('under reduced motion no pulse starts, and the event still counts as presented', async () => {
  const r = rig({ reduced: true });
  r.p.show('mi_a');
  await r.p.frame(frame(10));
  assert.equal(r.heard(), 0);
  assert.deepEqual(r.reads, [], 'nothing to draw: nothing read');
  r.flags.reduced = false;
  await r.p.frame(frame(10));
  assert.equal(r.heard(), 0, 'switching reduced motion off replays nothing');
  await r.p.frame(frame(11));
  assert.equal(r.heard(), 1);
});

test('while frames run slow no pulse starts, and the event still counts as presented', async () => {
  const r = rig({ degraded: true });
  r.p.show('mi_a');
  await r.p.frame(frame(10));
  assert.equal(r.heard(), 0);
  r.flags.degraded = false;
  await r.p.frame(frame(10));
  assert.equal(r.heard(), 0);
});

test('frames are handled in order: a slow read never lets an older event lose to a newer one', async () => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const p = new RowPulses(new Timeline(), {
    now: () => 0,
    reduced: () => false,
    degraded: () => false,
    read: async (id) => {
      if (id === 'ex_a') await gate;
      return { mission_id: id === 'ex_a' ? 'mi_a' : 'mi_b', state: 'RUNNING' };
    },
  });
  p.show('mi_a');
  p.show('mi_b');
  const a = p.frame(frame(10, 'ex_a'));
  const b = p.frame(frame(11, 'ex_b'));
  release();
  await Promise.all([a, b]);
  assert.equal(p.seq('mi_a'), 10);
  assert.equal(p.seq('mi_b'), 11);
});

test('the page counts as slow exactly while a loop is degraded', () => {
  const h = fakeHost();
  const l = new Loop(h, () => {
    if (l.degraded) seen.push(framesSlow());
    h.tick(25);
  });
  const seen: boolean[] = [];
  assert.equal(framesSlow(), false);
  l.animate('execution-pulse');
  h.run();
  assert.ok(seen.length && seen.every(Boolean), 'slow while degraded');
  assert.equal(framesSlow(), false, 'and not once the animation ended');
});

test('the rows read the page\'s reduced motion and its slow frames', () => {
  const ui = readFileSync(new URL('../src/components/ui.tsx', import.meta.url), 'utf8');
  assert.match(ui, /reduced: reducedMotion,\r?\n\s+degraded: framesSlow,/);
});
