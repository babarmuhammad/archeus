// P19.5: the motion foundation (ADR-0024 §2-§6, ADR-0029 §1): the registry
// is the only place an animation is declared, the presentation clock is
// separate from the event's own time, nothing replays, reduced motion keeps
// the meaning, and with no event nothing is scheduled. Mutation-verified.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { MOTIONS, type MotionId } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { Loop } from '../src/graph/loop.ts';
import { allExpanded, build, keyOf, lifted, visible, type GraphData } from '../src/graph/model.ts';
import type { Scene } from '../src/graph/render.ts';
import { fakeHost, renderAt } from './motion-harness.ts';

const ids = Object.keys(MOTIONS) as MotionId[];
const PULSE = MOTIONS['execution-pulse'].max_ms;

// ── the registry ──

test('every registered motion carries the metadata ADR-0024 §3 asks for', () => {
  assert.ok(ids.length >= 7, 'read the registry');
  for (const id of ids) {
    const m = MOTIONS[id];
    for (const k of ['status', 'source', 'trigger', 'driven_by', 'runs_on', 'idle', 'reduced', 'equivalent'] as const)
      assert.ok(m[k], `${id} has no ${k}`);
    assert.ok(m.surfaces.length, `${id} names no surface`);
    assert.equal(m.replay, false, `${id} may replay`);
    if (m.max_ms === null) assert.equal(m.idle, 'static', `${id}: only a static entry may be there while idle`);
    else {
      assert.ok(m.max_ms > 0 && m.easing, `${id}: an animation is finite and names its easing`);
      assert.equal(m.idle, 'never', `${id} animates while idle`);
      assert.notEqual(m.driven_by, 'state', `${id}: an animation is triggered by an event or the user`);
    }
  }
});

test('the travelling marker is 600 ms at most and 8 at once, oldest dropped (ADR-0024 §6)', () => {
  const m = MOTIONS['travelling-marker'];
  assert.ok(m.max_ms <= 600, `${m.max_ms} ms`);
  assert.ok(m.cap <= 8, `${m.cap} at once`);
  assert.equal(m.over_cap, 'drop-oldest');
  assert.equal(MOTIONS['execution-pulse'].max_ms, 240);
  assert.equal(MOTIONS['execution-pulse'].cap, 12);
  assert.equal(MOTIONS['execution-pulse'].min_interval_ms, 2000);
});

