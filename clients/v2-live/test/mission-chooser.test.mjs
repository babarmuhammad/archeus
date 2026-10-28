import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matches, filterRows, facetCounts, projectCounts, rankProjects, sortRows, sections, pushRecent, recentRows, remembered, stops, CAP } from '../mission-chooser-model.js';
import { workCounts } from '../page-model.js';

// 240 missions over 100 projects, in the four facets Work counts by
const FAC = ['needs', 'running', 'blocked', 'done'], CLS = { needs: 'needs_you', running: 'active', blocked: 'blocked', done: 'done' };
const projects = Array.from({ length: 100 }, (_, i) => ({ id: 'p' + i, name: 'Project ' + String(i).padStart(2, '0') }));
const rows = Array.from({ length: 240 }, (_, i) => { const facet = FAC[(i * 7) % 4 === 0 ? 0 : i % 4], p = projects[i % 100]; return { id: 'm' + i, title: 'Mission ' + i, project: p.id, projectName: p.name, branch: i % 5 ? 'fix/b' + i : '', facet, cls: CLS[facet], at: 1000 - i, steps: i % 3 }; });

test('a search needs every word, in the title, project, branch or id', () => {
  assert.ok(matches(rows[7], 'mission 7'));
  assert.ok(matches(rows[7], 'PROJECT 07 m7'));
  assert.ok(matches(rows[7], 'fix/b7'));
  assert.ok(!matches(rows[7], 'mission nothing'));
  assert.ok(matches(rows[7], '   '));
});

test('the facet counts are the Work counts when nothing else is chosen, and honour the other filters', () => {
  const c = facetCounts(rows, {}), w = workCounts(rows.map((r) => ({ id: r.id, project: r.project, cls: r.cls })));
  assert.deepEqual([c.needs, c.running, c.blocked, c.done, c.all], [w.needs, w.running, w.blocked, w.done, w.all]);
  const one = facetCounts(rows, { project: 'p3' });
  assert.equal(one.all, rows.filter((r) => r.project === 'p3').length);
  assert.equal(facetCounts(rows, { facet: 'done' }).all, rows.length, 'a facet is counted by what choosing it would show, so the row of counts stays whole');
  assert.equal(facetCounts(rows, { history: true }).all, rows.filter((r) => r.steps > 0).length);
});

test('project counts leave the project out and follow the search and the state', () => {
  const p = projectCounts(rows, { facet: 'needs' });
  assert.equal(p.all, rows.filter((r) => r.facet === 'needs').length);
  assert.equal([...p.by.values()].reduce((a, b) => a + b, 0), p.all);
  assert.equal(projectCounts(rows, { q: 'project 04' }).by.size, 1);
});

test('projects rank by Needs you, then Running, then recent, and the order ignores the filters', () => {
  const r = rankProjects(rows, projects);
  assert.equal(r.length, 100);
  for (let i = 1; i < r.length; i++) assert.ok(r[i - 1].needs > r[i].needs || (r[i - 1].needs === r[i].needs && r[i - 1].running >= r[i].running));
  assert.deepEqual(rankProjects(rows, projects).map((p) => p.id), r.map((p) => p.id));
});

test('rows sort attention first, then most recent', () => {
  const s = sortRows(rows);
  const order = { needs: 0, running: 1, blocked: 2, done: 3 };
  for (let i = 1; i < s.length; i++) assert.ok(order[s[i - 1].facet] < order[s[i].facet] || (order[s[i - 1].facet] === order[s[i].facet] && s[i - 1].at >= s[i].at));
});

test('sections hold at most CAP rows each, say what they hold back, and grow when asked', () => {
  const s = sections(rows, {});
  assert.ok(s.every((x) => x.rows.length <= CAP && x.rows.length + x.more === x.total));
  assert.ok(s.reduce((a, x) => a + x.rows.length, 0) <= 4 * CAP, 'the DOM stays under 80 rows at 240 missions');
  const more = sections(rows, {}, { needs: CAP });
  assert.equal(more.find((x) => x.facet === 'needs').rows.length, Math.min(2 * CAP, more.find((x) => x.facet === 'needs').total));
  assert.deepEqual(sections(rows, { facet: 'done' }).map((x) => x.facet), ['done']);
  assert.deepEqual(sections(rows, { q: 'no such mission' }), []);
});

test('the keyboard stops are recents, then rows, with one Show more per section that holds rows back', () => {
  const s = sections(rows, {}), st = stops(recentRows(rows, ['m3', 'gone', 'm9']), s);
  assert.equal(st.filter((x) => x.recent).length, 2, 'a recent that no longer exists is dropped');
  assert.equal(st.filter((x) => x.type === 'more').length, s.filter((x) => x.more).length);
  assert.equal(st.filter((x) => x.type === 'row' && !x.recent).length, s.reduce((a, x) => a + x.rows.length, 0));
});

test('recents keep five, newest first, once each', () => {
  let r = [];
  for (const id of ['a', 'b', 'c', 'd', 'e', 'f', 'c']) r = pushRecent(r, id);
  assert.deepEqual(r, ['c', 'f', 'e', 'd', 'b']);
  assert.deepEqual(pushRecent(undefined, 'x'), ['x']);
});

test('what is remembered drops a project or a state that is gone', () => {
  assert.deepEqual(remembered({ project: 'p1', facet: 'blocked' }, projects), { project: 'p1', facet: 'blocked' });
  assert.deepEqual(remembered({ project: 'zzz', facet: 'nonsense' }, projects), { project: null, facet: 'all' });
  assert.deepEqual(remembered(null, projects), { project: null, facet: 'all' });
});

test('filterRows combines search, project, state and history', () => {
  const f = filterRows(rows, { q: 'mission', project: 'p5', facet: 'all', history: true });
  assert.ok(f.every((r) => r.project === 'p5' && r.steps > 0));
});
