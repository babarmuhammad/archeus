// The inspector's width (rulebook §15): 360–560 px, the window-splitter keys,
// remembered in this browser, never failing on a missing or refusing storage.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { INSPECTOR_MAX, INSPECTOR_MIN, INSPECTOR_STEP, clampWidth, keyWidth, loadWidth, saveWidth } from '../src/state/inspector.ts';

test('a width is whole pixels within 360–560', () => {
  assert.deepEqual([INSPECTOR_MIN, INSPECTOR_MAX], [360, 560]);
  assert.equal(clampWidth(100), 360);
  assert.equal(clampWidth(900), 560);
  assert.equal(clampWidth(400.6), 401);
});

test('the divider is the inspector\'s left edge: ← widens, → narrows, Home and End are the bounds', () => {
  assert.equal(keyWidth(400, 'ArrowLeft'), 400 + INSPECTOR_STEP);
  assert.equal(keyWidth(400, 'ArrowRight'), 400 - INSPECTOR_STEP);
  assert.equal(keyWidth(555, 'ArrowLeft'), 560);
  assert.equal(keyWidth(365, 'ArrowRight'), 360);
  assert.equal(keyWidth(400, 'Home'), 360);
  assert.equal(keyWidth(400, 'End'), 560);
  assert.equal(keyWidth(400, 'Enter'), null);
});

test('remembered in this browser; junk, nothing or a refusing storage give the default', () => {
  const m = new Map<string, string>();
  const s = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  assert.equal(loadWidth(s), null);
  saveWidth(s, 444);
  assert.equal(loadWidth(s), 444);
  saveWidth(s, 9999);
  assert.equal(loadWidth(s), 560, 'kept within bounds');
  m.set('archeus:inspector-width', 'wide');
  assert.equal(loadWidth(s), null);
  assert.equal(loadWidth(null), null);
  const refusing = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
  assert.equal(loadWidth(refusing), null);
  assert.doesNotThrow(() => saveWidth(refusing, 400));
});
