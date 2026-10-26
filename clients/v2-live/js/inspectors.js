// S3 inspectors for the work things: mission (Outcome, Plan, Now, Evidence, Why, Timeline, Relations), task, route decision, execution,
// approval (the decision sheet), plan, verification, review, idea, knowledge, project. Area inspectors are in inspectors2.js.
// A sheet on a phone, a right sheet on a tablet, a column on a desktop; the same content. Offline it reads what was kept and offers no actions.
import { h } from './dom.js';
import { icon } from './icons.js';
import { present } from '../core-words.js';
import { clockLabel, categoryOf } from '../sim.js';
import { badge, projName, word, dnote } from './views.js';
import { spineInspector, spineRow } from './spine.js';
import { areasOf, kindOfId, whyOf, routeOf, policyOf, execOutput, checkpoints, relationsOf, stationTimes, harnessLabel, accountLabel, IDEA_PATH } from './areas-model.js';
import { pill, sec, note, kv, link, entity, hrefFor } from './ax.js';
import { inspectorArea } from './inspectors2.js';
import { overview, pane, meta } from './inspector-mission.js';

const KIND_WORD = { mission: 'Mission', task: 'Task', route: 'Route decision', execution: 'Execution', approval: 'Decision', plan: 'Plan', verification: 'Verification', review: 'Review', idea: 'Idea', knowledge: 'Knowledge', project: 'Project' };
export const isCompact = () => (document.getElementById('device') || document.body).clientWidth < 600;
export const ask = (ctx, c) => { ctx.ui.confirm = Object.assign({ at: ctx.route.id }, c); ctx.render(); };
export function confirmNodes(ctx) {
  const c = ctx.ui.confirm; if (!c || c.at !== ctx.route.id) return null;
  return [h('p', { class: 'ax-confirm-q' }, c.text),
    h('button', { class: 'btn ' + (c.tone === 'danger' ? 'danger decide' : 'primary decide'), type: 'button', 'data-key': 'confirm-yes', onclick: () => { ctx.ui.confirm = null; c.run(); } }, c.label),
    h('button', { class: 'btn', type: 'button', onclick: () => { ctx.ui.confirm = null; ctx.render(); } }, 'Back')];
}

export function frame(ctx, A, o) {
  const tabs = o.tabs || [], cur = (tabs.find((t) => t[0] === ctx.ui.tab) || tabs[0] || [])[0];
  const off = A.isOffline(), on = o.pin ? A.pinned(o.pin) : false;
  const foot = off ? null : confirmNodes(ctx) || (o.foot ? [].concat(o.foot(cur)).filter(Boolean) : null);
  return h('div', { class: o.cls || null }, h('div', { class: 'grab', 'aria-hidden': 'true' }),
    h('div', { class: 'insp-head' }, h('div', { class: 'ax-ih' }, h('p', { class: 'ax-eyebrow' }, o.kind), h('h2', null, o.title), o.sub ? h('p', { class: 'm' }, o.sub) : null),
      h('div', { class: 'ax-head-actions' }, o.pin ? h('button', { class: 'btn quiet', type: 'button', 'aria-pressed': on ? 'true' : 'false', onclick: () => { A.togglePin(o.pin); ctx.toast(A.pinned(o.pin) ? 'Pinned.' : 'Unpinned.'); ctx.render(); } }, on ? 'Pinned' : 'Pin') : null,
        h('button', { class: 'btn quiet', type: 'button', 'aria-label': 'Close details', onclick: () => ctx.closeInsp() }, 'Close'))),
    o.meta || null,
    tabs.length > 1 ? h('div', { class: 'tabs', role: 'tablist' }, ...tabs.map(([id, l]) => h('button', { class: 'tab', type: 'button', role: 'tab', 'aria-selected': id === cur ? 'true' : 'false', onclick: () => { ctx.ui.tab = id; ctx.render(); } }, l))) : null,
    h('div', { class: 'insp-body' }, off ? h('p', { class: 'ax-stale-note' }, 'Offline: last seen ' + clockLabel(A.offlineAt()) + '. This is what the client kept. Actions are off until Core is back.') : null, o.body(cur)),
    foot && foot.length ? h('div', { class: 'insp-foot' }, ...foot) : null);
}

