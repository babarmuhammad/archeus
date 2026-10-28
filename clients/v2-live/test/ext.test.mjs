import test from 'node:test';
import assert from 'node:assert/strict';
import { tabOf, matches } from '../js/ext-model.js';

test('an id belongs to the kind it opens in', () => {
  assert.equal(tabOf('h-1'), 'hooks'); assert.equal(tabOf('h-live-5'), 'hooks'); assert.equal(tabOf('mcp-live-4'), 'mcp');
  assert.equal(tabOf('ag-2'), 'agents'); assert.equal(tabOf('au-3'), 'automations'); assert.equal(tabOf('d-1'), 'clients');
  assert.equal(tabOf('m-date'), null); assert.equal(tabOf(null), null);
});
test('search is a case-blind contains, empty matches everything', () => {
  assert.equal(matches('', 'anything'), true); assert.equal(matches(' GIT ', 'ask before git push'), true); assert.equal(matches('curl', 'ask before git push'), false);
});
