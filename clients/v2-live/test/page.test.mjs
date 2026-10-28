import { test } from 'node:test';
import assert from 'node:assert/strict';
import { graphPick, parseHash, workQuery, workHref, viewOfCls, filterWork, workCounts, countLine, relTime, sortProjects, sortOf, projectTab, projectHref, replayQuery, replayHref, openStep, compactRows, whatChanged, vocabOf } from '../page-model.js';

test('parseHash reads the route, an id, a sub page and the query', () => {
  assert.deepEqual(parseHash('#/work'), { name: 'work', id: null, sub: null, q: {} });
  assert.deepEqual(parseHash('#/work?view=running&project=notes'), { name: 'work', id: null, sub: null, q: { view: 'running', project: 'notes' } });
  assert.deepEqual(parseHash('#/projects/prj-notes/missions'), { name: 'projects', id: 'prj-notes', sub: 'missions', q: {} });
  assert.deepEqual(parseHash('#/replay/m-date?mode=compact'), { name: 'replay', id: 'm-date', sub: null, q: { mode: 'compact' } });
  assert.equal(parseHash('').name, null);
});

test('a work URL keeps only what is valid, and writes the shortest address', () => {
  assert.deepEqual(workQuery({ view: 'nonsense', project: 'zzz', as: 'x' }, ['a']), { view: 'all', project: null, as: 'list' });
  assert.deepEqual(workQuery({ view: 'blocked', project: 'a', as: 'graph' }, ['a']), { view: 'blocked', project: 'a', as: 'graph' });
  assert.equal(workHref({ view: 'all' }), '#/work');
  assert.equal(workHref({ view: 'running', project: 'notes' }), '#/work?view=running&project=notes');
  assert.equal(workHref({ view: 'all', as: 'graph' }), '#/work?as=graph');
  const q = workQuery(parseHash(workHref({ view: 'done', project: 'a' })).q, ['a']);
  assert.deepEqual(q, { view: 'done', project: 'a', as: 'list' });
});

test('views group the state classes, and the state vocabulary maps to ours', () => {
  assert.equal(viewOfCls('needs_you'), 'needs'); assert.equal(viewOfCls('reviewing'), 'needs');
  assert.equal(viewOfCls('failed'), 'blocked'); assert.equal(viewOfCls('paused'), 'blocked');
  assert.equal(viewOfCls('done'), 'done'); assert.equal(viewOfCls('planning'), 'running'); assert.equal(viewOfCls('verifying'), 'running');
  assert.equal(vocabOf('needs_you'), 'awaiting input'); assert.equal(vocabOf('failed'), 'error'); assert.equal(vocabOf('done'), 'complete'); assert.equal(vocabOf('?'), 'pending');
});

test('filters and counts agree, and a narrowed list says so', () => {
  const items = [{ id: 1, project: 'a', cls: 'needs_you' }, { id: 2, project: 'a', cls: 'active' }, { id: 3, project: 'b', cls: 'failed' }, { id: 4, project: 'b', cls: 'done' }, { id: 5, project: 'b', cls: 'active' }];
  assert.equal(filterWork(items, { view: 'running' }).length, 2);
  assert.equal(filterWork(items, { view: 'running', project: 'b' }).length, 1);
  assert.equal(filterWork(items, {}).length, 5);
  assert.deepEqual(workCounts(items), { all: 5, needs: 1, running: 2, blocked: 1, done: 1 });
  assert.deepEqual(workCounts(items, 'b'), { all: 3, needs: 0, running: 1, blocked: 1, done: 1 });
  assert.equal(countLine(2, 5), '2 of 5'); assert.equal(countLine(5, 5), '5');
});

test('relative time reads against the simulated clock', () => {
  assert.equal(relTime(1000000, 1000000), 'now'); assert.equal(relTime(1000000, 1000000 + 5000), 'now');
  assert.equal(relTime(1000000, 1000000 - 180000), '3m ago'); assert.equal(relTime(1000000, 1000000 - 7200000), '2h ago'); assert.equal(relTime(1000000, 1000000 - 4 * 86400000), '4d ago');
});

test('projects sort by attention, recency or name, and an unknown sort falls back', () => {
  const p = [{ id: 'a', name: 'Zed', attention: 0, running: 1, lastAt: 5 }, { id: 'b', name: 'Amy', attention: 2, running: 0, lastAt: 1 }, { id: 'c', name: 'Bob', attention: 2, running: 3, lastAt: 9 }];
  assert.deepEqual(sortProjects(p, 'attention').map((x) => x.id), ['c', 'b', 'a']);
  assert.deepEqual(sortProjects(p, 'recent').map((x) => x.id), ['c', 'a', 'b']);
  assert.deepEqual(sortProjects(p, 'name').map((x) => x.id), ['b', 'c', 'a']);
  assert.equal(sortOf('weird'), 'attention'); assert.equal(p[0].id, 'a');
});

