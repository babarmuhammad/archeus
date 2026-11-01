import test from 'node:test';
import assert from 'node:assert/strict';
import {planBorn, cameraToward, BORN_MS} from './born.js';
import {INSET} from './geometry.js';

const hub = (id, x = 100, y = 100) => ({id, kind: 'Project', x, y, radius: 20, hub: true, cluster: id});
const mission = (id, project, x = 140, y = 100) => ({id, kind: 'Mission', project, x, y, radius: 10, cluster: project});

test('a born project is tagged on its hub and linked to the core by a dashed spoke', () => {
  const plan = planBorn([{id: 'p2', kind: 'project', project: 'p2'}], [hub('p1'), hub('p2')]);
  assert.deepEqual([...plan.tags], ['p2']);
  assert.deepEqual([...plan.spokes], ['p2']);
  assert.equal(plan.edges.size, 0);
  assert.equal(plan.focus, 'p2');
});

test('a born mission is tagged on its own mark and its relation to the project is the dashed link; if the mark is not drawn the hub stands for it', () => {
  const drawn = planBorn([{id: 'm1', kind: 'mission', project: 'p1'}], [hub('p1'), mission('m1', 'p1')]);
  assert.deepEqual([...drawn.tags], ['m1']);
  assert.deepEqual([...drawn.edges], ['m1']);
  assert.equal(drawn.spokes.size, 0);
  const hidden = planBorn([{id: 'm1', kind: 'mission', project: 'p1'}], [hub('p1')]);
  assert.deepEqual([...hidden.tags], ['p1']);
  assert.deepEqual([...hidden.spokes], ['p1']);
  assert.equal(hidden.focus, 'p1');
});

test('a born idea has no mark, so its project hub carries the tag; nothing born that the scene does not draw is planned', () => {
  const plan = planBorn([{id: 'i-9', kind: 'idea', project: 'p1'}, {id: 'i-10', kind: 'idea', project: 'p1'}], [hub('p1')]);
  assert.deepEqual([...plan.tags], ['p1']);
  assert.deepEqual([...plan.spokes], ['p1']);
  const none = planBorn([{id: 'p9', kind: 'project', project: 'p9'}], [hub('p1')]);
  assert.equal(none.tags.size + none.spokes.size + none.edges.size, 0);
  assert.equal(none.focus, null);
  assert.equal(planBorn(undefined, []).tags.size, 0);
});

test('the camera goes to a mark only when it is off the scene, keeps its zoom and centres the mark', () => {
  const camera = {x: 0, y: 0, k: 2};
  assert.equal(cameraToward({x: 300, y: 200}, camera, 1000, 700, INSET), null);
  const to = cameraToward({x: 900, y: 200}, camera, 1000, 700, INSET);
  assert.equal(to.k, 2);
  assert.equal(900 * 2 + to.x, 500);
  const top = INSET.top + 28, bottom = 700 - INSET.bottom - 28;
  assert.equal(200 * 2 + to.y, (top + bottom) / 2);
  assert.ok(cameraToward({x: 300, y: 690}, camera, 1000, 700, INSET), 'under the bottom band counts as off the scene');
});

test('the tag lasts six seconds', () => assert.equal(BORN_MS, 6000));
