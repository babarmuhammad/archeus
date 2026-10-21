// P21 D6: the activity chip (ADR-0024 §6, rulebook §21 A-17). An execution.hook
// frame names an execution; Core's read gives its mission and the current
// action Core recorded when it judged the call; that mission's row on screen
// shows it in words for 2.5 s (4 s when Core refused or held it), at most 3 at a
// time, never again for an action or a frame already presented. Mutation-
// verified by tools/mutate_p21.py (Z90 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MOTIONS } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { CHIPS_PER_ROW, CHIP_TTL_ERROR_MS, CHIP_TTL_MS, Chips, chipText, hookSubject, type ChipFrame, type Current } from '../src/state/chips.ts';

const frame = (id: number | undefined, ex = 'ex_a', event = 'execution.hook'): ChipFrame => ({
  id,
  event,
  data: { subject: { kind: 'execution', id: ex } },
});
const act = (seq: number, over: Partial<Current> = {}): Current => ({ action_class: 'read', label: 'src/a.py', decision: 'allow', seq, ...over });

function rig(reduced = false) {
  const missions: Record<string, string> = { ex_a: 'mi_a', ex_b: 'mi_b' };
  const current: Record<string, Current | null> = { ex_a: act(1), ex_b: null };
  const reads: string[] = [];
  const c = new Chips(new Timeline(), {
    now: () => 0,
    reduced: () => reduced,
    read: async (id) => {
      reads.push(id);
      return { mission_id: missions[id], current_action: current[id] };
    },
  });
  return { c, reads, current };
}

test('the chip is a built CSS motion with the approved budget', () => {
  const m = MOTIONS['activity-chip'];
  assert.equal(m.status, 'built');
  assert.deepEqual([...(m.css ?? [])], ['activity-chip']);
  assert.deepEqual([m.max_ms, CHIP_TTL_MS, CHIP_TTL_ERROR_MS, CHIPS_PER_ROW, m.cap_per], [160, 2500, 4000, 3, 'target']);
});

test('only an execution.hook frame with a seq, about an execution, can chip a row', () => {
  assert.equal(hookSubject(frame(5)), 'ex_a');
  assert.equal(hookSubject(frame(undefined)), null);
  assert.equal(hookSubject(frame(5, 'ex_a', 'execution.progress')), null);
  assert.equal(hookSubject({ id: 5, event: 'execution.hook', data: { subject: { kind: 'task', id: 't' } } }), null);
});

test('the words say what the agent asked and whether Core let it', () => {
  assert.equal(chipText(act(1)), 'reading src/a.py');
  assert.equal(chipText(act(1, { action_class: 'exec', label: 'npm', decision: 'deny' })), 'refused: running npm');
  assert.equal(chipText(act(1, { action_class: 'web', label: 'example.com', decision: 'halt' })), 'held: fetching example.com');
  assert.equal(chipText(act(1, { action_class: 'mission.start', label: 'x' })), 'mission.start x', 'an unknown class is named as it is');
});

test('a frame chips exactly the row of the mission Core says, with Core\'s current action', async () => {
  const r = rig();
  r.c.show('mi_a');
  r.c.show('mi_b');
  await r.c.frame(frame(10));
  assert.deepEqual(r.reads, ['ex_a'], 'the execution is read again from Core');
  assert.deepEqual(r.c.chips('mi_a').map((x) => [x.seq, x.text, x.ttl, x.still]), [[10, 'reading src/a.py', 2500, false]]);
  assert.deepEqual(r.c.chips('mi_b'), []);
});

test('a refused or held call stays 4 s; reduced motion shows the chip without its fade', async () => {
  const r = rig(true);
  r.current.ex_a = act(1, { decision: 'deny' });
  r.c.show('mi_a');
  await r.c.frame(frame(10));
  const [x] = r.c.chips('mi_a');
  assert.equal(x.ttl, 4000);
  assert.equal(x.still, true, 'it still appears: the text is its own equivalent');
});

test('no row on screen reads nothing; a row off screen gets no chip; no action, no chip', async () => {
  const r = rig();
  await r.c.frame(frame(10));
  assert.deepEqual(r.reads, []);
  const off = r.c.show('mi_b');
  await r.c.frame(frame(11, 'ex_a'));
  assert.deepEqual(r.c.chips('mi_a'), []);
  await r.c.frame(frame(12, 'ex_b'));
  assert.deepEqual(r.c.chips('mi_b'), [], 'Core holds no current action for it');
  off();
  assert.deepEqual(r.c.chips('mi_b'), []);
});

test('nothing replays: an older frame, or the same action re-read, adds no chip', async () => {
  const r = rig();
  r.c.show('mi_a');
  await r.c.frame(frame(10));
  await r.c.frame(frame(10));
  await r.c.frame(frame(9));
  await r.c.frame(frame(11));
  assert.equal(r.c.chips('mi_a').length, 1, 'a later frame re-reading the same action is not a new action');
  r.current.ex_a = act(2);
  await r.c.frame(frame(12));
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [10, 12]);
});

test('at most three on a row; one leaving makes room; dismiss is exact', async () => {
  const r = rig();
  r.c.show('mi_a');
  for (let i = 1; i <= 4; i++) {
    r.current.ex_a = act(i);
    await r.c.frame(frame(10 + i));
  }
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [11, 12, 13], 'the fourth is not shown');
  r.c.dismiss('mi_a', 99);
  assert.equal(r.c.chips('mi_a').length, 3);
  r.c.dismiss('mi_a', 11);
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [12, 13]);
  r.current.ex_a = act(5);
  await r.c.frame(frame(20));
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [12, 13, 20]);
});

test('the chips of a row are the same array until they change', async () => {
  const r = rig();
  r.c.show('mi_a');
  const before = r.c.chips('mi_a');
  assert.equal(r.c.chips('mi_a'), before);
  await r.c.frame(frame(10));
  assert.notEqual(r.c.chips('mi_a'), before);
  assert.equal(r.c.chips('mi_a'), r.c.chips('mi_a'));
});
