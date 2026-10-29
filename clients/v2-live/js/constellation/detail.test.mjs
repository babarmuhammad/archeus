import test from 'node:test';
import assert from 'node:assert/strict';
import {levelFor, expansion, costOf, pickFocus, receding, sameLevels, expandCluster, UP, HYST, BUDGET, OVERVIEW_MAX, MAX_K, MIN_K} from './detail.js';

const hubAt = {x: 0, y: 0, tag: {width: 200}, outward: 0};
const missions = n => Array.from({length: n}, (_, i) => ({id: `m${i}`, kind: 'Mission', project: 'p', label: `Mission ${i}`, state: ['needs-you', 'running', 'idle', 'done'][i % 4]}));
const kidsFor = (ms, per) => new Map(ms.map(m => [m.id, Array.from({length: per}, (_, i) => ({id: `${m.id}-k${i}`, kind: ['Task', 'Execution', 'Verification', 'Decision'][i % 4], project: 'p', state: 'idle'}))]));
const wts = n => Array.from({length: n}, (_, i) => ({id: `w${i}`, kind: 'Worktree', project: 'p', label: `branch/${i}`, state: 'idle'}));
const gap = (a, b) => Math.hypot(a.x - b.x, a.y - b.y) - a.radius - b.radius;

test('levels follow the zoom scale: 1, 1.6, 3.2 and 6.4 begin a level', () => {
  assert.deepEqual([.5, 1, 1.59, 1.6, 3.19, 3.2, 6.39, 6.4, 8].map(k => levelFor(k, 0)), [0, 0, 0, 1, 1, 2, 2, 3, 3]);
  assert.ok(MIN_K < 1 && MAX_K >= UP[3]);
});
test('hysteresis: a level is kept until the scale falls 15 % under its start, so a wheel hovering at a threshold does not flicker', () => {
  assert.equal(levelFor(1.5, 1), 1);            // the level begins at 1.6 and is kept down to 1.6 / 1.15 = 1.39
  assert.equal(levelFor(1.4, 1), 1);
  assert.equal(levelFor(1.39, 1), 0);
  assert.equal(levelFor(1.6, 0), 1);
  let l = 0; const seen = [];
  for (const k of [1.55, 1.62, 1.58, 1.61, 1.57, 1.5, 1.45]) { l = levelFor(k, l); seen.push(l); }
  assert.deepEqual(seen, [0, 1, 1, 1, 1, 1, 1]);
  assert.ok(OVERVIEW_MAX < UP[1] / HYST, 'Fit stays under the first level, whatever it was');
  assert.equal(levelFor(OVERVIEW_MAX, 3), 0);
});
test('only the projects near the centre open; the nearest goes deepest, the rest stop at level 2', () => {
  const hubs = [{id: 'a', x: 500, y: 400, missions: 5, ideas: 1}, {id: 'b', x: 560, y: 400, missions: 5, ideas: 0}, {id: 'c', x: 900, y: 400, missions: 5, ideas: 0}, {id: 'far', x: 5000, y: 5000, missions: 5, ideas: 0}];
  const r = expansion({k: 7, hubs, centre: {x: 500, y: 400}, radius: 450});
  assert.equal(r.global, 3);
  assert.deepEqual([...r.levels], [['a', 3], ['b', 2], ['c', 2]]);
  assert.equal(expansion({k: 1.2, hubs, centre: {x: 500, y: 400}, radius: 450}).levels.size, 0, 'nothing opens in the overview');
  assert.equal(expansion({k: 2, hubs, centre: {x: 500, y: 400}, radius: 450}).levels.get('a'), 1);
});
test('an open project stays open a little farther out than one that is closed', () => {
  const hubs = [{id: 'a', x: 500 + 460, y: 400, missions: 3, ideas: 0}];
  assert.equal(expansion({k: 3, hubs, centre: {x: 500, y: 400}, radius: 450}).levels.size, 0);
  assert.equal(expansion({k: 3, hubs, centre: {x: 500, y: 400}, radius: 450, prev: new Map([['a', 2]])}).levels.size, 1);
});
test('the node budget holds at 100 projects: 300 detailed nodes at most, nearest first', () => {
  const hubs = Array.from({length: 100}, (_, i) => ({id: `p${i}`, x: 100 + (i % 10) * 40, y: 100 + Math.floor(i / 10) * 40, missions: 40, ideas: 5, worktrees: 2}));
  const r = expansion({k: 7, hubs, centre: {x: 300, y: 300}, radius: 2000});
  const total = [...r.levels].reduce((t, [id, lv]) => t + costOf(40, 5, lv, 2), 0);
  assert.ok(total <= BUDGET, `${total} costs`);
  assert.ok(r.levels.size >= 1 && r.levels.size < 100);
  assert.equal([...r.levels.keys()][0], 'p55', 'the nearest hub is first (and the deepest)');
  assert.equal(expansion({k: 7, hubs, centre: {x: 300, y: 300}, radius: 2000, budget: 10}).levels.size, 0, 'a budget too small for any project opens none');
});
test('the focused mission changes only when another is clearly nearer', () => {
  const c = [{id: 'x', d: 50}, {id: 'y', d: 35}];
  assert.equal(pickFocus('x', c), 'x');
  assert.equal(pickFocus('x', [{id: 'x', d: 60}, {id: 'y', d: 35}]), 'y');
  assert.equal(pickFocus(null, c), 'y');
  assert.equal(pickFocus('x', []), null);
});
test('a closed project under an open one gives way', () => {
  const out = receding([{id: 'a', x: 0, y: 0}, {id: 'b', x: 80, y: 0}, {id: 'c', x: 900, y: 0}], [{id: 'a', x: 0, y: 0, extent: 100}]);
  assert.deepEqual([...out], ['b']);
  assert.ok(sameLevels(new Map([['a', 1]]), new Map([['a', 1]])) && !sameLevels(new Map([['a', 1]]), new Map([['a', 2]])));
});
test('two open projects that overlap: the one nearer the centre stays, the other gives way to it', () => {
  const hubs = [{id: 'a', x: 0, y: 0}, {id: 'b', x: 80, y: 0}, {id: 'c', x: 900, y: 0}], open = [{id: 'a', x: 0, y: 0, extent: 100}, {id: 'b', x: 80, y: 0, extent: 100}];
  assert.deepEqual([...receding(hubs, open)], ['b']);
  assert.deepEqual([...receding(hubs, [open[1], open[0]])], ['a']);
});

