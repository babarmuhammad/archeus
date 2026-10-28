import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim } from '../sim.js';
import * as M from '../js/areas-model.js';

const run = (sim, secs) => sim.advance(secs * 1000);
const mk = (seed) => { const s = createSim(seed == null ? {} : { seed }); return [s, M.areasOf(s)]; };

test('meter thresholds: the 20% line, almost out, out, and unknown is never 0', () => {
  assert.equal(M.meterState(50).key, 'ok');
  assert.equal(M.meterState(79.9).key, 'ok');
  assert.equal(M.meterState(80).key, 'low');
  assert.equal(M.meterState(95).key, 'critical');
  assert.equal(M.meterState(100).key, 'out');
  const u = M.meterState(null);
  assert.equal(u.key, 'unknown'); assert.equal(u.left, null);
});

test('usage rows: accounts grouped by harness in failover order, the unverified Codex reading stays unknown', () => {
  const [, A] = mk();
  const rows = A.usage();
  assert.deepEqual(rows.map((r) => r.id), ['acc-work', 'acc-personal', 'acc-codex', 'acc-codex-2']);
  assert.equal(rows[2].session.key, 'unknown'); assert.equal(rows[2].week.left, null);
  assert.equal(rows[1].session.key, 'low');
});

test('the story: personal window nearly full at 12 min, work week reaches the 20% line at 24 min', () => {
  const [s, A] = mk();
  run(s, 12 * 60 + 5);
  const p = A.usage().find((r) => r.id === 'acc-personal').session; assert.equal(p.key, 'low'); assert.equal(p.left, 6);
  assert.notEqual(A.usage().find((r) => r.id === 'acc-work').week.key, 'low');
  run(s, 12 * 60);
  assert.equal(A.usage().find((r) => r.id === 'acc-work').week.key, 'low');
  assert.ok(A.log().some((l) => /20% reserve line/.test(l.text)));
});

test('health: six checks; the Codex breaker trips at 8 min and the Harness check follows it, with a cause and a fix', () => {
  const [s, A] = mk();
  assert.equal(A.health().checks.length, 6);
  assert.equal(A.health().checks.find((c) => c.id === 'chk-harness').state, 'ok');
  assert.equal(A.health().checks.find((c) => c.id === 'chk-disk').state, 'unknown');
  run(s, 8 * 60 + 5);
  const c = A.health().checks.find((x) => x.id === 'chk-harness');
  assert.equal(c.state, 'attention'); assert.ok(c.cause && c.fix.length >= 1);
  assert.equal(A.security().open, 1);
});

test('breaker: trip, reset and the scheduled half-open does not reopen a reset breaker', () => {
  const [s, A] = mk();
  assert.equal(A.tripBreaker('claude_code').ok, true);
  assert.equal(A.breaker('claude_code').state, 'open');
  assert.equal(A.tripBreaker('claude_code').ok, false);
  assert.equal(A.resetBreaker('claude_code').ok, true);
  assert.equal(A.breaker('claude_code').state, 'closed');
  run(s, 400);
  assert.equal(A.breaker('claude_code').state, 'closed');
  assert.ok(!s.state.events.some((e) => e.type === 'harness.breaker_half_open' && e.subject.id === 'claude_code'));
  assert.equal(A.resetBreaker('claude_code').ok, false);
  assert.equal(A.tripBreaker('pi').ok, false);
});

test('breaker that is left alone goes open, half open after 5 min, then closes', () => {
  const [s, A] = mk();
  A.tripBreaker('claude_code');
  run(s, 301); assert.equal(A.breaker('claude_code').state, 'half_open');
  run(s, 45); assert.equal(A.breaker('claude_code').state, 'closed');
});

test('hooks: a locked hook cannot be switched off, the push hook counts runs and gates the simulated approval', () => {
  const [s, A] = mk();
  assert.equal(A.toggleHook('h-live-5').ok, false);
  run(s, 30);
  const before = A.hooks().find((h) => h.id === 'h-1').runs;
  assert.equal(s.triggerApproval().ok, true);
  assert.equal(A.hooks().find((h) => h.id === 'h-1').runs, before + 1);
  assert.equal(A.toggleHook('h-1').on, false);
  assert.equal(A.hookAllows('h-1'), false);
  assert.equal(A.privileges().find((p) => p.id === 'p5').state, 'unguarded');
});

