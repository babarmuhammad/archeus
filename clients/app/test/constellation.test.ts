// R3 (ADR-0025 §3-4, rulebook §12, §20, §22, §24): the constellation
// treatment — the project hull, depth by graph distance, the cored live node,
// receding lines — and "What does this affect?". Pure: the model's distances
// and impact set, and the renderer's ops through a recording context.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dashOf, radiusOf } from '../src/graph/encoding.ts';
import { applyLegend, legendRows } from '../src/graph/legend.ts';
import { allExpanded, build, depthAlphas, hops, IMPACT_HOPS, impactOf, keyOf, lifted, toggle, visible, type GraphData } from '../src/graph/model.ts';
import { CORE, draw, hulls, recede, type Scene } from '../src/graph/render.ts';
import { mirrorRows } from '../src/graph/mirror.ts';
import { ALPHA } from '../src/state/tokens.ts';
import { recorder } from './motion-harness.ts';

const P = { kind: 'project', id: 'prj_1' };
const M = { kind: 'mission', id: 'msn_1' };
const PL = { kind: 'plan', id: 'pln_1' };
const T = { kind: 'task', id: 'tsk_1' };
const X = { kind: 'execution', id: 'exe_1' };
const K = { kind: 'knowledge_item', id: 'kn_1' };
const K2 = { kind: 'knowledge_item', id: 'kn_2' };

const e = (field: string, from: { kind: string; id: string }, to: { kind: string; id: string }, extra = {}) => ({
  id: `${field}|${from.id}|${to.id}`, from, to, field, rel: null, tier: null, inactive: false, structural: false, ...extra,
});

// project ⊃ mission ⊃ plan ⊃ task ⊃ execution, and two lessons in the project:
// one recorded (supersedes), one only suggested (learned_from)
const DATA: GraphData = {
  nodes: [
    { ...P, label: 'Atlas' },
    { ...M, label: 'Ship the chart', parent: P, machine: 'mission', state: 'EXECUTING' },
    { ...PL, label: 'Plan v1', parent: M },
    { ...T, label: 'Write it', parent: PL, machine: 'task', state: 'RUNNING' },
    { ...X, label: 'Attempt 1', parent: T, machine: 'execution', state: 'RUNNING' },
    { ...K, label: 'Use bars', parent: P },
    { ...K2, label: 'Use lines', parent: P },
  ],
  edges: [
    e('missions.project_id', M, P),
    e('plans.mission_id', PL, M),
    e('tasks.plan_id', T, PL, { structural: true }),
    e('executions.task_id', X, T),
    e('knowledge_items.project_id', K, P, { structural: true }),
    e('relations.supersedes', K2, K, { rel: 'supersedes', tier: 'EXTRACTED' }),
    e('relations.learned_from', K, M, { rel: 'learned_from', tier: 'INFERRED' }),
  ],
};
const m = build(DATA);
const k = keyOf;
const LIVE = new Set([k(M), k(T), k(X)]);

function scene(expanded = allExpanded(m), extra: Partial<Scene> = {}, hidden: ReadonlySet<string> = new Set()): Scene {
  const { vis, keep } = applyLegend(m, visible(m, expanded), hidden);
  const keys = m.nodes.map(keyOf).filter((x) => vis.has(x));
  const pos = new Map(keys.map((x, i) => [x, { x: i * 40, y: (i % 3) * 30 }]));
  return {
    model: m, keys, drawn: lifted(m, vis, keep), pos, cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: new Set(), liveStatic: false,
    pulse: new Map(), halo: new Set(), colour: (v) => v, width: 400, height: 300, dpr: 1, ...extra,
  };
}
const ops = (s: Scene) => {
  const { ctx, ops: o } = recorder();
  return { o, stats: draw(ctx, s) };
};

// ── the hull ──

