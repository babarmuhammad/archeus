import test from 'node:test';
import assert from 'node:assert/strict';
import {missionScene, sceneMarkup, BOX} from './scene.js';

const full = {id: 'm1', title: 'Fix date test', lines: ['Project: Archeus'], state: 'running', exec: {title: 'Codex'}, result: {title: 'Verification', lines: ['Running']}, task: {title: 'Date suite'}, out: true};
test('mission scene draws only the relations the record holds', () => {
  assert.deepEqual(missionScene(full).arrows.map(a => a.label), ['ORCHESTRATES', 'EXECUTES', 'RESULTS IN', 'USES', 'PRODUCES', 'VERIFIES']);
  assert.deepEqual(missionScene({id: 'm2', title: 'Bare', state: 'idle'}).arrows.map(a => a.label), ['ORCHESTRATES']);
  const noOut = missionScene({...full, out: false});
  assert.ok(!noOut.arrows.some(a => ['PRODUCES', 'VERIFIES'].includes(a.label)) && noOut.nodes.length === 4);
  assert.ok(!missionScene({...full, result: {title: 'Review', meta: 'REVIEW'}}).arrows.some(a => a.label === 'VERIFIES'));
});
test('mission scene is deterministic, inside its box, and its arrows run rim to rim', () => {
  const a = missionScene(full), b = missionScene(full);
  assert.deepEqual(a, b);
  assert.equal(sceneMarkup(a), sceneMarkup(b));
  for (const n of a.nodes) assert.ok(n.x - n.radius >= 0 && n.x + n.radius <= BOX.width && n.y + n.radius <= BOX.height - 70, n.id);
  for (const arrow of a.arrows) for (const [x, y] of [[arrow.x1, arrow.y1], [arrow.x2, arrow.y2]])
    for (const n of a.nodes) assert.ok(Math.hypot(x - n.x, y - n.y) >= n.radius, `${arrow.label} enters ${n.id}`);
  assert.ok(a.nodes.some(n => n.radius >= 100) && a.nodes.filter(n => n.radius >= 100).length === 1);
});
test('scene markup uses the shared node art, escapes text and carries every label', () => {
  const svg = sceneMarkup(missionScene({...full, title: '<b>&"'}), s => s);
  assert.ok(svg.includes('am-e2') && svg.includes('am-arrowhead') && svg.includes('am-core-thread') && svg.includes('&#60;b&#62;&#38;&#34;'));
  assert.ok(!svg.includes('<b>'));
  for (const word of ['ORCHESTRATES', 'EXECUTES', 'RESULTS IN', 'USES', 'PRODUCES', 'VERIFIES', 'ARCHEUS']) assert.ok(svg.includes(word), word);
});
