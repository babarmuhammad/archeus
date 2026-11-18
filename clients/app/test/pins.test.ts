// Pinned missions (D-9): a local preference that survives a reload, never fails
// on a missing, unreadable or refusing storage, and is never sent anywhere.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Pins } from '../src/state/pins.ts';

const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m };
};

test('a pin toggles, keeps pin order and survives a new page', () => {
  const s = memory();
  const a = new Pins(s);
  a.toggle('msn_2');
  a.toggle('msn_1');
  assert.deepEqual(a.list(), ['msn_2', 'msn_1']);
  assert.equal(a.has('msn_1'), true);
  assert.deepEqual(new Pins(s).list(), ['msn_2', 'msn_1'], 'kept in this browser');
  a.toggle('msn_2');
  assert.deepEqual(new Pins(s).list(), ['msn_1'], 'unpinning is kept too');
});

test('no storage, an unreadable value or a refusing storage: pins still work for the page', () => {
  const none = new Pins(null);
  none.toggle('msn_1');
  assert.deepEqual(none.list(), ['msn_1']);
  const junk = memory();
  junk.setItem('archeus:pins', '{not json');
  assert.deepEqual(new Pins(junk).list(), []);
  junk.setItem('archeus:pins', JSON.stringify(['msn_1', 3, null]));
  assert.deepEqual(new Pins(junk).list(), ['msn_1'], 'only ids are kept');
  const refusing = { getItem: () => null, setItem: () => { throw new Error('quota'); } };
  const p = new Pins(refusing);
  p.toggle('msn_9');
  assert.equal(p.has('msn_9'), true);
});

test('a change tells its listeners', () => {
  const p = new Pins(memory());
  let n = 0;
  const off = p.subscribe(() => n++);
  p.toggle('msn_1');
  off();
  p.toggle('msn_1');
  assert.equal(n, 1);
});