test('MCP: enabling connects after a moment, a server that was never checked cannot be enabled', () => {
  const [s, A] = mk();
  const x = A.mcp().find((m) => m.id === 'mcp-2');
  assert.equal(A.mcpStatus(x), 'DISABLED');
  A.toggleMcp('mcp-2');
  assert.equal(A.mcpStatus(x), 'CONNECTING');
  run(s, 10); assert.equal(A.mcpStatus(x), 'CONNECTED');
  assert.equal(A.mcpStatus(A.mcp().find((m) => m.id === 'mcp-live-4')), 'UNKNOWN');
  const calls = A.mcp()[0].calls; run(s, 120); assert.ok(A.mcp()[0].calls > calls);
});

test('agents: the planner works while a mission is planning, the verifier while checks run', () => {
  const [s, A] = mk();
  run(s, 100);
  assert.equal(A.agentStatus(A.agents()[0]).key, 'working');
  assert.equal(A.agentStatus(A.agents()[1]).key, 'working');
  A.toggleAgent('ag-1'); assert.equal(A.agentStatus(A.agents()[0]).key, 'off');
});

test('launch preview follows accounts and breakers; failover order is editable', () => {
  const [s, A] = mk();
  assert.match(A.preview('archeus').note, /work/);
  assert.equal(A.moveAccount('acc-personal', -1).ok, true);
  assert.deepEqual(A.failover().order.claude_code, ['acc-personal', 'acc-work']); assert.deepEqual(A.failover().order.codex, ['acc-codex', 'acc-codex-2']); // each harness has its own order
  assert.equal(A.moveAccount('acc-personal', -1).ok, false);
  A.setLaunch('archeus', 'harness', 'codex');
  assert.equal(A.launch('archeus').model, 'codex-main');
  run(s, 8 * 60 + 5);
  assert.equal(A.preview('archeus').tone, 'attention');
  assert.equal(A.setDefaultModel('claude-opus').ok, true); assert.equal(A.defaultModel(), 'claude-opus');
  assert.equal(A.setDefaultModel('nope').ok, false);
});

test('launch settings: one default, and a project has its own entry only when it differs', () => {
  const [, A] = mk();
  assert.equal(A.isOverride('archeus'), false);
  assert.equal(A.launch('archeus'), A.launch('default'));
  assert.equal(A.isOverride('notes'), true); assert.equal(A.launch('notes').mode, 'plan');
  assert.equal(A.setLaunch('archeus', 'parallel', 4).ok, true);
  assert.equal(A.isOverride('archeus'), true); assert.equal(A.launch('archeus').parallel, 4); assert.equal(A.launch('default').parallel, 2);
  assert.equal(A.setLaunch('default', 'mode', 'plan').ok, true);
  assert.equal(A.launch('nope-but-inherits').mode, 'plan'); assert.equal(A.launch('archeus').mode, 'ask');
  assert.equal(A.resetLaunch('archeus').ok, true); assert.equal(A.launch('archeus'), A.launch('default'));
  assert.equal(A.resetLaunch('archeus').ok, false); assert.equal(A.overrideLaunch('nope').ok, false); assert.equal(A.setLaunch('nope', 'mode', 'ask').ok, false);
});

test('digest: groups changes since the cursor, and marking it seen empties it', () => {
  const [s, A] = mk();
  run(s, 600);
  const d = A.digest(A.cursor());
  assert.ok(d.counts.missions >= 4 && d.counts.decisions >= 1);
  assert.ok(d.items.every((i, k) => k === 0 || d.items[k - 1].at >= i.at));
  A.acknowledge();
  assert.equal(A.digest(A.cursor()).items.length, 0);
});

