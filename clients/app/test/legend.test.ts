// R2 (ADR-0025 §1-2, rulebook §12 and §25, X-20): the graph's legend, expand
// all / collapse all, and the plain tier words. Pure: the legend's rows and
// its filter, the two whole-graph commands over the expanded set, the swatches
// against what the renderer draws, and the words against the enum.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ENCODING, dashOf, lookOf, radiusOf, tracePath } from '../src/graph/encoding.ts';
import { allExpanded, build, keyOf, lift, lifted, toggle, visible, type GraphData } from '../src/graph/model.ts';
import { applyLegend, kindKey, legendRows, type LegendRow } from '../src/graph/legend.ts';
import { drawSwatch, HALO_RINGS, MARKER_HEAD, MARKER_TAIL } from '../src/graph/render.ts';
import { step, start } from '../src/graph/keys.ts';
import { mirrorRows } from '../src/graph/mirror.ts';
import { TIER_STYLE, TIER_WORD, tierOf } from '../src/graph/relations.ts';
import { ALPHA } from '../src/state/tokens.ts';
import { recorder } from './motion-harness.ts';

const P = { kind: 'project', id: 'prj_1' };
const M = { kind: 'mission', id: 'msn_1' };
const PL = { kind: 'plan', id: 'pln_1' };
const T = { kind: 'task', id: 'tsk_1' };
const X = { kind: 'execution', id: 'exe_1' };
const K = { kind: 'knowledge_item', id: 'kn_1' };
const D = { kind: 'decision', id: 'dec_1' };

const e = (field: string, from: { kind: string; id: string }, to: { kind: string; id: string }, extra = {}) => ({
  id: `${field}|${from.id}|${to.id}`, from, to, field, rel: null, tier: null, inactive: false, structural: false, ...extra,
});

const DATA: GraphData = {
  nodes: [
    { ...P, label: 'Atlas' },
    { ...M, label: 'Ship the chart', parent: P, machine: 'mission', state: 'EXECUTING' },
    { ...PL, label: 'Plan v1', parent: M },
    { ...T, label: 'Write it', parent: PL, machine: 'task', state: 'RUNNING' },
    { ...X, label: 'Attempt 1', parent: T, machine: 'execution', state: 'RUNNING' },
    { ...K, label: 'Use bars', parent: P, type: 'DECISION' },
    { ...D, label: 'decision dec_1', endpoint: true },
  ],
  edges: [
    e('missions.project_id', M, P),
    e('plans.mission_id', PL, M),
    e('tasks.plan_id', T, PL, { structural: true }),
    e('executions.task_id', X, T),
    e('relations.learned_from', K, M, { rel: 'learned_from', tier: 'INFERRED' }),
  ],
};
const m = build(DATA);
const k = keyOf;
const words = (rows: LegendRow[]) => rows.map((r) => r.word);

// ── the legend's rows ──

test('the legend names every kind in the picture by its noun, in the encoding order, and nothing absent', () => {
  const rows = legendRows(m);
  assert.deepEqual(rows.filter((r) => r.group === 'kind').map((r) => r.key), ['kind:project', 'kind:mission', 'kind:task', 'kind:execution', 'kind:plan', 'kind:decision', 'kind:endpoint']);
  for (const r of rows) if (r.group === 'kind' && r.key !== 'kind:endpoint' && r.key !== 'kind:decision') assert.equal(r.word, ENCODING[r.key.slice(5)].noun);
  assert.equal(rows.find((r) => r.key === 'kind:decision')?.word, 'decision');
  assert.ok(!rows.some((r) => r.key === 'kind:session'), 'a kind not loaded is not in the legend');
});

test('the legend lists the tiers loaded edges carry, in plain words; AMBIGUOUS only once one is loaded (X-20)', () => {
  const tiers = (d: GraphData) => legendRows(build(d)).filter((r) => r.group === 'tier').map((r) => r.word);
  assert.deepEqual(tiers(DATA), ['recorded', 'suggested by Archeus']);
  assert.deepEqual(tiers({ ...DATA, edges: DATA.edges.filter((x) => !x.tier) }), ['recorded'], 'a column edge is recorded');
  assert.deepEqual(tiers({ ...DATA, edges: [...DATA.edges, e('relations.motivated', D, K, { rel: 'motivated', tier: 'AMBIGUOUS' })] }), ['recorded', 'suggested by Archeus', 'unclear']);
  assert.deepEqual(tiers({ ...DATA, edges: [e('relations.x', K, M, { tier: 'GUESSED' })] }), [], 'a tier Core does not define is not guessed');
});