export const rowLine = (a, b) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, a), b == null ? null : h('span', { class: 'b' }, b));
export const relationsBody = (S, kind, id) => relationsOf(S, kind, id).map((g) => sec(g.title, h('div', { class: 'ax-ents' }, ...g.items.map((i) => entity(i)))));
const relTab = (S, kind, id) => h('div', { class: 'ax-body' }, ...relationsBody(S, kind, id), dnote('E07', 'Relations lists what this thing is connected to; each row opens its own details.'));

export function inspectorFor(ctx) {
  const id = ctx.route.id; if (!id) return null;
  const kind = kindOfId(id), A = areasOf(ctx.sim), S = A.S();
  const b = { mission, task, route, execution, approval, plan, verification, review, idea, knowledge, project }[kind];
  if (b) return b(ctx, A, S, id);
  return inspectorArea(ctx, A, S, id, kind);
}

// ---------- mission ----------
function mission(ctx, A, S, id) {
  const m = S.missions[id]; if (!m) return null;
  const tasks = m.tasks.map((x) => S.tasks[x]), execs = Object.values(S.executions).filter((x) => x.mission === id);
  const act = (kind, label, primary, confirm) => h('button', { class: 'btn' + (primary ? ' primary' : ''), type: 'button', onclick: () => (confirm ? ask(ctx, { text: confirm, label, tone: 'danger', run: () => ctx.act(kind, id) }) : ctx.act(kind, id)) }, label);
  const foot = () => {
    if (m.state === 'BLOCKED') return [act('unblock', 'Answer and unblock', true), act('cancel', 'Cancel mission', false, 'Cancel "' + m.title + '"? Cancelling ends the mission and stops its runs. This cannot be undone.')];
    if (m.state === 'PAUSED') return [act('resume', 'Resume', true), act('cancel', 'Cancel mission', false, 'Cancel "' + m.title + '"? Its paused runs are discarded. This cannot be undone.')];
    if (m.state === 'FAILED') return [act('replan', 'Replan', true), act('cancel', 'Cancel mission', false, 'Cancel "' + m.title + '"? This cannot be undone.')];
    if (m.state === 'REVIEWING') return [act('accept', 'Accept', true), act('changes', 'Request changes')];
    if (m.state === 'EXECUTING') return [act('pause', 'Pause')];
    if (m.state === 'APPROVAL_REQUIRED' && m.approval) return [h('a', { class: 'btn primary', href: '#/attention/' + m.approval }, 'Open decision')];
    if (m.state === 'CREATED') return [act('cancel', 'Cancel mission', false, 'Cancel "' + m.title + '"? This cannot be undone.')];
    return null;
  };
  const body = (tab) => {
    if (tab === 'outcome') {
      const last = S.events.filter((e) => e.mission === id && e.type === 'mission.state_changed').pop();
      const facts = kv([['State', badge('mission', m.state)], ['Project', link(hrefFor('project', 'prj-' + m.project), projName(ctx.sim, m.project))], ['Branch', m.branch], ['Origin', m.origin], ['Plan', m.plan_version ? 'version ' + m.plan_version : 'none yet'], ['Tasks', tasks.filter((t) => t.state === 'SUCCEEDED').length + ' of ' + tasks.length + ' done'], ['Account', link(hrefFor('account', m.account), accountLabel(S, m.account))], last ? ['Last change', clockLabel(last.at) + (last.actor === 'device' ? ' by you' : ' by Core')] : null, m.reason ? ['Why', m.reason] : null]);
      return overview(ctx, S, m, tasks, execs, { compact: isCompact(), facts, d08: dnote('D08', 'Time at each station on the inspector spine; omitted when events are pruned.') });
    }
    if (tab === 'plan') {
      const plans = Object.values(S.plans).filter((p) => p.mission === id), aps = Object.values(S.approvals).filter((a) => a.mission === id);
      return h('div', { class: 'ax-body' },
        sec('Tasks', tasks.length ? h('div', { class: 'ax-ents' }, ...tasks.map((t) => entity({ kind: 'task', id: t.id, label: t.title }, badge('task', t.state)))) : note('No plan yet.')),
        sec('Plan versions', plans.length ? h('div', { class: 'ax-ents' }, ...plans.map((p) => entity({ kind: 'plan', id: p.id, label: 'Version ' + p.version }, badge('plan', p.state)))) : note('No plan yet.')),
        aps.length ? sec('Decisions', h('div', { class: 'ax-ents' }, ...aps.map((a) => entity({ kind: 'approval', id: a.id, label: a.presented.what }, badge('approval', a.state))))) : null);
    }
    if (tab === 'now') return h('div', { class: 'ax-body' }, sec('Executions', execs.length ? h('div', { class: 'ax-ents' }, ...execs.map((x) => entity({ kind: 'execution', id: x.id, label: x.id, note: harnessLabel(x.harness) + ' · ' + (S.models.find((q) => q.id === x.model) || {}).label + (ctx.sim.reading(x) ? ' · ' + ctx.sim.reading(x) : '') }, badge('execution', x.state)))) : note('No execution yet.')));
    if (tab === 'evidence') {
      const vs = Object.values(S.verifications).filter((x) => x.mission === id), rs = Object.values(S.reviews).filter((x) => x.mission === id);
      return h('div', { class: 'ax-body' }, sec('Verification', vs.length ? vs.map((v) => h('div', { class: 'ax-block' }, h('a', { class: 'ax-ent', href: hrefFor('verification', v.id) }, h('span', { class: 'e-main' }, h('span', { class: 'e-name' }, v.id + ' on ' + v.base_revision)), badge('verification', v.state)), ...v.checks.map((c) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, c.name), pill(c.result === 'pass' ? 'ok' : 'blocked', c.result === 'pass' ? 'Passed' : 'Failed'))))) : note('Nothing has been verified yet.')),
        rs.length ? sec('Review', h('div', { class: 'ax-ents' }, ...rs.map((r) => entity({ kind: 'review', id: r.id, label: r.id }, badge('review', r.state))))) : null);
    }
    if (tab === 'why') {
      const rows = whyOf(S, m);
      return h('div', { class: 'ax-body' }, sec('Why it went this way', h('ol', { class: 'ax-why' }, ...rows.slice(0, 14).map((r) => h('li', null, h('p', { class: 'w-meta' }, r.time + ' · ' + r.by), h('p', { class: 'w-title' }, r.title), h('p', { class: 'w-because' }, r.because), r.link ? link(hrefFor(kindOfId(r.link), r.link), r.link.startsWith('rd-') ? 'See the route decision' : 'Open the decision') : null))), rows.length > 14 ? note('Showing the latest 14 of ' + rows.length + ' decisions.') : null, rows.length ? null : note('Nothing has been decided yet.')),
        dnote('E07', 'Why lists each decision with its reason, in plain words, and who made it: Core by policy, or you on a card.'));
    }
    if (tab === 'timeline') {
      const att = execs.slice().sort((a, b) => a.started_at - b.started_at), shown = att.slice(-8);
      const steps = S.events.filter((e) => e.mission === id && e.type === 'mission.state_changed').slice(-6).reverse();
      return h('div', { class: 'ax-body' },
        sec('Attempts', shown.length ? h('div', { class: 'ax-ents' }, ...shown.map((x, i) => entity({ kind: 'execution', id: x.id, label: 'Attempt ' + (att.length - shown.length + i + 1), note: clockLabel(x.started_at) + ' to ' + (x.state.startsWith('ENDED') ? clockLabel(x.last_output_at) : 'now') + ' · ' + accountLabel(S, x.account) }, badge('execution', x.state)))) : note('No attempt yet.'), note('Showing ' + shown.length + ' of ' + att.length + '. The trace reads a bounded set of attempts, so a long mission shows its latest.')),
        sec('Last recorded steps', steps.length ? steps.map((e) => rowLine(word('mission', e.payload.to), clockLabel(e.at) + ' · ' + categoryOf('mission', e.payload.to, e.payload.trigger))) : note('No recorded steps for this mission.'), h('a', { class: 'btn', href: '#/replay/' + id }, 'Open Replay')),
        dnote('G13', 'The mission trace shows attempts, not a transcript: each execution is one attempt, and failures stay visible.'));
    }
    return relTab(S, 'mission', id);
  };
  const fr = frame(ctx, A, { cls: 'msn-panel', kind: KIND_WORD.mission, title: m.title, meta: meta(ctx, S, m), pin: id, tabs: [['outcome', 'Outcome'], ['plan', 'Plan'], ['now', 'Now'], ['evidence', 'Evidence'], ['why', 'Why'], ['timeline', 'Timeline'], ['relations', 'Relations']], body, foot });
  return h('div', { class: 'msn' }, pane(ctx, S, m), fr);
}

