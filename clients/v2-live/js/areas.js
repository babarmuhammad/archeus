// S3 areas: Security, Health, Usage, Accounts and models, Hooks / MCP / agents (Extensions), plus what S3 adds to Now and Work
// (digest, pins, idea path) and the offline view. Everything is SIMULATED; each page says so in its header.
import { h } from './dom.js';
import { reducedMotion } from './store.js';
import { icon, glyph } from './icons.js';
import { illustration } from './illustrations.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { head, dnote, missionRow, badge, projName, attentionItem, controlBody, mark } from './views.js';
import { spineRow } from './spine.js';
import { ask, ideaPath } from './inspectors.js';
import { done, MCP_TONE } from './inspectors2.js';
import { areasOf, forecast, breakerView, waitLabel, keptSummary, harnessLabel, harnessShort, CAP_LABEL, METER_WORD } from './areas-model.js';
import { EXT_TABS, tabOf, matches } from './ext-model.js';
import { whenShort, whenExact } from './time-model.js';
import { isPhone } from './viewport.js';
import { openSheet } from './sheet.js';
import { edgeRow, lede } from './phone-pages.js';
import { closeThen } from './phone.js';
import { pill, note, link, entity, hrefFor, sw, ringNode, patchRing, spark, eyebrow, TONE_OF_METER, TONE_OF_STATE } from './ax.js';

function axHead(ctx, eyebrowText, title, lede) {
  const hd = head(ctx, title);
  hd.querySelector('h1').before(eyebrow(eyebrowText));
  hd.classList.add('ax-head');
  return h('div', { class: 'ax-hero' }, hd, lede ? h('p', { class: 'ax-lede' }, lede) : null);
}
export const onTick = (ctx, fn) => { (ctx.ticks = ctx.ticks || []).push(fn); };
function inline(ctx, key) {
  const c = ctx.ui.confirm; if (!c || c.at !== key) return null;
  return h('div', { class: 'ax-inline-confirm', role: 'group' }, h('p', null, c.text), h('div', { class: 'actions' },
    h('button', { class: 'btn ' + (c.tone === 'danger' ? 'danger solid' : 'primary'), type: 'button', onclick: () => { ctx.ui.confirm = null; c.run(); } }, c.label), h('button', { class: 'btn', type: 'button', onclick: () => { ctx.ui.confirm = null; ctx.render(); } }, 'Back')));
}

// ---------- shared page pieces ----------
// The page opens with its answer: a serif state sentence (the colour only on the part that is a state, always with its words) and one line of ledger under it.
const sentence = (parts) => parts.flatMap(([t, tone], i) => [i ? ' · ' : null, h('span', { 'data-tone': tone || null }, t)]);
const top = (eye, parts, ledger, ...extra) => h('header', { class: 'ax-top' }, h('p', { class: 'ax-eyebrow' }, eye), h('div', { class: 'sec-sent-wrap' }, h('h1', { class: 'ax-sentence', 'data-key': 'sentence' }, ...sentence(parts))), ledger ? (isPhone() && typeof ledger === 'string' ? lede(ledger) : h('p', { class: 'ax-ledger' }, ledger)) : null, ...extra);
const sect = (title, count, sub, ...kids) => h('section', { class: 'ax-sect', 'aria-label': title }, h('h2', null, title, count != null ? h('span', { class: 'ax-count' }, String(count)) : null), sub ? h('p', { class: 'ax-sub' }, sub) : null, ...kids);
const dim = (...kids) => h('div', { class: 'ax-dim' }, ...kids);
const chev = () => h('span', { class: 'ax-go', 'aria-hidden': 'true' }, icon('chevron', 18));
// A details row keeps its open state across redraws, and records only what differs from its default.
const toggler = (store, id, dflt) => (e) => { if (e.currentTarget.open !== dflt) store[id] = e.currentTarget.open; else delete store[id]; };

// ---------- sections ----------
// Each page is a few real parts. A part is a link (#/security/policy), so it can be shared and the Back button works. The ids never collide with an inspector id (sec-b5, chk-core, acc-work).
export const SECTIONS = {
  security: [['overview', 'Overview'], ['policy', 'Policy'], ['boundaries', 'Boundaries'], ['activity', 'Activity'], ['emergency', 'Emergency']],
  health: [['all', 'All'], ['attention', 'Needs attention'], ['unknown', 'Unknown'], ['ok', 'OK']],
  usage: [['accounts', 'Accounts'], ['windows', 'Windows'], ['history', 'History']],
  accounts: [['accounts', 'Accounts'], ['models', 'Models'], ['failover', 'Failover'], ['launch', 'Launch settings']]
};
export const isSection = (name, id) => !!id && !!SECTIONS[name] && SECTIONS[name].some(([s]) => s === id);
// An inspector opened from a part (#/security/bk-claude_code) leaves that part behind it; a cold link falls back to the part that owns the id.
const OF_ID = { security: (id) => (id.startsWith('bk-') ? 'emergency' : id.startsWith('sec-b') ? 'boundaries' : 'overview'), accounts: (id) => (id.startsWith('mdl-') ? 'models' : 'accounts') };
function whereAt(ctx, name) {
  const list = SECTIONS[name], id = ctx.route.id, mem = (ctx.ui.sect ||= {});
  const s = isSection(name, id) ? id : !id ? list[0][0] : mem[name] || (OF_ID[name] ? OF_ID[name](id) : list[0][0]);
  mem[name] = s; return s;
}
// Counts are plain totals; a dot (always with its word for a screen reader) marks the part that needs you.
const subnav = (name, cur, label, counts = {}, dots = {}, qs = '') => edgeRow(h('nav', { class: 'ax-subnav', 'aria-label': label },
  ...SECTIONS[name].map(([id, t]) => h('a', { class: 'set-nav-item', href: '#/' + name + '/' + id + qs, 'data-key': name + '-nav-' + id, 'aria-current': id === cur ? 'page' : null }, t,
    counts[id] != null ? h('span', { class: 'ax-count' }, String(counts[id])) : null, dots[id] ? h('span', { class: 'x-dot', 'data-tone': dots[id][0] }, h('span', { class: 'vh' }, dots[id][1])) : null))));
const frame = (cur, header, nav, ...body) => h('div', { class: 'ax-page' }, h('div', { class: 'view ax-view' }, header, ...[].concat(nav), h('div', { class: 'ax-panel', 'data-section': cur }, ...body)));
// Relative under a day, with the exact time on hover.
const ago = (ctx, t) => { const m = Math.floor(Math.max(0, ctx.sim.state.clock - t) / 60000); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.floor(m / 60) + ' h ago' : clockLabel(t); };
const when = (ctx, t) => h('time', { title: clockLabel(t, true) }, ago(ctx, t));
// "Showing 12 of 48" with the one button that changes it.
const fold = (ctx, key, total, cap, dk) => (total > cap ? h('div', { class: 'ax-fold' }, h('span', { class: 'ax-ledger' }, ctx.ui[key] ? 'Showing all ' + total : 'Showing ' + cap + ' of ' + total), h('button', { class: 'btn', type: 'button', 'data-key': dk, onclick: () => { ctx.ui[key] = !ctx.ui[key]; ctx.render(); } }, ctx.ui[key] ? 'Show fewer' : 'Show all ' + total)) : null);
// A flat row: the state first, then what it is and why.
const lrow = (title, detail, state, tone, href, here) => h(href ? 'a' : 'div', { class: 'sec-row', href, 'aria-current': here ? 'true' : null }, pill(tone, state), h('span', { class: 'sec-main' }, h('span', { class: 'sec-name' }, title), h('span', { class: 'sec-detail' }, ...[].concat(detail))));

// A phone row shows two actions at 44 px; the rest wait behind a "..." that opens a sheet of links.
const more = (title, links) => h('button', { class: 'btn quiet ax-dots', type: 'button', 'aria-label': 'More actions', 'aria-haspopup': 'dialog', onclick: () => {
  const s = openSheet({ id: 'ax-more', title, detents: ['peek'], content: h('div', { class: 'ax-sheet-list' }, ...links.map(([label, href]) => h('a', { class: 'ax-sheet-row', href, onclick: (e) => { e.preventDefault(); closeThen(s, () => { location.hash = href; }); } }, label, icon('chevron', 18)))) });
} }, icon('more', 20));

// ---------- harness ----------
// Archeus drives several harnesses, each with its own accounts, models, failover order, launch settings and extensions. The harness is a facet
// of the pages that hold those things: chips that are links, the choice kept in the address (?harness=codex), "All" grouping by harness.
const hvOf = (ctx, hs) => { const v = ctx.route.q && ctx.route.q.harness; return hs.some((x) => x.id === v) ? v : ''; };
const hqs = (v) => (v ? '?harness=' + v : '');
const dot = (tone, word) => h('span', { class: 'x-dot', 'data-tone': tone }, h('span', { class: 'vh' }, word));
const facet = (name, part, hs, cur, countOf) => edgeRow(h('nav', { class: 'chips ax-facet', 'aria-label': 'Harness' },
  ...[{ id: '', label: 'All', n: countOf(null) }, ...hs.map((x) => ({ id: x.id, label: x.label, n: countOf(x), tone: x.tone, word: x.word }))].map((o) => h('a', { class: 'chip', href: '#/' + name + (part && part !== SECTIONS[name][0][0] ? '/' + part : '') + hqs(o.id), 'data-key': 'hf-' + (o.id || 'all'), 'aria-current': o.id === cur ? 'true' : null },
    o.label, h('span', { class: 'ax-count' }, String(o.n)), o.tone ? dot(o.tone, o.word) : null))));
