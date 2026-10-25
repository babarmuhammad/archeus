// S3 inspectors for the area things: hook, MCP server, agent, account, model, spawn breaker, isolation boundary, health check, automation, client.
import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { badge, dnote } from './views.js';
import { frame, ask } from './inspectors.js';
import { mcpStatus, accountLabel, harnessLabel, breakerView, waitLabel, BOUNDARIES } from './areas-model.js';
import { pill, sec, note, kv, link, hrefFor, sw, ringNode, spark, TONE_OF_STATE } from './ax.js';

export const done = (ctx, r, msg) => { ctx.toast(r.ok ? msg : 'Not done: ' + r.reason); ctx.render(); };
const ago = (S, t) => (t == null ? 'Never' : clockLabel(t));
export const MCP_TONE = { CONNECTED: ['ok', 'Connected'], CONNECTING: ['active', 'Connecting'], DISABLED: ['paused', 'Disabled'], UNKNOWN: ['unknown', 'Unknown'] };

export function inspectorArea(ctx, A, S, id, kind) {
  const f = { hook, mcp, agent, account, model, breaker, boundary, check, automation, device }[kind];
  return f ? f(ctx, A, S, id) : null;
}

function hook(ctx, A, S, id) {
  const x = A.hooks().find((q) => q.id === id); if (!x) return null;
  const flip = () => { const r = A.toggleHook(id); done(ctx, r, r.on ? 'Hook switched on (simulated).' : 'Hook switched off (simulated).'); };
  return frame(ctx, A, { kind: 'Hook · ' + x.event, title: x.name, sub: x.scope,
    body: () => h('div', { class: 'ax-body' }, sec('What it does', h('p', null, x.does)),
      sec('Facts', kv([['State', pill(x.enabled ? 'ok' : 'paused', x.enabled ? 'Enabled' : 'Disabled')], ['Event', x.event], ['Matches', h('code', null, x.matcher)], ['Scope', x.scope], ['Runs', String(x.runs)], ['Last run', ago(S, x.last)], ['Last outcome', x.outcome]])),
      x.locked ? note('Built in and fail closed: it cannot be switched off.') : x.sensitive && x.enabled ? note('Switching this off changes what an execution may do without asking you. It asks you to confirm.') : null,
      link('#/security', 'See the privileges on Security'), dnote('H09', 'Hooks are listed with status and last run; enable and disable go through a confirm when they guard something.')),
    foot: () => (x.locked ? null : [h('button', { class: 'btn' + (x.enabled ? '' : ' primary'), type: 'button', onclick: () => (x.enabled && x.sensitive ? ask(ctx, { text: 'Switch off "' + x.name + '"? An execution can then do this without asking you.', label: 'Switch off', tone: 'danger', run: flip }) : flip()) }, x.enabled ? 'Switch off' : 'Switch on')]) });
}

function mcp(ctx, A, S, id) {
  const x = A.mcp().find((q) => q.id === id); if (!x) return null;
  const st = mcpStatus(x, S.clock), t = MCP_TONE[st];
  return frame(ctx, A, { kind: 'MCP server · ' + x.transport, title: x.name, sub: x.scope,
    body: () => h('div', { class: 'ax-body' }, sec('What it is', h('p', null, x.detail)),
      sec('Facts', kv([['State', pill(t[0], t[1])], ['Scope', x.scope], ['Calls', String(x.calls)], ['Last call', ago(S, x.last)]])),
      sec('Tools', x.tools.length ? x.tools.map(([n, k]) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('code', null, n)), pill(k === 'read' ? 'ok' : 'attention', k === 'read' ? 'Read only' : 'Writes, asks first'))) : note('No tool is known yet.')),
      note('Credentials are never passed to an MCP server by Archeus.'), dnote('H09', 'MCP servers: status, last call, enable and disable. A server whose capability has not been checked cannot be switched on from chat.')),
    foot: () => (x.unchecked ? null : [h('button', { class: 'btn' + (x.enabled ? '' : ' primary'), type: 'button', onclick: () => { const r = A.toggleMcp(id); done(ctx, r, r.on ? 'Connecting (simulated).' : 'Switched off (simulated).'); } }, x.enabled ? 'Switch off' : 'Switch on')]) });
}