// ---------- task and route decision ----------
function routeBody(S, t) {
  if (!t.execution) return note('Not routed yet. Core routes a task when it is ready to start.');
  const r = routeOf(S, t);
  return h('div', { class: 'ax-body' }, sec('Chosen', kv([['Harness', r.chosen.harnessLabel], ['Model', link(hrefFor('model', 'mdl-' + r.chosen.model), r.chosen.modelLabel)], ['Account', link(hrefFor('account', r.chosen.account), r.chosen.accountLabel)], ['Decided', clockLabel(r.at)]])),
    sec('Considered', h('ul', { class: 'ax-cons' }, ...r.considered.map((c) => h('li', { 'data-result': c.result }, h('span', { class: 'c-name' }, c.label), pill(c.result === 'Chosen' ? 'ok' : c.result === 'Passed over' ? 'paused' : 'blocked', c.result), h('span', { class: 'c-why' }, c.why))))),
    sec('Rule', note(r.rule)), dnote('E08', 'A route decision names every candidate and why it was chosen, passed over or not eligible. Nothing is picked silently.'));
}
function task(ctx, A, S, id) {
  const t = S.tasks[id]; if (!t) return null;
  const m = S.missions[t.mission];
  return frame(ctx, A, { kind: KIND_WORD.task, title: t.title, sub: m.title, tabs: [['overview', 'Overview'], ['route', 'Route'], ['relations', 'Relations']],
    body: (tab) => tab === 'route' ? routeBody(S, t) : tab === 'relations' ? relTab(S, 'task', id) : h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('task', t.state)], ['Mission', link(hrefFor('mission', m.id), m.title)], ['Execution', t.execution ? link(hrefFor('execution', t.execution), t.execution) : 'None yet'], ['Task key', t.key]]))) });
}
function route(ctx, A, S, id) {
  const t = S.tasks[id.replace(/^rd-/, '')]; if (!t) return null;
  return frame(ctx, A, { kind: KIND_WORD.route, title: 'How "' + t.title + '" was routed', sub: S.missions[t.mission].title, body: () => h('div', { class: 'ax-body' }, routeBody(S, t), link(hrefFor('task', t.id), 'Open the task')) });
}

