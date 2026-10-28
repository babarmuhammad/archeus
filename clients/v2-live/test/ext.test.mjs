import test from 'node:test';
import assert from 'node:assert/strict';
import { tabOf, whenShort, matches } from '../js/ext-model.js';

const label = (ms) => 'HH:MM@' + ms;
const MIN = 60000;
test('an id belongs to the kind it opens in', () => {
  assert.equal(tabOf('h-1'), 'hooks'); assert.equal(tabOf('h-live-5'), 'hooks'); assert.equal(tabOf('mcp-live-4'), 'mcp');
  assert.equal(tabOf('ag-2'), 'agents'); assert.equal(tabOf('au-3'), 'automations'); assert.equal(tabOf('d-1'), 'clients');
  assert.equal(tabOf('m-date'), null); assert.equal(tabOf(null), null);
});
test('the short time form: today, yesterday, never', () => {
  assert.equal(whenShort(null, 0, label), 'Never');
  assert.equal(whenShort(-26 * MIN, 0, label), 'Today HH:MM@' + -26 * MIN);
  assert.equal(whenShort(-10 * 60 * MIN, 0, label), 'Yesterday HH:MM@' + -10 * 60 * MIN);
  assert.equal(whenShort(-40 * 60 * MIN, 0, label).startsWith('Earlier'), true);
});
test('search is a case-blind contains, empty matches everything', () => {
  assert.equal(matches('', 'anything'), true); assert.equal(matches(' GIT ', 'ask before git push'), true); assert.equal(matches('curl', 'ask before git push'), false);
});