function agent(ctx, A, S, id) {
  const x = A.agents().find((q) => q.id === id); if (!x) return null;
  const st = A.agentStatus(x), md = S.models.find((q) => q.id === x.model);
  return frame(ctx, A, { kind: 'Agent · ' + x.tier, title: x.name, sub: x.role,
    body: () => h('div', { class: 'ax-body' }, sec('Facts', kv([['Status', pill(st.key === 'working' ? 'active' : st.key === 'off' ? 'paused' : st.key === 'ready' ? 'attention' : 'ok', st.text)], ['Model', link(hrefFor('model', 'mdl-' + x.model), md.label)], ['Tier', x.tier], ['Runs', String(x.runs)], ['Last run', ago(S, x.last)]])),
      note('An agent proposes or records. It never decides for you: approvals and acceptance stay yours.'), dnote('H09', 'Agents are listed with the model tier they use, what they are doing now and when they last ran.')),
    foot: () => [h('button', { class: 'btn' + (x.enabled ? '' : ' primary'), type: 'button', onclick: () => { const r = A.toggleAgent(id); done(ctx, r, r.on ? 'Agent switched on (simulated).' : 'Agent switched off (simulated).'); } }, x.enabled ? 'Switch off' : 'Switch on')] });
}

function account(ctx, A, S, id) {
  const a = S.accounts.find((q) => q.id === id); if (!a) return null;
  const u = A.usage().find((q) => q.id === id), order = A.failover().order, i = order.indexOf(id);
  return frame(ctx, A, { kind: 'Account · ' + harnessLabel(a.harness), title: a.label, sub: present('account_health', a.state).label, tabs: [['account', 'Account'], ['usage', 'Usage']],
    body: (tab) => tab === 'usage' ? h('div', { class: 'ax-body' }, h('div', { class: 'ax-rings' }, h('figure', null, ringNode({ left: u.session.left, key: u.session.key, label: '5 hour window' }), h('figcaption', null, '5 hour window')), h('figure', null, ringNode({ left: u.week.left, key: u.week.key, label: 'Week' }), h('figcaption', null, 'Week'))),
      sec('Session over the last hour', h('div', { class: 'ax-spark-w' }, spark(u.hist.map((p) => ({ t: p.t, s: p.s })), 200, 44)), note(u.resets ? u.resets + '.' : 'No reset time is known.')), note('These are account percentages, not the cost or tokens of one session. Unknown stays unknown, never 0.'))
      : h('div', { class: 'ax-body' }, sec('Facts', kv([['Health', badge('account_health', a.state)], ['Harness', harnessLabel(a.harness)], ['Sign in', 'A subscription login. Archeus never reads, stores, copies, injects or relays the token.'], ['Failover order', (i + 1) + ' of ' + order.length], ['Role', u.role]])), dnote('H03', 'Account health states are Core\'s own words; the order decides which account takes the next mission.')),
    foot: () => [h('button', { class: 'btn', type: 'button', disabled: i <= 0 ? true : null, onclick: () => done(ctx, A.moveAccount(id, -1), 'Moved up in the failover order.') }, 'Move up'), h('button', { class: 'btn', type: 'button', disabled: i >= order.length - 1 ? true : null, onclick: () => done(ctx, A.moveAccount(id, 1), 'Moved down in the failover order.') }, 'Move down')] });
}

function model(ctx, A, S, id) {
  const mid = id.replace(/^mdl-/, ''), m = S.models.find((q) => q.id === mid); if (!m) return null;
  const isDef = A.defaultModel() === mid, used = Object.values(S.missions).filter((q) => q.model === mid).length;
  return frame(ctx, A, { kind: 'Model · ' + harnessLabel(m.harness), title: m.label, sub: 'Tier ' + m.tier,
    body: () => h('div', { class: 'ax-body' }, sec('Facts', kv([['Default', pill(isDef ? 'ok' : 'paused', isDef ? 'Default model' : 'Not the default')], ['Harness', harnessLabel(m.harness)], ['Tier', m.tier], ['Missions using it', String(used)]])),
      note('This is the model Archeus asks for. It is not proof of which model the provider served.'), dnote('H10', 'Accounts and models: four models across two harnesses, one default; a project can override it in its launch settings.')),
    foot: () => [isDef ? null : h('button', { class: 'btn primary', type: 'button', onclick: () => done(ctx, A.setDefaultModel(mid), m.label + ' is now the default (simulated).') }, 'Make default')] });
}

