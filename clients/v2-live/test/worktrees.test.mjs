import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim } from '../sim.js';
import { railProjects } from '../js/rail-model.js';

// A worktree belongs to a project and is never a project. The model tests read the simulation; the map's own readers are covered through the same state.
const wtOf = (s) => s.state.projects.flatMap((p) => p.worktrees || []);

test('the default story: Archeus has three worktrees, Notes one, Ideas none, and "main" is not listed', () => {
  const s = createSim(), by = (id) => s.state.projects.find((p) => p.id === id).worktrees;
  assert.deepEqual(by('archeus').map((w) => [w.branch, w.owner, w.state]), [['fix/date-test', 'archeus', 'active'], ['feat/search', 'linked', 'active'], ['chore/old-lint', 'linked', 'stale']]);
  assert.equal(by('notes').length, 1);
  assert.equal(by('ideas').length, 0);
  assert.ok(wtOf(s).every((w) => w.branch !== 'main' && !w.path && !/[\\/]{2}|^[A-Za-z]:|^\//.test(w.label)), 'no absolute path anywhere, only a short label');
});
test('worktrees never count as projects: the project list, its count and ?projects=N are untouched', () => {
  assert.equal(createSim().state.projects.length, 3);
  for (const n of [10, 30]) { const s = createSim({ projects: n }); assert.equal(s.state.projects.length, n); assert.ok(wtOf(s).length > 0); assert.ok(wtOf(s).every((w) => s.state.projects.some((p) => p.id === w.project)), 'every worktree names a project'); assert.ok(!s.state.projects.some((p) => p.id.startsWith('wt-'))); }
  const s = createSim({ projects: 30 }), shown = railProjects(s.state.projects, () => 'idle', null, 7);
  assert.equal(shown.shown.length + shown.more, 30);
  assert.ok(shown.shown.every((p) => !p.branch));
});
test('a mission that works in a worktree carries its id, and the worktree names the mission', () => {
  const s = createSim();
  for (const w of wtOf(s).filter((x) => x.mission)) {
    const m = s.state.missions[w.mission];
    assert.equal(m.worktree, w.id);
    assert.equal(m.branch, w.branch, 'the mission branch is the worktree branch');
    assert.equal(m.project, w.project);
  }
  assert.equal(s.state.missions['m-date'].worktree, 'wt-fix-date-test');
  assert.equal(s.state.missions['m-docs'].worktree, undefined, 'a mission with no worktree hangs off its project');
});
test('the crowd gives each project 0 to 6 worktrees, skewed, and missions pick one by branch', () => {
  const s = createSim({ projects: 50 }), counts = s.state.projects.map((p) => p.worktrees.length);
  assert.ok(Math.max(...counts) <= 6 && Math.max(...counts) >= 3);
  assert.ok(counts.filter((c) => c === 0).length > counts.filter((c) => c >= 2).length, 'most have 0 or 1');
  for (const w of wtOf(s).filter((x) => x.mission)) assert.equal(s.state.missions[w.mission].branch, w.branch);
  assert.ok(wtOf(s).some((w) => w.state === 'stale' || w.state === 'missing'));
});
test('events worktree.created and worktree.merged are recorded, and a stale or missing worktree needs you', () => {
  const s = createSim({ story: 'many' });
  assert.ok(s.state.events.some((e) => e.type === 'worktree.created' && e.subject.kind === 'worktree' && e.project));
  assert.ok(s.state.events.some((e) => e.type === 'worktree.merged') || s.state.events.some((e) => e.type === 'worktree.missing'));
  const d = createSim(), items = d.attention().filter((a) => a.kind === 'worktree');
  assert.equal(items.length, 1);
  assert.equal(items[0].group, 'Unblock');
  assert.equal(items[0].project_id, 'archeus');
  assert.equal(items[0].state, 'stale');
  assert.ok(items.every((a) => d.state.projects.find((p) => p.id === a.project_id).worktrees.some((w) => w.id === a.ref)));
});
test('a linked worktree that goes missing at a simulated time raises its event and stays an item for the project', () => {
  const s = createSim(); s.play(); s.advance(11 * 60000);
  const w = s.state.projects[0].worktrees.find((x) => x.id === 'wt-chore-old-lint');
  assert.equal(w.state, 'missing');
  assert.ok(s.state.events.some((e) => e.type === 'worktree.missing' && e.subject.id === w.id));
  assert.equal(s.attention().filter((a) => a.kind === 'worktree').length, 1);
});
test('the skew story: one project with 60 missions, three with 3, 2 and 1, the rest empty', () => {
  const s = createSim({ story: 'skew' }), n = (id) => Object.values(s.state.missions).filter((m) => m.project === id).length;
  const counts = s.state.projects.slice(3).map((p) => n(p.id));
  assert.deepEqual(counts, [60, 3, 2, 1, 0, 0, 0]);
  assert.ok(s.state.projects.slice(3).some((p) => p.worktrees.length === 6) && s.state.projects.slice(3).some((p) => p.worktrees.length === 0));
  assert.ok(s.state.events.filter((e) => e.mission === 'm-x13').length > 3, 'the retained history keeps the first missions');
});
