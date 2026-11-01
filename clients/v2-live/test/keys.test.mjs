import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=it' };
const { tr } = await import('../js/i18n.js');
const { overviewKey, KEYS } = await import('../js/keys-model.js');

const ev = (code, o = {}) => ({ code, altKey: true, ctrlKey: false, metaKey: false, shiftKey: false, ...o });

test('Alt+1, Alt+2 and Alt+3 pick Territories, Rings and Network, in the order of the view switch', () => {
  assert.deepEqual(['Digit1', 'Digit2', 'Digit3'].map((c) => overviewKey(ev(c))), ['territories', 'rings', 'network']);
  assert.equal(overviewKey(ev('Numpad2')), 'rings');
});
test('other digits and any other modifier do nothing', () => {
  assert.equal(overviewKey(ev('Digit4')), null);
  assert.equal(overviewKey(ev('Digit1', { altKey: false })), null);
  assert.equal(overviewKey(ev('Digit1', { ctrlKey: true })), null);
  assert.equal(overviewKey(ev('Digit1', { metaKey: true })), null);
  assert.equal(overviewKey(ev('Digit1', { shiftKey: true })), null);
  assert.equal(overviewKey({ altKey: true, key: '1' }), null);
});
test('the help lists Ctrl+Enter, the chat bar key that steers a running mission, in both languages', () => {
  const row = KEYS.find(([k]) => k === 'Ctrl+Enter or Cmd+Enter');
  assert.ok(row);
  assert.equal(tr(row[0]), 'Ctrl+Invio o Cmd+Invio');
  assert.match(tr(row[1]), /guida la missione/);
});
test('the help lists Alt+1, Alt+2, Alt+3 and the Italian row names the views in Italian only', () => {
  const row = KEYS.find(([k]) => k === 'Alt+1, Alt+2, Alt+3');
  assert.ok(row);
  assert.equal(tr(row[1]), 'Nella panoramica: Territori, Anelli, Rete');
});
