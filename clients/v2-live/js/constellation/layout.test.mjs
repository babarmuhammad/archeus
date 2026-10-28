import test from 'node:test';
import assert from 'node:assert/strict';
import {layout, plan, coreScaleFor, taglineOn, coversNode, overlaps, CELLS, coreCentre, coreKeepOut, unit} from './geometry.js';

const STATES = ['needs-you', 'running', 'idle', 'done', 'blocked', 'idle', 'paused'];
const id = i => `p${String(i).padStart(3, '0')}`;
// P projects, each with a hub, 1 to 9 missions in every state, and an execution or a decision under some of them.
function world(P, per = i => 1 + (i * 7) % 9) {
  const nodes = [], edges = [];
  for (let i = 0; i < P; i++) {
    nodes.push({id: id(i), kind: 'Project', project: id(i), label: `Project ${i}`, state: i % 3 === 0 ? 'needs-you' : 'idle'});
    for (let j = 0; j < per(i); j++) {
      const m = `${id(i)}-m${j}`;
      nodes.push({id: m, kind: 'Mission', project: id(i), label: `Mission ${j}`, state: STATES[(i + j) % STATES.length]}); edges.push({from: id(i), to: m, kind: 'contains'});
      if ((i + j) % 4 === 0) { nodes.push({id: `${m}-x`, kind: 'Execution', project: id(i), state: 'running'}); edges.push({from: m, to: `${m}-x`, kind: 'runs'}); }
      if ((i + j) % 5 === 1) { nodes.push({id: `${m}-d`, kind: 'Decision', project: id(i), state: 'needs-you'}); edges.push({from: m, to: `${m}-d`, kind: 'asks'}); }
    }
  }
  return {nodes, edges};
}
const slots = P => new Map(Array.from({length: P}, (_, i) => [id(i), i]));
const INSET = {top: 150, bottom: 88, left: 24, right: 24};
const SIZES = [[1440, 900], [1248, 900], [1280, 720], [1024, 768], [2560, 1440], [768, 1024]];
const same = (a, b) => a.x === b.x && a.y === b.y && a.radius === b.radius;

test('clusters: 1 to 100 projects never overlap, stay inside the inset, off the core, its wordmark and the zoom buttons', () => {
  for (const [w, h] of SIZES) for (const P of [...Array.from({length: 24}, (_, i) => i + 1), 30, 40, 50, 64, 80, 100]) {
    const controls = {x: w - 68, y: h - 96 - 156, width: 68, height: 160}, out = layout(world(P), w, h, INSET, {avoid: [controls]}), nodes = out.nodes;
    const keep = coreKeepOut(w, h, unit(w, h), INSET, false, coreScaleFor(P)), tags = nodes.filter(n => n.tag).map(n => n.tag), at = `${w}x${h} ${P}`;
    assert.equal(nodes.filter(n => n.hub).length, P, at + ': every project has its hub');
    nodes.forEach((a, i) => {
      assert.ok(a.x - a.radius >= INSET.left - .01 && a.x + a.radius <= w - INSET.right + .01 && a.y - a.radius >= INSET.top - .01 && a.y + a.radius <= h - INSET.bottom + .01, `${at}: ${a.id} outside`);
      assert.ok(Math.hypot(a.x - keep.x, a.y - keep.y) >= keep.radius && !coversNode(keep.box, a, 0), `${at}: ${a.id} on the core`);
      assert.ok(!coversNode(controls, a, 0), `${at}: ${a.id} under the zoom buttons`);
      for (const b of nodes.slice(i + 1)) assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= a.radius + b.radius, `${at}: ${a.id} touches ${b.id}`);
      if (!a.hub) for (const t of tags) assert.ok(!coversNode(t, a, 0), `${at}: ${a.id} on a hub label`);
    });
    tags.forEach((t, i) => { assert.ok(!overlaps(t, keep.box) && t.x >= 0 && t.x + t.width <= w, `${at}: label`); for (const o of tags.slice(i + 1)) assert.ok(!overlaps(t, o), `${at}: labels overlap`); });
  }
});

test('clusters: deterministic, independent of input order, and the input is untouched', () => {
  const input = world(14), snapshot = structuredClone(input);
  const first = layout(input, 1440, 900, INSET);
  assert.deepEqual(first, layout(input, 1440, 900, INSET));
  assert.deepEqual(first.nodes, layout({nodes: [...input.nodes].reverse(), edges: [...input.edges].reverse()}, 1440, 900, INSET).nodes);
  assert.deepEqual(input, snapshot);
  assert.deepEqual(layout({nodes: [], edges: []}, 1440, 900).nodes, []);
});

test('clusters: adding a project moves nothing already placed while the density level holds', () => {
  for (const [w, h] of [[1440, 900], [1024, 768]]) {
    let memory, before = null, steady = 0;
    for (let P = 1; P <= 60; P++) {
      const out = layout(world(P), w, h, INSET, {slots: slots(P), memory});
      if (before && plan(P - 1, w, h, INSET).level === plan(P, w, h, INSET).level && coreScaleFor(P - 1) === coreScaleFor(P)) {
        steady++;
        const now = new Map(out.nodes.map(n => [n.id, n]));
        for (const n of before.nodes) assert.ok(same(n, now.get(n.id)), `${w}x${h}: ${n.id} moved when project ${P} arrived`);
      }
      before = out; memory = out.memory;
    }
    assert.ok(steady >= 40, `${w}x${h}: only ${steady} of 59 steps kept the level`);
  }
});