// ---------- execution ----------
function execution(ctx, A, S, id) {
  const x = S.executions[id]; if (!x) return null;
  const m = S.missions[x.mission], t = S.tasks[x.task];
  const body = (tab) => {
    if (tab === 'output') {
      const o = execOutput(S, x);
      return h('div', { class: 'ax-body' }, sec('Latest output', h('ol', { class: 'ax-out' }, ...o.lines.map((l) => h('li', { class: l.end ? 'end' : '' }, h('span', { class: 'o-t' }, clockLabel(l.at, true)), h('span', { class: 'o-x' }, l.text)))), note('Last ' + o.lines.length + ' of ' + o.total + ' lines. Core keeps a bounded tail for the activity chip, not the whole transcript.'), ctx.sim.reading(x) ? note('Reading: ' + ctx.sim.reading(x) + '.') : null), dnote('E08', 'Execution inspector: Output, Checkpoints, Facts. The private reasoning and tool transcript are not recorded (see Replay, Not recorded).'));
    }
    if (tab === 'checkpoints') {
      const c = checkpoints(S, x);
      return h('div', { class: 'ax-body' }, sec('Checkpoints', c.length ? h('ol', { class: 'ax-why' }, ...c.map((k) => h('li', null, h('p', { class: 'w-meta' }, clockLabel(k.at) + ' · Checkpoint ' + k.n), h('p', { class: 'w-because' }, k.text)))) : note('No checkpoint yet. One is written about every 8 minutes of work, and before a handoff.')));
    }
    if (tab === 'relations') return relTab(S, 'execution', id);
    return h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('execution', x.state)], ['Harness', harnessLabel(x.harness)], ['Model', (S.models.find((q) => q.id === x.model) || {}).label], ['Account', link(hrefFor('account', x.account), accountLabel(S, x.account))], ['Task', link(hrefFor('task', t.id), t.title)], ['Mission', link(hrefFor('mission', m.id), m.title)], ['Started', clockLabel(x.started_at)], ['Last output', clockLabel(x.last_output_at)], x.reason ? ['Ended because', x.reason] : null])));
  };
  return frame(ctx, A, { kind: KIND_WORD.execution, title: x.id, sub: m.title + ' · ' + t.title, tabs: [['output', 'Output'], ['checkpoints', 'Checkpoints'], ['facts', 'Facts'], ['relations', 'Relations']], body });
}

