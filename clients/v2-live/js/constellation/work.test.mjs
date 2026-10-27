import test from 'node:test';
import assert from 'node:assert/strict';
import {layoutWork, workCore, workGroup} from './geometry.js';

const states = ['needs-you', 'running', 'blocked', 'done', 'idle', 'paused'];
const graphOf = count => {
  const missions = Array.from({length: count}, (_, i) => ({id: `m${i}`, kind: 'Mission', project: `p${i % 3}`, state: states[i % 6]}));
  const asks = missions.filter(m => m.state === 'needs-you').slice(0, 3).map(m => ({id: `a-${m.id}`, kind: 'Decision', project: m.project, state: 'needs-you'}));
  return {nodes: [...missions, ...asks], edges: asks.map(a => ({from: a.id.slice(2), to: a.id, kind: 'asks'}))};
};

test('work layout: 1 to 12 missions stay apart, inside the inset and clear of the core', () => {
  for (const [w, h] of [[1280, 720], [1440, 900], [2000, 930], [390, 700], [1100, 420], [390, 240]]) for (let count = 1; count <= 12; count++) {
    const inset = {top: 16, bottom: 16, left: 16, right: 16}, graph = graphOf(count), nodes = layoutWork(graph, w, h, 's', inset), core = workCore(w, h, inset);
    assert.equal(nodes.length, graph.nodes.length);
    nodes.forEach((a, i) => {
      const at = `${w}x${h} ${count}: ${a.id}`;
      assert.ok(a.x - a.radius >= inset.left - .5 && a.x + a.radius <= w - inset.right + .5 && a.y - a.radius >= inset.top - .5 && a.y + a.radius <= h - inset.bottom + .5, `${at} outside the inset`);
      assert.ok(Math.hypot(a.x - core.x, a.y - core.y) >= core.keep + a.radius - .6, `${at} on the core`);
      for (const b of nodes.slice(i + 1)) assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= a.radius + b.radius - .6, `${at} touches ${b.id}`);
    });
  }
});

test('work layout is deterministic and groups run needs-you first, done last', () => {
  const g = graphOf(8), a = layoutWork(g, 1100, 420, 's'), b = layoutWork(g, 1100, 420, 's');
  assert.deepEqual(a.map(n => [n.id, n.x, n.y]), b.map(n => [n.id, n.x, n.y]));
  assert.deepEqual(a.map(workGroup), [...a.map(workGroup)].sort((x, y) => x - y));
  assert.deepEqual(layoutWork({nodes: [], edges: []}, 800, 400), []);
});