test('clusters: the level only gets denser as projects are added, and a level holds the cells it needs', () => {
  let last = 0;
  for (let P = 1; P <= 100; P++) {
    const p = plan(P, 1440, 900, INSET);
    assert.ok(p.level >= last && p.cells.length >= P, `${P} projects: level ${p.level}, ${p.cells.length} cells`);
    last = p.level;
  }
  assert.ok(plan(3, 1440, 900, INSET).level <= 1 && plan(12, 1440, 900, INSET).level <= 3 && CELLS[plan(100, 1440, 900, INSET).level].lines <= 1);
});

test('clusters: projects take the cells in the order given, nearest the core first', () => {
  const P = 12, order = new Map(Array.from({length: P}, (_, i) => [id(P - 1 - i), i])), out = layout(world(P), 1440, 900, INSET, {slots: order}), p = plan(P, 1440, 900, INSET);
  const hubs = new Map(out.nodes.filter(n => n.hub).map(n => [n.id, n]));
  for (let i = 0; i < P; i++) assert.equal(Math.round(hubs.get(id(P - 1 - i)).x), Math.round(p.cells[i].x + p.cells[i].w / 2), `slot ${i}`);
  const core = coreCentre(1440, 900, INSET), dist = c => Math.hypot(c.x + c.w / 2 - core.x, c.y + c.h / 2 - core.y);
  assert.ok(dist(p.cells[0]) <= dist(p.cells[P - 1]));
});

test('clusters: a satellite keeps its place when another arrives, and a new attention one takes a place before quiet ones', () => {
  const base = world(100, () => 6), a = layout(base, 1440, 900, INSET, {slots: slots(100)});
  const grown = {nodes: [...base.nodes, {id: 'p005-new', kind: 'Mission', project: id(5), label: 'New', state: 'needs-you'}], edges: [...base.edges, {from: id(5), to: 'p005-new', kind: 'contains'}]};
  const b = layout(grown, 1440, 900, INSET, {slots: slots(100), memory: a.memory}), now = new Map(b.nodes.map(n => [n.id, n]));
  for (const n of a.nodes) assert.ok(same(n, now.get(n.id)), `${n.id} moved`);
  assert.ok(now.has('p005-new'), 'the new mission that needs you is shown at the densest level');
  assert.equal(b.nodes.find(n => n.id === id(5)).quiet, a.nodes.find(n => n.id === id(5)).quiet, 'the count of folded missions does not change when the new one shows');
});

test('clusters: only attention, running and blocked satellites show when dense; the rest fold into the hub count', () => {
  const g = world(100, () => 8), out = layout(g, 1440, 900, INSET, {slots: slots(100)});
  for (const n of out.nodes.filter(n => !n.hub && n.kind === 'Mission')) assert.ok(['needs-you', 'running', 'blocked'].includes(n.state), `${n.id} is ${n.state}`);
  const shown = out.nodes.filter(n => n.cluster === id(1) && !n.hub && n.kind === 'Mission').length, mine = g.nodes.filter(n => n.project === id(1) && n.kind === 'Mission').length;
  assert.equal(out.nodes.find(n => n.id === id(1)).quiet, mine - shown);
  assert.ok(out.nodes.some(n => n.quiet > 0));
});

test('clusters: needs-you comes before running before idle when a hub has more missions than room', () => {
  const g = {nodes: [{id: 'a', kind: 'Project', project: 'a', label: 'A'}, ...Array.from({length: 40}, (_, i) => ({id: `m${String(i).padStart(2, '0')}`, kind: 'Mission', project: 'a', label: `M${i}`, state: i < 3 ? 'idle' : i < 6 ? 'running' : i < 9 ? 'needs-you' : 'done'}))], edges: []};
  const out = layout(g, 1440, 900, INSET), shown = out.nodes.filter(n => n.kind === 'Mission'), cap = CELLS[out.level].cap;
  assert.ok(shown.length <= cap && shown.length >= 9);
  for (const m of ['m06', 'm07', 'm08', 'm03', 'm04', 'm05']) assert.ok(shown.some(n => n.id === m), `${m} shown`);
});

test('clusters: missions of a project without a Project node still get a place, and children sit beside their mission', () => {
  const g = {nodes: [{id: 'm1', kind: 'Mission', project: 'ghost', label: 'One', state: 'running'}, {id: 'x1', kind: 'Execution', project: 'ghost', state: 'running'}], edges: [{from: 'm1', to: 'x1'}]};
  const out = layout(g, 1440, 900, INSET), m = out.nodes.find(n => n.id === 'm1'), x = out.nodes.find(n => n.id === 'x1');
  assert.equal(out.nodes.length, 2);
  assert.ok(Math.hypot(m.x - x.x, m.y - x.y) < m.radius + x.radius + 50);
});

test('core scale shrinks with the project count and the tagline gives way', () => {
  assert.deepEqual([1, 3, 4, 8, 9, 16, 17, 100].map(coreScaleFor), [1, 1, .85, .85, .7, .7, .5, .5]);
  assert.ok(taglineOn(.7) && !taglineOn(.5));
});
