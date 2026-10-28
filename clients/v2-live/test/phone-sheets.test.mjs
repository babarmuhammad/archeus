// Phone slice C: the sheet maths the Tell sheet relies on (a detent pinned to pixels, a short viewport with the keyboard up) and the static rules of the slice's files.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { heights, snap, step, stepLabel } from '../js/sheet-model.js';

const NAMES = ['peek', 'half', 'full'];

test('a fixed detent is pixels, the others stay shares of the space', () => {
  const h = heights(NAMES, 800, { peek: 280 });
  assert.deepEqual(h.map((d) => [d.name, d.px]), [['peek', 280], ['half', 448], ['full', 736]]);
});

test('with the keyboard up a detent never exceeds what is left, fixed or not', () => {
  for (const avail of [300, 440]) {
    const h = heights(NAMES, avail, { peek: 280 });
    assert.ok(h.every((d) => d.px <= avail - 8), 'avail ' + avail + ': ' + JSON.stringify(h));
  }
  assert.deepEqual(heights(NAMES, 440, { peek: 280 }).map((d) => d.px), [280, 280, 405]);
  assert.deepEqual(heights(NAMES, 300, { peek: 280 }).map((d) => d.px), [280, 280, 280]);
  assert.deepEqual(heights(NAMES, 200, { peek: 280 }).map((d) => d.px), [192, 192, 192]);
});

test('the same names without fixed behave as before', () => {
  assert.deepEqual(heights(NAMES, 800), heights(NAMES, 800, {}));
  assert.equal(heights(['peek', 'full'], 800)[0].px, 320);
});

test('a drag with a fixed peek lands on the nearest detent and closes below half of it', () => {
  const d = heights(NAMES, 800, { peek: 280 });
  assert.equal(snap({ height: 300, velocity: 0, detents: d }), 'peek');
  assert.equal(snap({ height: 400, velocity: 0, detents: d }), 'half');
  assert.equal(snap({ height: 130, velocity: 0, detents: d }), 'close');
  assert.equal(snap({ height: 290, velocity: 1, detents: d }), 'half');
  assert.equal(snap({ height: 300, velocity: -1, detents: d }), 'peek');
});

test('the handle steps peek, half, full and back to peek, and names the next move', () => {
  assert.equal(step('peek', NAMES), 'half');
  assert.equal(step('half', NAMES), 'full');
  assert.equal(step('full', NAMES), 'peek');
  assert.equal(stepLabel('peek', NAMES), 'Expand');
  assert.equal(stepLabel('full', NAMES), 'Collapse');
  assert.equal(stepLabel('full', ['peek', 'full']), 'Collapse');
});

test('no bar offset is written down in the slice: the full pages are measured, the sheets are the shared primitive', () => {
  for (const f of ['../css/inspector.css', '../css/chat.css', '../css/picker.css', '../css/phone.css']) {
    assert.ok(!/bottom:\s*(77|88)px/.test(readFileSync(new URL(f, import.meta.url), 'utf8')), f);
  }
});

test('the old chat sheet is gone: no scrim, no private keyboard height, no Expand state', () => {
  const js = readFileSync(new URL('../js/chat.js', import.meta.url), 'utf8'), css = readFileSync(new URL('../css/chat.css', import.meta.url), 'utf8');
  assert.ok(!/cscrim|kbh-real|data-exp|buildSheet/.test(js + css));
  assert.match(js, /openSheet\(/);
});
