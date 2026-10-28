import test from 'node:test';
import assert from 'node:assert/strict';
import { direction, staggerDelay, delta, plan, keyOf, ticks } from '../js/motion-model.js';

const box = (left, top, w = 100, h = 40) => ({ left, top, right: left + w, bottom: top + h });
const snap = (o) => new Map(Object.entries(o).map(([k, [rect, sig]]) => [k, { rect, sig: sig || '' }]));

test('direction follows the rail order', () => {
  assert.equal(direction('now', 'work'), 1);
  assert.equal(direction('usage', 'work'), -1);
  assert.equal(direction('work', 'work'), 1);
  assert.equal(direction('nope', 'now'), 1);
});

test('stagger is 40 ms a step and stops after four steps', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 9].map((i) => staggerDelay(i)), [0, 40, 80, 120, 120, 120]);
});

test('delta is First minus Last and ignores sub pixel moves', () => {
  assert.deepEqual(delta(box(0, 100), box(0, 40)), { dx: 0, dy: 60 });
  assert.equal(delta(box(10, 10), box(10.4, 10.3)), null);
  assert.deepEqual(delta(box(0, 0), box(30, 0)), { dx: -30, dy: 0 });
});

test('plan: a reorder moves the rows that changed place, not the ones that stayed', () => {
  const ops = plan(snap({ a: [box(0, 0)], b: [box(0, 50)], c: [box(0, 100)] }), snap({ a: [box(0, 0)], b: [box(0, 100)], c: [box(0, 50)] }));
  assert.deepEqual(ops, [{ key: 'b', op: 'move', dx: 0, dy: -50 }, { key: 'c', op: 'move', dx: 0, dy: 50 }]);
});

test('plan: new rows enter, gone rows leave, a changed text tints once', () => {
  const ops = plan(snap({ a: [box(0, 0), 'Running'], gone: [box(0, 50)] }), snap({ a: [box(0, 0), 'Done'], fresh: [box(0, 50)] }));
  assert.deepEqual(ops.map((o) => o.op + ':' + o.key), ['tint:a', 'enter:fresh', 'leave:gone']);
});

test('plan: an unchanged page makes no animation', () => {
  const s = snap({ a: [box(0, 0), 'x'], b: [box(0, 50), 'y'] });
  assert.deepEqual(plan(s, snap({ a: [box(0, 0), 'x'], b: [box(0, 50), 'y'] })), []);
});

test('plan: rows far outside the window are skipped, caps hold at 100 rows', () => {
  const view = { top: 0, bottom: 900, left: 0, right: 1440 };
  const off = plan(snap({ a: [box(0, 5000)] }), snap({ a: [box(0, 5100)] }), { view });
  assert.deepEqual(off, []);
  const many = (shift) => snap(Object.fromEntries(Array.from({ length: 100 }, (_, i) => ['r' + i, [box(0, i * 5 + shift)]])));
  assert.equal(plan(many(0), many(60), { maxMove: 30 }).length, 30);
  const gone = plan(many(0), snap({}), { maxLeave: 8 });
  assert.equal(gone.length, 8);
});

test('keyOf: data-mk, then data-key, then a data-key inside, then the rail project', () => {
  const el = (dataset, inner) => ({ dataset, querySelector: () => (inner ? { dataset: { key: inner } } : null) });
  assert.equal(keyOf(el({ mk: 'x', key: 'y' })), 'x');
  assert.equal(keyOf(el({ key: 'y' })), 'y');
  assert.equal(keyOf(el({ proj: 'p1' })), 'proj:p1');
  assert.equal(keyOf(el({}, 'in')), 'in');
  assert.equal(keyOf(el({})), null);
});

test('ticks only when both numbers exist and differ', () => {
  assert.equal(ticks('3', '4'), true);
  assert.equal(ticks('3', '3'), false);
  assert.equal(ticks(null, '3'), false);
});