test('why, station times, relations and route decisions', () => {
  const [s, A] = mk();
  run(s, 700);
  const S = A.S(), m = S.missions['m-date'];
  const why = M.whyOf(S, m);
  assert.ok(why.some((r) => r.title === 'Adopted the execution again'));
  assert.ok(why.some((r) => r.title === 'Asked you to decide' && r.by === 'Core'));
  const t = M.stationTimes(S, m);
  assert.equal(t.length, 6);
  assert.ok(t.filter((x) => x != null).every((x, i, a) => i === 0 || x >= a[i - 1] - 1));
  const rel = M.relationsOf(S, 'mission', 'm-date').map((g) => g.title);
  for (const need of ['Project', 'Tasks', 'Executions', 'Decisions', 'Verifications']) assert.ok(rel.includes(need), need);
  const r = M.routeOf(S, S.tasks['t-date-1']);
  assert.equal(r.chosen.account, 'acc-work');
  assert.equal(r.considered.filter((c) => c.result === 'Chosen').length, 1);
  assert.equal(M.policyOf(S, Object.values(S.approvals)[0]).checks.length >= 3, true);
  assert.equal(M.kindOfId('mcp-1'), 'mcp'); assert.equal(M.kindOfId('m-date'), 'mission'); assert.equal(M.kindOfId('rd-t-date-1'), 'route'); assert.equal(M.kindOfId('mdl-claude-sonnet'), 'model');
});

test('offline keeps a stale read while the simulation moves on, and reconnect returns the live one', () => {
  const [s, A] = mk();
  run(s, 100);
  const k0 = M.keptSummary(A.S());
  assert.equal(A.goOffline().ok, true); assert.equal(A.goOffline().ok, false);
  const at = A.offlineAt(); run(s, 500);
  assert.equal(A.offlineAt(), at);
  assert.equal(JSON.stringify(M.keptSummary(A.S())), JSON.stringify(k0));
  assert.notEqual(A.S(), s.state);
  assert.equal(A.reconnect().ok, true); assert.equal(A.S(), s.state);
});

test('request changes on a plan decision sends the plan back and a new decision follows', () => {
  const [s] = mk();
  const id = s.state.missions['m-search'].approval;
  assert.equal(s.act('plan_changes', id).ok, true);
  assert.equal(s.state.missions['m-search'].state, 'PLANNING');
  run(s, 40);
  assert.equal(s.state.missions['m-search'].state, 'APPROVAL_REQUIRED');
  assert.notEqual(s.state.missions['m-search'].approval, id);
  assert.equal(s.state.approvals[id].state, 'SUPERSEDED');
});

test('ideas move along the path; exec output and checkpoints are bounded', () => {
  const [s, A] = mk();
  assert.equal(A.advanceIdea('i-5').ok, true);
  assert.equal(s.state.ideas.find((i) => i.id === 'i-5').state, 'UNDERSTOOD');
  assert.equal(A.advanceIdea('i-2').ok, false);
  run(s, 300);
  const o = M.execOutput(A.S(), s.state.executions['x-date-1']);
  assert.ok(o.lines.length > 0 && o.lines.length <= 12);
  assert.ok(M.checkpoints(A.S(), s.state.executions['x-date-1']).length <= 6);
});

test('the areas do not change the simulation: same seed, same hash with or without them', () => {
  const a = createSim({ seed: 7 }), b = createSim({ seed: 7 }); M.areasOf(b);
  run(a, 1500); run(b, 1500);
  assert.equal(a.hash(), b.hash());
});

test('idea drafts are kept per project, so a draft typed in one project is not offered in another', () => {
  const ui = {};
  M.ideaDraft(ui, 'a').v = 'half an idea';
  assert.equal(M.ideaDraft(ui, 'b').v, '');
  assert.equal(M.ideaDraft(ui, 'a').v, 'half an idea');
});

test('forecast: a rising window gives minutes to the limit; flat, or too few readings, gives no limit', () => {
  const rising = Array.from({ length: 30 }, (_, i) => ({ t: i * 120000, s: 60 + i * 0.9 }));
  assert.equal(M.forecast(rising).mins, 31); // 0.45% per minute, 14.7% left after the last reading
  assert.deepEqual(M.forecast(rising.map((p) => ({ t: p.t, s: 50 }))), { flat: true });
  assert.equal(M.forecast(rising.slice(0, 2)), null);
  assert.equal(M.forecast([{ t: 0, s: null }, { t: 1, s: null }, { t: 2, s: null }]), null);
});

