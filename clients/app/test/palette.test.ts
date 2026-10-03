// The command palette (rulebook §18; D-12): hits from what this client read,
// actions offered by the state table with their effect from Core's live work,
// ↑/↓ over the hits.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PALETTE_SHOWN, effectOf, moveActive, paletteHits } from '../src/state/palette.ts';

const input = {
  destinations: [{ id: 'work', label: 'Work', to: '#/work' }],
  missions: [
    { id: 'msn_1', title: 'Ship the chart', state: 'EXECUTING', version: 3 },
    { id: 'msn_2', title: 'Write the notes', state: 'PAUSED', version: 1 },
    { id: 'msn_3', title: 'Done thing', state: 'COMPLETED', version: 9 },
  ],
  projects: [{ id: 'prj_1', name: 'Atlas' }],
  knowledge: [{ id: 'kno_1', title: 'A deploy asks first' }, { id: 'kno_2', title: null }],
  live: [{ mission_id: 'msn_1' }, { mission_id: 'msn_1' }, { mission_id: 'msn_9' }],
};

test('an action is offered exactly where the state table has its trigger', () => {
  const labels = paletteHits(input, '').map((h) => h.label);
  const all = paletteHits({ ...input, destinations: [], projects: [], knowledge: [] }, '').map((h) => h.label);
  assert.deepEqual(all, ['Mission: Ship the chart', 'Pause “Ship the chart”', 'Mission: Write the notes', 'Resume “Write the notes”', 'Mission: Done thing']);
  assert.equal(labels[0], 'Go to Work');
});

test('the effect is said from Core\'s live work', () => {
  const pause = paletteHits(input, 'pause').find((h) => 'act' in h);
  assert.ok(pause && 'effect' in pause && pause.effect === '2 running attempts pause');
  assert.equal(effectOf('pause', input.missions[1], input.live), 'nothing of it is running now');
  assert.equal(effectOf('pause', input.missions[0], [{ mission_id: 'msn_1' }]), '1 running attempt pauses');
  assert.equal(effectOf('resume', input.missions[1], input.live), 'its work is dispatched again');
});

test('search is over the reads held, by words, capped', () => {
  assert.deepEqual(paletteHits(input, 'atlas').map((h) => h.label), ['Project: Atlas', 'Open “Atlas” as a graph']);
  assert.equal(paletteHits(input, 'atlas')[1].key, 'graph:prj_1');
  assert.deepEqual(paletteHits(input, 'deploy').map((h) => h.label), ['Knowledge: A deploy asks first']);
  assert.ok(paletteHits(input, '').length <= PALETTE_SHOWN);
  assert.equal(paletteHits(input, 'nothing like it').length, 0);
});

test('↑/↓ move the active hit round the list; other keys stay the text field\'s', () => {
  assert.equal(moveActive(0, 3, 'ArrowDown'), 1);
  assert.equal(moveActive(2, 3, 'ArrowDown'), 0);
  assert.equal(moveActive(0, 3, 'ArrowUp'), 2);
  assert.equal(moveActive(0, 3, 'Home'), null);
  assert.equal(moveActive(0, 0, 'ArrowDown'), null);
});
