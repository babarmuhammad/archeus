// P19.5: the travelling marker (ADR-0024 §5-6, rulebook §21 A-04, P18 A8 as
// amended). One marker per `execution.*` frame about a loaded execution whose
// Core-recorded `executions.task_id` edge is drawn and live: it runs from the
// execution to the task in a straight line at constant speed for the
// registry's 600 ms, at most 8 at once (oldest dropped), and never replays.
// Rendered with the deterministic harness (renderAt); mutation-verified by
// tools/mutate_p19_5.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MOTIONS } from '../src/state/motion.ts';
import { Timeline } from '../src/state/timeline.ts';
import { Loop } from '../src/graph/loop.ts';
import { widthOf } from '../src/graph/encoding.ts';
import { mirrorRows } from '../src/graph/mirror.ts';
import { allExpanded, build, haloed, keyOf, lifted, liveExecutions, markerFor, markerTarget, pulseEdge, visible, type GraphData } from '../src/graph/model.ts';
import { MARKER_HEAD, MARKER_TAIL, type Scene } from '../src/graph/render.ts';
import { present } from '../src/state/present.ts';
import { fakeHost, renderAt } from './motion-harness.ts';

const M = MOTIONS['travelling-marker'];
const MS = M.max_ms;
const isActive = (m: string, s: string) => present(m, s).cls === 'active';

const X1 = { kind: 'execution', id: 'exe_1' };
const X2 = { kind: 'execution', id: 'exe_2' };
const X3 = { kind: 'execution', id: 'exe_3' }; // ended: its edge is not live
const T1 = { kind: 'task', id: 'tsk_1' };
const T2 = { kind: 'task', id: 'tsk_2' };
const F = { kind: 'file', id: 'f' }; // an unrelated object

const DATA: GraphData = {
  nodes: [
    { ...X1, label: 'first', machine: 'execution', state: 'RUNNING' },
    { ...X2, label: 'second', machine: 'execution', state: 'RUNNING' },
    { ...X3, label: 'third', machine: 'execution', state: 'ENDED_OK' },
    { ...T1, label: 'task one', machine: 'task', state: 'RUNNING' },
    { ...T2, label: 'task two', machine: 'task', state: 'RUNNING' },
    { ...F, label: 'file' },
  ],
  edges: [
    { id: 'a', field: 'executions.task_id', from: X1, to: T1 },
    { id: 'b', field: 'executions.task_id', from: X2, to: T2 },
    { id: 'c', field: 'executions.task_id', from: X3, to: T1 },
    { id: 'd', field: 'tasks.files', from: T1, to: F },
  ],
};

// the execution on the left, its task to the right: travel is +x
const POS = new Map([
  [keyOf(X1), { x: 0, y: 0 }], [keyOf(T1), { x: 60, y: 0 }],
  [keyOf(X2), { x: 0, y: 40 }], [keyOf(T2), { x: 60, y: 40 }],
  [keyOf(X3), { x: 0, y: 80 }], [keyOf(F), { x: 100, y: 0 }],
]);

/** What GraphView derives from a read: the visible set, the drawn edges and
 * the live ones, exactly as the view does. */
function view(d: GraphData = DATA) {
  const model = build(d);
  const vis = visible(model, allExpanded(model));
  const drawn = lifted(model, vis);
  const live = new Set<string>();
  for (const x of liveExecutions(model, isActive)) {
    const e = pulseEdge(drawn, x);
    if (e) live.add(e.id);
  }
  return { model, vis, drawn, live };
}
type View = ReturnType<typeof view>;

function scene(v: View, extra: Partial<Scene> = {}): Scene {
  return {
    model: v.model, keys: v.model.nodes.map(keyOf).filter((k) => v.vis.has(k)), drawn: v.drawn, pos: POS,
    cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: v.live, liveStatic: false,
    pulse: new Map(), halo: haloed(v.model, isActive), colour: (c) => c, width: 200, height: 200, dpr: 1, ...extra,
  };
}

const frameOf = (seq: number | undefined, subject: { kind: string; id: string } = X1, event = 'execution.progress') => ({ id: seq, event, data: { subject } });

