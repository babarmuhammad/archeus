// R12: the static project cage (ADR-0025 §4, rulebook §12). A project cluster at
// the world level is a 12-junction cage when drawn 48 px across or more, and its
// circle below that, and anywhere but the world level; the cage is the same at
// every time — it never rotates — and costs two paths. Rendered with the
// deterministic harness (renderAt); mutation-verified by tools/mutate_p19_5.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Timeline } from '../src/state/timeline.ts';
import { allExpanded, build, keyOf, lifted, visible, type GraphData } from '../src/graph/model.ts';
import { CAGE, CAGE_MIN_PX, JUNCTION, cageShown, type Scene } from '../src/graph/render.ts';
import { radiusOf } from '../src/graph/encoding.ts';
import { renderAt } from './motion-harness.ts';

const P = { kind: 'project', id: 'prj_1' };
const data: GraphData = { nodes: [{ ...P, label: 'Atlas' }], edges: [] };

function scene(extra: Partial<Scene> = {}): Scene {
  const m = build(data);
  const vis = visible(m, allExpanded(m));
  return {
    model: m, keys: m.nodes.map(keyOf).filter((k) => vis.has(k)), drawn: lifted(m, vis), pos: new Map([[keyOf(P), { x: 0, y: 0 }]]),
    cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: new Set(), liveStatic: false,
    pulse: new Map(), halo: new Set(), colour: (v) => v, width: 200, height: 200, dpr: 1, world: true, ...extra,
  };
}
const TL = new Timeline();
const ops = (s: Scene, t = 0) => renderAt(s, TL, t).ops;
const R = radiusOf('cluster');
const lines = (o: string[]) => o.filter((x) => x.startsWith('lineTo(')).length;
const arcs = (o: string[], r: number) => o.filter((x) => x.startsWith('arc(') && x.split(',')[2] === String(Math.round(r * 100) / 100)).length;

test('the cage is 12 distinct junctions joined by 30 edges, five at each, inside its circle', () => {
  assert.equal(CAGE.points.length, 12);
  assert.equal(CAGE.edges.length, 30);
  const degree = CAGE.points.map((_, i) => CAGE.edges.filter(([a, b]) => a === i || b === i).length);
  assert.ok(degree.every((d) => d === 5), String(degree));
  for (let i = 0; i < 12; i++)
    for (let j = i + 1; j < 12; j++) assert.ok(Math.hypot(CAGE.points[i].x - CAGE.points[j].x, CAGE.points[i].y - CAGE.points[j].y) > 0.1, `${i} and ${j} apart`);
  assert.ok(CAGE.points.every((p) => Math.hypot(p.x, p.y) <= 1 + 1e-9));
  assert.ok(CAGE.points.some((p) => Math.abs(Math.hypot(p.x, p.y) - 1) < 1e-9), 'the cage spans its circle');
});

test('at the world level a project 48 px across or more is its cage, smaller it is its circle', () => {
  const at = CAGE_MIN_PX / (2 * R);
  assert.equal(cageShown(true, at), true);
  assert.equal(cageShown(true, at - 0.01), false);
  assert.equal(cageShown(false, 4), false, 'only at the world level');
  const big = ops(scene());
  assert.equal(lines(big), 30, 'thirty edges');
  assert.equal(arcs(big, JUNCTION * R), 12, 'twelve junctions');
  assert.equal(arcs(big, R), 0, 'no circle');
  const small = ops(scene({ cam: { x: 0, y: 0, k: at - 0.01 } }));
  assert.equal(lines(small), 0);
  assert.equal(arcs(small, R), 1, 'below 48 px, the circle');
});

test('anywhere but the world level a project stays its circle', () => {
  const o = ops(scene({ world: false, cam: { x: 0, y: 0, k: 3 } }));
  assert.equal(lines(o), 0);
  assert.equal(arcs(o, R), 1);
});

test('static: the same picture at every time, never rotated, two paths for the cage', () => {
  const a = ops(scene(), 0);
  assert.deepEqual(ops(scene(), 450), a);
  assert.deepEqual(ops(scene(), 60_000), a);
  const s = renderAt(scene(), TL, 0).stats;
  const circle = renderAt(scene({ world: false }), TL, 0).stats;
  assert.equal(s.paths - circle.paths, 1, 'the cage costs one path more than the circle: edges and junctions');
});