// A small tag: the short name in words, so a harness is never told by colour alone.
const htag = (id) => h('span', { class: 'hn-tag', title: harnessLabel(id) }, harnessShort(id));
const capList = (caps) => caps.flatMap((c, i) => (i ? [', ', CAP_LABEL[c]] : [CAP_LABEL[c]]));
// A harness that is not installed has nothing to list, and says what the next step is.
const noHarness = (x) => h('div', { class: 'ax-empty' }, h('p', { class: 'sec-empty' }, x.label + ' is not installed on this machine.'),
  h('p', { class: 'ax-note' }, 'Install its CLI and Archeus detects it. It would support ', ...capList(x.caps), '.'), link('#/health', 'Run Health after installing', 'ax-link'));
const hsect = (x, count, sub, ...kids) => h('section', { class: 'ax-sect ax-hsect', 'data-harness': x.id, 'aria-label': x.label },
  h('div', { class: 'ax-hh' }, h('h2', null, x.label), count != null ? h('span', { class: 'ax-count' }, String(count)) : null, h('span', { class: 'r-note' }, x.installed ? x.kind + ' · v' + x.version : x.kind + ' · not detected'), pill(x.tone, x.word)),
  sub ? h('p', { class: 'ax-sub' }, sub) : null, ...kids);

// ---------- Security ----------
const PRIV = { allowed: ['ok', 'Allowed'], asks: ['attention', 'Asks you'], denied: ['paused', 'Denied'], 'denied-policy': ['attention', 'Denied by policy only'], unguarded: ['blocked', 'Unguarded'], unconfined: ['blocked', 'Not confined'] };
const TONE_RANK = { blocked: 0, attention: 1, paused: 2, ok: 3 };
const LAYER = (w) => (w === 'Built' ? 'ok' : w === 'Open' ? 'blocked' : w === 'Designed' || w === 'Partly' ? 'attention' : 'paused');
const MODES = [['ask', 'Ask on risky actions'], ['plan', 'Plan only, never execute'], ['auto', 'Approve low risk automatically']];
const LOG_CAP = 12;

function breakerRow(ctx, A, S, hs) {
  const v = breakerView(S, hs), key = 'row:bk-' + hs.id, ok = v.state === 'closed';
  const line = () => (!v.installed ? 'Not installed on this machine.' : v.state === 'closed' ? 'Starts normally.' : v.state === 'half_open' ? 'One trial start is allowed. If it works, the breaker closes.' : 'Cannot start. A trial start is allowed in ' + waitLabel(Math.max(0, hs.breaker.until - ctx.sim.state.clock)) + '.');
  const ln = h('p', { class: 'br-line', 'data-ax': 'bk:' + hs.id }, line());
  onTick(ctx, () => { const t = line(); if (ln.textContent !== t) ln.textContent = t; });
  return h('div', { class: 'ax-br', 'data-state': v.state },
    h('div', { class: 'br-top' }, h('a', { class: 'br-name', href: hrefFor('breaker', 'bk-' + hs.id) }, hs.label), pill(!v.installed ? 'unknown' : ok ? 'ok' : v.state === 'open' ? 'blocked' : 'attention', !v.installed ? 'Not installed' : ok ? 'Closed' : v.state === 'open' ? 'Open: cannot start' : 'Half open')),
    ln, v.installed ? h('p', { class: 'br-dots' }, ...[0, 1, 2].map((i) => h('i', { 'data-on': i < v.failures ? 'true' : 'false' })), h('span', null, v.failures + ' of 3 failed starts in 10 minutes')) : null,
    inline(ctx, key),
    v.installed && !ctx.ui.confirm ? h('div', { class: 'actions' }, ok ? h('button', { class: 'btn', type: 'button', 'data-key': 'trip-' + hs.id, onclick: () => ask(ctx, { at: key, text: 'Simulate three failed starts of ' + hs.label + '? New starts stop until the breaker recovers.', label: 'Trip the breaker', tone: 'danger', run: () => done(ctx, A.tripBreaker(hs.id), 'The breaker opened (simulated).') }) }, 'Trip the breaker')
      : h('button', { class: 'btn primary', type: 'button', 'data-key': 'reset-' + hs.id, onclick: () => ask(ctx, { at: key, text: 'Reset the breaker for ' + hs.label + '? Check that it starts from a terminal first. A real reset needs a step-up.', label: 'Reset the breaker', tone: 'primary', run: () => done(ctx, A.resetBreaker(hs.id), 'The breaker is closed (simulated).') }) }, 'Reset the breaker')) : null);
}

