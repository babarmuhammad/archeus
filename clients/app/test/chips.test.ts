// P21 D6: the activity chip (ADR-0024 §6, rulebook §21 A-17). An execution.hook
// frame names an execution; Core's read gives its mission and the current
// action Core recorded when it judged the call; that mission's row on screen
// shows it in words for 2.5 s (4 s when Core refused or held it). At most 3 show
// at a time; a further one waits in a queue (6 per row, the oldest dropped beyond
// that) and shows when a chip leaves, if its execution is still live then. Never
// again for an action or a frame already presented. Mutation-verified by
// tools/mutate_p21.py (Z90 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MOTIONS } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { CHIPS_PER_ROW, CHIP_TTL_ERROR_MS, CHIP_TTL_MS, Chips, QUEUE_MAX, announcement, chipText, hookSubject, type ChipFrame, type Current } from '../src/state/chips.ts';

const frame = (id: number | undefined, ex = 'ex_a', event = 'execution.hook'): ChipFrame => ({
  id,
  event,
  data: { subject: { kind: 'execution', id: ex } },
});
const act = (seq: number, over: Partial<Current> = {}): Current => ({ action_class: 'read', label: 'src/a.py', decision: 'allow', seq, ...over });

function rig(reduced = false) {
  const missions: Record<string, string> = { ex_a: 'mi_a', ex_b: 'mi_b' };
  const current: Record<string, Current | null> = { ex_a: act(1), ex_b: null };
  const states: Record<string, string> = { ex_a: 'RUNNING', ex_b: 'RUNNING' };
  const reads: string[] = [];
  const c = new Chips(new Timeline(), {
    now: () => 0,
    reduced: () => reduced,
    read: async (id) => {
      reads.push(id);
      return { mission_id: missions[id], state: states[id], current_action: current[id] };
    },
  });
  return { c, reads, current, states };
}

test('the chip is a built CSS motion with the approved budget', () => {
  const m = MOTIONS['activity-chip'];
  assert.equal(m.status, 'built');
  assert.deepEqual([...(m.css ?? [])], ['activity-chip']);
  assert.deepEqual([m.max_ms, CHIP_TTL_MS, CHIP_TTL_ERROR_MS, CHIPS_PER_ROW, m.cap_per, m.over_cap], [160, 2500, 4000, 3, 'target', 'queue']);
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
  assert.equal(chipText(act(1, { action_class: 'git_push', label: '' })), 'pushing', 'a label Core withheld leaves only the verb');
});

test('a frame chips exactly the row of the mission Core says, with Core\'s current action', async () => {
  const r = rig();
  r.c.show('mi_a');
  r.c.show('mi_b');
  await r.c.frame(frame(10));
  assert.deepEqual(r.reads, ['ex_a'], 'the execution is read again from Core');
  assert.deepEqual(r.c.chips('mi_a').map((x) => [x.seq, x.text, x.ttl, x.still, x.announce]), [[10, 'reading src/a.py', 2500, false, false]]);
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

test('at most three show; a fourth waits and shows when one leaves, first in first out', async () => {
  const r = rig();
  r.c.show('mi_a');
  for (let i = 1; i <= 5; i++) {
    r.current.ex_a = act(i);
    await r.c.frame(frame(10 + i));
  }
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [11, 12, 13], 'the fourth and fifth wait');
  r.c.dismiss('mi_a', 99);
  assert.equal(r.c.chips('mi_a').length, 3, 'a chip not on the row leaves nothing');
  r.c.dismiss('mi_a', 11);
  await r.c.idle();
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [12, 13, 14]);
  r.c.dismiss('mi_a', 12);
  await r.c.idle();
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [13, 14, 15]);
});

test('the queue holds six per row; beyond that the oldest waiting chip is dropped', async () => {
  const r = rig();
  r.c.show('mi_a');
  for (let i = 1; i <= 3 + QUEUE_MAX + 1; i++) {
    r.current.ex_a = act(i);
    await r.c.frame(frame(10 + i));
  }
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [11, 12, 13]);
  r.c.dismiss('mi_a', 11);
  await r.c.idle();
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [12, 13, 15], 'frame 14 was the oldest waiting when the seventh came: it is gone');
});

test('a queued chip whose execution has ended is never shown', async () => {
  const r = rig();
  r.c.show('mi_a');
  for (let i = 1; i <= 4; i++) {
    r.current.ex_a = act(i);
    await r.c.frame(frame(10 + i));
  }
  r.states.ex_a = 'ENDED';
  r.c.dismiss('mi_a', 11);
  await r.c.idle();
  assert.deepEqual(r.c.chips('mi_a').map((x) => x.seq), [12, 13], 'the queued fourth waited on work that already ended');
});

test('a read Core does not answer in time drops its chip; the frames after it still chip', { timeout: 5000 }, async () => {
  const c = new Chips(new Timeline(), {
    now: () => 0,
    reduced: () => false,
    readMs: 10,
    read: (id) => (id === 'ex_hang'
      ? new Promise<null>(() => undefined)
      : Promise.resolve({ mission_id: 'mi_a', state: 'RUNNING', current_action: act(1) })),
  });
  c.show('mi_a');
  await c.frame(frame(10, 'ex_hang'));
  assert.deepEqual(c.chips('mi_a'), []);
  await c.frame(frame(11, 'ex_a'));
  assert.deepEqual(c.chips('mi_a').map((x) => x.seq), [11]);
});

test('a refused or held chip is announced beside the row; an allowed one is not', async () => {
  const r = rig();
  r.c.show('mi_a');
  r.current.ex_a = act(1);
  await r.c.frame(frame(10));
  assert.equal(announcement(r.c.chips('mi_a')), undefined, 'an allowed read is not said aloud');
  r.current.ex_a = act(2, { decision: 'halt', action_class: 'exec', label: 'npm' });
  await r.c.frame(frame(11));
  const said = announcement(r.c.chips('mi_a'));
  assert.equal(said?.text, 'held: running npm');
  assert.equal(said?.seq, 11);
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