// ---------- approval: the decision sheet ----------
function approval(ctx, A, S, id) {
  const a = S.approvals[id]; if (!a) return null;
  const m = S.missions[a.mission], open = a.state === 'PENDING', plan = a.kind === 'plan';
  const decide = (kind, label, text, danger) => h('button', { class: 'btn decide ' + (danger ? 'danger outline' : kind === 'approve' ? 'primary' : ''), type: 'button', onclick: () => {
    const run = () => { const r = ctx.act(kind, id); if (kind === 'plan_changes' && r.ok) ctx.toast('Plan sent back (simulated). Core plans again.'); };
    if (isCompact() || kind === 'reject') ask(ctx, { text, label: 'Confirm: ' + label.toLowerCase(), tone: danger ? 'danger' : 'primary', run }); else run();
  } }, label);
  const noundo = h('div', { class: 'noundo', role: 'note' }, icon('warning', 22), h('p', null, h('b', null, 'No Undo.'), h('span', null, ' Decision cannot be changed.')));
  const foot = () => (open ? [noundo, decide('approve', 'Approve', 'Approve this? ' + a.presented.consequence), plan ? decide('plan_changes', 'Request changes', 'Send the plan back? Core plans again and asks you once more.') : null, decide('reject', 'Reject', 'Reject this? ' + (plan ? 'The mission is cancelled.' : 'The execution ends and the mission is blocked.'), true)] : null);
  const body = (tab) => {
    if (tab === 'policy') {
      const p = policyOf(S, a);
      return h('div', { class: 'ax-body' }, sec('Policy outcome', h('p', { class: 'ax-big' }, p.outcome)), sec('Checks', h('ul', { class: 'ax-cons' }, ...p.checks.map(([n, d, r]) => h('li', null, h('span', { class: 'c-name' }, n), pill(r === 'ok' ? 'ok' : 'attention', r === 'ok' ? 'Passed' : 'Asks'), h('span', { class: 'c-why' }, d))))), dnote('E09', 'Policy shows which rule made this a decision for you, so a card is never unexplained.'));
    }
    if (tab === 'relations') return relTab(S, 'approval', id);
    return h('div', { class: 'ax-body' },
      sec('What you approve', h('p', null, a.presented.what)), sec('Why Archeus asks', h('p', null, a.presented.why)), sec('What Core does next', h('p', null, a.presented.consequence)),
      plan && m.tasks.length ? sec('Plan v' + (m.plan_version || 1), h('ol', { class: 'dcn-steps' }, ...m.tasks.map((x) => S.tasks[x]).map((t, i) => h('li', { 'data-now': i === 0 ? 'true' : null }, h('span', { class: 'st-g', 'aria-hidden': 'true' }), t.title)))) : null,
      sec('Where the mission is', spineInspector(m.state, m.held_from)),
      h('p', { class: 'sp-text' }, open ? 'Expires ' + clockLabel(a.expires_at) + '. This is a simulated decision: nothing is run, sent or spent.' : 'Decided: ' + word('approval', a.state) + '.'),
      dnote('I05', 'On a phone a decision takes two steps: choose, then confirm. Reject always asks twice.'));
  };
  return frame(ctx, A, { cls: 'dcn', kind: KIND_WORD.approval, title: plan ? 'Approve this plan?' : 'Allow this action?', sub: m.title + ' · ' + projName(ctx.sim, a.project), tabs: [['decision', 'Decision'], ['policy', 'Policy'], ['relations', 'Relations']], body, foot });
}

