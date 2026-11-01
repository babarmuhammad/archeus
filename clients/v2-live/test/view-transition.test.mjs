import test from 'node:test';
import assert from 'node:assert/strict';
import { decide, start } from '../js/view-transition.js';

const ok = { from: 'now', to: 'work', api: true, quiet: false };

test('transitions between two pages when the browser can and Quiet is off', () => {
  assert.deepEqual(decide(ok), { run: true, dir: 1, name: 'fwd' });
});

test('the rail order decides the direction', () => {
  assert.deepEqual(decide({ ...ok, from: 'usage', to: 'work' }), { run: true, dir: -1, name: 'back' });
});

test('no API, Quiet, the same page and the terminal view all fall back to a plain redraw', () => {
  assert.equal(decide({ ...ok, api: false }).run, false);
  assert.equal(decide({ ...ok, api: undefined }).run, false);
  assert.equal(decide({ ...ok, quiet: true }).run, false);
  assert.equal(decide({ ...ok, to: 'now' }).run, false);
  assert.equal(decide({ ...ok, to: 'terminal' }).run, false);
  assert.equal(decide({ ...ok, from: 'terminal' }).run, false);
});

const fakeDoc = () => {
  const finished = new Promise((r) => { fakeDoc.end = r; });
  const doc = { documentElement: { dataset: {} }, calls: 0, startViewTransition(cb) { this.calls++; cb(); return { finished, ready: Promise.reject(new Error('skipped')) }; } };
  return doc;
};

test('start without a run calls update at once and never touches the document', () => {
  const doc = fakeDoc(); let got;
  assert.equal(start(doc, decide({ ...ok, api: false }), (d) => { got = d; }), false);
  assert.equal(got, 1);
  assert.equal(doc.calls, 0);
  assert.deepEqual(doc.documentElement.dataset, {});
});

test('start with a run sets data-vt, calls update inside the transition and clears it when finished', async () => {
  const doc = fakeDoc(); let got;
  assert.equal(start(doc, decide({ ...ok, from: 'usage', to: 'work' }), (d) => { got = d; }), true);
  assert.equal(got, -1);
  assert.equal(doc.documentElement.dataset.vt, 'back');
  fakeDoc.end();
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(doc.documentElement.dataset.vt, undefined);
});
