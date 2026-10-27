import test from 'node:test';
import assert from 'node:assert/strict';
import {coreKeepOut, crystalRadius, isCrystal, layout, randomSeed, placeLabels, overlaps, coversNode, convexHull, nearestNeighbour, stateKey, coreCentre, coreRadius, unit, INSET} from './geometry.js';

const graph = count => ({nodes: Array.from({length: count}, (_, i) => ({id: `n${i}`, label: `Node ${i}`, project: `p${i % 3}`, weight: i % 4 + 1, state: i === 2 ? 'needs-you' : 'idle'})), edges: []});
test('layout is seeded, deterministic, input-order independent and bounded', () => {
  const input = graph(25), snapshot = structuredClone(input);
  const first = layout(input, 960, 640, 'same');
  assert.deepEqual(first, layout(input, 960, 640, 'same'));
  assert.deepEqual(first, layout({...input, nodes: [...input.nodes].reverse()}, 960, 640, 'same'));
  assert.notDeepEqual(first, layout(input, 960, 640, 'different'));
  assert.deepEqual(input, snapshot);
  for (const n of first) { assert.ok(n.x >= 0 && n.x <= 960); assert.ok(n.y >= 0 && n.y <= 640); }
  assert.deepEqual(layout(graph(0), 320, 560), []);
});
test('generated label sets never overlap another label, star, or reserved area', () => {
  for (const width of [320, 479, 480, 960, 1280, 2560]) for (let seed = 0; seed < 8; seed++) {
    const nodes = layout(graph(80), width, 700, seed);
    const obstacle = {x: width / 2 - 35, y: 315, width: 70, height: 70};
    const boxes = placeLabels(nodes, width, 700, {selected: 'n0', obstacles: [obstacle]});
    assert.ok(boxes.length > 0);
    for (let i = 0; i < boxes.length; i++) {
      assert.ok(!overlaps(boxes[i], obstacle));
      assert.ok(!nodes.some(n => coversNode(boxes[i], n)));
      for (let j = i + 1; j < boxes.length; j++) assert.ok(!overlaps(boxes[i], boxes[j]));
    }
  }
});
test('selected and attention labels outrank ordinary labels', () => {
  const nodes = Array.from({length: 6}, (_, i) => ({id: `n${i}`, label: `Label ${i}`, x: 60 + i % 2 * 180, y: 65 + Math.floor(i / 2) * 130, radius: 5, state: i === 1 ? 'needs-you' : 'idle'}));
  const labels = placeLabels(nodes, 360, 600, {selected: 'n5'});
  assert.equal(labels[0].id, 'n5'); assert.equal(labels[1].id, 'n1');
});
test('collision predicates handle touching boxes and circular corners', () => {
  assert.equal(overlaps({x: 0, y: 0, width: 10, height: 10}, {x: 10, y: 0, width: 10, height: 10}), false);
  assert.equal(coversNode({x: 0, y: 0, width: 10, height: 10}, {x: 12, y: 12, radius: 1}, 0), false);
  assert.equal(coversNode({x: 0, y: 0, width: 10, height: 10}, {x: 11, y: 5, radius: 2}, 0), true);
});
test('hull drops duplicates, interior points, and collinear points', () => {
  const square = [{x: 0, y: 0}, {x: 10, y: 0}, {x: 10, y: 10}, {x: 0, y: 10}];
  assert.deepEqual(convexHull([...square, {x: 5, y: 5}, square[0]]), square);
  assert.deepEqual(convexHull([{x: 0, y: 0}, {x: 5, y: 0}, {x: 10, y: 0}]), [{x: 0, y: 0}, {x: 10, y: 0}]);
});
test('arrow movement picks directional neighbour and handles boundaries', () => {
  const nodes = [{id: 'a', x: 0, y: 0}, {id: 'b', x: 20, y: 0}, {id: 'c', x: 0, y: 30}, {id: 'd', x: 1, y: 100}];
  assert.equal(nearestNeighbour(nodes, 'a', 'ArrowRight'), 'b');
  assert.equal(nearestNeighbour(nodes, 'a', 'ArrowDown'), 'c');
  assert.equal(nearestNeighbour(nodes, 'a', 'ArrowLeft'), null);
  assert.equal(nearestNeighbour(nodes, 'missing', 'ArrowUp'), null);
  assert.equal(nearestNeighbour(nodes, 'a', 'Enter'), null);
});
test('seed generator repeats and stays within unit interval', () => {
  const a = randomSeed('fixture'), b = randomSeed('fixture');
  for (let i = 0; i < 100; i++) { const value = a(); assert.equal(value, b()); assert.ok(value >= 0 && value < 1); }
});
test('layout keeps every star inside the inset and clear of the core for 1 to 6 projects', () => {
  for (const [w, h] of [[320, 640], [390, 844], [768, 1024], [1440, 900], [2560, 1440]]) for (const projects of [1, 2, 3, 6]) {
    const nodes = layout({nodes: Array.from({length: 30}, (_, i) => ({id: `n${i}`, project: `p${i % projects}`, weight: 1 + i % 5, kind: i % 6 ? 'Mission' : 'Project'})), edges: []}, w, h, 's');
    const core = coreCentre(w, h), keep = coreRadius(unit(w, h));
    assert.equal(nodes.length, 30);
    for (const n of nodes) {
      assert.ok(n.x >= INSET.left && n.x <= w - INSET.right && n.y >= INSET.top && n.y <= h - INSET.bottom, `${w}x${h} ${projects}: ${n.id} outside`);
      assert.ok(Math.hypot(n.x - core.x, n.y - core.y) >= keep, `${w}x${h} ${projects}: ${n.id} on the core`);
    }
  }
});
test('state aliases normalise and rich labels reserve the eyebrow width', () => {
  assert.equal(stateKey('Needs You'), 'needs-you'); assert.equal(stateKey('waiting'), 'needs-you'); assert.equal(stateKey(undefined), 'idle');
  const node = {id: 'a', label: 'Hi', x: 400, y: 300, radius: 6, state: 'idle', kind: 'Mission'};
  const [box] = placeLabels([node], 1440, 900, {size: 15, rich: true, measure: () => 20, metaOf: () => 'MISSION · IDLE', measureMeta: () => 150});
  assert.ok(box.width >= 150 && box.rich);
});
test('running and needs-you missions lay out as larger crystals than idle ones', () => {
  const mk = (id, state) => ({id, label: id, project: 'p', kind: 'Mission', state, weight: 3});
  const nodes = layout({nodes: [mk('a', 'idle'), mk('b', 'running'), mk('c', 'needs-you'), mk('d', 'done')], edges: []}, 1440, 900, 's');
  const r = id => nodes.find(n => n.id === id).radius;
  assert.ok(isCrystal({kind: 'Mission', state: 'Needs you'}) && !isCrystal({kind: 'Idea', state: 'running'}));
  assert.ok(r('b') > r('a') * 2 && r('c') === r('b') && r('d') === r('a'));
});