test('project tabs and addresses', () => {
  assert.equal(projectTab('missions'), 'missions'); assert.equal(projectTab('details'), 'settings'); assert.equal(projectTab(null), 'overview'); assert.equal(projectTab('zzz'), 'overview');
  assert.equal(projectHref('prj-a'), '#/projects/prj-a'); assert.equal(projectHref('prj-a', 'overview'), '#/projects/prj-a'); assert.equal(projectHref('prj-a', 'activity'), '#/projects/prj-a/activity');
});

test('replay modes, sections and the address that carries them', () => {
  assert.deepEqual(replayQuery({}), { mode: 'timeline', detail: 'normal', section: null });
  assert.deepEqual(replayQuery({ mode: 'compact', detail: 'verbose', section: 'recovery' }), { mode: 'compact', detail: 'verbose', section: 'recovery' });
  assert.deepEqual(replayQuery({ mode: 'x', detail: 'y', section: 'z' }), { mode: 'timeline', detail: 'normal', section: null });
  assert.equal(replayHref('m-date', { mode: 'timeline', detail: 'normal', section: null }), '#/replay/m-date');
  assert.equal(replayHref('m-date', { mode: 'compact', detail: 'thinking', section: 'evidence' }), '#/replay/m-date?mode=compact&detail=thinking&section=evidence');
});

const S = (n, machine, state, category = 'RECORDED') => ({ n, machine, state, category, time: '08:' + String(n).padStart(2, '0') });
test('replay opens on the failed or awaiting step only when the mission still needs you', () => {
  const steps = [S(1, 'mission', 'CREATED', 'INTENDED'), S(2, 'execution', 'LOST', 'UNCERTAIN'), S(3, 'execution', 'ENDED_OK'), S(4, 'mission', 'EXECUTING')];
  assert.equal(openStep(steps, true), 2); assert.equal(openStep(steps, false), 4);
  assert.equal(openStep([S(1, 'mission', 'CREATED')], true), 1); assert.equal(openStep([], true), null);
  assert.equal(openStep([S(1, 'approval', 'PENDING', 'SUSPENDED'), S(2, 'mission', 'APPROVAL_REQUIRED', 'SUSPENDED')], true), 2);
});

test('compact mode merges neighbouring steps of one machine and keeps a bad step visible', () => {
  const rows = compactRows([S(1, 'mission', 'CREATED'), S(2, 'mission', 'PLANNING'), S(3, 'plan', 'CREATED'), S(4, 'plan', 'APPROVED'), S(5, 'mission', 'EXECUTING'), S(6, 'execution', 'LOST', 'UNCERTAIN')]);
  assert.deepEqual(rows.map((r) => [r.machine, r.n, r.step.n, r.bad]), [['mission', 2, 2, false], ['plan', 2, 4, false], ['mission', 1, 5, false], ['execution', 1, 6, true]]);
  assert.deepEqual(compactRows([]), []);
});

test('the what-changed line counts steps and bad steps', () => {
  assert.equal(whatChanged([]), null);
  const w = whatChanged([S(1, 'mission', 'CREATED'), S(2, 'execution', 'LOST', 'UNCERTAIN')]);
  assert.deepEqual([w.count, w.from, w.to, w.bad, w.last.n], [2, '08:01', '08:02', 1, 2]);
});

test('the graph draws what the filter keeps first, never fewer than it keeps, and the legend counts agree with the highlight', () => {
  const items = Array.from({ length: 20 }, (_, i) => ({ id: 'e' + i, project: i % 2 ? 'a' : 'b', cls: ['needs_you', 'active', 'failed', 'done'][i % 4] }));
  const rank = (e) => ({ needs_you: 0, active: 1, failed: 2, done: 4 })[e.cls];
  const shown = filterWork(items, { view: 'blocked' }), picked = graphPick(items, shown, 12, rank);
  assert.equal(picked.length, 12);
  assert.ok(shown.every((e) => picked.some((p) => p.id === e.id)), 'every kept entry is drawn');
  assert.deepEqual(picked.slice(0, shown.length).map((e) => e.id).sort(), shown.map((e) => e.id).sort(), 'kept entries come first');
  const few = items.slice(0, 8), all = graphPick(few, filterWork(few, { view: 'running' }), 12, rank);
  assert.equal(all.length, 8, 'a small scene is drawn whole, whatever the filter');
  const lit = all.filter((e) => filterWork(few, { view: 'running' }).some((s) => s.id === e.id)).length;
  assert.equal(lit, workCounts(few).running, 'highlighted entries equal the view count');
  assert.equal(graphPick(items, items, 12, rank).length, 12);
  const ids = picked.map((e) => e.id), again = graphPick(items, filterWork(items, { view: 'needs' }), 12, rank, ids);
  assert.deepEqual(again.map((e) => e.id), ids, 'a filter the drawing already holds keeps the drawing as it was');
  assert.notDeepEqual(graphPick(items, filterWork(items, { view: 'running' }), 12, rank, ids).map((e) => e.id), ids, 'a filter it does not hold draws again');
});