export function viewSecurity(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), sc = A.security(), offline = A.isOffline(), cur = whereAt(ctx, 'security');
  const held = Object.values(S.approvals).filter((a) => a.kind === 'action' && a.state === 'PENDING');
  const stopped = S.estop.engaged, previous = ctx.ui.securitySnapshot;
  const text = stopped ? 'Emergency stop engaged' : held.length ? (held.length === 1 ? '1 action is waiting for your decision' : held.length + ' actions are waiting for your decision') : sc.open ? 'New starts are blocked' : 'Nothing is blocked';
  const cards = new Map();
  const row = (title, detail, state, tone, href) => lrow(title, detail, state, tone, href, href === '#/security/' + ctx.route.id);
  const decisions = h('div', { class: 'sec-decisions' }, ...held.map((a) => {
    const item = attentionItem(ctx, { id: 'sec-' + a.id, kind: 'approval', group: 'Decide', mission_id: a.mission, project_id: a.project, since: a.created_at, reason: a.presented.what, ref: a.id });
    item.querySelector('a').href = '#/security/' + a.id;
    const decide = (kind, label) => h('button', { class: 'btn' + (kind === 'reject' ? ' danger' : ''), type: 'button', 'data-key': 'sec-' + kind + '-' + a.id,
      onclick: () => ask(ctx, { at: 'sec-decision-' + a.id, text: (kind === 'approve' ? 'Allow this action once? ' + a.presented.consequence : 'Deny this action? The execution ends and the mission is blocked.') + ' No Undo.', label, tone: kind === 'reject' ? 'danger' : 'primary', run: () => ctx.act(kind, a.id) }) }, label);
    const acts = item.querySelector('.actions'), open = acts.querySelector('a');
    if (isPhone()) { open.remove(); acts.append(decide('approve', 'Allow once'), decide('reject', 'Deny'), more('Decision', [['Open the decision', '#/security/' + a.id]])); } else acts.append(decide('approve', 'Allow once'), decide('reject', 'Deny'));
    item.append(h('p', { class: 'sec-detail' }, 'Ask me each time'), h('p', { class: 'sec-detail' }, a.presented.why), inline(ctx, 'sec-decision-' + a.id));
    const wrap = h('div', { class: 'sec-decision', 'data-approval': a.id }, item); cards.set(a.id, wrap); return wrap;
  }));
  // What a run may do is the same for every project; only the approval mode differs, so it is grouped by mode instead of repeated per project.
  const privs = A.privileges().map((r) => ({ r, tone: PRIV[r.state][0], word: r.state === 'asks' ? 'Ask me each time' : PRIV[r.state][1] })).sort((a, b) => TONE_RANK[a.tone] - TONE_RANK[b.tone]);
  const dflt = A.launch('default').mode, dfltTone = dflt === 'plan' ? 'paused' : 'attention', dfltWord = MODES.find(([id]) => id === dflt)[1];
  const modeGroups = [...MODES.map(([id, label]) => [id, label, id === 'plan' ? 'paused' : 'attention', S.projects.filter((p) => A.isOverride(p.id) && A.launch(p.id).mode === id)]), ['default', 'Default', dfltTone, S.projects.filter((p) => !A.isOverride(p.id))]].filter((g) => g[3].length);
  const names = (ps) => (ps.length > 6 ? [ps.slice(0, 6).map((p) => p.name).join(', '), h('details', { class: 'sec-names' }, h('summary', null, '+ ' + (ps.length - 6) + ' more'), ps.slice(6).map((p) => p.name).join(', '))] : [ps.map((p) => p.name).join(', ')]);
  const modes = modeGroups.map(([id, label, tone, ps]) => h('div', { class: 'sec-row sec-mode', 'data-key': 'sec-mode-' + id }, pill(tone, label), h('span', { class: 'sec-main' }, h('span', { class: 'sec-name' }, ps.length === 1 ? '1 project' : ps.length + ' projects', id === 'default' ? ' · ' : null, id === 'default' ? h('span', null, dfltWord) : null), h('span', { class: 'sec-detail' }, ...names(ps)))));
  const boundary = (b) => row(b.n + ' · ' + b.name, b.what, b.policy + ' / ' + b.physical, LAYER(b.physical), '#/security/' + b.id);
  const gaps = [['Execution isolation', sc.boundaries[0], 'Not confined', 'blocked'], ['Accounts and homes', sc.boundaries[4], 'Denied by policy only', 'attention'], ['Network', sc.boundaries[2], 'Not confined', 'blocked']].map(([title, b, state, tone]) => row(title, b.note, state, tone, '#/security/' + b.id));
  const events = A.log().filter((l) => ['hook', 'breaker'].includes(l.kind)).map((l) => {
    const hs = l.kind === 'breaker' ? S.harnesses.find((x) => l.text.includes(x.label)) : null;
    return { ...l, kind: l.kind === 'hook' ? 'Hook' : 'Spawn breaker', href: l.kind === 'hook' ? '#/extensions/h-1' : hs ? '#/security/bk-' + hs.id : null };
  });
  S.events.filter((e) => e.type.startsWith('approval.') || e.type.startsWith('core.estop')).forEach((e) => {
    const a = S.approvals[e.subject.id]; if (a && a.kind !== 'action') return;
    events.push({ at: e.at, kind: a ? 'Decision' : 'Emergency stop', text: a ? a.presented.what : e.type === 'core.estop_rearmed' ? 'Re-armed: new work can start again.' : 'Emergency stop engaged', state: a ? e.payload.to || 'PENDING' : null, href: a ? '#/security/' + a.id : null });
  });
  events.sort((a, b) => b.at - a.at);
  const log = (list) => h('ol', { class: 'sec-log ax-dim' }, ...list.map((e) => h('li', null, when(ctx, e.at), h('span', { class: 'sec-category' }, e.kind), h('span', { class: 'sec-event-text' }, e.text, e.state ? badge('approval', e.state) : null), e.href ? h('a', { class: 'btn quiet', href: e.href }, 'Evidence') : h('span', { class: 'sec-detail' }, 'Not recorded'))));
  const rearm = stopped ? h('a', { class: 'btn primary', href: '#/security/emergency', 'data-key': 'sec-rearm' }, 'Re-arm') : null;
  const warn = 'A started CLI still runs as your user. Policy does not physically confine it.', isoPill = pill('attention', 'Physical isolation is not built');
  const header = top('Security', [[text, stopped || held.length ? 'attention' : null]], null, ...(isPhone() ? [h('div', { class: 'ax-ledger sec-warning' }, isoPill, rearm), lede(warn)] : [h('div', { class: 'ax-ledger sec-warning' }, isoPill, h('span', null, warn), rearm)]));
  const posture = header.querySelector('.ax-sentence');

  const tally = [...new Map(privs.map((p) => [p.word, p.tone])).entries()].map(([word, tone]) => { const ps = privs.filter((p) => p.word === word); return row(ps.length + ' of ' + privs.length + ' actions', ps.flatMap((p, i) => (i ? [', ', p.r.label] : [p.r.label])), word, tone, '#/security/policy'); });
  const none = (t) => h('p', { class: 'sec-empty' }, t);
  const body = {
    overview: () => [
      sect('Needs a decision now', held.length, null, decisions, !held.length ? none('Held actions will appear here when a command needs your permission.') : null),
      sect('What Archeus may do', null, 'Held commands never auto-allow. Policy applies to every project.', dim(...tally), link('#/security/policy', 'See every action', 'ax-link')),
      sect('Boundaries', null, null, dim(...gaps), h('p', { class: 'sec-check' }, h('span', null, 'Last check'), ': ', h('span', null, 'Not recorded')), link('#/security/boundaries', 'See all ' + sc.boundaries.length + ' boundaries', 'ax-link')),
      sect('Recent security events', null, null, events.length ? log(events.slice(0, 5)) : none('Security events will appear here when an action is held, decided, or stopped.'), events.length > 5 ? link('#/security/activity', 'See all events', 'ax-link') : null)],
    policy: () => [
      sect('What Archeus may do', privs.length, 'Scope: every project. Source: Archeus policy. Read only here.', h('p', { class: 'sec-rule' }, 'Held commands never auto-allow.'), h('p', { class: 'sec-detail' }, 'Command policy applies inside an execution. Plan only never starts one.'),
        dim(...privs.map(({ r, tone, word }) => row(r.label, r.note, word, tone, r.link ? hrefFor(r.link.startsWith('sec-') ? 'boundary' : 'hook', r.link) : null)))),
      sect('Approval mode', null, 'The mode a new mission starts with. Each harness has its own default; a project can differ. No per-project command overrides are recorded.', modes.length ? dim(...modes) : none('No projects are recorded.'), link('#/accounts/launch', 'Change it in Launch settings', 'ax-link'))],
    boundaries: () => [
      sect('Boundaries', sc.boundaries.length, 'Where policy ends and physical confinement would have to begin.', dim(...sc.boundaries.map(boundary)), h('p', { class: 'sec-check' }, h('span', null, 'Last check'), ': ', h('span', null, 'Not recorded'))),
      sect('Policy boundary', null, null, h('ul', { class: 'sec-policy-notes' }, ...sc.policyList.map((t) => h('li', null, t)))),
      sect('Switches', sc.switches.length, null, dim(...sc.switches.map((x) => row(x.label, x.note, x.word, x.state === 'ok' ? 'ok' : 'paused'))))],
    activity: () => [
      sect('Security events', events.length, 'Every decision, hook and breaker change, newest first.', events.length ? log(ctx.ui.secAll ? events : events.slice(0, LOG_CAP)) : h('div', null, none('Security events will appear here when an action is held, decided, or stopped.'), link('#/security/policy', 'Review the policy', 'ax-link')), fold(ctx, 'secAll', events.length, LOG_CAP, 'sec-all'))],
    emergency: () => [
      sect('Emergency controls', null, null, pill(stopped ? 'blocked' : 'ok', stopped ? 'Engaged: nothing new starts' : 'Not stopped: accepts new work.'), h('div', { class: 'sec-controls' }, controlBody(ctx, false))),
      sect('Spawn breakers', S.harnesses.length, 'After three failed starts in ten minutes a harness stops starting new work until it recovers.', ...S.harnesses.map((hs) => breakerRow(ctx, A, S, hs)),
        h('p', { class: 'sec-detail' }, 'A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run.'))]
  }[cur]();
  const page = frame(cur, header, subnav('security', cur, 'Security sections', { policy: privs.length, boundaries: sc.boundaries.length, activity: events.length }, { overview: held.length ? ['attention', 'needs you'] : null, emergency: stopped ? ['blocked', 'engaged'] : null }), ...body);
  if (offline) {
    page.querySelectorAll('.ax-panel button').forEach((b) => { b.disabled = true; });
    page.querySelectorAll('.sec-decisions a').forEach((a) => { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); });
  }
  let mounted = false;
  ctx.mounts.push(() => {
    const motion = !reducedMotion() && !window.matchMedia('(prefers-reduced-motion: reduce)').matches && !offline;
    if (!mounted && previous && motion) {
      if (previous.sentence !== text) {
        const old = h('span', { class: 'sec-old-sentence ax-sentence', 'aria-hidden': 'true' }, previous.sentence); posture.before(old);
        old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: 'ease-out' }).finished.then(() => old.remove());
        posture.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' });
      }
      if (decisions.isConnected) previous.cards.forEach((c, id) => {
        if (cards.has(id) || !S.approvals[id] || S.approvals[id].state === 'PENDING') return;
        const ghost = c.node; ghost.setAttribute('aria-hidden', 'true'); ghost.inert = true; ghost.classList.add('sec-resolved'); decisions.append(ghost);
        ghost.animate([{ height: c.height + 'px', opacity: .6 }, { height: '0px', opacity: 0 }], { duration: 180, easing: 'ease-out' }).finished.then(() => ghost.remove());
      });
    }
    mounted = true;
    ctx.ui.securitySnapshot = { sentence: text, cards: new Map([...cards].map(([id, node]) => [id, { node: node.cloneNode(true), height: node.getBoundingClientRect().height }])) };
  });
  return page;
}