/** What GraphView's frame handler does with a frame: true when it started a marker. */
function hear(tl: Timeline, v: View, f: ReturnType<typeof frameOf>, now: number, reduced = false): boolean {
  const t = markerFor(f, v.model, v.vis, v.drawn, v.live);
  return !!t && tl.start('travelling-marker', markerTarget(t, f.id), f.id, now, reduced);
}

/** The markers drawn: heads (the arcs filled in thread ink) and tails (the
 * segments stroked in it), in camera units. */
function marks(o: string[]) {
  const heads: [number, number][] = [];
  const tails: number[][] = [];
  let fill = '';
  let stroke = '';
  let arcs: [number, number][] = [];
  let segs: number[][] = [];
  let at: number[] = [];
  for (const op of o) {
    const n = /\(([^)]*)\)/.exec(op)?.[1].split(',').map(Number) ?? [];
    if (op.startsWith('fillStyle=')) fill = op.slice(10);
    else if (op.startsWith('strokeStyle=')) stroke = op.slice(12);
    else if (op === 'beginPath()') (arcs = []), (segs = []);
    else if (op.startsWith('arc(')) arcs.push([n[0], n[1]]);
    else if (op.startsWith('moveTo(')) at = n;
    else if (op.startsWith('lineTo(')) segs.push([...at, ...n]);
    else if (op === 'fill()' && fill === '--thread') heads.push(...arcs);
    else if (op === 'stroke()' && stroke === '--thread') tails.push(...segs);
  }
  return { heads, tails };
}
const draw = (s: Scene, tl: Timeline, t: number) => renderAt(s, tl, t).ops;

test('the registry: built, event-driven, 600 ms, linear, exactly 8 at once with the oldest dropped, never idle, never replayed', () => {
  assert.equal(M.status, 'built');
  assert.equal(M.driven_by, 'event');
  assert.equal(M.runs_on, 'loop');
  assert.equal(MS, 600);
  assert.ok(MS <= 600);
  assert.equal(M.easing, 'linear');
  assert.equal(M.cap, 8);
  assert.equal(M.cap_per, 'surface');
  assert.equal(M.over_cap, 'drop-oldest');
  assert.equal(M.idle, 'never');
  assert.equal(M.replay, false);
  assert.deepEqual([...M.surfaces], ['graph']);
  assert.equal(MOTIONS['execution-pulse'].cap, 12, 'the pulse cap is its own');
});

test('no event, no marker: an empty timeline draws the static picture at every time', () => {
  const s = scene(view());
  const tl = new Timeline();
  const still = draw(s, tl, 0);
  for (const t of [0, 300, 600, 1e6]) {
    assert.deepEqual(draw(s, tl, t), still);
    assert.deepEqual(marks(draw(s, tl, t)).heads, []);
  }
});

test('an eligible frame sends one marker from the execution to its task along Core\'s edge', () => {
  const v = view();
  const t = markerFor(frameOf(1), v.model, v.vis, v.drawn, v.live);
  assert.deepEqual(t, { edge: 'a', from: keyOf(X1), to: keyOf(T1) });
  // every execution.* event names a batch of the execution's output
  for (const event of ['execution.progress', 'execution.output', 'execution.state'])
    assert.ok(markerFor(frameOf(1, X1, event), v.model, v.vis, v.drawn, v.live), event);
});

test('an unrelated event sends none: not an execution, not execution.*, not loaded, not live, no seq', () => {
  const v = view();
  const none = (f: ReturnType<typeof frameOf>) => assert.equal(markerFor(f, v.model, v.vis, v.drawn, v.live), null, JSON.stringify(f));
  none(frameOf(1, T1)); // a task's own frame
  none(frameOf(1, F));
  none(frameOf(1, X1, 'mission.updated'));
  none(frameOf(1, X1, 'task.progress'));
  none(frameOf(1, { kind: 'execution', id: 'exe_unloaded' }));
  none(frameOf(1, X3)); // an ended execution: its edge is drawn but not live
  none({ id: 1, event: 'execution.progress', data: {} } as never);
  none({ id: 1, event: 'execution.progress' } as never);
  const tl = new Timeline();
  assert.equal(hear(tl, v, frameOf(undefined), 0), false, 'a frame with no seq presented');
  assert.deepEqual(tl.at(0), []);
});

