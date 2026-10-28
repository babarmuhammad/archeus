import test from 'node:test';
import assert from 'node:assert/strict';
import {LANES, TIERS, tierOf, laneOf, markRadius, perimeter, pointsOn, layoutRings} from './rings.js';
import {coversNode} from './geometry.js';

const inset = {top: 150, right: 24, bottom: 88, left: 24};
const mk = (n, laneFor = i => LANES[i % 5], missions = i => 3 + (i % 9)) => Array.from({length: n}, (_, i) => ({id: 'p' + String(i).padStart(3, '0'), lane: laneFor(i), missions: missions(i), worktrees: i % 3}));
const lay = (projects, w = 1440, h = 900, memory) => layoutRings(projects, w, h, inset, {memory});

test('tiers: pitch 96 for 1 to 12 projects, 64 for 13 to 40, 28 for 41 and more', () => {
  assert.deepEqual([1, 12, 13, 40, 41, 100, 400].map(n => tierOf(n).pitch), [96, 96, 64, 64, 28, 28, 28]);
  assert.deepEqual(TIERS.map(t => t.name), ['named', 'mixed', 'dense']);
});
test('a project sits on the lane of its worst state, with all its missions counted', () => {
  assert.equal(laneOf({running: 3, done: 9}, 0), 'running');
  assert.equal(laneOf({blocked: 1, running: 3}, 0), 'blocked');
  assert.equal(laneOf({done: 4}, 1), 'needs-you');
  assert.equal(laneOf({'needs-you': 1, blocked: 2}, 0), 'needs-you');
  assert.equal(laneOf({done: 4}, 0), 'done');
  assert.equal(laneOf({}, 0), 'paused');
  assert.equal(laneOf({thinking: 2, idle: 1}, 0), 'paused');
  assert.equal(laneOf({done: 2, idle: 1}, 0), 'paused');
});
test('mark radius grows with the square root of the missions inside the tier range', () => {
  const [named, mixed, dense] = TIERS;
  assert.equal(markRadius(0, named), 10); assert.equal(markRadius(500, named), 26); assert.ok(markRadius(7, named) > markRadius(2, named));
  assert.ok(markRadius(500, mixed) === 18 && markRadius(0, mixed) === 7 && markRadius(500, dense) === 9 && markRadius(0, dense) === 3);
});
test('points on a lane are even by arc length and the first stands at the start angle', () => {
  const pts = pointsOn(200, 120, 20, 90), d = pts.map((p, i) => Math.hypot(p.x - pts[(i + 1) % 20].x, p.y - pts[(i + 1) % 20].y));
  assert.ok(Math.max(...d) / Math.min(...d) < 1.12, 'spacing ' + Math.min(...d) + ' to ' + Math.max(...d));
  assert.ok(Math.abs(pts[0].deg - 90) < 1.5 && pts[0].x > 190);
  assert.ok(Math.abs(perimeter(100, 100) - 2 * Math.PI * 100) < .01);
});
test('one lane per state that has members, in the order needs you, blocked, running, paused, done', () => {
  const r = lay(mk(3, i => ['paused', 'needs-you', 'running'][i]));
  assert.deepEqual(r.lanes.map(l => l.state), ['needs-you', 'running', 'paused']);
  assert.ok(r.lanes[0].rx < r.lanes[1].rx && r.lanes[1].rx < r.lanes[2].rx);
  assert.deepEqual(r.order.map(id => r.nodes.find(n => n.id === id).state), ['needs-you', 'running', 'paused']);
  const all = lay(mk(5));
  assert.deepEqual(all.lanes.map(l => l.state), [...LANES]);
});
test('capacity is the perimeter over the pitch of the tier', () => {
  for (const [count, pitch] of [[6, 96], [30, 64], [100, 28]]) {
    const r = lay(mk(count, () => 'running')), l = r.lanes[0];
    assert.equal(l.slots, Math.floor(perimeter(l.rx, l.ry) / pitch), count + ' projects');
  }
});
test('overflow adds a lane of the same state just outside, before the next state starts', () => {
  const projects = [...mk(25, () => 'needs-you', () => 5), ...mk(3, () => 'running').map(p => ({...p, id: 'r' + p.id}))];
  const r = lay(projects), states = r.lanes.map(l => l.state);
  assert.ok(states.filter(s => s === 'needs-you').length >= 2, states.join());
  assert.equal(states.lastIndexOf('needs-you') + 1, states.indexOf('running'));
  const need = r.lanes.filter(l => l.state === 'needs-you');
  assert.ok(need[0].members.length === need[0].capacity && need[1].members.length > 0);
  assert.deepEqual(need.map(l => l.n), need.map((_, i) => i));
  assert.ok(need[1].ry > need[0].ry && need[1].rx > need[0].rx);
  assert.equal(r.nodes.length, 28);
});
test('slots are stable: a new project never moves another', () => {
  const before = mk(10, i => (i < 7 ? 'needs-you' : 'running')), a = lay(before), grown = [...before, {id: 'zz1', lane: 'needs-you', missions: 4, worktrees: 0}], b = lay(grown, 1440, 900, a.memory);
  for (const n of a.nodes) { const m = b.nodes.find(x => x.id === n.id); assert.deepEqual([m.x, m.y], [n.x, n.y], n.id); }
  // a project that leaves leaves a hole that the next one takes, the rest stay
  const left = lay(grown.filter(p => p.id !== 'p002'), 1440, 900, b.memory), again = lay([...grown.filter(p => p.id !== 'p002'), {id: 'zz2', lane: 'needs-you', missions: 1, worktrees: 0}], 1440, 900, left.memory);
  for (const n of left.nodes) { const m = again.nodes.find(x => x.id === n.id); assert.deepEqual([m.x, m.y], [n.x, n.y], n.id); }
  assert.deepEqual([again.nodes.find(x => x.id === 'zz2').x, again.nodes.find(x => x.id === 'zz2').y], [b.nodes.find(x => x.id === 'p002').x, b.nodes.find(x => x.id === 'p002').y]);
  // overflowing into a new last lane leaves the earlier states where they are
  const full = lay(mk(20, () => 'needs-you'), 1440, 900), more = lay([...mk(20, () => 'needs-you'), {id: 'new', lane: 'needs-you', missions: 2}], 1440, 900, full.memory);
  for (const n of full.nodes) { const m = more.nodes.find(x => x.id === n.id); assert.deepEqual([m.x, m.y], [n.x, n.y], n.id); }
});
test('1, 3, 30 and 100 projects: every mark is placed, clear of the core keep zone and of each other, inside the scene', () => {
  for (const count of [1, 3, 30, 100]) for (const [w, h] of [[1440, 900], [1024, 768], [1920, 1080]]) {
    const r = lay(mk(count), w, h);
    assert.equal(r.nodes.length, count); assert.equal(r.order.length, count);
    for (const n of r.nodes) {
      assert.ok(Math.hypot(n.x - r.keep.x, n.y - r.keep.y) >= r.keep.radius + n.radius - .01, `${count}@${w}: ${n.id} in the core zone`);
      assert.ok(!coversNode(r.keep.box, n, 0), `${count}@${w}: ${n.id} on the wordmark`);
      assert.ok(n.x - n.radius >= 0 && n.x + n.radius <= w && n.y - n.radius >= inset.top - 1 && n.y + n.radius <= h - inset.bottom + 1, `${count}@${w}: ${n.id} outside`);
    }
    for (let i = 0; i < r.nodes.length; i++) for (let k = i + 1; k < r.nodes.length; k++) { const a = r.nodes[i], b = r.nodes[k]; assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= a.radius + b.radius - .01, `${count}@${w}: ${a.id} and ${b.id} touch`); }
    assert.ok(r.fits !== false, `${count}@${w} fits`);
  }
});
test('the controls column stays free', () => {
  const ctl = {x: 1440 - 68, y: 900 - 100 - 156, width: 68, height: 160}, r = layoutRings(mk(30, () => 'running'), 1440, 900, inset, {avoid: [ctl]});
  for (const n of r.nodes) assert.ok(!coversNode(ctl, n, 0), n.id);
});
test('a narrow scene (360, 390, 430 px) still holds every project', () => {
  for (const w of [360, 390, 430]) for (const count of [3, 30]) {
    const r = layoutRings(mk(count), w, 560, {top: 16, right: 16, bottom: 16, left: 16});
    assert.equal(r.nodes.length, count);
    for (const n of r.nodes) assert.ok(n.x >= 0 && n.x <= w, `${w}: ${n.id} at ${n.x}`);
  }
});
test('no projects, no lanes', () => assert.deepEqual(lay([]).nodes, []));
test('a scene too small for any slot still places every project (no throw)', () => {
  const r = layoutRings(mk(3), 40, 40, {top: 16, right: 16, bottom: 16, left: 16});
  assert.equal(r.nodes.length, 3);
});
