import test from 'node:test';
import assert from 'node:assert/strict';
import { STATES } from '../js/state-vocab.js';

test('the six states and Cancelled each have a word, a tone and a glyph, and no two share a word', () => {
  assert.deepEqual(Object.keys(STATES), ['pending', 'active', 'awaiting', 'error', 'complete', 'stale', 'cancelled']);
  for (const s of Object.values(STATES)) { assert.ok(s.word && s.tone && s.icon); }
  assert.equal(new Set(Object.values(STATES).map((s) => s.word)).size, 7);
  assert.equal(new Set(Object.values(STATES).map((s) => s.icon)).size, 7);
});