test('it begins at the source, travels deterministically toward the target, reaches it, and is gone at 600 ms', () => {
  const v = view();
  const s = scene(v);
  const tl = new Timeline();
  const still = draw(s, tl, 0);
  assert.equal(hear(tl, v, frameOf(1), 1000), true);
  const at = (t: number) => marks(draw(s, tl, t));
  assert.deepEqual(at(1000).heads, [[0, 0]], 'the head at t=start is not on the execution');
  assert.deepEqual(at(1000 + MS / 2).heads, [[30, 0]], 'the head at the midpoint');
  assert.deepEqual(at(1000 + MS / 4).heads, [[15, 0]], 'the speed is not constant');
  const end = at(1000 + MS - 1).heads[0];
  assert.ok(Math.abs(end[0] - 60) < 0.2 && end[1] === 0, `the head does not reach the task: ${end}`);
  // the tail trails it toward the source and never past it
  assert.deepEqual(at(1000).tails, [[0, 0, 0, 0]]);
  assert.deepEqual(at(1000 + MS / 2).tails, [[30 - MARKER_TAIL, 0, 30, 0]]);
  // the head's radius is the token's, in screen pixels
  assert.ok(draw(s, tl, 1000).includes(`arc(0,0,${MARKER_HEAD / 2},0,6.28)`));
  const zoomed = marks(draw({ ...s, cam: { x: 0, y: 0, k: 2 } }, tl, 1000 + MS / 2)).tails[0];
  assert.equal(zoomed[2] - zoomed[0], MARKER_TAIL / 2, 'the tail is not 12 screen pixels at zoom 2');
  // deterministic: the same t is the same picture, a second timeline agrees
  const again = new Timeline();
  hear(again, v, frameOf(1), 1000);
  assert.deepEqual(draw(s, again, 1300), draw(s, tl, 1300));
  assert.deepEqual(draw(s, tl, 1300), draw(s, tl, 1300));
  // gone once it ends, and the picture is the static one again
  assert.deepEqual(tl.at(1000 + MS), []);
  assert.deepEqual(draw(s, tl, 1000 + MS), still);
  assert.deepEqual(draw(s, tl, 1e9), still);
  assert.deepEqual(draw(s, tl, 999), still, 'drawn before it began');
});

test('source and target are Core\'s: the frame\'s execution is the source whichever way the edge is stored', () => {
  // the same relation stored task → execution in the drawn list's order still
  // travels execution → task
  const v = view({ ...DATA, nodes: [...DATA.nodes].reverse() });
  const t = markerFor(frameOf(1), v.model, v.vis, v.drawn, v.live)!;
  assert.equal(t.from, keyOf(X1));
  assert.equal(t.to, keyOf(T1));
  const tl = new Timeline();
  hear(tl, v, frameOf(1), 0);
  assert.deepEqual(marks(draw(scene(v), tl, MS / 4)).heads, [[15, 0]]);
  // a marker whose edge no longer joins its two ends (a re-read moved it) is not drawn
  const moved = view({ ...DATA, edges: DATA.edges.map((e) => (e.id === 'a' ? { ...e, to: T2 } : e)) });
  assert.deepEqual(marks(draw(scene(moved), tl, MS / 4)).heads, []);
});

test('the same event never replays: again mid-travel, again after it ended; a newer one is exactly one new marker', () => {
  const v = view();
  const s = scene(v);
  const tl = new Timeline();
  assert.equal(hear(tl, v, frameOf(5), 0), true);
  assert.equal(hear(tl, v, frameOf(5), 200), false, 'the event heard again started a second marker');
  assert.deepEqual(marks(draw(s, tl, 200)).heads, [[20, 0]], 'the marker restarted from the source');
  assert.equal(tl.at(200).length, 1);
  assert.equal(hear(tl, v, frameOf(5), 5000), false, 'the event replayed after its window');
  assert.equal(hear(tl, v, frameOf(4), 5000), false, 'an older event presented');
  assert.deepEqual(tl.at(5000), []);
  assert.equal(hear(tl, v, frameOf(6), 5000), true);
  assert.equal(tl.at(5000).length, 1);
  assert.deepEqual(marks(draw(s, tl, 5000)).heads, [[0, 0]]);
});

