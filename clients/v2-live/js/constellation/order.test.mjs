import test from 'node:test';
import assert from 'node:assert/strict';
import {orderProjects, leadMission} from './order.js';

test('projects needing you come first, then running, then the most recent', () => {
  const list = orderProjects([{id: 'a', attention: 0, running: 0, lastAt: 9}, {id: 'b', attention: 1, running: 0, lastAt: 1}, {id: 'c', attention: 0, running: 2, lastAt: 5}, {id: 'd', attention: 0, running: 0, lastAt: 20}]);
  assert.deepEqual(list.map(p => p.id), ['b', 'c', 'd', 'a']);
});
test('the lead mission is the one that needs you, else the one that runs, else the latest', () => {
  assert.equal(leadMission({missions: [{id: 'x', state: 'done', at: 9}, {id: 'y', state: 'needs-you', at: 1}, {id: 'z', state: 'running', at: 5}]}).id, 'y');
  assert.equal(leadMission({missions: []}), null);
});