test('the legend always explains the halo and the marker; under reduced motion it describes the static live edge', () => {
  const live = legendRows(m).filter((r) => r.group === 'live');
  assert.deepEqual(live.map((r) => r.key), ['halo', 'marker']);
  assert.equal(live[0].word, 'live work now');
  assert.match(legendRows(m, true).find((r) => r.key === 'marker')!.word, /thicker line/);
  assert.match(live[1].word, /travelling/);
});

test('an empty picture has no shape or line rows, only the two marks of live work', () => {
  const rows = legendRows(build({ nodes: [], edges: [] }));
  assert.deepEqual(rows.map((r) => r.key), ['halo', 'marker']);
});

test('no legend word or mirror word is an enum, a field name or an id', () => {
  const all = [...words(legendRows(m)), ...words(legendRows(build({ ...DATA, edges: [...DATA.edges, e('relations.x', D, K, { tier: 'AMBIGUOUS' })] })))];
  for (const w of all) assert.ok(!/EXTRACTED|INFERRED|AMBIGUOUS|extracted|inferred|ambiguous|_id\b|\.|[a-z]+_[a-z]+/.test(w.replace('“+N more”', '')), w);
  const text = mirrorRows(m).flatMap((r) => r.edges.map((x) => x.text)).join('\n');
  assert.ok(text.includes('(suggested by Archeus)') && !/\((inferred|extracted|ambiguous)\)/i.test(text), text);
  assert.deepEqual(Object.keys(TIER_WORD), Object.keys(TIER_STYLE), 'a word for every tier the renderer styles');
});

// ── the swatches are the renderer's own marks ──

test('a kind swatch traces the kind\'s own shape, filled or stroked as encoded, in the neutral node colour', () => {
  for (const r of legendRows(build({ nodes: Object.keys(ENCODING).map((kind) => ({ kind, id: 'x', label: 'x' })), edges: [] }))) {
    if (r.group !== 'kind') continue;
    const { ctx, ops } = recorder();
    drawSwatch(ctx, r, 28, 24, (v) => v);
    const want = recorder();
    const { filled } = tracePath(want.ctx, r.shape, 14, 12, Math.min(radiusOf(r.shape), 10));
    assert.ok(ops.join(';').includes(want.ops.join(';')), r.key);
    assert.ok(ops.includes(filled ? 'fillStyle=--text-2' : 'strokeStyle=--text-2'), r.key);
  }
  const { ctx, ops } = recorder();
  drawSwatch(ctx, legendRows(m).find((r) => r.key === 'kind:endpoint')!, 28, 24, (v) => v);
  assert.ok(ops.includes('setLineDash([1.5,3])'), 'the endpoint is the dotted circle the graph draws');
});

test('a tier swatch is the tier\'s own dash in edge ink; the live swatches use the halo\'s rings and the marker\'s ink', () => {
  for (const t of ['EXTRACTED', 'INFERRED', 'AMBIGUOUS'] as const) {
    const { ctx, ops } = recorder();
    drawSwatch(ctx, { key: 'tier:' + t, group: 'tier', tier: t, dash: dashOf(t), word: TIER_WORD[t] }, 28, 24, (v) => v);
    assert.ok(ops.includes(`setLineDash(${JSON.stringify(dashOf(t))})`) && ops.includes('strokeStyle=--line-strong'), t);
  }
  const halo = legendRows(m).find((r) => r.key === 'halo')!;
  const h = recorder();
  drawSwatch(h.ctx, halo, 28, 24, (v) => v);
  assert.ok(h.ops.includes('strokeStyle=--state-active') && h.ops.includes(`globalAlpha=${ALPHA['halo-inner']}`) && h.ops.includes(`globalAlpha=${ALPHA['halo-outer']}`));
  assert.ok(h.ops.includes(`arc(14,12,${radiusOf('dot') + HALO_RINGS[1]},0,6.28)`));
  const hs = recorder();
  drawSwatch(hs.ctx, halo, 28, 24, (v) => v, true);
  assert.ok(hs.ops.includes('globalAlpha=1') && !hs.ops.includes(`globalAlpha=${ALPHA['halo-outer']}`), 'one solid ring when transparency must not carry it');
  const mk = recorder();
  drawSwatch(mk.ctx, legendRows(m).find((r) => r.key === 'marker')!, 28, 24, (v) => v);
  assert.ok(mk.ops.includes('strokeStyle=--thread') && mk.ops.includes('fillStyle=--thread'));
  assert.ok(mk.ops.some((o) => o === `arc(19.6,12,${MARKER_HEAD / 2},0,6.28)`) && mk.ops.includes(`moveTo(${Math.round((19.6 - MARKER_TAIL) * 100) / 100},12)`));
  const rm = recorder();
  drawSwatch(rm.ctx, legendRows(m, true).find((r) => r.key === 'marker')!, 28, 24, (v) => v, false, true);
  assert.ok(!rm.ops.includes('strokeStyle=--thread') && rm.ops.includes('strokeStyle=--line-strong'), 'reduced motion: the static live edge, no marker');
});