test('crystal radius is large on desktop and smaller on phones', () => {
  assert.ok(crystalRadius(1, 1440) >= 60 && crystalRadius(1, 390) <= 28 && crystalRadius(1, 390) >= 20);
});
test('crystal is a seeded convex hull: 60 to 100 edges, depth bands, bounded by its radius', async () => {
  const {crystal, hull3, triangle, coreStar, ICONS} = await import('./nodeart.js');
  const count = d => (d.match(/M/g) || []).length;
  for (const id of ['m-date', 'm-export', 'a1', 'prj-notes', 'x', 'long node id 7']) {
    const c = crystal(id, 80);
    assert.deepEqual(c, crystal(id, 80));
    assert.ok(c.edgeCount >= 60 && c.edgeCount <= 100, id + ' ' + c.edgeCount);
    assert.equal(c.edgeCount, 3 * c.vertexCount - 6);
    assert.equal(count(c.back) + count(c.mid) + count(c.front), c.edgeCount);
    assert.ok(count(c.front) > 0 && count(c.back) > 0 && count(c.dotsBack) + count(c.dotsFront) === c.vertexCount);
    for (const n of (c.outline.match(/-?d+.d/g) || []).map(Number)) assert.ok(Math.abs(n) <= 80.1);
  }
  assert.notDeepEqual(crystal('a', 80), crystal('b', 80));
  assert.ok(crystal('a', 20).edgeCount < 40 && crystal('a', 20).edgeCount === 3 * crystal('a', 20).vertexCount - 6);
  const {pts, edges} = hull3('a', 12);   // every point sits on the ellipsoid, so all of them are hull vertices
  assert.equal(new Set(edges.flat()).size, pts.length);
  assert.ok(triangle('x1', 40).outline.split('L').length === 3 && Object.keys(ICONS).length >= 6);
  const star = coreStar(40, 1.75);
  assert.ok((star.spikes.match(/M/g) || []).length === 16 && (star.threads.match(/M/g) || []).length >= 80);
});
test('layout honours a custom inset: stars stay below the headline band', () => {
  const nodes = layout({nodes: Array.from({length: 12}, (_, i) => ({id: `n${i}`, project: `p${i % 2}`, weight: 3, kind: 'Mission', state: 'idle'})), edges: []}, 1280, 800, 's', {top: 180, bottom: 76, left: 24, right: 24});
  for (const n of nodes) assert.ok(n.y >= 180 && n.y <= 800 - 76, `${n.id} outside the inset`);
});
test('layout is open: no two nodes overlap and none touches the core mark or its wordmark', () => {
  const kinds = ['Mission', 'Idea', 'Knowledge', 'Mission'], states = ['idle', 'running', 'needs-you', 'done'];
  for (const [w, h] of [[1280, 720], [1440, 900], [2000, 930]]) for (const projects of [1, 2, 3]) {
    const input = {nodes: [...Array.from({length: projects}, (_, i) => ({id: `p${i}`, kind: 'Project', project: `p${i}`, weight: 8})), ...Array.from({length: 12}, (_, i) => ({id: `n${i}`, project: `p${i % projects}`, weight: 3, kind: kinds[i % 4], state: states[i % 4]}))],
      edges: Array.from({length: 12}, (_, i) => ({from: `p${i % projects}`, to: `n${i}`}))};
    const nodes = layout(input, w, h, 'open', {top: 170, bottom: 76, left: 24, right: 24}), keep = coreKeepOut(w, h, unit(w, h), {top: 170, bottom: 76, left: 24, right: 24});
    nodes.forEach((a, i) => {
      assert.ok(Math.hypot(a.x - keep.x, a.y - keep.y) >= keep.radius * .99, `${w}x${h} ${projects}: ${a.id} on the core`);
      assert.ok(!coversNode(keep.box, a, 0), `${w}x${h} ${projects}: ${a.id} on the wordmark`);
      for (const b of nodes.slice(i + 1)) assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= (a.radius + b.radius) * .98, `${w}x${h} ${projects}: ${a.id} touches ${b.id}`);
    });
    assert.ok(nodes.filter(n => n.radius > 60).length <= 3);
  }
});