// ---------- plan, verification, review ----------
function plan(ctx, A, S, id) {
  const p = S.plans[id]; if (!p) return null;
  const m = S.missions[p.mission], prev = Object.values(S.plans).find((x) => x.mission === m.id && x.version === p.version - 1);
  return frame(ctx, A, { kind: KIND_WORD.plan, title: 'Plan version ' + p.version, sub: m.title, tabs: [['plan', 'Plan'], ['relations', 'Relations']],
    body: (tab) => tab === 'relations' ? relTab(S, 'plan', id) : h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('plan', p.state)], ['Mission', link(hrefFor('mission', m.id), m.title)], prev ? ['Before it', link(hrefFor('plan', prev.id), 'Version ' + prev.version + ', ' + word('plan', prev.state).toLowerCase())] : null])),
      sec('Tasks', h('div', { class: 'ax-ents' }, ...m.tasks.map((x) => S.tasks[x]).map((t) => entity({ kind: 'task', id: t.id, label: t.title }, badge('task', t.state))))), prev ? note('A new version replaces the one before it; the old version stays in the record.') : null) });
}
function verification(ctx, A, S, id) {
  const v = S.verifications[id]; if (!v) return null;
  const m = S.missions[v.mission];
  return frame(ctx, A, { kind: KIND_WORD.verification, title: v.id + ' on ' + v.base_revision, sub: m.title, tabs: [['checks', 'Checks'], ['relations', 'Relations']],
    body: (tab) => tab === 'relations' ? relTab(S, 'verification', id) : h('div', { class: 'ax-body' }, sec('Result', kv([['State', badge('verification', v.state)], ['Base revision', v.base_revision], ['Mission', link(hrefFor('mission', m.id), m.title)]])),
      sec('Checks', v.checks.length ? v.checks.map((c) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, c.name + ' · ' + c.kind), pill(c.result === 'pass' ? 'ok' : 'blocked', c.result === 'pass' ? 'Passed' : 'Failed'))) : note(v.state === 'RUNNING' ? 'The checks are running.' : 'No check has run yet.')), note('A verifier error is not a failure of the work. Passing a check does not accept the result: you do that on the review.')) });
}
function review(ctx, A, S, id) {
  const r = S.reviews[id]; if (!r) return null;
  const m = S.missions[r.mission];
  return frame(ctx, A, { kind: KIND_WORD.review, title: 'Review of ' + m.title, sub: projName(ctx.sim, m.project), body: () => h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('review', r.state)], ['Mission', link(hrefFor('mission', m.id), m.title)]])), note('Verified is not accepted. The verdict is yours.')),
    foot: () => (m.state === 'REVIEWING' ? [h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('accept', m.id) }, 'Accept'), h('button', { class: 'btn', type: 'button', onclick: () => ctx.act('changes', m.id) }, 'Request changes')] : null) });
}