// ---------- Health ----------
const HEALTH_WORD = { ok: 'OK', attention: 'Needs attention', unknown: 'Unknown' }, HEALTH_RANK = { attention: 0, unknown: 1, ok: 2 };
const HEALTH_NONE = { attention: 'No check needs attention.', unknown: 'No check is unknown.', ok: 'No check is OK.' };
const STALE = 30 * 60000;
export function viewHealth(ctx) {
  const A = areasOf(ctx.sim), hl = A.health(), c = hl.counts, opened = (ctx.ui.hlOpen ||= {}), cur = whereAt(ctx, 'health'), clock = ctx.sim.state.clock;
  // What changed: the page remembers each check's last state, so a change is stated with its time.
  const seen = (ctx.ui.hlSeen ||= {}), ran = (ctx.ui.hlRan ||= {});
  hl.checks.forEach((k) => { const p = seen[k.id]; if (!p) seen[k.id] = { state: k.state, at: null, from: null }; else if (p.state !== k.state) seen[k.id] = { state: k.state, at: clock, from: p.state }; if (ran[k.id] == null) ran[k.id] = clock; });
  const last = Math.max(...hl.checks.map((k) => ran[k.id])), stale = clock - last > STALE;
  const runAgain = (ids, msg) => () => { ids.forEach((id) => { ran[id] = ctx.sim.state.clock; }); ctx.toast(msg); ctx.render(); };
  const parts = [c.attention && [c.attention + (c.attention === 1 ? ' check needs attention' : ' checks need attention'), 'attention'], c.unknown && [c.unknown + ' unknown', 'unknown']].filter(Boolean);
  const all = hl.checks.slice().sort((a, b) => HEALTH_RANK[a.state] - HEALTH_RANK[b.state]), shown = cur === 'all' ? all : all.filter((k) => k.state === cur);
  const rowOf = (k) => {
    const tone = TONE_OF_STATE[k.state], dflt = k.state !== 'ok', s = seen[k.id];
    return h('details', { class: 'hl-row', 'data-tone': tone, 'data-key': 'hl-' + k.id, open: (opened[k.id] ?? dflt) ? true : null, ontoggle: toggler(opened, k.id, dflt) },
      h('summary', null, pill(tone, HEALTH_WORD[k.state]), h('span', { class: 'hl-name' }, k.label), h('span', { class: 'hl-sum' }, k.summary), chev()),
      h('div', { class: 'hl-body' },
        k.cause ? h('div', null, h('h3', null, 'Cause'), h('p', null, k.cause)) : null,
        k.fix ? h('div', null, h('h3', null, 'Fix'), h('ol', { class: 'ax-steps' }, ...k.fix.map((t) => h('li', null, t)))) : h('p', { class: 'ax-note' }, 'Nothing to fix.'),
        h('p', { class: 'ax-note hl-meta' }, s.at != null ? h('span', { title: clockLabel(s.at, true) }, 'Changed ' + ago(ctx, s.at) + ' from ' + HEALTH_WORD[s.from]) : h('span', null, 'No change this session'), ' · ', h('span', { title: clockLabel(ran[k.id], true) }, 'Checked ' + ago(ctx, ran[k.id]))),
        h('div', { class: 'actions' }, k.action ? h('a', { class: 'btn' + (k.state === 'attention' ? ' primary' : ''), href: k.action.href }, k.action.label) : null, h('button', { class: 'btn', type: 'button', 'data-key': 'hl-run-' + k.id, onclick: runAgain([k.id], k.label + ' checked again (simulated).') }, 'Check again'),
          k.action && isPhone() ? more(k.label, [['Readings', hrefFor('check', k.id)]]) : h('a', { class: 'btn quiet', href: hrefFor('check', k.id) }, 'Readings'))));
  };
  const header = top('Health', parts.length ? parts : [['Every check is OK', 'ok']], null,
    h('div', { class: 'ax-ledger hl-run' }, stale ? pill('paused', 'Stale') : null, h('span', null, h('span', null, 'Last run'), ' ', h('time', { title: clockLabel(last, true) }, ago(ctx, last))), h('button', { class: 'btn', type: 'button', 'data-key': 'hl-run', onclick: runAgain(hl.checks.map((k) => k.id), 'Every check ran again (simulated).') }, 'Run all')));
  return frame(cur, header, subnav('health', cur, 'Health filter', { all: all.length, attention: c.attention, unknown: c.unknown, ok: c.ok }, { attention: c.attention ? ['attention', 'needs attention'] : null }),
    cur === 'all' ? h('p', { class: 'ax-ledger hl-note' }, 'Six checks, each read from records. A missing reading is unknown, never 0.') : h('p', { class: 'ax-ledger' }, 'Showing ' + shown.length + ' of ' + all.length),
    shown.length ? h('div', { class: 'ax-dim' }, ...shown.map(rowOf)) : h('div', null, h('p', { class: 'sec-empty' }, HEALTH_NONE[cur]), link('#/health/all', 'Show all checks', 'ax-link')),
    dnote('H15', 'Health is read from records, one live derivation (P21 D12). Each check has a cause and a fix when it is not OK.'));
}

// ---------- Usage ----------
// A ring is what is LEFT and empties as it is used; its tick is the 20% line. Small and fixed in size, so a row per account scales.
const USAGE_CAP = 12;
const forecastText = (f, clock) => (!f ? 'No forecast yet: not enough readings.' : f.flat || f.mins > 300 ? 'At this rate the 5 hour window does not run out.' : 'At this rate you reach the limit at ' + clockLabel(clock + f.mins * 60000) + ' (in ' + (f.mins < 1 ? 'under 1 min' : f.mins + ' min') + ').');
export function viewUsage(ctx) {
  const A = areasOf(ctx.sim), hs = A.harnesses(), hv = hvOf(ctx, hs), f = A.failover(), cur = whereAt(ctx, 'usage'), clock = ctx.sim.state.clock;
  const all = A.usage(), rows = hv ? all.filter((r) => r.harness === hv) : all;
  const low = all.filter((r) => ['low', 'critical', 'out'].includes(r.worst)), unk = all.filter((r) => r.worst === 'unknown');
  const live = [], capped = (list) => (ctx.ui.usAll ? list : list.slice(0, USAGE_CAP));
  const accRow = (r) => {
    const s = ringNode({ left: r.session.left, key: r.session.key, label: r.label + ', 5 hour window', live: r.id + ':session' }), w = ringNode({ left: r.week.left, key: r.week.key, label: r.label + ', week', live: r.id + ':week' });
    const fc = h('p', { class: 'r-note', 'data-ax': 'fc:' + r.id }, forecastText(forecast(r.hist), clock));
    live.push([r.id, s, w, fc]);
    const msg = r.worst === 'unknown' ? 'No reading yet: Core has never started this account. Unknown is not zero.' : r.worst === 'out' ? 'Limit reached. New work uses another account.' : r.worst === 'critical' ? 'Almost out. New work prefers another account.' : 'At or under your ' + f.pauseAt + '% line. New work prefers another account.';
    return h('div', { class: 'us-row', 'data-tone': TONE_OF_METER[r.worst], 'data-key': 'us-' + r.id },
      h('div', { class: 'us-who' }, h('a', { class: 'us-name', href: hrefFor('account', r.id) }, r.label), h('span', { class: 'r-note' }, harnessLabel(r.harness) + ' · ' + r.role), badge('account_health', r.state)),
      h('div', { class: 'us-m' }, s, h('span', { class: 'us-cap', 'aria-hidden': 'true' }, '5 hour window')),
      h('div', { class: 'us-m' }, w, h('span', { class: 'us-cap', 'aria-hidden': 'true' }, 'Week')),
      h('div', { class: 'us-st' }, pill(TONE_OF_METER[r.worst], METER_WORD[r.worst]), h('p', { class: 'r-note' }, r.resets || 'Reset time unknown'), r.worst === 'unknown' ? null : fc,
        r.worst === 'ok' ? null : h('p', { class: 'ac-msg', 'data-ax': 'umsg:' + r.id }, msg, ' ', link('#/accounts/failover' + hqs(hv), 'Failover rules', 'ax-link'))));
  };
  onTick(ctx, () => { const now = A.usage(); live.forEach(([id, s, w, fc]) => { const r = now.find((x) => x.id === id); patchRing(s, r.session.left, r.session.key); patchRing(w, r.week.left, r.week.key); const t = forecastText(forecast(r.hist), ctx.sim.state.clock); if (fc.textContent !== t) fc.textContent = t; }); });
  // A harness is shown when it has accounts, or when it is the one asked for. Not installed ones are named once, below.
  const groups = (hv ? hs.filter((x) => x.id === hv) : hs.filter((x) => x.accounts.length));
  const missing = hv ? [] : hs.filter((x) => !x.accounts.length);
  const group = (x, build) => h('section', { class: 'us-group', 'data-harness': x.id }, h('div', { class: 'ax-hh' }, h('h2', null, x.label), h('span', { class: 'ax-count' }, String(x.accounts.length)), h('span', { class: 'r-note' }, x.installed ? x.kind + ' · v' + x.version : x.kind + ' · not detected'), pill(x.tone, x.word)),
    x.accounts.length ? build(capped(x.accounts), x) : noHarness(x));
  const win = (title, key, detail) => sect(title, null, null, ...groups.map((x) => group(x, (list) => dim(...list.map((r) => lrow(r.label, detail(r), METER_WORD[r[key].key], TONE_OF_METER[r[key].key], hrefFor('account', r.id)))))));
  const body = {
    accounts: () => [
      h('div', { class: 'us-table' }, h('div', { class: 'us-head', 'aria-hidden': 'true' }, h('span', null, 'Account'), h('span', null, '5 hour window'), h('span', null, 'Week'), h('span', null, 'Headroom and reset')),
        ...groups.map((x) => group(x, (list) => h('div', { class: 'ax-dim' }, ...list.map(accRow))))),
      missing.length ? h('p', { class: 'ax-note' }, 'No readings: ', ...missing.flatMap((x, i) => (i ? [', ', link('#/usage?harness=' + x.id, x.label, 'ax-link')] : [link('#/usage?harness=' + x.id, x.label, 'ax-link')])), '.') : null,
      fold(ctx, 'usAll', Math.max(0, ...groups.map((x) => x.accounts.length)), USAGE_CAP, 'us-all'),
      h('div', { class: 'ax-legend' }, h('span', { class: 'lg' }, h('b', { class: 'tk', 'aria-hidden': 'true' }), 'The tick is the 20% line'), h('span', { class: 'lg', 'data-tone': 'unknown' }, h('i', { 'aria-hidden': 'true' }), 'Unknown, never 0'), link('#/accounts/failover' + hqs(hv), 'Failover rules', 'ax-link')),
      note('These are account percentages read about every 15 minutes, not the cost or tokens of one session.')],
    windows: () => [
      win('5 hour window', 'session', (r) => [r.session.left == null ? 'No reading yet' : r.session.left + '% left', ' · ', r.resets || 'Reset time unknown']),
      win('Week', 'week', (r) => [r.week.left == null ? 'No reading yet' : r.week.left + '% left', ' · ', 'Reset time not recorded']),
      fold(ctx, 'usAll', Math.max(0, ...groups.map((x) => x.accounts.length)), USAGE_CAP, 'us-all'),
      sect('Your line', null, null, lrow('New work waits at ' + f.pauseAt + '% left', 'Running work finishes; nothing new starts on an account at or under the line.', f.pauseOn ? 'On' : 'Off', f.pauseOn ? 'active' : 'paused', '#/accounts/failover' + hqs(hv)))],
    history: () => [
      sect('Last hour', null, 'The 5 hour window, as the share used. Read about every two minutes.', ...groups.map((x) => group(x, (list) => dim(...list.map((r) => h('div', { class: 'us-hist', 'data-key': 'uh-' + r.id }, h('div', { class: 'us-who' }, h('a', { class: 'us-name', href: hrefFor('account', r.id) }, r.label), h('span', { class: 'r-note' }, r.hist.length > 2 ? r.hist[0].s + '% to ' + r.hist[r.hist.length - 1].s + '% used' : 'No readings yet. Unknown is not zero.')), r.hist.length > 2 ? h('div', { class: 'us-sp' }, spark(r.hist, 240, 48)) : null)))))),
      fold(ctx, 'usAll', Math.max(0, ...groups.map((x) => x.accounts.length)), USAGE_CAP, 'us-all')]
  }[cur]();
  const parts = [low.length && [low.length === 1 ? '1 account is low' : low.length + ' accounts are low', 'attention'], unk.length && [unk.length + ' unknown', 'unknown']].filter(Boolean);
  return frame(cur, top('Usage', parts.length ? parts : [['Every account has room', 'ok']], 'How much of each account is left, per harness, read only from the existing usage reader. Archeus shows a number only when it can source it.'),
    [facet('usage', cur, hs, hv, (x) => (x ? x.accounts.length : all.length)), subnav('usage', cur, 'Usage views', { accounts: rows.length }, { accounts: low.length ? ['attention', 'low'] : null }, hqs(hv))], ...body,
    dnote('H03', 'Usage: a ring is what is left and empties as it is used; the tick is your 20% line. "20% weekly usage" is read here as 20% left (owner to confirm). Unknown stays unknown.'));
}