// every `.animate(` in the client names a built loop motion by its id: a
// WAAPI element.animate(), a duration or an approved-but-unbuilt id fails
const SRC = new URL('../src/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
function sources(): [string, string][] {
  const out: [string, string][] = [];
  const walk = (dir: string) => {
    for (const f of readdirSync(dir)) {
      const p = join(dir, f);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.tsx?$/.test(f) && !p.replace(/\\/g, '/').endsWith('state/motion.ts'))
        out.push([p.replace(/\\/g, '/'), readFileSync(p, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')]);
    }
  };
  walk(SRC);
  return out;
}

test('every animation the client starts is a registered, built motion; nothing approved is used yet', () => {
  const used = new Set<string>();
  let calls = 0;
  for (const [p, src] of sources()) {
    for (const m of src.matchAll(/\.animate\(([^)]*)\)/g)) {
      calls++;
      const id = /^\s*'([a-z-]+)'\s*$/.exec(m[1])?.[1];
      assert.ok(id && id in MOTIONS, `${p}: .animate(${m[1]}) is not a registered motion`);
      const e = MOTIONS[id as MotionId];
      assert.ok(e.status === 'built' && e.runs_on === 'loop', `${p}: ${id} is not a built loop motion`);
      used.add(id!);
    }
    for (const id of ids)
      if (MOTIONS[id].status === 'approved') assert.ok(!src.includes(`'${id}'`), `${p} uses ${id}, which is not built: set its status first`);
  }
  assert.ok(calls >= 2, 'read the call sites');
  for (const id of ids)
    if (MOTIONS[id].status === 'built' && MOTIONS[id].runs_on === 'loop') assert.ok(used.has(id), `${id} is built but nothing runs it`);
});

// ── two clocks and renderAt (ADR-0024 §5, ADR-0029 §1) ──

const X = { kind: 'execution', id: 'exe_1' };
const T = { kind: 'task', id: 'tsk_1' };
const DATA: GraphData = {
  nodes: [
    { ...X, label: 'run', machine: 'execution', state: 'RUNNING' },
    { ...T, label: 'task', machine: 'task', state: 'RUNNING' },
  ],
  edges: [{ id: 'x-t', field: 'executions.task_id', from: X, to: T, tier: 'EXTRACTED' }],
};

function scene(): Scene {
  const m = build(DATA);
  const vis = visible(m, allExpanded(m));
  const keys = m.nodes.map(keyOf).filter((k) => vis.has(k));
  return {
    model: m, keys, drawn: lifted(m, vis), pos: new Map([[keyOf(X), { x: 10, y: 10 }], [keyOf(T), { x: 60, y: 40 }]]),
    cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: new Set(), liveStatic: false,
    pulse: new Map(), colour: (v) => v, width: 100, height: 100, dpr: 1,
  };
}

test('idle: an empty timeline shows nothing at any time and the picture is the static one', () => {
  const tl = new Timeline();
  const s = scene();
  const still = renderAt(s, tl, 0).ops;
  for (const t of [0, 1, 240, 1e6]) {
    assert.deepEqual(tl.at(t), []);
    assert.deepEqual(renderAt(s, tl, t).ops, still, `the idle picture changed at t=${t}`);
  }
});

test('renderAt: the same event and the same presentation time give the same picture; an active motion moves; an ended one is gone', () => {
  const s = scene();
  const edge = s.drawn[0].id;
  const tl = new Timeline();
  const still = renderAt(s, tl, 0).ops;
  assert.equal(tl.start('execution-pulse', edge, 7, 1000, false), true);
  const again = new Timeline();
  again.start('execution-pulse', edge, 7, 1000, false);
  const mid = renderAt(s, tl, 1000 + PULSE / 2).ops;
  assert.deepEqual(renderAt(s, again, 1000 + PULSE / 2).ops, mid, 'same event, same t, different picture');
  assert.deepEqual(renderAt(s, tl, 1000 + PULSE / 2).ops, mid, 'rendering twice changed the picture');
  assert.notDeepEqual(renderAt(s, tl, 1000).ops, mid, 'the pulse did not move between t=0 and t=½');
  assert.notDeepEqual(mid, still, 'the active pulse is not drawn');
  assert.equal(tl.progress('execution-pulse', 1000).get(edge), 0);
  assert.equal(tl.progress('execution-pulse', 1000 + PULSE / 2).get(edge), 0.5);
  assert.deepEqual(tl.at(999), [], 'drawn before it began');
  assert.deepEqual(tl.at(1000 + PULSE), [], 'still animated when it ended');
  assert.deepEqual(renderAt(s, tl, 1000 + PULSE).ops, still, 'the completed pulse left the picture changed');
  assert.deepEqual(renderAt(s, tl, 1e9).ops, still);
});

test('no replay: an event read again — reconnect, resync, a second tab — never restarts its presentation', () => {
  const tl = new Timeline();
  assert.equal(tl.start('execution-pulse', 'e1', 5, 0, false), true);
  // the reconnect re-sends seq 5 at t=100: refused, and the pulse keeps its start
  assert.equal(tl.start('execution-pulse', 'e1', 5, 100, false), false, 'a re-read event restarted');
  assert.equal(tl.progress('execution-pulse', 100).get('e1'), 100 / PULSE, 'the pulse restarted from zero');
  assert.equal(tl.start('execution-pulse', 'e2', 4, 100, false), false, 'an older event presented');
  assert.equal(tl.start('execution-pulse', 'e1', undefined, 100, false), false, 'an event with no seq presented');
  // after it ended, the same event still never plays again
  assert.equal(tl.start('execution-pulse', 'e1', 5, 10_000, false), false);
  assert.deepEqual(tl.at(10_000), []);
  // a genuinely new event does
  assert.equal(tl.start('execution-pulse', 'e1', 6, 10_000, false), true);
});

test('reduced motion: nothing starts, the event still counts as presented, so it never plays later', () => {
  const tl = new Timeline();
  assert.equal(tl.start('execution-pulse', 'e1', 9, 0, true), false);
  assert.deepEqual(tl.at(0), []);
  assert.equal(tl.start('execution-pulse', 'e1', 9, 1, false), false, 'switching reduced motion off replayed an event');
  for (const id of ids) assert.ok(MOTIONS[id].reduced.length > 8, `${id} has no reduced-motion equivalent`);
});

test('caps: a start at the cap is refused, or drops the oldest where the registry says so; a static entry never starts', () => {
  const tl = new Timeline();
  const cap = MOTIONS['execution-pulse'].cap;
  for (let i = 0; i < cap; i++) assert.equal(tl.start('execution-pulse', `e${i}`, i + 1, 0, false), true);
  assert.equal(tl.start('execution-pulse', 'over', cap + 1, 0, false), false, 'a pulse over the cap');
  assert.equal(tl.at(0).length, cap);
  const m = new Timeline();
  const mc = MOTIONS['travelling-marker'].cap;
  for (let i = 0; i <= mc; i++) m.start('travelling-marker', `e${i}`, i + 1, 0, false);
  const shown = m.at(0).map((s) => s.target);
  assert.equal(shown.length, mc);
  assert.ok(!shown.includes('e0') && shown.includes(`e${mc}`), 'the oldest marker was not the one dropped');
  assert.equal(new Timeline().start('activity-halo', 'x', 1, 0, false), false, 'a static entry animated');
});

// ── the idle invariant (ADR-0024 §2) at the loop ──

test('idle: a mounted loop with no event asks for no frame; a pulse asks for a bounded run, then none', () => {
  const h = fakeHost();
  const l = new Loop(h, () => h.tick(16));
  for (let i = 0; i < 100; i++) {
    h.tick(1000);
    h.run();
  }
  assert.equal(h.asked(), 0, 'a frame was scheduled with nothing happening');
  assert.equal(l.state, 'parked');
  l.animate('execution-pulse');
  h.run();
  const ran = h.asked();
  assert.ok(ran > 1 && ran <= Math.ceil(PULSE / 16) + 2, `${ran} frames for one ${PULSE} ms pulse`);
  for (let i = 0; i < 100; i++) {
    h.tick(1000);
    h.run();
  }
  assert.equal(h.asked(), ran, 'frames went on after the pulse ended');
  assert.equal(h.pending(), 0);
  assert.equal(l.state, 'parked');
});
