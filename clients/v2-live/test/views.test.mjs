import test from 'node:test';
import assert from 'node:assert/strict';

const load = async (search) => { globalThis.location = { search }; return import('../js/store.js?' + search); };

test('the Overview opens on Territories; ?overview= picks any of the three views and an unknown value falls back', async () => {
  assert.equal((await load('')).get('overview'), 'territories');
  for (const v of ['territories', 'rings', 'network']) assert.equal((await load('?overview=' + v)).get('overview'), v);
  assert.equal((await load('?overview=projects')).get('overview'), 'territories');
});