// ---------- idea, knowledge, project ----------
export function ideaPath(state, compact) {
  const k = IDEA_PATH.indexOf(state), off = k < 0;
  return h('ol', { class: 'ax-path' + (compact ? ' compact' : ''), 'aria-label': 'Idea path' }, ...IDEA_PATH.map((s, i) => h('li', { 'data-s': off ? 'off' : i < k ? 'done' : i === k ? 'now' : 'next', 'aria-current': i === k ? 'step' : null }, h('span', { class: 'p-dot', 'aria-hidden': 'true' }), compact ? h('span', { class: 'vh' }, present('idea', s).label) : h('span', { class: 'p-w' }, present('idea', s).label))));
}
function idea(ctx, A, S, id) {
  const i = S.ideas.find((x) => x.id === id); if (!i) return null;
  const k = IDEA_PATH.indexOf(i.state), next = k >= 0 && k < IDEA_PATH.length - 1 ? IDEA_PATH[k + 1] : null;
  return frame(ctx, A, { kind: KIND_WORD.idea, title: i.title, sub: projName(ctx.sim, i.project), pin: id, tabs: [['path', 'Path'], ['relations', 'Relations']],
    body: (tab) => tab === 'relations' ? relTab(S, 'idea', id) : h('div', { class: 'ax-body' }, sec('Where it is', ideaPath(i.state), note(k < 0 ? 'This idea is off the path: ' + present('idea', i.state).label + '.' : 'An idea is not a commitment. It moves forward only when you say so.')), dnote('E17', 'The idea path runs Captured to Learned; Parked and Discarded sit beside it.')),
    foot: () => [next ? h('button', { class: 'btn primary', type: 'button', onclick: () => { A.advanceIdea(id); ctx.toast('Moved to ' + present('idea', next).label + ' (simulated).'); ctx.render(); } }, 'Move to ' + present('idea', next).label) : null, i.state !== 'PARKED' && i.state !== 'DISCARDED' && i.state !== 'LEARNED' ? h('button', { class: 'btn', type: 'button', onclick: () => { A.setIdea(id, 'PARKED'); ctx.render(); } }, 'Park') : null, i.state === 'PARKED' ? h('button', { class: 'btn', type: 'button', onclick: () => { A.setIdea(id, 'CAPTURED'); ctx.render(); } }, 'Bring back') : null] });
}
function knowledge(ctx, A, S, id) {
  const k = S.knowledge.find((x) => x.id === id); if (!k) return null;
  return frame(ctx, A, { kind: KIND_WORD.knowledge, title: k.text, sub: projName(ctx.sim, k.project), tabs: [['item', 'Item'], ['relations', 'Relations']],
    body: (tab) => tab === 'relations' ? relTab(S, 'knowledge', id) : h('div', { class: 'ax-body' }, sec('Facts', kv([['State', badge('knowledge_item', k.state)], ['Source', k.source === 'user' ? 'You said it' : 'Suggested from feedback'], ['Project', link(hrefFor('project', 'prj-' + k.project), projName(ctx.sim, k.project))]])), note(k.state === 'CANDIDATE' ? 'Archeus will not remember this until you confirm it.' : k.state === 'CONFIRMED' ? 'Confirmed: new missions in this project can use it as context.' : 'Not used as context.')),
    foot: () => (k.state === 'CANDIDATE' ? [h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('confirm', id) }, 'Remember'), h('button', { class: 'btn', type: 'button', onclick: () => ctx.act('retract', id) }, 'Not this')] : null) });
}
function project(ctx, A, S, id) {
  const pid = id.replace(/^prj-/, ''), p = S.projects.find((x) => x.id === pid); if (!p) return null;
  const c = A.launch(pid), pv = A.preview(pid);
  return frame(ctx, A, { kind: KIND_WORD.project, title: p.name, sub: p.note, pin: id, tabs: [['project', 'Project'], ['relations', 'Relations']],
    body: (tab) => tab === 'relations' ? relTab(S, 'project', id) : h('div', { class: 'ax-body' }, sec('Repository', kv([['Folder', p.root], ['Missions', String(Object.values(S.missions).filter((m) => m.project === pid).length)], ['Confirmed knowledge', String(S.knowledge.filter((k) => k.project === pid && k.state === 'CONFIRMED').length)]])),
      sec('Phase', h('ul', { class: 'prj-phase' }, ...Object.values(S.missions).filter((m) => m.project === pid).map((m) => h('li', null, h('a', { href: hrefFor('mission', m.id) }, h('span', { class: 'ph-n' }, m.title), spineRow(m.state, m.held_from), h('span', { class: 'ph-w' }, word('mission', m.state))))))),
      sec('Next mission launches', h('p', null, harnessLabel(pv.harness) + ' · ' + pv.model + (pv.account ? ' · ' + pv.account : '')), note(pv.note), link('#/accounts', 'Change the launch settings'))) });
}
