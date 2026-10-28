import test from 'node:test';
import assert from 'node:assert/strict';
import { createSim, localPlan } from '../sim.js';
import { projectCodes } from '../js/project-code.js';

const row = (name, m, i, days, kind, extra) => ({ name, slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'), missions_hint: m, ideas_hint: i, last_active_days: days, kind, ...extra });
const LIST = [
  row('Alpha', 6, 2, 0, 'running'), row('Alpine', 3, 1, 1, 'running'), row('Alp', 0, 0, 90, 'quiet'),
  row('Beta Gamma Delta', 12, 5, 9, 'waiting', { worktrees: [{ branch: 'fix', label: 'fix', owner: 'archeus', state: 'stale' }, { branch: 'x', label: 'x', owner: 'bogus', state: 'nope' }] }),
  row('Old one', 8, 0, 60, 'quiet'), row('Alpha', 2, 0, 20, 'waiting'), row('Zed', 1, 1, 400, 'weird')
];
const of = (s, p) => Object.values(s.state.missions).filter((m) => m.project === p.id);

test('codes: initials, two letters, and a number when taken, never twice', () => {
  assert.deepEqual(projectCodes(['Alpha', 'Alpine', 'Alp', 'Alpha Beta', 'Beta Gamma Delta Eps', 'ab']), ['AL', 'AL2', 'AL3', 'AB', 'BGD', 'AB2']);
  const many = projectCodes(Array.from({ length: 300 }, (_, i) => (i % 2 ? 'Proj' : 'proj ') + (i % 3 ? '' : 'x')));
  assert.equal(new Set(many).size, 300);
});

test('codes: a taken number is skipped, and odd names still get a code', () => {
  assert.deepEqual(projectCodes(['Al2', 'Alpha', 'Alpine']), ['AL', 'AL2', 'AL3']);
  const odd = projectCodes(['', '   ', '___', '\u{1F680}\u{1F680}x', 'ßa', '中文项目', '日本語 テスト']);
  assert.equal(new Set(odd).size, odd.length);
  assert.ok(odd.every((c) => c.isWellFormed() && Array.from(c).length >= 1 && Array.from(c).length <= 4));
});

test('plan: clean names, unique ids, the three most recent first and the biggest of them first', () => {
  const plan = localPlan([...LIST, row('\u0007Wide\n   name ' + 'w'.repeat(200), 1, 0, 5, 'running')]);
  assert.deepEqual(plan.slice(0, 2).map((p) => p.name), ['Alpha', 'Alpine']);
  assert.ok(plan[2].name.startsWith('Wide'));
  assert.equal(plan[0].missions >= plan[1].missions && plan[1].missions >= plan[2].missions, true);
  const ids = plan.slice(3).map((p) => p.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.every((id) => /^[a-z0-9-]+$/.test(id) && !['archeus', 'notes', 'ideas'].includes(id)));
  const wide = plan.find((p) => p.name.startsWith('Wide'));
  assert.ok(wide.name.length <= 60 && !/[\u0000-\u001f]/.test(wide.name));
  const z = plan.find((p) => p.name === 'Zed');
  assert.equal(z.days, 60);
  assert.equal(z.mix, plan.find((p) => p.name === 'Old one').mix);
  assert.deepEqual(plan.find((p) => p.name === 'Beta Gamma Delta').trees.map((w) => [w.owner, w.state]), [['archeus', 'stale'], ['linked', 'active']]);
});

test('plan: fewer than three usable rows, or no list, mean the default story', () => {
  assert.equal(localPlan(null), null);
  assert.equal(localPlan({}), null);
  assert.equal(localPlan([LIST[0], null, 5]), null);
  assert.equal(createSim({ local: LIST.slice(0, 2) }).state.projects.length, 3);
});

test('sim: each project gets its own mission and idea counts, empty ones stay empty', () => {
  const s = createSim({ local: LIST, strict: true }), st = s.state, plan = localPlan(LIST);
  assert.equal(st.projects.length, LIST.length);
  assert.deepEqual(st.projects.map((p) => p.name), plan.map((p) => p.name));
  plan.forEach((l, k) => {
    const p = st.projects[k], base = k < 3 ? [5, 2, 1][['archeus', 'notes', 'ideas'].indexOf(p.id)] : 0;
    assert.equal(of(s, p).length, Math.max(l.missions, base), l.name);
  });
  assert.equal(of(s, st.projects.find((p) => p.name === 'Alp')).length, 0);
  assert.equal(st.ideas.filter((i) => i.project === st.projects.find((p) => p.name === 'Alp').id).length, 0);
  assert.equal(new Set(st.projects.map((p) => p.id)).size, LIST.length);
});

test('sim: recent projects run and ask, old ones are done', () => {
  const big = Array.from({ length: 3 }, (_, i) => row('Seed' + i, 1, 0, 0, 'running')).concat([row('Hot', 20, 0, 0, 'running'), row('Cold', 20, 0, 80, 'quiet')]);
  const s = createSim({ local: big }), st = s.state, share = (name, f) => { const ms = of(s, st.projects.find((p) => p.name === name)); return ms.filter(f).length / ms.length; };
  const active = (m) => ['EXECUTING', 'APPROVAL_REQUIRED', 'BLOCKED', 'VERIFYING'].includes(m.state);
  assert.ok(share('Hot', active) > 0.5, 'hot');
  assert.ok(share('Cold', (m) => m.state === 'COMPLETED') > 0.7, 'cold');
  assert.ok(share('Cold', active) < share('Hot', active));
});

test('sim: the local story is deterministic, the worktrees ride along, the default is untouched', () => {
  const a = createSim({ local: LIST, seed: 3 }), b = createSim({ local: LIST, seed: 3 });
  assert.equal(a.hash(), b.hash());
  assert.equal(a.state.worktrees.length, 2);
  assert.deepEqual(a.state.worktrees.map((w) => w.state), ['stale', 'active']);
  assert.ok(a.state.worktrees.every((w) => a.state.projects.some((p) => p.id === w.project)));
  assert.equal(createSim().state.projects.length, 3);
  assert.equal(createSim({ projects: 10 }).state.projects.length, 10);
});