test('a project with drawn members has one hull, filled in text ink at hull, under every stroke', () => {
  const s = scene();
  const hs = hulls(s);
  assert.equal(hs.length, 1);
  assert.equal(hs[0].project, k(P));
  assert.ok(hs[0].pts.length >= 3);
  const { o, stats } = ops(s);
  assert.equal(stats.hulls, 1);
  const fill = o.indexOf(`globalAlpha=${ALPHA.hull}`);
  assert.ok(fill >= 0 && o[fill + 1] === 'fillStyle=--text', o.slice(fill, fill + 3).join(' '));
  assert.ok(fill < o.indexOf('stroke()'), 'the hull is under the first stroke');
  // every drawn member is inside it
  const inside = (p: { x: number; y: number }) =>
    hs[0].pts.every((a, i) => {
      const b = hs[0].pts[(i + 1) % hs[0].pts.length];
      return (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x) >= -1e-9;
    });
  for (const key of s.keys) assert.ok(inside(s.pos.get(key)!), key);
});

test('the focused project, or a focused member, wears hull-focus', () => {
  for (const f of [k(P), k(X)]) {
    const { o } = ops(scene(undefined, { focus: f }));
    assert.ok(o.includes(`globalAlpha=${ALPHA['hull-focus']}`) && !o.includes(`globalAlpha=${ALPHA.hull}`), f);
  }
});

test('no hull for a collapsed project, a project alone, or a picture with no project; it follows what is drawn', () => {
  assert.equal(hulls(scene(toggle(allExpanded(m), k(P)))).length, 0, 'collapsed');
  const alone = build({ nodes: [{ ...P, label: 'Atlas' }], edges: [] });
  assert.equal(hulls({ model: alone, keys: [k(P)], pos: new Map([[k(P), { x: 0, y: 0 }]]), focus: null }).length, 0);
  assert.equal(ops(scene(undefined, {}, new Set(['kind:project']))).stats.hulls, 0, 'the project unticked in the legend');
  const all = hulls(scene())[0].pts;
  const fewer = hulls(scene(toggle(allExpanded(m), k(M))))[0].pts;
  assert.notDeepEqual(fewer, all, 'collapsing the mission reshapes the hull');
  const empty = build({ nodes: [], edges: [] });
  assert.deepEqual(hulls({ model: empty, keys: [], pos: new Map(), focus: null }), []);
});

test('opaque (forced colours, reduced transparency): the hull is a 1 px outline, never a fill', () => {
  const { o } = ops(scene(undefined, { opaque: true }));
  assert.ok(!o.includes(`globalAlpha=${ALPHA.hull}`) && o.includes('strokeStyle=--line'));
});

// ── depth by graph distance ──

test('depth tiers: the focus and its neighbours full, two steps alpha-tier1, three or more alpha-tier2', () => {
  const s = scene();
  const d = depthAlphas(s.drawn, s.keys, k(PL));
  const h = hops(s.drawn, k(PL));
  for (const key of s.keys) {
    const want = (h.get(key) ?? Infinity) <= 1 ? 1 : h.get(key) === 2 ? ALPHA['alpha-tier1'] : ALPHA['alpha-tier2'];
    assert.equal(d.get(key), want, key);
  }
  assert.equal(d.get(k(PL)), 1);
  assert.equal(d.get(k(M)), 1, 'a neighbour');
  assert.equal(d.get(k(X)), ALPHA['alpha-tier1'], 'two steps');
  assert.ok([...d.values()].includes(ALPHA['alpha-tier2']), 'three or more steps');
});

test('shallow and partly expanded pictures: distance is over what is drawn; no focus or a hidden focus dims nothing', () => {
  const shallow = scene(new Set([k(P)])); // project open, mission closed
  const d = depthAlphas(shallow.drawn, shallow.keys, k(M));
  assert.ok(!shallow.keys.includes(k(X)) && !d.has(k(X)));
  assert.equal(d.get(k(P)), 1);
  const s = scene();
  assert.equal(depthAlphas(s.drawn, s.keys, null).size, 0);
  assert.equal(depthAlphas(shallow.drawn, shallow.keys, k(X)).size, 0, 'a focus not drawn is no focus');
  assert.equal(depthAlphas([], [], null).size, 0);
});