for (const level of [1, 2, 3]) {
  test(`level ${level}: a project with 60 missions fits rings with no overlap, the count and the extent grow, and the rest is counted`, () => {
    const ms = missions(60), r = expandCluster({level, key: 'p', hub: hubAt, missions: ms, kids: kidsFor(ms, 3), ideas: [{id: 'i1', kind: 'Idea'}, {id: 'i2', kind: 'Idea'}], events: [], focusId: 'm0'});
    const m = r.nodes.filter(n => n.kind === 'Mission');
    assert.equal(m.length + r.quiet, 60);
    assert.ok(m.length === 60, `all ${m.length} placed`);
    for (let i = 0; i < r.nodes.length; i++) for (let j = i + 1; j < r.nodes.length; j++) assert.ok(gap(r.nodes[i], r.nodes[j]) > -.01, `${r.nodes[i].id} touches ${r.nodes[j].id}`);
    for (const n of r.nodes) assert.ok(Math.hypot(n.x, n.y) >= r.hub.radius + n.radius, `${n.id} sits on the hub`);
    assert.ok(r.nodes.length <= BUDGET);
    const small = expandCluster({level, key: 'p', hub: hubAt, missions: missions(3)}), s = n => n.extent;
    assert.ok(s(r) > s(small) * 2, 'the cluster radius grows with the count');
    assert.ok(s(r) < 40 * Math.sqrt(60) / UP[Math.min(level, 2)] * 6, 'and stays bounded');
  });
}
test('0 missions: an empty hub, nothing else', () => {
  const r = expandCluster({level: 2, key: 'p', hub: hubAt, missions: []});
  assert.equal(r.nodes.length, 0);
  assert.equal(r.quiet, 0);
  assert.equal(r.hub.lines, 2);
});
test('ideas are marks of their own, counted apart from missions', () => {
  const r = expandCluster({level: 1, key: 'p', hub: hubAt, missions: missions(2), ideas: Array.from({length: 4}, (_, i) => ({id: `i${i}`, kind: 'Idea'}))});
  assert.equal(r.nodes.filter(n => n.kind === 'Idea').length, 4);
  assert.equal(r.nodes.filter(n => n.kind === 'Mission').length, 2);
  assert.ok(r.edges.filter(e => e.to.startsWith('i')).every(e => e.from === 'p' && e.kind === 'contains'));
});
test('a mission cap leaves "+N quiet" and the deeper level shows no more than its cap', () => {
  const r = expandCluster({level: 2, key: 'p', hub: hubAt, missions: missions(90)});
  assert.equal(r.nodes.filter(n => n.kind === 'Mission').length + r.quiet, 90);
  assert.ok(r.quiet >= 30);
});
test('only the focused mission has an events ring, at the deepest level', () => {
  const ms = missions(5), events = Array.from({length: 20}, (_, i) => ({id: `e${i}`, kind: 'Event', project: 'p', label: `event ${i}`}));
  const deep = expandCluster({level: 3, key: 'p', hub: hubAt, missions: ms, kids: kidsFor(ms, 2), events, focusId: 'm2'});
  const ev = deep.nodes.filter(n => n.kind === 'Event');
  assert.equal(ev.length, 16, 'the last 16');
  assert.ok(ev.every(e => e.parent === 'm2'));
  assert.equal(deep.nodes.filter(n => n.parent === 'm2' && n.kind !== 'Event').length, 0, 'its marks give way to the ring');
  assert.equal(expandCluster({level: 2, key: 'p', hub: hubAt, missions: ms, events, focusId: 'm2'}).nodes.filter(n => n.kind === 'Event').length, 0);
});
test('level 1 has the live marks, level 2 has tasks and attempts, verification and approval', () => {
  const ms = missions(4), kids = kidsFor(ms, 4);
  const kinds = level => new Set(expandCluster({level, key: 'p', hub: hubAt, missions: ms, kids}).nodes.filter(n => n.parent && n.kind !== 'Mission').map(n => n.kind));
  assert.equal(kinds(1).size, 2, 'two marks per mission at most');
  assert.deepEqual([...kinds(2)].sort(), ['Decision', 'Execution', 'Task', 'Verification']);
});
test('the cluster keeps off a blocked place (the core, the zoom column, another hub)', () => {
  const blocked = (x, y, r) => Math.hypot(x - 60, y) < 40 + r;
  const r = expandCluster({level: 1, key: 'p', hub: hubAt, missions: missions(20), blocked});
  assert.ok(r.nodes.every(n => !blocked(n.x, n.y, n.radius)));
  assert.equal(r.nodes.filter(n => n.kind === 'Mission').length, 20);
});
test('the limit stops the cluster at the node budget it is given', () => {
  const ms = missions(60), r = expandCluster({level: 2, key: 'p', hub: hubAt, missions: ms, kids: kidsFor(ms, 4), limit: 25});
  assert.equal(r.nodes.length, 25);
});