test('a reconnect, a resync, a remount and a route change re-read the same event: the marker keeps its start', () => {
  const tl = new Timeline(); // the page's one timeline: it outlives every mount
  const first = view();
  assert.equal(hear(tl, first, frameOf(10), 0), true);
  // the resync re-reads the graph (new objects, same state) and the stream re-sends seq 10
  const reread = view(structuredClone(DATA));
  assert.equal(hear(tl, reread, frameOf(10), 250), false, 'the reconnect replayed the marker');
  // the remounted view (a new scene over the re-read) draws the running marker where it is
  assert.deepEqual(marks(draw(scene(reread), tl, 300)).heads, [[30, 0]], 'the remount restarted it');
  assert.equal(tl.at(300).length, 1);
  // a route change away and back after it ended: nothing
  assert.deepEqual(marks(draw(scene(view()), tl, 5000)).heads, []);
  assert.equal(hear(tl, view(), frameOf(10), 5000), false);
  // a genuinely newer event after the reconnect is a new marker
  assert.equal(hear(tl, reread, frameOf(11), 5000), true);
});

test('reduced motion: no marker is drawn, the event counts as presented, the live edge and the mirror still say it', () => {
  const v = view();
  const tl = new Timeline();
  assert.equal(hear(tl, v, frameOf(3), 0, true), false);
  assert.deepEqual(tl.at(0), []);
  assert.deepEqual(marks(draw(scene(v, { liveStatic: true }), tl, 100)).heads, []);
  assert.equal(hear(tl, v, frameOf(3), 100, false), false, 'switching reduced motion off replayed the event');
  // the static form: the live edge is drawn 2 px
  assert.notDeepEqual(draw(scene(v, { liveStatic: true }), tl, 0), draw(scene(v), tl, 0), 'no static live edge under reduced motion');
  assert.equal(widthOf(1, true), 2);
  assert.match(M.reduced, /2 px and static/);
  // the loop refuses the animation outright, and draws the change once
  const h = fakeHost({ reduced: () => true });
  const l = new Loop(h, () => h.tick(16));
  assert.equal(l.animate('travelling-marker'), false);
  assert.equal(h.run(), 1);
  assert.equal(l.state, 'parked');
});

test('the text equivalent: the mirror says the execution\'s relation to its task is live now, and only that one', () => {
  const v = view();
  const rows = mirrorRows(v.model, new Set(), haloed(v.model, isActive));
  const edge = (k: string, id: string) => rows.find((r) => r.k === k)!.edges.find((e) => e.id === id)!;
  assert.equal(edge(keyOf(X1), 'a').live, true);
  assert.match(edge(keyOf(X1), 'a').text, / — live now$/);
  assert.match(edge(keyOf(T1), 'a').text, / — live now$/, 'the task\'s side of the live relation');
  assert.equal(edge(keyOf(X3), 'c').live, false, 'an ended execution\'s relation said live');
  assert.equal(edge(keyOf(T1), 'd').live, false, 'an unrelated relation said live');
  assert.doesNotMatch(JSON.stringify(rows), /marker|moving/i, 'the mirror narrates the animation');
});