// ---------- Accounts and models ----------
const sel = (key, value, opts, on, label) => h('select', { class: 'ax-sel', 'aria-label': label, 'data-key': key, onchange: (e) => on(e.target.value) }, ...opts.map(([v, l]) => h('option', { value: v, selected: v === value ? true : null }, l)));
const LAUNCH_KEYS = ['harness', 'model', 'account', 'mode', 'parallel'];
const orderText = (x) => x.accounts.map((r) => r.label).join(' → ');
export function viewAccounts(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), st = S.accounts, hs = A.harnesses(), hv = hvOf(ctx, hs), f = A.failover(), models = S.models, opened = (ctx.ui.lnOpen ||= {}), cur = whereAt(ctx, 'accounts');
  const shown = hv ? hs.filter((x) => x.id === hv) : hs, nAcc = hs.reduce((n, x) => n + x.accounts.length, 0), nShownAcc = shown.reduce((n, x) => n + x.accounts.length, 0);
  const none = (t) => h('p', { class: 'sec-empty' }, t);
  // A switch that turns a rule off says so and offers Undo; turning one on needs no undo.
  const flip = (key, label) => () => { const was = f[key]; A.setFailover(key, !was); ctx.render(); if (was) ctx.toast(label + ' is off.', { action: { label: 'Undo', run: () => { A.setFailover(key, true); ctx.render(); } } }); };
  const fo = (key, label, sub, locked) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, label), h('span', { class: 'r-note' }, sub)), locked ? pill('ok', 'Always on') : sw({ on: f[key], label, key: 'fo-' + key, onclick: flip(key, label) }));
  const accountRow = (r, i, n) => h('div', { class: 'ax-row ax-acct', 'data-key': 'ac-' + r.id },
    h('span', { class: 'n', 'aria-hidden': 'true' }, String(i + 1)),
    h('a', { class: 'a-main', href: hrefFor('account', r.id) }, h('span', { class: 'r-name' }, r.label), h('span', { class: 'r-note' }, r.role + ' · ' + (r.session.left == null ? 'usage unknown' : r.session.left + '% of the session left'))),
    badge('account_health', r.state),
    h('span', { class: 'a-mv' }, h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' up', disabled: i === 0 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, -1), 'Moved up in the failover order.') }, '↑'), h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' down', disabled: i === n - 1 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, 1), 'Moved down in the failover order.') }, '↓')));
  const modelRow = (m) => { const d = A.defaultModel(m.harness) === m.id; return h('div', { class: 'ax-model', 'data-default': d ? 'true' : 'false', 'data-key': 'md-' + m.id }, h('a', { class: 'm-main', href: hrefFor('model', 'mdl-' + m.id) }, h('span', { class: 'r-name' }, m.label), h('span', { class: 'r-note' }, 'Tier ' + m.tier)), d ? pill('ok', 'Default') : h('button', { class: 'btn', type: 'button', onclick: () => done(ctx, A.setDefaultModel(m.id), m.label + ' is now the default (simulated).') }, 'Make default')); };

  // One launch row. `o.form` says which fields it edits: a project edits all five, a harness default everything but the harness, the account wide default only the harness.
  const launchRow = (o) => {
    const c = o.cfg, pv = A.preview(o.preview), har = S.harnesses.filter((x) => x.state !== 'MISSING'), id = o.id;
    const set = (k) => (v) => { done(ctx, o.set(k, v), 'Launch setting saved (simulated).'); };
    const field = (label, key, value, opts, name) => h('label', null, h('span', null, label), sel(key, value, opts, set(name), label + ' for ' + o.name));
    const fields = o.form === 'harness' ? [field('Starts with', 'ln-h-' + id, c.harness, har.map((x) => [x.id, x.label]), 'harness')] : [
      o.form === 'project' ? field('Harness', 'ln-h-' + id, c.harness, har.map((x) => [x.id, x.label]), 'harness') : null,
      field('Model', 'ln-m-' + id, c.model, models.filter((m) => m.harness === c.harness).map((m) => [m.id, m.label]), 'model'),
      field('Account', 'ln-a-' + id, c.account, [['auto', 'Automatic, by failover order'], ...st.filter((a) => a.harness === c.harness).map((a) => [a.id, a.label])], 'account'),
      field('Approvals', 'ln-d-' + id, c.mode, MODES, 'mode'), field('Runs at once', 'ln-p-' + id, String(c.parallel), [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']], 'parallel')].filter(Boolean);
    return h('details', { class: 'ln-row', 'data-tone': pv.tone, 'data-key': 'ln-' + id, open: opened[id] ? true : null, ontoggle: toggler(opened, id, false) },
      h('summary', null, h('span', { class: 'ln-name' }, o.name), pill(pv.tone, pv.tone === 'ok' ? 'Can start' : pv.tone === 'blocked' ? 'Cannot start' : 'Waits'), chev(),
        h('span', { class: 'ln-prev' }, h('b', null, 'Next mission: '), harnessLabel(pv.harness) + ' · ' + pv.model + (pv.account ? ' · ' + pv.account : ''))),
      h('div', { class: 'ln-body' }, h('p', { class: 'ax-note' }, pv.note), h('div', { class: 'ax-form' }, ...fields, o.form === 'harness' ? null : h('p', { class: 'ax-note' }, 'Isolation: required. It cannot be switched off here.')), o.actions || null));
  };
  const project = (p) => { const id = p.id, reset = () => { const was = { ...A.launch(id) }; delete opened[id]; A.resetLaunch(id); ctx.render(); ctx.toast('Back to the default (simulated).', { action: { label: 'Undo', run: () => { A.overrideLaunch(id); LAUNCH_KEYS.forEach((k) => A.setLaunch(id, k, was[k])); opened[id] = true; ctx.render(); } } }); };
    return launchRow({ id, name: p.name, cfg: A.launch(id), preview: id, form: 'project', set: (k, v) => A.setLaunch(id, k, v), actions: h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', 'data-key': 'ln-reset-' + id, onclick: reset }, 'Use the default'), h('a', { class: 'ax-link', href: hrefFor('project', 'prj-' + id) }, 'Open project')) }); };
  const overrides = S.projects.filter((p) => A.isOverride(p.id)), inheriting = S.projects.filter((p) => !A.isOverride(p.id));

  const body = {
    accounts: () => [h('div', { class: 'ax-hgrid' }, ...shown.map((x) => hsect(x, x.accounts.length, x.installed && x.accounts.length ? 'In failover order within ' + x.label + '. ' + (x.next ? x.next.label + ' takes the next ' + x.label + ' mission.' : 'No account can take new work.') : null,
        !x.installed ? noHarness(x) : x.accounts.length ? dim(...x.accounts.map((r, i) => accountRow(r, i, x.accounts.length))) : none('No account is signed in for ' + x.label + '. Sign in with its own CLI; Archeus never reads the token.')))),
      h('p', { class: 'ax-note' }, 'A subscription login belongs to you. Archeus never reads, stores, copies, injects or relays the token.')],
    models: () => [h('div', { class: 'ax-hgrid' }, ...shown.map((x) => hsect(x, x.models.length, x.installed && x.models.length ? 'The default is what a new ' + x.label + ' mission asks for. Saved as you choose.' : null,
        !x.installed ? noHarness(x) : x.models.length ? dim(...x.models.map(modelRow)) : none('No model is listed for ' + x.label + '.')))),
      h('p', { class: 'ax-note' }, 'This is the model Archeus asks for, not proof of which model the provider served.')],
    failover: () => [
      sect('Order within each harness', null, 'An order only makes sense inside one harness: a run never fails over from one harness to another without asking.', dim(...shown.map((x) => h('div', { class: 'ax-row', 'data-key': 'fo-h-' + x.id }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, x.label), h('span', { class: 'r-note' }, x.accounts.length ? orderText(x) : x.installed ? 'No account is signed in.' : 'Not installed.')),
        x.accounts.length ? link('#/accounts' + hqs(x.id), 'Change order', 'ax-link') : pill(x.tone, x.word))))),
      sect('Rules for every harness', null, 'What happens when an account runs low or out. Each switch saves as you flip it.', dim(
        fo('handoff', 'Hand off a run when its account is limited', 'The run writes a checkpoint and continues on the next account of the same harness.'),
        h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, 'New work waits when the week is low'), h('span', { class: 'r-note' }, 'Your line. Running work finishes; nothing new starts on that account.')), h('span', { class: 'r-ctl' }, f.pauseOn ? sel('fo-at', String(f.pauseAt), [['10', '10% left'], ['20', '20% left'], ['30', '30% left']], (v) => { A.setFailover('pauseAt', Number(v)); ctx.render(); }, 'Line, percent left') : null, sw({ on: f.pauseOn, label: 'New work waits when the week is low', key: 'fo-pauseOn', onclick: flip('pauseOn', 'New work waits when the week is low') }))),
        fo('askHarness', 'Ask before switching to another harness', 'A move from Claude Code to Codex is a card you confirm.'),
        fo('never', 'Never run without isolation', 'There is no unisolated fallback, whatever else fails.', true)))],
    launch: () => [
      sect('Launch settings', null, 'A project starts with the default harness and that harness’s defaults. Only a project that differs has its own row. Saved as you choose.',
        dim(launchRow({ id: 'default', name: 'Default', cfg: A.launch('default'), preview: 'default', form: 'harness', set: (k, v) => A.setLaunch('default', k, v) }))),
      h('div', { class: 'ax-hgrid' }, ...shown.map((x) => { const mine = overrides.filter((p) => A.launch(p.id).harness === x.id);
        return hsect(x, mine.length, x.installed ? 'Defaults for ' + x.label + ', and the projects that use ' + x.label + ' differently.' : null, !x.installed ? noHarness(x) : dim(
          launchRow({ id: 'hd-' + x.id, name: 'Defaults for ' + x.label, cfg: A.harnessDefault(x.id), preview: A.harnessDefault(x.id), form: 'harness-default', set: (k, v) => A.setHarnessDefault(x.id, k, v) }), ...mine.map(project))); })),
      inheriting.length ? sel('ln-add', '', [['', 'Give a project its own settings'], ...inheriting.map((p) => [p.id, p.name])], (v) => { if (v) { opened[v] = true; done(ctx, A.overrideLaunch(v), 'This project now has its own launch settings (simulated).'); } }, 'Project that gets its own settings') : null]
  }[cur]();
  const ceiling = hs.reduce((n, x) => n + x.ceiling, 0), blocked = hs.filter((x) => x.installed && x.tone === 'blocked').length, installed = hs.filter((x) => x.installed).length;
  const parts = [[installed === 1 ? '1 harness' : installed + ' harnesses'], [nAcc === 1 ? '1 account' : nAcc + ' accounts'], ceiling ? [ceiling + ' near the ceiling', 'attention'] : null, blocked ? [blocked === 1 ? '1 cannot take work' : blocked + ' cannot take work', 'blocked'] : null].filter(Boolean);
  return frame(cur, top('Accounts', parts, 'Each harness has its own accounts, models, failover order and launch settings. A subscription login belongs to you.'),
    [facet('accounts', cur, hs, hv, (x) => (x ? x.accounts.length : nAcc)), subnav('accounts', cur, 'Account sections', { accounts: nShownAcc, models: shown.reduce((n, x) => n + x.models.length, 0) }, {}, hqs(hv))], ...body,
    dnote('H10', 'Accounts and models: each harness has its own accounts in a failover order, its own models with one default, and its own launch defaults; a project can differ. No token is shown or handled.'));
}