test('worktrees: a project with 6 hangs its missions off them, a project with 0 is as before', () => {
  const ms = missions(12).map((m, i) => ({...m, worktree: i < 9 ? `w${i % 6}` : null}));
  const r = expandCluster({level: 1, key: 'p', hub: hubAt, missions: ms, worktrees: wts(6)});
  const w = r.nodes.filter(n => n.kind === 'Worktree');
  assert.equal(w.length, 6);
  assert.equal(r.wtQuiet, 0);
  assert.equal(r.nodes.filter(n => n.kind === 'Mission').length, 12);
  for (let i = 0; i < r.nodes.length; i++) for (let j = i + 1; j < r.nodes.length; j++) assert.ok(gap(r.nodes[i], r.nodes[j]) > -.01, `${r.nodes[i].id} touches ${r.nodes[j].id}`);
  // edges run hub - worktree - mission and nothing else: a mission has one parent, a worktree hangs off the hub
  for (const e of r.edges) assert.ok(e.from === 'p' || r.nodes.some(n => n.id === e.from));
  const parent = id => r.edges.filter(e => e.to === id);
  for (const n of r.nodes.filter(n => n.kind === 'Mission')) {
    assert.equal(parent(n.id).length, 1);
    assert.equal(parent(n.id)[0].from, n.worktree || 'p', `${n.id} hangs off its worktree, or the hub when it has none`);
  }
  for (const n of w) assert.deepEqual(parent(n.id).map(e => e.from), ['p']);
  assert.ok(w.every(n => n.radius < r.nodes.find(m => m.kind === 'Mission').radius), 'a sub-hub is smaller than a mission');
  const none = expandCluster({level: 1, key: 'p', hub: hubAt, missions: missions(12), worktrees: []});
  assert.equal(none.nodes.filter(n => n.kind === 'Worktree').length, 0);
  assert.ok(none.edges.every(e => e.from === 'p'));
});
test('a worktree with no mission stands alone; a mission whose worktree is not shown hangs off the hub', () => {
  const r = expandCluster({level: 1, key: 'p', hub: hubAt, missions: [{...missions(1)[0], worktree: 'gone'}], worktrees: wts(2)});
  assert.equal(r.nodes.filter(n => n.kind === 'Worktree').length, 2);
  assert.equal(r.edges.find(e => e.to === 'm0').from, 'p');
});
test('at the overview level a project opens nothing, so worktrees stay a count (the cost of a closed project is 0)', () => {
  assert.equal(costOf(10, 2, 0, 4), 0);
  assert.ok(costOf(10, 2, 1, 4) >= 10 + 4);
});