// ── unticking a row hides what it names ──

test('an unticked kind leaves the drawing with its edges; the mirror still lists it', () => {
  const vis = visible(m, allExpanded(m));
  const { vis: shown, keep } = applyLegend(m, vis, new Set(['kind:execution']));
  assert.ok(!shown.has(k(X)) && shown.has(k(T)));
  const d = lifted(m, shown, keep);
  assert.ok(!d.some((x) => x.edges.some((y) => y.field === 'executions.task_id')));
  assert.ok(mirrorRows(m).some((r) => r.k === k(X)));
  assert.equal(kindKey(DATA.nodes[5]), 'kind:decision');
  assert.equal(kindKey(DATA.nodes[6]), 'kind:endpoint');
});

test('an unticked tier leaves the drawing; nothing else changes; nothing unticked is the identity', () => {
  const vis = visible(m, allExpanded(m));
  const { vis: shown, keep } = applyLegend(m, vis, new Set(['tier:INFERRED']));
  assert.deepEqual([...shown], [...vis]);
  assert.ok(!lifted(m, shown, keep).some((x) => x.tier === 'INFERRED'));
  assert.equal(lifted(m, shown, keep).length, lifted(m, vis).length - 1);
  const same = applyLegend(m, vis, new Set());
  assert.deepEqual([...same.vis], [...vis]);
  assert.equal(tierOf(DATA.edges[0]), 'EXTRACTED');
});

// ── expand all / collapse all ──

test('expand all opens every node with children; collapse all leaves only the top; both are idempotent', () => {
  const all = allExpanded(m);
  assert.deepEqual([...all].sort(), [k(M), k(P), k(PL), k(T)].sort());
  assert.deepEqual(visible(m, all), new Set(m.nodes.map(keyOf)), 'expanded: every loaded node is drawn');
  assert.deepEqual([...allExpanded(m)], [...all], 'twice is once');
  const none = new Set<string>();
  assert.deepEqual([...visible(m, none)].sort(), [k(P), k(D)].sort(), 'collapsed: the top-level nodes only');
  assert.deepEqual(visible(m, new Set(none)), visible(m, none));
});

test('from a partly expanded picture, expand all reaches the full one and collapse all the top', () => {
  const partial = toggle(toggle(allExpanded(m), k(PL)), k(T));
  const before = visible(m, partial);
  assert.ok(!before.has(k(T)) && before.has(k(PL)));
  assert.deepEqual(visible(m, allExpanded(m)), new Set(m.nodes.map(keyOf)));
  assert.deepEqual([...visible(m, new Set())].sort(), [k(P), k(D)].sort());
});

test('an empty picture has nothing to expand or collapse', () => {
  const empty = build({ nodes: [], edges: [] });
  assert.equal(allExpanded(empty).size, 0);
  assert.equal(visible(empty, allExpanded(empty)).size, 0);
  const flat = build({ nodes: [{ ...P, label: 'Atlas' }], edges: [] });
  assert.equal(allExpanded(flat).size, 0);
});

test('one node\'s toggle still opens and closes just that node after a whole-graph command', () => {
  const none = new Set<string>();
  const one = toggle(none, k(P));
  const v = visible(m, one);
  assert.ok(v.has(k(M)) && v.has(k(K)) && !v.has(k(PL)));
  assert.deepEqual(visible(m, toggle(one, k(P))), visible(m, none));
  const all = allExpanded(m);
  assert.ok(!visible(m, toggle(all, k(M))).has(k(PL)) && visible(m, toggle(all, k(M))).has(k(K)));
});

test('a collapse that hides the focused node moves the keyboard to what stands for it', () => {
  assert.equal(lift(m, visible(m, new Set()), k(X)), k(P));
  assert.equal(lift(m, visible(m, allExpanded(m)), k(X)), k(X));
});

test('E and C are the whole-graph commands; they move nothing and leave the walk as it was', () => {
  const w = start(k(M));
  const d = lifted(m, visible(m, allExpanded(m)));
  for (const [key, cmd] of [['e', 'expand-all'], ['c', 'collapse-all']] as const) {
    const r = step(w, key, d, k(M));
    assert.equal(r.command, cmd);
    assert.equal(r.walk, w);
  }
  assert.equal(lookOf('decision', true).shape, 'endpoint');
});
