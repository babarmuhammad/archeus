// The completion toast (rulebook §17, §21 A-13; D-8): only work that ran ≥ 10 s
// and finished, by Core's own read, while nothing on screen showed it; one at a
// time; never replayed; still under reduced motion.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Timeline } from '../src/state/timeline.ts';
import { TOAST_AFTER_MS, Toasts, deserves, endedSubject, ranFor, type Ended } from '../src/state/toast.ts';

const T0 = '2026-10-03T10:00:00.000Z';
const at = (ms: number) => new Date(Date.parse(T0) + ms).toISOString();
const ended = (over: Partial<Ended> = {}): Ended => ({
  id: 'exe_1', mission_id: 'msn_1', attempt: 1, state: 'ENDED_OK', started_at: T0, ended_at: at(12_000), ...over,
});
const frame = (seq: number, id = 'exe_1', event = 'execution.ended') => ({ id: seq, event, data: { subject: { kind: 'execution', id } } });

function setup(reads: Record<string, Ended>, o: { reduced?: boolean; onScreen?: boolean } = {}) {
  const host = {
    t: 0,
    reduced: o.reduced ?? false,
    screen: o.onScreen ?? false,
    reads: 0,
  };
  const toasts = new Toasts(new Timeline(), {
    now: () => host.t,
    reduced: () => host.reduced,
    read: async (id) => {
      host.reads++;
      return reads[id];
    },
    title: async () => 'Ship the chart',
    onScreen: () => host.screen,
  });
  return { host, toasts };
}

test('only an execution.ended frame with a seq about an execution names an ended attempt', () => {
  assert.equal(endedSubject(frame(3)), 'exe_1');
  assert.equal(endedSubject({ event: 'execution.ended', data: { subject: { kind: 'execution', id: 'x' } } }), null);
  assert.equal(endedSubject(frame(3, 'exe_1', 'execution.progress')), null);
  assert.equal(endedSubject({ id: 3, event: 'execution.ended', data: { subject: { kind: 'mission', id: 'm' } } }), null);
});

test('work deserves a toast when Core read it ENDED_OK after running 10 s or more (D-8)', () => {
  assert.equal(ranFor(ended()), 12_000);
  assert.equal(deserves(ended({ ended_at: at(TOAST_AFTER_MS) })), true);
  assert.equal(deserves(ended({ ended_at: at(TOAST_AFTER_MS - 1) })), false, 'short work does not celebrate');
  assert.equal(deserves(ended({ state: 'ENDED_ERROR' })), false, 'a failure shows where it happened, never as a toast');
  assert.equal(deserves(ended({ state: 'ENDED_HANDOFF' })), false, 'a hand-off is not finished work');
  assert.equal(deserves(ended({ ended_at: null })), false, 'no time from Core, no toast');
});

test('an off-screen completion gives one toast; on screen, none', async () => {
  const a = setup({ exe_1: ended() });
  await a.toasts.frame(frame(5));
  assert.deepEqual(a.toasts.showing(), { seq: 5, mission: 'msn_1', attempt: 1, title: 'Ship the chart', still: false });
  const b = setup({ exe_1: ended() }, { onScreen: true });
  await b.toasts.frame(frame(5));
  assert.equal(b.toasts.showing(), null, 'the row on screen says it');
});

test('nothing replays: a frame heard again or an older one gives no toast, after dismissal too', async () => {
  const { toasts } = setup({ exe_1: ended(), exe_0: ended({ id: 'exe_0' }) });
  await toasts.frame(frame(5));
  toasts.dismiss(5);
  await toasts.frame(frame(5));
  assert.equal(toasts.showing(), null, 'the same seq again');
  await toasts.frame(frame(4, 'exe_0'));
  assert.equal(toasts.showing(), null, 'an older seq');
});

test('one at a time: a newer completion replaces the toast, and dismissing the old one leaves it', async () => {
  const { toasts, host } = setup({ exe_1: ended(), exe_2: ended({ id: 'exe_2', mission_id: 'msn_2', attempt: 2 }) });
  await toasts.frame(frame(5));
  host.t = 50;
  await toasts.frame(frame(6, 'exe_2'));
  assert.equal(toasts.showing()?.seq, 6);
  toasts.dismiss(5);
  assert.equal(toasts.showing()?.mission, 'msn_2', 'an old timer never takes the newer toast');
  toasts.dismiss(6);
  assert.equal(toasts.showing(), null);
});

test('reduced motion: the toast still appears, still (no fade)', async () => {
  const { toasts } = setup({ exe_1: ended() }, { reduced: true });
  await toasts.frame(frame(5));
  assert.equal(toasts.showing()?.still, true);
});

test('a failure and short work give none, and frames are read in order', async () => {
  const { toasts, host } = setup({ exe_1: ended({ state: 'ENDED_KILLED' }), exe_2: ended({ id: 'exe_2', ended_at: at(3000) }) });
  await Promise.all([toasts.frame(frame(1)), toasts.frame(frame(2, 'exe_2')), toasts.frame(frame(3, 'exe_1', 'execution.progress'))]);
  assert.equal(toasts.showing(), null);
  assert.equal(host.reads, 2, 'an unrelated frame is never read');
});
