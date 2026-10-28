import test from 'node:test';
import assert from 'node:assert/strict';
import { railProjects } from '../js/rail-model.js';

const ps = Array.from({ length: 10 }, (_, i) => ({ id: 'p' + i }));
const states = { p7: 'needs_you', p3: 'running', p9: 'needs_you', p1: 'done' };
const st = (p) => states[p.id] || 'idle';

test('few projects keep their order and nothing is hidden', () => {
  const r = railProjects(ps.slice(0, 4), st, null, 4);
  assert.deepEqual(r.shown.map((p) => p.id), ['p0', 'p1', 'p2', 'p3']);
  assert.equal(r.more, 0);
});
test('many projects: needs you, then running, then the rest in given order', () => {
  const r = railProjects(ps, st, null, 4);
  assert.deepEqual(r.shown.map((p) => p.id), ['p7', 'p9', 'p3', 'p0']);
  assert.equal(r.more, 6);
});
test('the selected project is always shown', () => {
  const r = railProjects(ps, st, 'p5', 4);
  assert.deepEqual(r.shown.map((p) => p.id), ['p7', 'p9', 'p3', 'p5']);
  assert.equal(r.more, 6);
});
