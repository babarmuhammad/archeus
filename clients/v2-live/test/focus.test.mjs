import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trapTab } from '../js/dom.js';

test('dialog Tab wraps both ways, skips hidden and disabled controls, keeps interior Tab native', () => {
  const previous = globalThis.document;
  const control = (visible = true, disabled = false) => ({ disabled, getClientRects: () => visible ? [{}] : [], focus() { document.activeElement = this; } });
  const first = control(), middle = control(), last = control();
  const controls = [control(false), first, middle, last, control(true, true)];
  const root = { querySelectorAll: () => controls, contains: (el) => controls.includes(el) };
  globalThis.document = { activeElement: last };
  let prevented = false;
  const tab = (shiftKey = false) => { prevented = false; trapTab({ key: 'Tab', shiftKey, preventDefault() { prevented = true; } }, root); };
  try {
    tab(); assert.equal(document.activeElement, first); assert.ok(prevented);
    tab(true); assert.equal(document.activeElement, last); assert.ok(prevented);
    document.activeElement = middle;
    tab(); assert.equal(document.activeElement, middle); assert.equal(prevented, false);
    document.activeElement = {};
    tab(true); assert.equal(document.activeElement, last); assert.ok(prevented);
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});
