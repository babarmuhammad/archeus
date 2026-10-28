import test from 'node:test';
import assert from 'node:assert/strict';
import { whenShort, whenExact } from '../js/time-model.js';

const label = (ms, sec) => 'HH:MM' + (sec ? ':SS' : '');
const MIN = 60000, H = 60 * MIN, DAY = 24 * H;
test('no time reads Never, and has no exact form', () => {
  assert.equal(whenShort(null, 0, label), 'Never'); assert.equal(whenExact(null, label), null);
});
test('the same day, the day before, the week, then a date', () => {
  assert.equal(whenShort(-26 * MIN, 0, label), 'Today HH:MM');
  assert.equal(whenShort(-10 * H, 0, label), 'Yesterday HH:MM');
  assert.equal(whenShort(-2 * DAY, 0, label), 'Mon HH:MM'); // the fixtures' today is Wednesday 2026-10-28
  assert.equal(whenShort(-6 * DAY, 0, label), 'Thu HH:MM');
  assert.equal(whenShort(-8 * DAY, 0, label), '2026-10-20');
});
test('the day rolls over at 00:00, not at the start of the simulation', () => {
  assert.equal(whenShort(-8 * H, 0, label), 'Today HH:MM'); // 01:00
  assert.equal(whenShort(-10 * H, 0, label), 'Yesterday HH:MM'); // 23:00 the day before
  assert.equal(whenShort(1 * H, 14 * H, label), 'Today HH:MM'); assert.equal(whenShort(1 * H, 15 * H, label), 'Yesterday HH:MM'); // 23:00 and 00:00
});
test('the exact form is an ISO local time with seconds', () => {
  assert.equal(whenExact(-26 * MIN, label), '2026-10-28 HH:MM:SS'); assert.equal(whenExact(-10 * H, label), '2026-10-27 HH:MM:SS');
});
