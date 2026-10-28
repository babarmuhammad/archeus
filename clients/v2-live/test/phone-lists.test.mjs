import test from 'node:test';
import assert from 'node:assert/strict';
import { workChips, workSections, rankProjects, phoneGraphPick, ringLayout, shortLabel, labelWidth, placeLabels, clampView, projectGroups, SECTION_CAP, GRAPH_NODES, LABEL_MAX } from '../js/phone-lists-model.js';

const CLS = ['needs_you', 'active', 'verifying', 'blocked', 'done', 'paused', 'planning'];
const entries = Array.from({ length: 97 }, (_, i) => ({ id: 'e' + i, project: 'p' + (i % 5), cls: CLS[i % CLS.length], at: 1000 + i }));
const RANK = { needs_you: 0, active: 1, verifying: 1, blocked: 2, done: 4 };
const rank = (e) => RANK[e.cls] ?? 3;

test('chips: three states, a hidden view takes a fourth chip while it is shown', () => {
  const counts = { needs: 42, running: 39, blocked: 4, done: 7, all: 97 };
  assert.deepEqual(workChips(counts, 'all').chips.map((c) => [c.id, c.n, c.on]), [['needs', 42, false], ['running', 39, false], ['all', 97, true]]);
  const b = workChips(counts, 'blocked');
  assert.deepEqual(b.chips.map((c) => c.id), ['needs', 'running', 'all', 'blocked']);
  assert.equal(b.chips[3].on, true);
  assert.deepEqual(b.more.map((c) => [c.id, c.n]), [['blocked', 4], ['done', 7]]);
  assert.equal(workChips(counts, 'needs').chips.length, 3);
});

test('sections: counts add up, 20 rows each, needs you oldest first, the rest newest first', () => {
  const s = workSections(entries);
  assert.equal(s.reduce((n, x) => n + x.count, 0), 97);
  assert.ok(s.every((x) => x.rows.length <= SECTION_CAP));
  const needs = s.find((x) => x.key === 'needs'), run = s.find((x) => x.key === 'running');
  assert.ok(needs.rows.every((r, i, a) => !i || a[i - 1].at <= r.at));
  assert.ok(run.rows.every((r, i, a) => !i || a[i - 1].at >= r.at));
  assert.equal(needs.left, needs.count - needs.rows.length);
  assert.equal(needs.next, Math.min(SECTION_CAP, needs.left));
});

test('sections: show more adds a page, the last page is partial, an empty section is gone', () => {
  const many = Array.from({ length: 45 }, (_, i) => ({ id: 'm' + i, cls: 'active', at: i }));
  assert.deepEqual(workSections(many).map((s) => [s.key, s.rows.length, s.left, s.next]), [['running', 20, 25, 20]]);
  assert.deepEqual(workSections(many, { running: 1 }).map((s) => [s.rows.length, s.left, s.next]), [[40, 5, 5]]);
  assert.deepEqual(workSections(many, { running: 2 }).map((s) => [s.rows.length, s.left, s.next]), [[45, 0, 0]]);
  assert.deepEqual(workSections([]), []);
});

test('the main column stays small at 100 projects of rows: capped sections never exceed 4 pages of 20', () => {
  const all = Array.from({ length: 2000 }, (_, i) => ({ id: 'x' + i, cls: CLS[i % CLS.length], at: i }));
  assert.ok(workSections(all).reduce((n, s) => n + s.rows.length, 0) <= 4 * SECTION_CAP);
});

test('project picker ranking: needs you first, then size, then name', () => {
  const ps = ['a', 'b', 'c'].map((id) => ({ id, name: id.toUpperCase() }));
  const es = [{ project: 'b', cls: 'needs_you' }, { project: 'b', cls: 'done' }, { project: 'c', cls: 'active' }, { project: 'c', cls: 'active' }, { project: 'a', cls: 'active' }];
  assert.deepEqual(rankProjects(es, ps).map((x) => [x.p.id, x.needs, x.all]), [['b', 1, 2], ['c', 0, 2], ['a', 0, 1]]);
});

test('graph pick: capped, matches first, the rest is only counted', () => {
  const unfiltered = phoneGraphPick(entries, entries, false, rank);
  assert.equal(unfiltered.picked.length, GRAPH_NODES);
  assert.equal(unfiltered.more, 97 - GRAPH_NODES);
  assert.ok(unfiltered.picked.every((e) => e.cls === 'needs_you'), 'the most urgent come first');
  const shown = entries.filter((e) => e.cls === 'blocked');
  const f = phoneGraphPick(entries, shown, true, rank);
  assert.equal(f.picked.length, GRAPH_NODES);
  assert.ok(f.picked.every((e) => e.cls === 'blocked'), 'a filter draws only what it keeps');
  assert.equal(f.more, shown.length - GRAPH_NODES);
  const few = phoneGraphPick(entries, shown.slice(0, 3), true, rank);
  assert.deepEqual([few.picked.length, few.more], [3, 0]);
  assert.deepEqual(phoneGraphPick(entries, [], true, rank), { picked: [], more: 0 });
});

test('graph pick keeps the previous nodes while they still qualify, so the picture does not jump', () => {
  const first = phoneGraphPick(entries, entries, false, rank).picked.map((e) => e.id);
  assert.deepEqual(phoneGraphPick(entries, entries, false, rank, first).picked.map((e) => e.id), first);
});

