// P19.5: the activity halo (ADR-0024 §5-6, P18 A8 as amended, ADR-0028 §3).
// A halo is Core's state in the read the view holds: present on a node whose
// presentation class is `active`, gone once a read shows it is not, static,
// in the static layer, never a frame. Rendered with the deterministic
// harness (renderAt); mutation-verified by tools/mutate_p19_5.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MOTIONS } from '../src/state/motion.ts';
import { ALPHA } from '../src/state/tokens.ts';
import { Timeline } from '../src/state/timeline.ts';
import { Loop } from '../src/graph/loop.ts';
import { mirrorRows } from '../src/graph/mirror.ts';
import { allExpanded, build, haloed, keyOf, lifted, visible, type GraphData } from '../src/graph/model.ts';
import { frame, HALO_RINGS, type Scene } from '../src/graph/render.ts';
import { present } from '../src/state/present.ts';
import { fakeHost, recorder, renderAt } from './motion-harness.ts';

const isActive = (m: string, s: string) => present(m, s).cls === 'active';
const X1 = { kind: 'execution', id: 'exe_1' };
const X2 = { kind: 'execution', id: 'exe_2' };
const T = { kind: 'task', id: 'tsk_1' };

function data(x1: string, x2 = 'ENDED_OK'): GraphData {
  return {
    nodes: [
      { ...X1, label: 'first', machine: 'execution', state: x1 },
      { ...X2, label: 'second', machine: 'execution', state: x2 },
      { ...T, label: 'task', machine: 'task', state: 'COMPLETED' },
    ],
    edges: [
      { id: 'a', field: 'executions.task_id', from: X1, to: T },
      { id: 'b', field: 'executions.task_id', from: X2, to: T },
    ],
  };
}

const POS = new Map([[keyOf(X1), { x: 0, y: 0 }], [keyOf(X2), { x: 60, y: 0 }], [keyOf(T), { x: 30, y: 40 }]]);

/** The view's scene for a read: the halo derived exactly as GraphView does. */
function scene(d: GraphData, extra: Partial<Scene> = {}): Scene {
  const m = build(d);
  const vis = visible(m, allExpanded(m));
  return {
    model: m, keys: m.nodes.map(keyOf).filter((k) => vis.has(k)), drawn: lifted(m, vis), pos: POS,
    cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: new Set(), liveStatic: false,
    pulse: new Map(), halo: haloed(m, isActive), colour: (v) => v, width: 100, height: 100, dpr: 1, ...extra,
  };
}

const TL = new Timeline(); // nothing presented: the halo needs no timeline
const ops = (s: Scene, t = 0) => renderAt(s, TL, t).ops;
/** The halo rings drawn: the arcs of every path stroked in --state-active. */
function rings(o: string[]): string[] {
  const out: string[] = [];
  let blue = false;
  let path: string[] = [];
  for (const op of o) {
    if (op.startsWith('strokeStyle=')) blue = op === 'strokeStyle=--state-active';
    else if (op === 'beginPath()') path = [];
    else if (op.startsWith('arc(')) path.push(op);
    else if (op === 'stroke()' && blue) out.push(...path);
  }
  return out;
}
const R = 7; // an execution is a triangle of radius 7 (encoding.radiusOf)

/** The ops without each live node's core: thread ink, one arc, one fill. */
function uncored(o: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < o.length; i++) {
    if (o[i] === 'fillStyle=--thread' && o[i + 1] === 'beginPath()' && o[i + 2]?.startsWith(`arc(`) && o[i + 3] === 'fill()') i += 3;
    else out.push(o[i]);
  }
  return out;
}

test('an inactive object has no halo; an active one has two static strokes at the approved alphas', () => {
  const still = scene(data('ENDED_OK'));
  assert.equal(still.halo.size, 0);
  assert.deepEqual(rings(ops(still)), []);
  const live = scene(data('RUNNING'));
  assert.deepEqual([...live.halo], [keyOf(X1)]);
  const o = ops(live);
  assert.deepEqual(rings(o), [`arc(0,0,${R + HALO_RINGS[0]},0,6.28)`, `arc(0,0,${R + HALO_RINGS[1]},0,6.28)`]);
  assert.ok(o.includes(`globalAlpha=${ALPHA['halo-inner']}`) && o.includes(`globalAlpha=${ALPHA['halo-outer']}`));
  assert.deepEqual([ALPHA['halo-outer'], ALPHA['halo-inner']], [0.35, 0.7], 'the ADR-0028 halo alphas');
});

test('the halo follows presentation class active and nothing else (no fake activity)', () => {
  for (const [state, want] of [['INTENT', 1], ['STARTING', 1], ['RUNNING', 1], ['HANDING_OFF', 1], ['AWAITING_APPROVAL', 0], ['PAUSED', 0], ['STOPPING', 0], ['LOST', 0], ['ENDED_OK', 0], ['ENDED_ERROR', 0]] as const)
    assert.equal(scene(data(state)).halo.size, want, state);
  // a node with no machine state (a file, a project) is never live
  const m = build({ nodes: [{ kind: 'file', id: 'f', label: 'f' }, { kind: 'project', id: 'p', label: 'p' }], edges: [] });
  assert.equal(haloed(m, () => true).size, 0);
});