test('opaque: depth is 1 / 1 / .64; the renderer draws each node at its depth', () => {
  const s = scene();
  const d = depthAlphas(s.drawn, s.keys, k(PL), true);
  assert.deepEqual([...new Set(d.values())].sort(), [0.64, 1]);
  const { o } = ops({ ...s, focus: k(PL), depth: depthAlphas(s.drawn, s.keys, k(PL)) });
  assert.ok(o.includes(`globalAlpha=${ALPHA['alpha-tier1']}`) && o.includes(`globalAlpha=${ALPHA['alpha-tier2']}`));
});

// ── the cored live node ──

test('a live node, and only a live node, has a core of thread ink inside its shape', () => {
  const { o } = ops(scene(undefined, { halo: LIVE }));
  const cores = o.filter((x, i) => x.startsWith('arc(') && o[i - 2] === 'fillStyle=--thread');
  assert.equal(cores.length, LIVE.size);
  assert.ok(cores.includes(`arc(${(1 * 40)},${30},${Math.round(radiusOf('circle') * CORE * 100) / 100},0,6.28)`), cores.join(' '));
  assert.ok(!ops(scene()).o.includes('fillStyle=--thread'), 'nothing live, no core');
  assert.deepEqual(legendRows(m).filter((r) => r.group === 'live').map((r) => r.key), ['halo', 'marker'], 'the legend gains no row');
});

// ── receding lines ──

test('an edge the focus does not touch, and a suggested edge, recede; a recorded edge of the focus is full', () => {
  const at = { focus: k(K), opaque: false };
  assert.equal(recede(at, { a: k(K2), b: k(K), tier: 'EXTRACTED' }), 1);
  assert.equal(recede(at, { a: k(K), b: k(M), tier: 'INFERRED' }), ALPHA['alpha-recede'], 'suggested recedes even at the focus');
  assert.equal(recede(at, { a: k(M), b: k(P), tier: null }), ALPHA['alpha-recede']);
  assert.equal(recede({ focus: null }, { a: k(M), b: k(P), tier: null }), 1, 'no focus: recorded lines full');
  assert.equal(recede({ focus: null }, { a: k(K), b: k(M), tier: 'INFERRED' }), ALPHA['alpha-recede']);
  assert.equal(recede({ focus: k(K), opaque: true }, { a: k(K), b: k(M), tier: 'INFERRED' }), 1, 'opaque: nothing recedes');
});

test('receding changes only alpha: each tier keeps its dash; selected and live edges stay bright', () => {
  const s = scene(undefined, { focus: k(X) });
  const { o } = ops(s);
  const inferred = s.drawn.find((d) => d.tier === 'INFERRED')!;
  assert.ok(o.includes(`setLineDash(${JSON.stringify(dashOf('INFERRED'))})`));
  const sel = ops({ ...s, selected: inferred.id }).o;
  const at = sel.indexOf(`setLineDash(${JSON.stringify(dashOf('INFERRED'))})`);
  assert.ok(sel.slice(at, at + 4).includes('globalAlpha=1') && sel.slice(at, at + 4).includes('strokeStyle=--focus'), 'the selected edge is bright');
  const allLive = ops({ ...s, live: new Set(s.drawn.map((d) => d.id)) }).o;
  assert.ok(o.includes(`globalAlpha=${ALPHA['alpha-recede']}`) && !allLive.includes(`globalAlpha=${ALPHA['alpha-recede']}`), 'live edges never recede');
  assert.equal(s.drawn.length, lifted(m, visible(m, allExpanded(m))).length, 'no edge is added or removed');
});

// ── "What does this affect?" ──