test('the project count option builds that many projects with a proportional mission mix', () => {
  for (const n of [10, 15, 30, 50, 100]) {
    const st = createSim({ seed: 7, projects: n }).state;
    assert.equal(st.projects.length, n);
    assert.ok(Object.keys(st.missions).length > n);
  }
  assert.equal(createSim({ seed: 7 }).state.projects.length, 3);
});

test('harnesses: what each is, what it supports, and its own accounts, models and failover order', () => {
  const [, A] = mk(), hs = Object.fromEntries(A.harnesses().map((h) => [h.id, h]));
  assert.deepEqual(Object.keys(hs), ['claude_code', 'codex', 'pi']);
  assert.ok(M.supports('claude_code', 'hooks') && !M.supports('codex', 'hooks') && M.supports('codex', 'sandbox'));
  assert.equal(hs.pi.installed, false); assert.equal(hs.pi.word, 'Not installed'); assert.equal(hs.pi.accounts.length, 0);
  assert.deepEqual(hs.codex.accounts.map((r) => r.id), ['acc-codex', 'acc-codex-2']);
  assert.deepEqual(hs.codex.models.map((m) => m.id), ['codex-main', 'codex-mini']);
  assert.equal(hs.claude_code.word, 'Near its ceiling'); assert.equal(hs.claude_code.next.id, 'acc-work');
  assert.equal(A.nextAccount('codex').id, 'acc-codex'); assert.equal(A.nextAccount('pi'), undefined);
  assert.equal(A.moveAccount('acc-codex-2', -1).ok, true); // moves inside Codex only
  assert.deepEqual(A.failover().order.codex, ['acc-codex-2', 'acc-codex']); assert.deepEqual(A.failover().order.claude_code, ['acc-work', 'acc-personal']);
  assert.equal(A.moveAccount('acc-codex-2', -1).ok, false); // the first of its own harness, though it is not first overall
  assert.equal(A.nextAccount('codex').id, 'acc-codex-2');
});

test('launch defaults are per harness; the default harness says which a project starts with', () => {
  const [, A] = mk();
  assert.equal(A.setDefaultModel('codex-mini').ok, true);
  assert.equal(A.defaultModel('codex'), 'codex-mini'); assert.equal(A.defaultModel(), 'claude-sonnet'); // the default harness is still Claude Code
  assert.equal(A.setHarnessDefault('codex', 'mode', 'plan').ok, true);
  assert.equal(A.harnessDefault('codex').mode, 'plan'); assert.equal(A.launch('default').mode, 'ask');
  assert.equal(A.setLaunch('default', 'harness', 'codex').ok, true);
  assert.equal(A.defaultHarness(), 'codex'); assert.equal(A.launch('archeus').model, 'codex-mini'); assert.equal(A.launch('archeus').mode, 'plan');
  assert.equal(A.setLaunch('default', 'harness', 'nope').ok, false);
  assert.equal(A.preview(A.harnessDefault('claude_code')).harness, 'claude_code'); // a preview of a harness default, not only of a project
});

test('a shared MCP server has one switch per harness; a harness it is not set up for is refused', () => {
  const [, A] = mk(), x = () => A.mcp().find((q) => q.id === 'mcp-1');
  assert.deepEqual(x().on, { claude_code: true, codex: false }); assert.equal(x().enabled, true);
  assert.equal(A.toggleMcp('mcp-1', 'codex').on, true); assert.deepEqual(x().on, { claude_code: true, codex: true });
  assert.equal(A.toggleMcp('mcp-1', 'claude_code').on, false); assert.equal(x().enabled, true); // still on in Codex
  assert.equal(A.toggleMcp('mcp-1').on, false); assert.equal(x().enabled, false); assert.deepEqual(x().on, { claude_code: false, codex: false });
  assert.equal(A.toggleMcp('mcp-2', 'codex').ok, false);
  assert.ok(A.hooks().every((h) => h.harnesses.join() === 'claude_code'));
});