test('ring layout: inside the box, one point per node, the first at the top', () => {
  for (const n of [1, 2, 5, 9]) {
    const pts = ringLayout(n, 390, 420, 26);
    assert.equal(pts.length, n);
    assert.ok(pts.every((p) => p.x >= 26 && p.x <= 390 - 26 && p.y >= 26 && p.y <= 420 - 26), 'n=' + n);
    assert.ok(pts[0].y <= 210 && Math.abs(pts[0].x - 195) <= 1);
  }
  assert.deepEqual(ringLayout(0, 390, 420, 26), []);
});

test('labels are short and their width is an upper bound', () => {
  assert.equal(shortLabel('Short'), 'Short');
  assert.equal(shortLabel('Migrate config loading to the new store').length, LABEL_MAX);
  assert.ok(shortLabel('Migrate config loading to the new store').endsWith('…'));
  assert.equal(labelWidth('abcdefghij', 13), Math.ceil(10 * 13 * .62));
});

function overlaps(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }
const titles = ['Migrate config loading', 'Document retry logic', 'Clean up release notes', 'Search provenance', 'Fix flaky date test', 'Add date pinning', 'Plan v1 for docs', 'Review the harness', 'Check the account limits'];

test('label collision: no two labels overlap, none leaves the box, none covers a node (22 and 60 missions drawn as 9)', () => {
  for (const total of [22, 60]) {
    const n = Math.min(total, GRAPH_NODES), pts = ringLayout(n, 390, 430, 26);
    const items = pts.map((p, i) => ({ id: 'n' + i, ...p, r: 26, text: shortLabel(titles[(i + total) % titles.length]), priority: i % 3 === 0 ? 2 : 1 }));
    const box = { x: 0, y: 0, w: 390, h: 430 }, out = placeLabels(items, box);
    assert.ok(out.size >= 1);
    const rects = [...out.entries()].map(([id, l]) => ({ id, x: l.anchor === 'middle' ? l.x - l.w / 2 : l.anchor === 'start' ? l.x : l.x - l.w, y: l.y - l.h / 2, w: l.w, h: l.h }));
    rects.forEach((r, i) => {
      assert.ok(r.x >= 0 && r.y >= 0 && r.x + r.w <= box.w && r.y + r.h <= box.h, 'inside the box ' + r.id);
      rects.slice(i + 1).forEach((q) => assert.ok(!overlaps(r, q), r.id + ' overlaps ' + q.id));
      items.forEach((it) => { const cx = Math.max(r.x, Math.min(it.x, r.x + r.w)), cy = Math.max(r.y, Math.min(it.y, r.y + r.h)); assert.ok((cx - it.x) ** 2 + (cy - it.y) ** 2 >= it.r ** 2, r.id + ' covers ' + it.id); });
    });
  }
});

test('label collision: the higher priority label wins a contested spot, a label with no room is dropped', () => {
  const a = { id: 'a', x: 60, y: 100, r: 20, text: 'Alpha one', priority: 5 }, b = { id: 'b', x: 100, y: 100, r: 20, text: 'Beta two', priority: 1 };
  const out = placeLabels([b, a], { x: 0, y: 0, w: 200, h: 200 });
  assert.ok(out.get('a').y > a.y, 'a takes the spot below');
  assert.ok(out.get('b').y < b.y, 'b gives way and goes above');
  const tight = placeLabels([{ id: 'c', x: 10, y: 10, r: 8, text: 'A very long label here', priority: 1 }], { x: 0, y: 0, w: 30, h: 30 });
  assert.equal(tight.size, 0);
});

test('pan and zoom never go below the fitted view and keep the content in the box', () => {
  assert.deepEqual(clampView({ k: .4, x: 50, y: 50 }, 390, 400), { k: 1, x: 0, y: 0 });
  assert.deepEqual(clampView({ k: 9, x: 0, y: 0 }, 390, 400), { k: 3, x: 0, y: 0 });
  const v = clampView({ k: 2, x: -999, y: 10 }, 390, 400);
  assert.deepEqual(v, { k: 2, x: -390, y: 0 });
});

test('project groups: a step per group, the quiet one folded when there are many and no search', () => {
  const ps = Array.from({ length: 100 }, (_, i) => ({ id: 'p' + i, g: i < 42 ? 'needs' : i < 70 ? 'running' : 'quiet' }));
  const G = [{ key: 'needs', label: 'Needs you' }, { key: 'running', label: 'Running' }, { key: 'quiet', label: 'Quiet' }];
  const g = projectGroups(ps, (p) => p.g, G, { many: true });
  assert.deepEqual(g.map((x) => [x.key, x.count, x.rows.length, x.left, x.fold]), [['needs', 42, 20, 22, false], ['running', 28, 20, 8, false], ['quiet', 30, 20, 10, true]]);
  assert.equal(projectGroups(ps, (p) => p.g, G, { many: true, searching: true })[2].fold, false);
  assert.equal(projectGroups(ps, (p) => p.g, G, { pages: { needs: 2 } })[0].rows.length, 42);
  assert.deepEqual(projectGroups(ps.slice(0, 3), (p) => p.g, G).map((x) => x.key), ['needs']);
});