test('impact: what is reachable over recorded relations within the hops, both ways; suggested relations are not crossed', () => {
  const s = scene();
  const vis = visible(m, allExpanded(m));
  const one = impactOf(m, vis, s.drawn, k(K2), 1);
  assert.deepEqual([...one.steps], [[k(K), 1]]);
  const two = impactOf(m, vis, s.drawn, k(K2));
  assert.equal(two.hops, IMPACT_HOPS.default);
  assert.deepEqual([...two.steps.keys()].sort(), [k(K), k(P)].sort(), 'K2 → K → P, never K → M (only suggested)');
  const three = impactOf(m, vis, s.drawn, k(K2), 3);
  assert.ok(three.steps.has(k(M)) && !three.steps.has(k(PL)) && three.steps.get(k(M)) === 3);
  assert.equal(impactOf(m, vis, s.drawn, k(K2), 9).hops, IMPACT_HOPS.max, 'bounded at 3 hops');
  assert.equal(impactOf(m, vis, s.drawn, k(K2), 0).hops, 1);
});

test('impact is drawn as the path highlight and stands on what is drawn when its objects are collapsed', () => {
  const s = scene();
  const vis = visible(m, allExpanded(m));
  const r = impactOf(m, vis, s.drawn, k(M), 3);
  for (const id of r.edges) assert.ok(s.drawn.some((d) => d.id === id && d.tier !== 'INFERRED'), id);
  const closed = toggle(allExpanded(m), k(PL));
  const cvis = visible(m, closed);
  const c = impactOf(m, cvis, lifted(m, cvis), k(M), 3);
  assert.ok(c.steps.has(k(X)) && !c.shown.has(k(X)) && c.shown.has(k(PL)), 'the attempt stands as its plan');
  const near = impactOf(m, vis, s.drawn, k(M), 1);
  const d = depthAlphas(s.drawn, s.keys, k(M), false, near.shown);
  assert.ok(s.keys.filter((key) => d.get(key) === ALPHA['alpha-tier2']).length >= 3, 'what it does not affect recedes');
  for (const key of s.keys) assert.equal(d.get(key), key === k(M) || near.shown.has(key) ? 1 : ALPHA['alpha-tier2'], key);
  const lone = build({ nodes: [{ ...P, label: 'Atlas' }], edges: [] });
  const none = impactOf(lone, new Set([k(P)]), [], k(P));
  assert.equal(none.steps.size + none.edges.size, 0, 'nothing recorded: nothing affected');
});

// ── the words: depth, hull and impact in the mirror ──

test('the mirror says the hull, the depth and the impact in words, with no id', () => {
  const s = scene();
  const steps = hops(s.drawn, k(PL));
  const r = impactOf(m, visible(m, allExpanded(m)), s.drawn, k(PL), 2);
  const rows = mirrorRows(m, new Set(), new Set(), { focus: k(PL), steps, affected: r.steps });
  const x = rows.find((row) => row.k === k(X))!;
  assert.ok(x.notes.includes('in project Atlas'), x.notes.join(' | '));
  assert.ok(x.notes.includes('2 steps from Plan v1'), x.notes.join(' | '));
  assert.ok(x.notes.includes('affected, 2 steps from Plan v1 over recorded relations'), x.notes.join(' | '));
  assert.deepEqual(rows.find((row) => row.k === k(PL))!.notes, ['in project Atlas'], 'the focus is not a step from itself');
  assert.deepEqual(rows.find((row) => row.k === k(P))!.notes.filter((n) => n.startsWith('in project')), []);
  const text = rows.flatMap((row) => row.notes).join('\n');
  assert.ok(!/(prj|msn|pln|tsk|exe|kn)_/.test(text), text);
  assert.deepEqual(mirrorRows(m).map((row) => row.notes.filter((n) => !n.startsWith('in project'))), m.nodes.map(() => []), 'without a focus: only the hull words');
});