// ---------- Extensions: hooks, MCP servers, agents, automations, clients ----------
// One strict row for every kind: [name, harness tags and what it is] [status, only when it says more than On or Off] [last activity] [a switch or one action].
// The kinds are tabs, one shown at a time; what needs you sits above them as the same rows with the action on the right.
// The harness is a facet of every list (?harness=codex), and a kind appears only if an installed harness supports it.
const TONE_OF_CLS = { needs_you: 'attention', blocked: 'blocked', failed: 'blocked', active: 'active', done: 'ok', neutral: 'ok', paused: 'paused', inactive: 'paused' };
const roleStat = (machine, state) => { const p = present(machine, state); return [TONE_OF_CLS[p.cls] || 'unknown', p.label]; };
const KIND_CAP = { hooks: 'hooks', mcp: 'mcp', agents: 'subagents' };
function xrow(o) {
  return h('div', { class: 'ax-xrow', 'data-key': o.key, 'data-q': (o.name + ' ' + o.does).toLowerCase(), 'data-nost': o.stat ? null : 'true' },
    h('a', { class: 'x-main', href: o.href }, h('span', { class: 'r-name' }, o.name, ...(o.tags || []).map(htag)), h('span', { class: 'x-does' }, o.does, ...(o.extra ? [' · ', ...o.extra] : [])),
      o.stat ? mark(o.stat[0], o.stat[1]) : null,
      h('span', { class: 'x-last', title: o.exact || null }, h('span', { class: 'vh' }, o.lastLabel + ' '), o.last)),
    h('span', { class: 'x-ctl' }, o.control || null), o.below || null);
}
const needRow = (o) => h('div', { class: 'ax-xrow ax-need', 'data-key': 'need-' + o.id },
  h('a', { class: 'x-main', href: o.href }, h('span', { class: 'r-name' }, o.name, ...(o.tags || []).map(htag)), h('span', { class: 'x-does' }, o.kind, ' · ', o.why)), h('span', { class: 'x-ctl' }, o.action));