test('the halo is still: every presentation time draws the same picture, and it asks for no frame', () => {
  const s = scene(data('RUNNING'));
  const at0 = ops(s, 0);
  for (const t of [1, 240, 600, 1e6]) assert.deepEqual(ops(s, t), at0, `the halo changed at t=${t}`);
  assert.deepEqual(TL.at(1e6), []);
  assert.equal(new Timeline().start('activity-halo', keyOf(X1), 1, 0, false), false, 'a static entry started as a motion');
  // a mounted loop asked only to draw it once parks and asks for nothing after
  const h = fakeHost();
  const l = new Loop(h, () => void ops(s));
  l.request();
  h.run();
  const asked = h.asked();
  for (let i = 0; i < 50; i++) {
    h.tick(1000);
    h.run();
  }
  assert.equal(asked, 1);
  assert.equal(h.asked(), asked, 'an active halo kept the loop running');
  assert.equal(l.state, 'parked');
});

test('it is in the static layer: a frame over an unchanged halo reuses the layer; a changed halo redraws it', () => {
  const layer = { ctx: recorder().ctx, sig: null as readonly unknown[] | null };
  const s = scene(data('RUNNING'));
  assert.equal(frame(recorder().ctx, layer, s).layer, true);
  assert.equal(frame(recorder().ctx, layer, s).layer, false, 'the same halo redrew the static layer');
  assert.equal(frame(recorder().ctx, layer, { ...s, halo: new Set() }).layer, true, 'a halo that ended left the layer as it was');
});

test('a reconnect or resync that re-reads the same state keeps the same halo, drawn the same', () => {
  // the re-read is new objects with the same state: a new model, the same picture
  const before = ops(scene(data('RUNNING')));
  const reread = scene(data('RUNNING'));
  assert.deepEqual(ops(reread), before, 'the re-read redrew the halo differently');
  assert.deepEqual([...reread.halo], [keyOf(X1)]);
});

test('completion: a read showing the work ended removes the halo, leaving the inactive picture', () => {
  const ended = ops(scene(data('ENDED_OK')));
  assert.deepEqual(rings(ended), []);
  assert.deepEqual(ended, ops(scene(data('ENDED_OK'))));
  // and a remount of a view over the ended read invents nothing
  assert.equal(haloed(build(data('ENDED_OK')), isActive).size, 0);
});

test('reduced motion keeps the halo; forced colours or reduced transparency make it one solid ring', () => {
  const live = scene(data('RUNNING'));
  assert.deepEqual(rings(ops({ ...live, liveStatic: true })), rings(ops(live)), 'reduced motion dropped the halo');
  const solid = ops({ ...live, opaque: true });
  assert.deepEqual(rings(solid), [`arc(0,0,${R + HALO_RINGS[0]},0,6.28)`]);
  assert.ok(solid.includes('globalAlpha=1') && !solid.includes(`globalAlpha=${ALPHA['halo-outer']}`));
});

test('several live objects each carry their own halo; the others are drawn exactly as before', () => {
  const both = scene(data('RUNNING', 'STARTING'));
  assert.deepEqual([...both.halo].sort(), [keyOf(X1), keyOf(X2)].sort());
  const r = rings(ops(both));
  assert.equal(r.length, 4);
  assert.ok(r.some((a) => a.startsWith('arc(60,0,')) && r.some((a) => a.startsWith('arc(0,0,')));
  // the halo is one inserted block of its own strokes: every other op — every
  // other node, edge and label — is exactly what the picture without it draws
  // ...and inside each live node its core (R3), the cored node's own block
  const without = ops({ ...both, halo: new Set() });
  const withHalo = uncored(ops(both));
  let a = 0;
  while (without[a] === withHalo[a]) a++;
  let z = 0;
  while (z < without.length - a && without[without.length - 1 - z] === withHalo[withHalo.length - 1 - z]) z++;
  assert.equal(a + z, without.length, 'the halo changed something besides adding its strokes');
  const block = withHalo.slice(a, withHalo.length - z);
  assert.ok(block.length && block.every((op) => /^(globalAlpha=|strokeStyle=--state-active|lineWidth|setLineDash|beginPath|moveTo|arc|stroke\()/.test(op)), block.join(' '));
});

test('the halo has a text equivalent in the mirror', () => {
  const s = scene(data('RUNNING'));
  const rows = mirrorRows(s.model, new Set(), s.halo);
  assert.equal(rows.find((r) => r.k === keyOf(X1))!.live, true);
  assert.equal(rows.find((r) => r.k === keyOf(X2))!.live, false);
  assert.equal(MOTIONS['activity-halo'].status, 'built');
  assert.equal(MOTIONS['activity-halo'].max_ms, null);
  assert.equal(MOTIONS['activity-halo'].idle, 'static');
});
