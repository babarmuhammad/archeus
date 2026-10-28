import test from 'node:test';
import assert from 'node:assert/strict';
import {driftOf, coreKeepOut, layout, layoutProjects, projectsLegendBox, projectsKeepOut, randomSeed, placeLabels, overlaps, coversNode, convexHull, nearestNeighbour, stateKey, coreCentre, coreRadius, unit, INSET} from './geometry.js';

const graph = count => ({nodes: Array.from({length: count}, (_, i) => ({id: `n${i}`, label: `Node ${i}`, project: `p${i % 3}`, weight: i % 4 + 1, state: i === 2 ? 'needs-you' : 'idle'})), edges: []});
test('projects plates fit the inset, avoid each other and reserve the core for 1 to 8 projects', () => {
  for (const [width, viewport] of [[1280, 720], [1440, 900], [2000, 930], [390, 700], [620, 500], [760, 650], [1000, 700]]) for (let count = 1; count <= 8; count++) {
    const height = Math.max(viewport, (width < 600 ? count : Math.ceil(count / 2)) * 56 + (width < 600 ? 120 : 0) + INSET.top + 142);
    const input = {nodes: Array.from({length: count}, (_, i) => ({id: `p${i}`, project: `p${i}`, kind: 'Project', label: `Project ${i}`, missionCount: i})), edges: []};
    const snapshot = structuredClone(input), nodes = layoutProjects(input, width, height), keep = projectsKeepOut(width, height);
    const legend = projectsLegendBox(width, height);
    assert.equal(legend.x, 16);
    assert.equal(height - legend.y - legend.height, 16);
    assert.ok(legend.x >= 0 && legend.y >= 0 && legend.x + legend.width <= width && legend.y + legend.height <= height);
    assert.ok(!overlaps(legend, keep.box) && !coversNode(legend, keep, 0), `${width}x${height}: legend/core`);
    assert.equal(nodes.length, count);
    assert.deepEqual(nodes, layoutProjects({...input, nodes: [...input.nodes].reverse()}, width, height));
    assert.deepEqual(input, snapshot);
    const boxes = nodes.map(n => ({x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width, height: n.height}));
    boxes.forEach((box, i) => {
      const message = `${width}x${height}, ${count} projects, ${i}`;
      assert.ok(box.width >= 44 && box.height >= 44, message + ': target');
      assert.ok(box.x >= INSET.left && box.y >= INSET.top && box.x + box.width <= width - INSET.right && box.y + box.height <= height - INSET.bottom, message + ': inset');
      assert.ok(!overlaps(box, keep.box) && !coversNode(box, keep, 0), message + ': core');
      assert.ok(!overlaps(box, legend, 2), message + ': legend');
      for (const other of boxes.slice(i + 1)) assert.ok(!overlaps(box, other, 8), message + ': overlap');
    });
  }
  assert.deepEqual(layoutProjects({nodes: [], edges: []}, 390, 700), []);
});

