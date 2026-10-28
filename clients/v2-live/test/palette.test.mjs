import test from 'node:test';
import assert from 'node:assert/strict';
import { score, search, sections, remember } from '../js/palette-model.js';

const item = (id, group, label, words = '', pin = false) => ({ id, group, label, words, pin });
const ITEMS = [
  item('p-now', 'Pages', 'Overview', 'home now', true), item('p-work', 'Pages', 'Work', 'missions'), item('p-set', 'Pages', 'Settings', 'preferences'),
  item('a-stop', 'Actions', 'Stop all', 'emergency halt', true), item('a-safe', 'Actions', 'Settings: Safety', 'pause resume stop'), item('a-tell', 'Actions', 'Tell Archeus', 'say ask'),
  ...Array.from({ length: 100 }, (_, i) => item('j-' + i, 'Projects', 'Project ' + i, 'archeus'))
];

test('a label scores by how the query matches it', () => {
  assert.ok(score(ITEMS[0], 'overview') > score(ITEMS[0], 'over'));
  assert.ok(score(ITEMS[0], 'over') > score(ITEMS[0], 'view'));
  assert.ok(score(ITEMS[0], 'view') > score(ITEMS[0], 'home'));
  assert.ok(score(ITEMS[0], 'home') > score(ITEMS[0], 'ovw'));
  assert.equal(score(ITEMS[0], 'zzz'), 0);
});
test('a query finds across all 100 projects, best first, and nothing for noise', () => {
  const r = search(ITEMS, 'project 99');
  assert.equal(r[0].id, 'j-99');
  assert.deepEqual(search(ITEMS, 'qqqq'), []);
  assert.ok(search(ITEMS, 'proj', [], { max: 30 }).length === 30);
});
test('a word inside a label or a keyword reaches the item', () => {
  assert.equal(search(ITEMS, 'safety')[0].id, 'a-safe');
  assert.equal(search(ITEMS, 'emergency')[0].id, 'a-stop');
  assert.equal(search(ITEMS, 'stop')[0].id, 'a-stop'); // label start beats a keyword in another item
});
test('with no query: recent first, pinned before the rest, projects capped', () => {
  const r = search(ITEMS, '', ['p-set', 'j-7']);
  assert.deepEqual(r.slice(0, 2).map((i) => i.id), ['p-set', 'j-7']);
  assert.equal(r[2].id, 'p-now'); // pinned page first
  assert.equal(r.filter((i) => i.group === 'Projects').length, 1 + 5);
  assert.equal(search(ITEMS, '   ').length, search(ITEMS, '').length);
});
test('recent breaks a tie in a query', () => {
  assert.equal(search(ITEMS, 'project 1', ['j-12'])[0].id, 'j-1');
  assert.equal(search(ITEMS, 'project 1', ['j-12'])[1].id, 'j-12');
});
test('sections: Recent only without a query, then the groups in order', () => {
  const none = sections(search(ITEMS, '', ['p-set']), '', ['p-set']);
  assert.deepEqual(none.map(([g]) => g), ['Recent', 'Pages', 'Actions', 'Projects']);
  assert.ok(!none[1][1].some((i) => i.id === 'p-set'));
  assert.deepEqual(sections(search(ITEMS, 'settings', ['p-set']), 'settings', ['p-set']).map(([g]) => g), ['Pages', 'Actions']);
});
test('remember keeps the newest first, once, up to five', () => {
  assert.deepEqual(remember(['a', 'b', 'c'], 'b'), ['b', 'a', 'c']);
  assert.equal(remember(['1', '2', '3', '4', '5'], '6').length, 5);
});