test('the cap: 8 markers coexist; the ninth drops exactly the oldest; the cap holds through a resync', () => {
  const v = view();
  const s = scene(v);
  const tl = new Timeline();
  for (let i = 0; i < 8; i++) assert.equal(hear(tl, v, frameOf(100 + i), i * 50), true);
  // eight batches of one execution: eight heads on the same edge, each where its own start puts it
  const eight = marks(draw(s, tl, 350)).heads.map(([x]) => x).sort((a, b) => a - b);
  assert.deepEqual(eight, [0, 5, 10, 15, 20, 25, 30, 35]);
  assert.equal(hear(tl, v, frameOf(108), 400), true);
  const nine = marks(draw(s, tl, 400)).heads.map(([x]) => x).sort((a, b) => a - b);
  assert.equal(nine.length, 8, 'a ninth marker is drawn');
  assert.deepEqual(nine, [0, 5, 10, 15, 20, 25, 30, 35], 'not exactly the oldest was dropped');
  assert.equal(tl.at(400).length, 8);
  // a resync re-sending all nine (and the dropped one) recreates nothing
  for (let i = 0; i <= 8; i++) assert.equal(hear(tl, view(structuredClone(DATA)), frameOf(100 + i), 450), false);
  assert.equal(tl.at(450).length, 8);
  assert.ok(!tl.at(450).some((x) => x.seq === 100), 'the dropped marker came back');
  // a burst over the cap never queues: twenty more at once leave eight
  for (let i = 0; i < 20; i++) hear(tl, v, frameOf(200 + i), 500);
  assert.equal(tl.at(500).length, 8);
  assert.deepEqual(tl.at(500).map((x) => x.seq), [212, 213, 214, 215, 216, 217, 218, 219]);
  assert.deepEqual(tl.at(500 + MS), [], 'a marker outlived its 600 ms');
});

test('two source/target pairs travel independently; the pulse and the marker are separate presentations', () => {
  const v = view();
  const s = scene(v);
  const tl = new Timeline();
  assert.equal(hear(tl, v, frameOf(1, X1), 0), true);
  assert.equal(hear(tl, v, frameOf(2, X2), 300), true);
  assert.deepEqual(marks(draw(s, tl, 300)).heads.sort(), [[0, 40], [30, 0]].sort());
  assert.deepEqual(marks(draw(s, tl, 600)).heads, [[30, 40]], 'the first ended the second');
  // the same frame also pulses: the marker's mark never refuses the pulse
  assert.equal(tl.start('execution-pulse', 'a', 2, 300, false), true);
});

test('unrelated nodes and edges are drawn exactly as before: the marker is one block of its own ops, last', () => {
  const v = view();
  const s = scene(v);
  const tl = new Timeline();
  const without = draw(s, tl, 300);
  hear(tl, v, frameOf(1), 0);
  const withMarker = draw(s, tl, 300);
  assert.deepEqual(withMarker.slice(0, without.length), without, 'the marker changed the static picture');
  const block = withMarker.slice(without.length);
  assert.ok(block.length && block.every((op) => /^(setTransform|setLineDash|globalAlpha=1|strokeStyle=--thread|fillStyle=--thread|lineWidth|beginPath|moveTo|lineTo|arc|stroke\(|fill\()/.test(op)), block.join(' '));
});

test('frames running slow: a marker becomes the pulse\'s form — one opacity step over its edge, no travel', () => {
  const v = view();
  const tl = new Timeline();
  hear(tl, v, frameOf(1), 0);
  const o = draw(scene(v, { degraded: true }), tl, MS / 2);
  assert.deepEqual(marks(o).heads, []);
  const i = o.lastIndexOf('strokeStyle=--state-active');
  assert.ok(i > 0 && o.slice(i - 3, i).includes('globalAlpha=0.5'), o.slice(i - 3, i + 5).join(' '));
  assert.deepEqual(o.slice(i + 1, i + 5), ['beginPath()', 'moveTo(0,0)', 'lineTo(60,0)', 'stroke()']);
});

test('idle: no frame without a marker; one marker is a bounded run of frames; completion parks the loop', () => {
  const h = fakeHost();
  const l = new Loop(h, () => h.tick(16));
  for (let i = 0; i < 50; i++) {
    h.tick(1000);
    h.run();
  }
  assert.equal(h.asked(), 0, 'a frame was scheduled with no marker');
  assert.equal(l.animate('travelling-marker'), true);
  assert.equal(l.state, 'running');
  h.run();
  const ran = h.asked();
  assert.ok(ran > 1 && ran <= Math.ceil(MS / 16) + 2, `${ran} frames for one ${MS} ms marker`);
  assert.equal(l.state, 'parked');
  assert.equal(l.animating, 0);
  for (let i = 0; i < 50; i++) {
    h.tick(1000);
    h.run();
  }
  assert.equal(h.asked(), ran, 'frames went on after the marker ended');
  assert.equal(h.pending(), 0);
});