const needsYou = (n) => (n === 1 ? '1 needs you' : n + ' need you');
export function viewExtensions(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), clock = S.clock, ui = ctx.ui, hs = A.harnesses(), hv = hvOf(ctx, hs), hn = hs.find((x) => x.id === hv);
  const when = (t) => whenShort(t, clock, clockLabel);
  const hookList = A.hooks(), mcpList = A.mcp(), agentList = A.agents(), autoList = S.automations, devList = S.devices;
  const agentState = agentList.map((x) => A.agentStatus(x));
  const waits = (a) => a.state === 'SUSPENDED' || a.state === 'PENDING_APPROVAL';
  const review = Object.values(S.reviews).find((r) => r.state === 'PENDING' || r.state === 'IN_REVIEW');
  const act = (a, label, key) => h('button', { class: 'btn primary', type: 'button', 'data-key': key, onclick: () => ctx.act('enable', a.id) }, label);
  // Automations and paired clients belong to Archeus, not to one harness: they show under every harness.
  const inFacet = (x) => !hv || !x.harnesses || x.harnesses.includes(hv);
  const tagsOf = (x) => (x.harnesses && (hv ? [hv] : x.harnesses)) || [];

  const needsAll = [
    ...autoList.filter(waits).map((a) => ({ id: a.id, name: a.name, kind: 'Automation', why: roleStat('automation', a.state)[1], href: hrefFor('automation', a.id), action: act(a, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve', 'need-act-' + a.id) })),
    ...agentList.filter((x, i) => agentState[i].key === 'ready').map((x) => ({ id: x.id, name: x.name, tags: x.harnesses, kind: 'Agent', why: 'Result waits', href: hrefFor('agent', x.id), action: h('a', { class: 'btn primary', href: review ? '#/work/' + review.mission : hrefFor('agent', x.id), 'data-key': 'need-act-' + x.id }, 'Open review') }))
  ];
  const needs = needsAll.filter((n) => !n.tags || !hv || n.tags.includes(hv));
  const needIn = { agents: needs.filter((n) => n.kind === 'Agent').length, automations: needs.filter((n) => n.kind === 'Automation').length };
  const off = [...hookList, ...mcpList, ...agentList].filter((x) => !x.enabled).length;

  // A switch-off can be taken back from the toast; a switch-on cannot need it.
  const flipped = (toggle, id, onMsg, offMsg, hid) => {
    const r = toggle(id, hid);
    if (!r.ok) { done(ctx, r); return; }
    ctx.toast(r.on ? onMsg : offMsg, r.on ? null : { action: { label: 'Undo', run: () => { toggle(id, hid); ctx.render(); } } });
    ctx.render();
  };
  const hookRow = (x) => {
    const key = 'row:' + x.id, flip = () => flipped(A.toggleHook, x.id, 'Hook switched on (simulated).', 'Hook switched off (simulated).');
    return xrow({ key: 'x-' + x.id, href: hrefFor('hook', x.id), name: x.name, tags: tagsOf(x), does: x.event + ' · ' + x.matcher, stat: x.locked ? ['ok', 'Built in'] : null, lastLabel: 'Last run', last: when(x.last), exact: whenExact(x.last, clockLabel),
      control: sw({ on: x.enabled, disabled: x.locked, label: x.name, key: 'sw-' + x.id, onclick: () => (x.enabled && x.sensitive ? ask(ctx, { at: key, text: 'Switch off "' + x.name + '"? An execution can then do this without asking you.', label: 'Switch off', tone: 'danger', run: flip }) : flip()) }), below: inline(ctx, key) });
  };
  // A server shared by two harnesses has one status each. The switch acts on the harness being looked at, or on all of them under All.
  const mcpRow = (x) => {
    const st = A.mcpStatus(x, clock), ks = Object.keys(x.on), differs = ks.length > 1 && new Set(ks.map((k) => x.on[k])).size > 1;
    const per = differs ? ks.flatMap((k, i) => [i ? ', ' : null, h('span', null, (x.on[k] ? 'On in ' : 'Off in ') + harnessShort(k))]).filter(Boolean) : null;
    const target = hv && x.on[hv] != null ? hv : undefined, on = target ? x.on[target] : x.enabled;
    return xrow({ key: 'x-' + x.id, href: hrefFor('mcp', x.id), name: x.name, tags: tagsOf(x), does: x.transport + ' · ' + (x.tools.length ? x.tools.length + (x.tools.length === 1 ? ' tool' : ' tools') : 'tools not known') + (st === 'CONNECTED' ? ' · ' + x.calls + ' calls' : ''), extra: per,
      stat: x.unchecked ? ['unknown', 'Not checked'] : st === 'CONNECTING' ? ['active', 'Connecting'] : null, lastLabel: 'Last call', last: when(x.last), exact: whenExact(x.last, clockLabel),
      control: sw({ on, disabled: x.unchecked, label: x.name + (target ? ' in ' + harnessLabel(target) : ''), key: 'sw-' + x.id, onclick: () => flipped(A.toggleMcp, x.id, 'Connecting (simulated).', 'Switched off (simulated).', target) }) });
  };
  const agentRow = (x) => {
    const s = agentState[agentList.indexOf(x)], live = s.key === 'working' || s.key === 'ready';
    return xrow({ key: 'x-' + x.id, href: hrefFor('agent', x.id), name: x.name, tags: tagsOf(x), does: live ? s.text : x.role, stat: s.key === 'working' ? ['active', 'Working'] : s.key === 'ready' ? ['attention', 'Result waits'] : null, lastLabel: 'Last run', last: when(x.last), exact: whenExact(x.last, clockLabel),
      control: sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => flipped(A.toggleAgent, x.id, 'Agent switched on (simulated).', 'Agent switched off (simulated).') }) });
  };
  const autoRow = (a) => xrow({ key: 'x-' + a.id, href: hrefFor('automation', a.id), name: a.name, does: a.note || a.trigger, stat: roleStat('automation', a.state), lastLabel: 'Next run', last: a.next_run || 'Not scheduled',
    control: waits(a) ? act(a, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve', 'act-' + a.id) : null });
  const clientRow = (d) => xrow({ key: 'x-' + d.id, href: hrefFor('device', d.id), name: d.name, does: 'Paired client', stat: roleStat('device', d.state), lastLabel: 'Last seen', last: d.state === 'ACTIVE' ? 'Now' : 'Not recorded' });
  const KINDS = { hooks: [hookList, hookRow, 'Last run'], mcp: [mcpList, mcpRow, 'Last call'], agents: [agentList, agentRow, 'Last run'], automations: [autoList, autoRow, 'Next run'], clients: [devList, clientRow, 'Last seen'] };

  // A kind is a tab only when some installed harness supports it.
  const tabsShown = EXT_TABS.filter(([id]) => !KIND_CAP[id] || hs.some((x) => x.installed && x.caps.includes(KIND_CAP[id])));
  if (ctx.route.id && ui.extSeen !== ctx.route.id) ui.extTab = tabOf(ctx.route.id) || ui.extTab;
  ui.extSeen = ctx.route.id;
  const want = ui.extTab || (tabsShown.find(([id]) => needIn[id]) || tabsShown[0])[0], tab = tabsShown.some(([id]) => id === want) ? want : tabsShown[0][0];
  const [allItems, build, lastHead] = KINDS[tab];
  const items = allItems.filter(inFacet), cap = KIND_CAP[tab], unsupported = hn && hn.installed && cap && !hn.caps.includes(cap);
  ui.extQ = ui.extQ || {};
  const q = ui.extQ[tab] || '';
  const countIn = (id) => KINDS[id][0].filter(inFacet).length;

  const pick = (id) => { ui.extTab = id; ctx.render(); };
  const tabs = edgeRow(h('div', { class: 'tabs ext-tabs', role: 'tablist', 'aria-label': 'Extension types' }, ...tabsShown.map(([id, label]) => h('button', { class: 'tab', type: 'button', role: 'tab', id: 'xtab-' + id, 'data-key': 'xtab-' + id, 'aria-selected': id === tab ? 'true' : 'false', 'aria-controls': 'ext-panel', tabindex: id === tab ? '0' : '-1', onclick: () => pick(id),
    onkeydown: (e) => {
      const i = tabsShown.findIndex(([x]) => x === id), n = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabsShown.length - 1 }[e.key];
      if (n == null) return;
      e.preventDefault(); const to = tabsShown[(n + tabsShown.length) % tabsShown.length][0];
      document.querySelector('[data-key="xtab-' + to + '"]').focus(); pick(to);
    } },
    label, h('span', { class: 'ax-count' }, String(countIn(id))), needIn[id] ? h('span', { class: 'x-dot', 'data-tone': 'attention' }, h('span', { class: 'vh' }, 'needs you')) : null))));

  const rows = items.map(build), anyStat = rows.some((r) => !r.dataset.nost), none = h('p', { class: 'x-empty', hidden: true }, 'No extension matches.', ' ', h('button', { class: 'btn quiet', type: 'button', 'data-key': 'ext-clear', onclick: () => { ui.extQ[tab] = ''; ctx.render(); } }, 'Clear search'));
  const filter = (text) => { let shown = 0; rows.forEach((r) => { const ok = matches(text, r.dataset.q); r.hidden = !ok; if (ok) shown++; }); none.hidden = shown > 0 || !text.trim(); };
  filter(q);
  const search = items.length > 12 ? h('input', { class: 'ext-search', type: 'search', name: 'ext-q', 'data-key': 'ext-q', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Search extensions', placeholder: 'Search extensions…', value: q, oninput: (e) => { ui.extQ[tab] = e.target.value; filter(e.target.value); } }) : null;

  // What the list says when it is empty for a reason: the harness does not support the kind, or is not installed, or simply has none.
  const supporters = hs.filter((x) => x.installed && cap && x.caps.includes(cap));
  const emptyLine = hn && !hn.installed ? h('div', null, h('p', { class: 'x-empty' }, hn.label + ' is not installed on this machine. Nothing is listed until it is detected.'), h('p', { class: 'x-empty' }, link('#/health', 'Run Health after installing', 'ax-link')))
    : unsupported ? h('p', { class: 'x-empty x-muted' }, 'Not supported by ' + hn.label + '.', ' ', supporters.length ? h('span', null, 'Available in ', ...supporters.flatMap((x, i) => (i ? [', ', link('#/extensions?harness=' + x.id, x.label, 'ax-link')] : [link('#/extensions?harness=' + x.id, x.label, 'ax-link')])), '.') : null)
    : items.length ? null : h('p', { class: 'x-empty' }, 'Nothing is listed here.');
  const agnostic = !cap && hv ? h('p', { class: 'ax-note' }, 'Not tied to one harness: these apply to every harness.') : null;

  const side = h('aside', { class: 'ext-side', 'aria-label': 'Harnesses' }, h('h2', null, 'Harnesses', h('span', { class: 'ax-count' }, String(hs.length))),
    h('div', { class: 'ax-dim' }, ...hs.map((x) => h('a', { class: 'ext-h', href: '#/extensions' + hqs(x.id), 'data-key': 'xh-' + x.id, 'aria-current': x.id === hv ? 'true' : null },
      h('span', { class: 'ext-h-top' }, h('span', { class: 'r-name' }, x.label), pill(x.tone, x.word)),
      h('span', { class: 'r-note' }, x.installed ? x.kind + ' · v' + x.version : 'Not detected'),
      h('span', { class: 'ext-h-caps' }, ...x.caps.map((c) => h('span', { class: 'ext-cap' }, CAP_LABEL[c]))))),
    h('p', { class: 'ax-note' }, 'A kind of extension is offered only where a harness supports it.')));

  const parts = [needsAll.length ? [needsYou(needsAll.length), 'attention'] : ['Nothing needs you', 'ok'], off ? [off + ' off'] : null].filter(Boolean);
  return h('div', { class: 'ax-page' }, h('div', { class: 'view ax-view' },
    top('Extensions', parts, 'What can act before, after and beside a run, in each harness. Each row says its harness, its status and when it last ran; a switch changes it for the next run.'),
    h('div', { class: 'ext-grid' }, h('div', { class: 'ext-col' },
      needs.length ? h('section', { class: 'ext-needs', 'aria-label': 'Needs you' }, h('h2', null, 'Needs you', h('span', { class: 'ax-count' }, String(needs.length))), h('div', { class: 'ax-dim' }, ...needs.map(needRow))) : null,
      facet('extensions', '', hs, hv, (x) => (x ? (KINDS[tab][0].filter((i) => !i.harnesses || i.harnesses.includes(x.id)).length) : KINDS[tab][0].length)),
      h('div', { class: 'ext-bar' }, tabs, search),
      h('div', { class: 'ext-list' + (anyStat ? '' : ' nostat'), role: 'tabpanel', id: 'ext-panel', 'aria-labelledby': 'xtab-' + tab },
        agnostic, items.length && !unsupported ? h('div', { class: 'x-hd', 'aria-hidden': 'true' }, h('span', null), anyStat ? h('span', null, 'Status') : null, h('span', null, lastHead), h('span', null)) : null,
        h('div', { class: 'ax-dim' }, ...(unsupported ? [] : rows), none), emptyLine)), side),
    dnote('H09', 'Hooks, MCP servers and agents managers: status, last run, enable and disable, and a details sheet for each. Automations and clients are the other Control lists.')));
}

// ---------- what S3 adds to Now and Work ----------
function digestPanel(ctx, A) {
  const S = A.S(), range = ctx.ui.digestRange || 'since', since = range === 'since' ? A.cursor() : -120 * 60000;
  const d = A.digest(since), shown = d.items.slice(0, 8);
  const sentence = d.items.length ? [d.counts.missions && d.counts.missions + (d.counts.missions === 1 ? ' mission changed' : ' missions changed'), d.counts.decisions && d.counts.decisions + (d.counts.decisions === 1 ? ' decision asked' : ' decisions asked'), d.counts.reviews && d.counts.reviews + (d.counts.reviews === 1 ? ' result to review' : ' results to review'), d.counts.other && d.counts.other + ' other'].filter(Boolean).join(' · ') : 'Nothing has changed.';
  return h('section', { class: 'panel ax-digest' }, h('h2', null, h('span', { class: 'gt' }, 'Since you last looked'), h('span', { class: 'n' }, range === 'since' ? 'since ' + clockLabel(since) : 'today, since ' + clockLabel(since))),
    h('div', { class: 'body' }, h('div', { class: 'chips', role: 'group', 'aria-label': 'Digest range' }, ...[['since', 'Since you last looked'], ['today', 'Today']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': range === id ? 'true' : 'false', onclick: () => { ctx.ui.digestRange = id; ctx.render(); } }, l))),
      h('p', { class: 'dg-sum' }, sentence),
      shown.length ? h('ul', { class: 'ax-dig' }, ...shown.map((i) => h('li', null, h('a', { href: i.href }, h('span', { class: 'g', 'data-tone': i.tone, 'aria-hidden': 'true' }, glyph(i.tone)), h('span', { class: 'dg-x' }, i.text), h('span', { class: 'dg-t' }, clockLabel(i.at)))))) : null,
      d.items.length > shown.length ? note((d.items.length - shown.length) + ' more are in Replay and Work.') : null,
      range === 'since' ? h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', disabled: d.items.length ? null : true, onclick: () => { A.acknowledge(); ctx.toast('Marked as seen.'); ctx.render(); } }, 'Mark as seen')) : null, dnote('E18', 'The digest groups what changed since your cursor; marking it seen moves the cursor. It reads the event log; nothing is counted twice.')));
}
function pinnedPanel(ctx, A) {
  const S = A.S(), pins = A.X.pins, ms = pins.filter((id) => S.missions[id]), others = pins.filter((id) => !S.missions[id]);
  const it = (id) => { const i = S.ideas.find((x) => x.id === id); if (i) return entity({ kind: 'idea', id, label: i.title, note: projName(ctx.sim, i.project) }); const p = S.projects.find((x) => 'prj-' + x.id === id); return p ? entity({ kind: 'project', id, label: p.name, note: p.note }) : null; };
  return h('section', { class: 'panel ax-pinned' }, h('h2', null, h('span', { class: 'gt' }, 'Pinned'), h('span', { class: 'n' }, String(pins.length))),
    pins.length ? h('div', { class: 'stack' }, ...ms.map((id) => missionRow(ctx, S.missions[id], 'work')), ...others.map(it).filter(Boolean)) : h('div', { class: 'empty art' }, illustration('first'), h('p', null, 'Nothing is pinned. Pin a mission or an idea from its details and it stays here.')));
}
function ideasPanel(ctx, A) {
  const S = A.S();
  return h('section', { class: 'panel ax-ideas' }, h('h2', null, h('span', { class: 'gt' }, 'Ideas'), h('span', { class: 'n' }, String(S.ideas.length))),
    h('div', { class: 'stack' }, ...S.ideas.map((i) => h('a', { class: 'ax-idea', href: hrefFor('idea', i.id), 'data-key': 'id-' + i.id }, h('span', { class: 'i-main' }, h('span', { class: 'r-name' }, i.title), h('span', { class: 'r-note' }, projName(ctx.sim, i.project))), ideaPath(i.state, true), badge('idea', i.state)))),
    dnote('E17', 'Every idea shows where it is on the path from Captured to Learned. An idea is not a commitment.'));
}

// offline: the client lost Core and shows what it kept, with the age on it
function staleRow(ctx, m) {
  return h('a', { class: 'mrow ax-stale', href: '#/work/' + m.id }, h('span', { class: 't' }, badge('mission', m.state), h('span', { class: 'name' }, m.title)), h('span', { class: 'm' }, projName(ctx.sim, m.project) + ' · ' + m.branch), h('span', { class: 'sp' }, spineRow(m.state, m.held_from)));
}
export function offlineBanner(ctx, A) {
  return h('div', { class: 'ax-offline', role: 'status' }, h('span', { class: 'g', 'aria-hidden': 'true' }, icon('offline', 20)), h('div', { class: 'of-t' }, h('b', null, 'Offline: last seen ' + clockLabel(A.offlineAt())), h('span', null, 'Showing what this client kept. Decisions are read only until Core is reachable.')), h('button', { class: 'btn primary', type: 'button', onclick: () => { A.reconnect(); ctx.toast('Reconnected.'); ctx.render(); } }, 'Reconnect'));
}
const GROUPS = [['Active', ['active', 'verifying', 'reviewing']], ['Planning', ['planning', 'approved']], ['Blocked or failed', ['blocked', 'failed']], ['Paused', ['paused']], ['Done', ['done']]];
function offlineList(ctx, A) {
  const S = A.S(), ms = Object.values(S.missions);
  return GROUPS.map(([t, cls]) => [t, ms.filter((m) => cls.includes(present('mission', m.state).cls))]).filter((g) => g[1].length).map(([t, items]) => h('section', { class: 'panel' }, h('h2', null, h('span', { class: 'gt' }, t), h('span', { class: 'n' }, String(items.length))), h('div', { class: 'stack' }, ...items.map((m) => staleRow(ctx, m)))));
}
function offlineDecide(ctx, A, k) {
  if (!k.decide.length && !k.review.length) return h('section', { class: 'panel' }, h('h2', null, h('span', { class: 'gt' }, 'Needs you')), h('p', { class: 'empty' }, 'Nothing was waiting for a decision when this was kept.'));
  const S = A.S();
  return h('section', { class: 'panel' }, h('h2', null, h('span', { class: 'gt' }, 'Needs you'), h('span', { class: 'n' }, String(k.decide.length + k.review.length) + ' · read only')), h('div', { class: 'stack' },
    ...k.decide.map((a) => h('a', { class: 'card band ax-stale', href: '#/work/' + a.id }, h('div', { class: 'top' }, badge('mission', 'APPROVAL_REQUIRED'), h('span', { class: 'why' }, projName(ctx.sim, a.project))), h('p', { class: 'ttl' }, a.presented.what), h('span', { class: 'ax-lock' }, 'Read only: decide when Core is back.'))),
    ...k.review.map((m) => h('a', { class: 'card band ax-stale', href: '#/work/' + m.id }, h('div', { class: 'top' }, badge('mission', m.state), h('span', { class: 'why' }, projName(ctx.sim, m.project))), h('p', { class: 'ttl' }, 'Verified, waiting for your review: ' + m.title), h('span', { class: 'ax-lock' }, 'Read only: accept when Core is back.')))));
}
function offlinePage(ctx, A, name) {
  const S = A.S(), k = keptSummary(S), title = { now: 'Now', work: 'Work' }[name];
  return h('div', { class: 'view ax-offline-page' }, offlineBanner(ctx, A),
    name === 'now' ? h('div', { class: 'now-hero' }, h('p', { class: 'state-sentence ax-stale-sentence' }, 'As of ' + clockLabel(A.offlineAt()) + ': ' + k.sentence), h('p', { class: 'sub2' }, 'This is the last read. It is not live.'), dnote('E12', 'Offline Now: kept missions with their spine drawn outlined, the time it was last seen, and Decide rows read only (D11).')) : h('header', { class: 'page-head', style: 'padding:0' }, h('div', null, h('h1', null, title), h('p', { class: 'sub' }, 'Offline: last seen ' + clockLabel(A.offlineAt())))),
    offlineDecide(ctx, A, k), ...offlineList(ctx, A));
}

export function decorate(ctx, content) {
  const A = areasOf(ctx.sim), name = ctx.route.name;
  if (A.isOffline() && ['now', 'work'].includes(name)) return offlinePage(ctx, A, name);
  if (A.isOffline() && !['terminal'].includes(name)) { const v = content.querySelector('.view') || content; v.prepend(offlineBanner(ctx, A)); return content; }
  if (name === 'now') { content.append(digestPanel(ctx, A)); return content; }
  if (name === 'work') {
    const view = content.querySelector('.view'), ideas = [...view.querySelectorAll('.panel')].find((p) => p.querySelector('h2') && /^Ideas/.test(p.querySelector('h2').textContent));
    if (ideas) ideas.replaceWith(pinnedPanel(ctx, A), ideasPanel(ctx, A));
  }
  return content;
}