function breaker(ctx, A, S, id) {
  const hid = id.replace(/^bk-/, ''), hs = S.harnesses.find((q) => q.id === hid); if (!hs) return null;
  const v = breakerView(S, hs);
  return frame(ctx, A, { kind: 'Spawn breaker', title: hs.label, sub: v.word,
    body: () => h('div', { class: 'ax-body' }, sec('State', kv([['Breaker', pill(v.state === 'closed' ? 'ok' : v.state === 'open' ? 'blocked' : 'attention', v.state === 'closed' ? 'Closed: starts normally' : v.state === 'open' ? 'Open: cannot start' : 'Half open: one trial')], ['Failed starts', v.failures + ' of 3 in 10 minutes'], v.state === 'open' ? ['Trial start in', waitLabel(v.left)] : null, v.error ? ['Last error', v.error] : null, ['Installed', v.installed ? 'Yes' : 'No']])),
      sec('How it works', note('Trips at 3 failed starts in 10 minutes. A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run.')),
      dnote('H04', 'One breaker per CLI. While it is open a mission shows "cannot start" and dispatch waits; Reset needs a step-up in the real thing.')),
    foot: () => (!v.installed ? null : v.state === 'closed' ? [h('button', { class: 'btn', type: 'button', onclick: () => ask(ctx, { text: 'Simulate three failed starts of ' + hs.label + '? New starts stop until the breaker recovers.', label: 'Trip the breaker', tone: 'danger', run: () => done(ctx, A.tripBreaker(hid), 'The breaker opened (simulated).') }) }, 'Trip the breaker')] : [h('button', { class: 'btn primary', type: 'button', onclick: () => ask(ctx, { text: 'Reset the breaker for ' + hs.label + '? Check that it starts from a terminal first. A real reset needs a step-up.', label: 'Reset the breaker', tone: 'primary', run: () => done(ctx, A.resetBreaker(hid), 'The breaker is closed (simulated).') }) }, 'Reset the breaker')]) });
}

function boundary(ctx, A, S, id) {
  const b = BOUNDARIES.find((q) => q.id === id); if (!b) return null;
  const tone = (w) => (/^Built$/.test(w) ? 'ok' : w === 'Open' ? 'blocked' : w === 'Designed' ? 'attention' : 'paused');
  return frame(ctx, A, { kind: 'Boundary · ' + b.n, title: b.name, sub: b.what,
    body: () => h('div', { class: 'ax-body' }, sec('Status', kv([['Policy layer', pill(tone(b.policy), b.policy)], ['Physical reach', pill(tone(b.physical), b.physical)]])), sec('What this means', h('p', null, b.note)),
      note('As the board records it on 2026-10-21. Nothing here is simulated as working: the physical layer is not built in V1.'), dnote('H14', 'Eight boundaries, each with its policy layer and its physical layer named apart. Neither stands in for the other.')) });
}

function check(ctx, A, S, id) {
  const c = A.health().checks.find((q) => q.id === id); if (!c) return null;
  return frame(ctx, A, { kind: 'Health check', title: c.label, sub: c.summary,
    body: () => h('div', { class: 'ax-body' }, sec('State', pill(TONE_OF_STATE[c.state], c.state === 'ok' ? 'OK' : c.state === 'attention' ? 'Needs attention' : 'Unknown')), sec('Readings', kv(c.readings)),
      c.cause ? sec('Cause', h('p', null, c.cause)) : null, c.fix ? sec('Fix', h('ol', { class: 'ax-steps' }, ...c.fix.map((s) => h('li', null, s)))) : null, c.action ? h('a', { class: 'btn', href: c.action.href }, c.action.label) : null,
      dnote('H15', 'Health is read from records: one live derivation, a cause and a fix when it is not OK, and unknown where nothing was read.')) });
}

function automation(ctx, A, S, id) {
  const a = S.automations.find((q) => q.id === id); if (!a) return null;
  return frame(ctx, A, { kind: 'Automation', title: a.name, sub: a.trigger,
    body: () => h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('automation', a.state)], ['Trigger', a.trigger], ['Next run', a.next_run || 'None'], ['Runs so far', String(a.runs)]])), a.note ? note(a.note) : null),
    foot: () => (a.state === 'SUSPENDED' || a.state === 'PENDING_APPROVAL' ? [h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('enable', id) }, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve')] : null) });
}

function device(ctx, A, S, id) {
  const d = S.devices.find((q) => q.id === id); if (!d) return null;
  return frame(ctx, A, { kind: 'Client', title: d.name, sub: present('device', d.state).label, body: () => h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('device', d.state)]])), note('A paired client can read and decide with its own scope. Revoking it needs a step-up in the real thing.')) });
}