test('projects retain captured idea plates and ignore unrelated mission nodes', async () => {
  const {projectPlateMarkup} = await import('./nodeart.js');
  const input = {nodes: [{id: 'p', project: 'p', kind: 'Project', label: '<Project>', missionCount: 2}, {id: 'i', project: 'p', kind: 'Idea', label: '<Idea>'}, {id: 'm', project: 'p', kind: 'Mission'}]};
  const nodes = layoutProjects(input, 1280, 720);
  assert.deepEqual(nodes.map(n => n.id), ['p', 'i']);
  const plate = projectPlateMarkup(nodes[0]);
  assert.ok(plate.includes('2 missions') && !plate.includes('<Project>'));
  assert.ok(projectPlateMarkup(nodes[1]).includes('Captured'));
  const {ICONS} = await import('./nodeart.js');
  assert.ok(plate.includes(ICONS.folder));
  assert.ok(projectPlateMarkup(nodes[1]).includes(ICONS.bulb));
  for (const [width, height] of [[1280, 720], [1440, 900], [2000, 930], [390, 700], [620, 500]]) {
    const legend = projectsLegendBox(width, height);
    for (const n of layoutProjects(input, width, height)) assert.ok(!overlaps(legend, {x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width, height: n.height}));
  }
});
test('generated label sets never overlap another label, star, or reserved area', () => {
  for (const width of [320, 479, 480, 960, 1280, 2560]) {
    const nodes = layout(graph(80), width, 700).nodes;
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
test('drift is seeded, small and slow, and differs per id', () => {
  const a = driftOf('s', 'n1'), b = driftOf('s', 'n2');
  assert.deepEqual(a, driftOf('s', 'n1'));
  assert.notDeepEqual(a, b);
  for (let i = 0; i < 200; i++) { const d = driftOf('s', 'n' + i); assert.ok(Math.hypot(d.dx, d.dy) <= 3.01 && Math.hypot(d.dx, d.dy) >= 1.49); assert.ok(d.period >= 9000 && d.period <= 17000 && d.delay <= 0 && d.delay >= -d.period); }
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
test('state aliases normalise and rich labels reserve the eyebrow width', () => {
  assert.equal(stateKey('Needs You'), 'needs-you'); assert.equal(stateKey('waiting'), 'needs-you'); assert.equal(stateKey(undefined), 'idle');
  const node = {id: 'a', label: 'Hi', x: 400, y: 300, radius: 6, state: 'idle', kind: 'Mission'};
  const [box] = placeLabels([node], 1440, 900, {size: 15, rich: true, measure: () => 20, metaOf: () => 'MISSION · IDLE', measureMeta: () => 150});
  assert.ok(box.width >= 150 && box.rich);
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
test('calm layout lists only projects: panels apart, clear of the core mark and wordmark, inside the inset', async () => {
  const {layoutCalm} = await import('./geometry.js'), inset = {top: 16, bottom: 300, left: 24, right: 24};
  for (const [w, h] of [[1280, 720], [1440, 900], [2000, 930], [390, 700]]) for (const count of [1, 2, 3, 4, 5, 6, 8]) {
    const graph = {nodes: [...Array.from({length: count}, (_, i) => ({id: `p${i}`, kind: 'Project', project: `p${i}`})), {id: 'm', kind: 'Mission', project: 'p0'}], edges: []};
    const ins = w < 600 ? {...inset, bottom: 230} : inset, nodes = layoutCalm(graph, w, h, 's', ins), keep = coreKeepOut(w, h, unit(w, h), ins, true);
    assert.equal(nodes.length, count);
    nodes.forEach((a, i) => {
      assert.ok(a.x - a.radius >= 0 && a.x + a.radius <= w && a.y - a.radius >= ins.top - 1 && a.y + a.radius <= h - ins.bottom + 1, `${w}x${h} ${count}: ${a.id} outside`);
      assert.ok(Math.hypot(a.x - keep.x, a.y - keep.y) >= keep.radius + a.radius * .5 - 1 && !coversNode(keep.box, a, 0), `${w}x${h} ${count}: ${a.id} on the core`);
      for (const b of nodes.slice(i + 1)) assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= a.radius * 2, `${w}x${h} ${count}: panels touch`);
    });
  }
});

test('projects: a long list keeps a plate-high step between rows, so no plate sits on another', () => {
  const input = {nodes: Array.from({length: 200}, (_, i) => ({id: `p${String(i).padStart(3, '0')}`, project: `p${i}`, kind: 'Project', label: `Project ${i}`, missionCount: 0})), edges: []};
  for (const [width, height] of [[1280, 600], [1440, 900], [390, 700]]) {
    const boxes = layoutProjects(input, width, height).map(n => ({x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width, height: n.height}));
    boxes.forEach((box, i) => { for (const other of boxes.slice(i + 1)) assert.ok(!overlaps(box, other), `${width}x${height}: ${i}`); });
  }
});

test('projects: a captured idea whose project is missing or unknown still gets a plate', () => {
  const idea = (id, project) => ({id, project, kind: 'Idea', label: id});
  assert.deepEqual(layoutProjects({nodes: [idea('i1', null)]}, 1280, 720).map(n => n.id), ['i1']);
  const nodes = layoutProjects({nodes: [{id: 'p', project: 'p', kind: 'Project', label: 'P', missionCount: 0}, idea('i2', 'gone'), idea('i1', 'p')]}, 1280, 720);
  assert.deepEqual(nodes.map(n => n.id), ['p', 'i1', 'i2']);
});
