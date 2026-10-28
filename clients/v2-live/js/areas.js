// S3 areas: Security, Health, Usage, Accounts and models, Hooks / MCP / agents (Extensions), plus what S3 adds to Now and Work
// (digest, pins, idea path) and the offline view. Everything is SIMULATED; each page says so in its header.
import { h } from './dom.js';
import { reducedMotion } from './store.js';
import { icon, glyph } from './icons.js';
import { illustration } from './illustrations.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { head, dnote, missionRow, badge, projName, attentionItem, controlBody } from './views.js';
import { spineRow } from './spine.js';
import { ask, ideaPath } from './inspectors.js';
import { done, MCP_TONE } from './inspectors2.js';
import { areasOf, breakerView, waitLabel, keptSummary, harnessLabel, METER_WORD } from './areas-model.js';
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
    h('button', { class: 'btn ' + (c.tone === 'danger' ? 'danger' : 'primary'), type: 'button', onclick: () => { ctx.ui.confirm = null; c.run(); } }, c.label), h('button', { class: 'btn', type: 'button', onclick: () => { ctx.ui.confirm = null; ctx.render(); } }, 'Back')));
}

// ---------- shared page pieces ----------
// The page opens with its answer: a serif state sentence (the colour only on the part that is a state, always with its words) and one line of ledger under it.
const sentence = (parts) => parts.flatMap(([t, tone], i) => [i ? ' · ' : null, h('span', { 'data-tone': tone || null }, t)]);
const top = (eye, parts, ledger, ...extra) => h('header', { class: 'ax-top' }, h('p', { class: 'ax-eyebrow' }, eye), h('div', { class: 'sec-sent-wrap' }, h('h1', { class: 'ax-sentence', 'data-key': 'sentence' }, ...sentence(parts))), ledger ? h('p', { class: 'ax-ledger' }, ledger) : null, ...extra);
const sect = (title, count, sub, ...kids) => h('section', { class: 'ax-sect', 'aria-label': title }, h('h2', null, title, count != null ? h('span', { class: 'ax-count' }, String(count)) : null), sub ? h('p', { class: 'ax-sub' }, sub) : null, ...kids);
const dim = (...kids) => h('div', { class: 'ax-dim' }, ...kids);
const chev = () => h('span', { class: 'ax-go', 'aria-hidden': 'true' }, icon('chevron', 18));
// A details row keeps its open state across redraws, and records only what differs from its default.
const toggler = (store, id, dflt) => (e) => { if (e.currentTarget.open !== dflt) store[id] = e.currentTarget.open; else delete store[id]; };

// ---------- Security ----------
const PRIV = { allowed: ['ok', 'Allowed'], asks: ['attention', 'Asks you'], denied: ['paused', 'Denied'], 'denied-policy': ['attention', 'Denied by policy only'], unguarded: ['blocked', 'Unguarded'], unconfined: ['blocked', 'Not confined'] };
const TONE_RANK = { blocked: 0, attention: 1, paused: 2, ok: 3 };
const LAYER = (w) => (w === 'Built' ? 'ok' : w === 'Open' ? 'blocked' : w === 'Designed' || w === 'Partly' ? 'attention' : 'paused');
const MODES = [['ask', 'Ask on risky actions'], ['plan', 'Plan only, never execute'], ['auto', 'Approve low risk automatically']];

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
  const A = areasOf(ctx.sim), S = A.S(), sc = A.security(), offline = A.isOffline();
  const held = Object.values(S.approvals).filter((a) => a.kind === 'action' && a.state === 'PENDING');
  const stopped = S.estop.engaged, previous = ctx.ui.securitySnapshot;
  const text = stopped ? 'Emergency stop engaged' : held.length ? (held.length === 1 ? '1 action is waiting for your decision' : held.length + ' actions are waiting for your decision') : sc.open ? 'New starts are blocked' : 'Nothing is blocked';
  const counts = [], cards = new Map();
  const region = (title, count, ...body) => { const s = sect(title, count, null, ...body); counts.push([title, s.querySelector('.ax-count'), count]); return s; };
  const row = (title, detail, state, tone, href) => h(href ? 'a' : 'div', { class: 'sec-row', href, 'aria-current': href === '#/security/' + ctx.route.id ? 'true' : null },
    pill(tone, state), h('span', { class: 'sec-main' }, h('span', { class: 'sec-name' }, title), h('span', { class: 'sec-detail' }, detail)));
  const decisions = h('div', { class: 'sec-decisions' }, ...held.map((a) => {
    const item = attentionItem(ctx, { id: 'sec-' + a.id, kind: 'approval', group: 'Decide', mission_id: a.mission, project_id: a.project, since: a.created_at, reason: a.presented.what, ref: a.id });
    item.querySelector('a').href = '#/security/' + a.id;
    const decide = (kind, label) => h('button', { class: 'btn' + (kind === 'reject' ? ' danger outline' : ''), type: 'button', 'data-key': 'sec-' + kind + '-' + a.id,
      onclick: () => ask(ctx, { at: 'sec-decision-' + a.id, text: (kind === 'approve' ? 'Allow this action once? ' + a.presented.consequence : 'Deny this action? The execution ends and the mission is blocked.') + ' No Undo.', label, tone: kind === 'reject' ? 'danger' : 'primary', run: () => ctx.act(kind, a.id) }) }, label);
    item.querySelector('.actions').append(decide('approve', 'Allow once'), decide('reject', 'Deny'));
    item.append(h('p', { class: 'sec-detail' }, 'Ask me each time'), h('p', { class: 'sec-detail' }, a.presented.why), inline(ctx, 'sec-decision-' + a.id));
    const wrap = h('div', { class: 'sec-decision', 'data-approval': a.id }, item); cards.set(a.id, wrap); return wrap;
  }));
  // What a run may do is the same for every project; only the approval mode differs, so it is grouped by mode instead of repeated per project.
  const privs = A.privileges().map((r) => ({ r, tone: PRIV[r.state][0], word: r.state === 'asks' ? 'Ask me each time' : PRIV[r.state][1] })).sort((a, b) => TONE_RANK[a.tone] - TONE_RANK[b.tone]);
  const dflt = A.launch('default').mode, dfltTone = dflt === 'plan' ? 'paused' : 'attention', dfltWord = MODES.find(([id]) => id === dflt)[1];
  const modeGroups = [...MODES.map(([id, label]) => [id, label, id === 'plan' ? 'paused' : 'attention', S.projects.filter((p) => A.isOverride(p.id) && A.launch(p.id).mode === id)]), ['default', 'Default', dfltTone, S.projects.filter((p) => !A.isOverride(p.id))]].filter((g) => g[3].length);
  const names = (ps) => (ps.length > 6 ? [ps.slice(0, 6).map((p) => p.name).join(', '), h('details', { class: 'sec-names' }, h('summary', null, '+ ' + (ps.length - 6) + ' more'), ps.slice(6).map((p) => p.name).join(', '))] : [ps.map((p) => p.name).join(', ')]);
  const modes = modeGroups.map(([id, label, tone, ps]) => h('div', { class: 'sec-row sec-mode', 'data-key': 'sec-mode-' + id }, pill(tone, label), h('span', { class: 'sec-main' }, h('span', { class: 'sec-name' }, ps.length === 1 ? '1 project' : ps.length + ' projects', id === 'default' ? ' · ' : null, id === 'default' ? h('span', null, dfltWord) : null), h('span', { class: 'sec-detail' }, ...names(ps)))));
  const boundaryRows = [['Execution isolation', sc.boundaries[0], 'Not confined', 'blocked'], ['Accounts and homes', sc.boundaries[4], 'Denied by policy only', 'attention'], ['Network', sc.boundaries[2], 'Not confined', 'blocked']].map(([title, b, state, tone]) => row(title, b.note, state, tone, '#/security/' + b.id));
  const events = A.log().filter((l) => ['hook', 'breaker'].includes(l.kind)).map((l) => {
    const hs = l.kind === 'breaker' ? S.harnesses.find((x) => l.text.includes(x.label)) : null;
    return { ...l, kind: l.kind === 'hook' ? 'Hook' : 'Spawn breaker', href: l.kind === 'hook' ? '#/extensions/h-1' : hs ? '#/security/bk-' + hs.id : null };
  });
  S.events.filter((e) => e.type.startsWith('approval.') || e.type.startsWith('core.estop')).forEach((e) => {
    const a = S.approvals[e.subject.id]; if (a && a.kind !== 'action') return;
    events.push({ at: e.at, kind: a ? 'Decision' : 'Emergency stop', text: a ? a.presented.what : e.type === 'core.estop_rearmed' ? 'Re-armed: new work can start again.' : 'Emergency stop engaged', state: a ? e.payload.to || 'PENDING' : null, href: a ? '#/security/' + a.id : null });
  });
  events.sort((a, b) => b.at - a.at);
  const rearm = stopped ? h('button', { class: 'btn primary', type: 'button', 'data-key': 'sec-rearm', onclick: () => { const controls = page.querySelector('.sec-controls'); controls.scrollIntoView({ block: 'center' }); controls.querySelector('[data-key="rearm"], [data-key="rearm-yes"]').focus(); } }, 'Re-arm') : null;
  const header = top('Security', [[text, stopped || held.length ? 'attention' : null]], null,
    h('div', { class: 'ax-ledger sec-warning' }, pill('attention', 'Physical isolation is not built'), h('span', null, 'A started CLI still runs as your user. Policy does not physically confine it.'), rearm));
  const posture = header.querySelector('.ax-sentence');
  const main = h('div', { class: 'sec-main-col' },
    region('Needs a decision now', held.length, decisions, !held.length ? h('p', { class: 'sec-empty' }, 'Held actions will appear here when a command needs your permission.') : null),
    region('What Archeus may do', privs.length, h('p', { class: 'sec-rule' }, 'Held commands never auto-allow.'), h('p', { class: 'sec-detail' }, 'Policy applies to every project below.'), h('p', { class: 'sec-detail' }, 'Command policy applies inside an execution. Plan only never starts one.'),
      dim(...privs.map(({ r, tone, word }) => row(r.label, r.note, word, tone, r.link ? hrefFor(r.link.startsWith('sec-') ? 'boundary' : 'hook', r.link) : null))),
      h('h3', { class: 'sec-sub' }, 'Approval mode'), h('p', { class: 'sec-detail' }, 'No per-project command overrides are recorded.'),
      modes.length ? dim(...modes) : h('p', { class: 'sec-empty' }, 'No projects are recorded.')),
    region('Boundaries', sc.boundaries.length, dim(...boundaryRows), h('p', { class: 'sec-check' }, h('span', null, 'Last check'), ': ', h('span', null, 'Not recorded')),
      h('details', { class: 'sec-more', 'data-key': 'sec-more', open: !!(ctx.ui.secMore || (ctx.route.id || '').startsWith('bk-') || (ctx.ui.confirm && (ctx.ui.confirm.at || '').startsWith('row:bk-'))), ontoggle: (e) => { ctx.ui.secMore = e.currentTarget.open; } }, h('summary', null, 'More boundary evidence'),
        dim(...sc.boundaries.map((b) => row(b.n + ' · ' + b.name, b.what, b.policy + ' / ' + b.physical, LAYER(b.physical), '#/security/' + b.id))),
        h('h3', null, 'Policy boundary'), h('ul', { class: 'sec-policy-notes' }, ...sc.policyList.map((t) => h('li', null, t))),
        h('h3', null, 'Switches'), dim(...sc.switches.map((x) => row(x.label, x.note, x.word, x.state === 'ok' ? 'ok' : 'paused'))),
        h('h3', null, 'Spawn breakers'), ...S.harnesses.map((hs) => breakerRow(ctx, A, S, hs)),
        h('p', { class: 'sec-detail' }, 'A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run.'))),
    region('Recent security events', events.length, events.length ? h('ol', { class: 'sec-log ax-dim' }, ...events.slice(0, 12).map((e) => h('li', null,
      h('time', null, clockLabel(e.at)), h('span', { class: 'sec-category' }, e.kind), h('span', { class: 'sec-event-text' }, e.text, e.state ? badge('approval', e.state) : null), e.href ? h('a', { class: 'btn quiet', href: e.href }, 'Evidence') : h('span', { class: 'sec-detail' }, 'Not recorded')))) : h('p', { class: 'sec-empty' }, 'Security events will appear here when an action is held, decided, or stopped.'), events.length > 12 ? h('p', { class: 'sec-detail' }, 'Latest events', ': 12 / ' + events.length) : null));
  const rail = h('aside', { class: 'sec-rail' }, region('Emergency controls', 3, pill(stopped ? 'blocked' : 'ok', stopped ? 'Engaged: nothing new starts' : 'Not stopped: accepts new work.'), h('div', { class: 'sec-controls' }, controlBody(ctx, false))));
  const page = h('div', { class: 'ax-page sec-page' }, h('div', { class: 'view ax-view' }, header, h('div', { class: 'sec-layout' }, main, rail)));
  if (offline) {
    page.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    page.querySelectorAll('.sec-decisions a').forEach((a) => { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); });
  }
  let mounted = false;
  ctx.mounts.push(() => {
    const motion = !reducedMotion() && !window.matchMedia('(prefers-reduced-motion: reduce)').matches && !offline;
    if (!mounted && previous && motion) {
      counts.forEach(([key, node, value]) => { if (previous.counts[key] !== value) node.animate([{ opacity: .4, transform: 'translateY(3px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 180, easing: 'ease-out' }); });
      if (previous.sentence !== text) {
        const old = h('span', { class: 'sec-old-sentence ax-sentence', 'aria-hidden': 'true' }, previous.sentence); posture.before(old);
        old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: 'ease-out' }).finished.then(() => old.remove());
        posture.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' });
      }
      previous.cards.forEach((c, id) => {
        if (cards.has(id) || !S.approvals[id] || S.approvals[id].state === 'PENDING') return;
        const ghost = c.node; ghost.setAttribute('aria-hidden', 'true'); ghost.inert = true; ghost.classList.add('sec-resolved'); decisions.append(ghost);
        ghost.animate([{ height: c.height + 'px', opacity: .6 }, { height: '0px', opacity: 0 }], { duration: 180, easing: 'ease-out' }).finished.then(() => ghost.remove());
      });
    }
    mounted = true;
    ctx.ui.securitySnapshot = { sentence: text, counts: Object.fromEntries(counts.map(([key, , value]) => [key, value])), cards: new Map([...cards].map(([id, node]) => [id, { node: node.cloneNode(true), height: node.getBoundingClientRect().height }])) };
  });
  return page;
}

// ---------- Health ----------
const HEALTH_WORD = { ok: 'OK', attention: 'Needs attention', unknown: 'Unknown' }, HEALTH_RANK = { attention: 0, unknown: 1, ok: 2 };
export function viewHealth(ctx) {
  const A = areasOf(ctx.sim), hl = A.health(), c = hl.counts, opened = (ctx.ui.hlOpen ||= {});
  const parts = [c.attention && [c.attention + (c.attention === 1 ? ' check needs attention' : ' checks need attention'), 'attention'], c.unknown && [c.unknown + ' unknown', 'unknown']].filter(Boolean);
  const checks = hl.checks.slice().sort((a, b) => HEALTH_RANK[a.state] - HEALTH_RANK[b.state]).map((k) => {
    const tone = TONE_OF_STATE[k.state], dflt = k.state !== 'ok';
    return h('details', { class: 'hl-row', 'data-tone': tone, 'data-key': 'hl-' + k.id, open: (opened[k.id] ?? dflt) ? true : null, ontoggle: toggler(opened, k.id, dflt) },
      h('summary', null, pill(tone, HEALTH_WORD[k.state]), h('span', { class: 'hl-name' }, k.label), h('span', { class: 'hl-sum' }, k.summary), chev()),
      h('div', { class: 'hl-body' },
        k.cause ? h('div', null, h('h3', null, 'Cause'), h('p', null, k.cause)) : null,
        k.fix ? h('div', null, h('h3', null, 'Fix'), h('ol', { class: 'ax-steps' }, ...k.fix.map((s) => h('li', null, s)))) : h('p', { class: 'ax-note' }, 'Nothing to fix.'),
        h('div', { class: 'actions' }, k.action ? h('a', { class: 'btn' + (k.state === 'attention' ? ' primary' : ''), href: k.action.href }, k.action.label) : null, h('a', { class: 'btn quiet', href: hrefFor('check', k.id) }, 'Readings'))));
  });
  return h('div', { class: 'ax-page' }, h('div', { class: 'view ax-view' },
    top('Health', parts.length ? parts : [['Every check is OK', 'ok']], 'Six checks, each read from records. When one is not OK it says why and what to do. A missing reading is unknown, never 0.'),
    h('div', { class: 'ax-dim' }, ...checks),
    dnote('H15', 'Health is read from records, one live derivation (P21 D12). Each check has a cause and a fix when it is not OK.')));
}

// ---------- Usage ----------
// A ring is what is LEFT and empties as it is used; its tick is the 20% line. Small and fixed in size, so a row per account scales.
const USAGE_CAP = 12;
export function viewUsage(ctx) {
  const A = areasOf(ctx.sim), rows = A.usage(), f = A.failover(), low = rows.filter((r) => ['low', 'critical', 'out'].includes(r.worst)), unk = rows.filter((r) => r.worst === 'unknown');
  const live = [], shown = ctx.ui.usAll ? rows : rows.slice(0, USAGE_CAP);
  const accRow = (r) => {
    const s = ringNode({ left: r.session.left, key: r.session.key, label: r.label + ', 5 hour window', live: r.id + ':session' }), w = ringNode({ left: r.week.left, key: r.week.key, label: r.label + ', week', live: r.id + ':week' });
    live.push([r.id, s, w]);
    const msg = r.worst === 'unknown' ? 'No reading yet: Core has never started this account. Unknown is not zero.' : r.worst === 'out' ? 'Limit reached. New work uses another account.' : r.worst === 'critical' ? 'Almost out. New work prefers another account.' : 'At or under your ' + f.pauseAt + '% line. New work prefers another account.';
    return h('div', { class: 'us-row', 'data-tone': TONE_OF_METER[r.worst], 'data-key': 'us-' + r.id },
      h('div', { class: 'us-who' }, h('a', { class: 'us-name', href: hrefFor('account', r.id) }, r.label), h('span', { class: 'r-note' }, harnessLabel(r.harness) + ' · ' + r.role), badge('account_health', r.state)),
      h('div', { class: 'us-m' }, s, h('span', { class: 'us-cap', 'aria-hidden': 'true' }, '5 hour window')),
      h('div', { class: 'us-m' }, w, h('span', { class: 'us-cap', 'aria-hidden': 'true' }, 'Week')),
      h('div', { class: 'us-st' }, pill(TONE_OF_METER[r.worst], METER_WORD[r.worst]), r.worst === 'ok' ? null : h('p', { class: 'ac-msg', 'data-ax': 'umsg:' + r.id }, msg), h('p', { class: 'r-note' }, r.resets || 'Reset time unknown')),
      h('div', { class: 'us-sp' }, r.hist.length > 2 ? spark(r.hist, 120, 32) : null));
  };
  onTick(ctx, () => { const now = A.usage(); live.forEach(([id, s, w]) => { const r = now.find((x) => x.id === id); patchRing(s, r.session.left, r.session.key); patchRing(w, r.week.left, r.week.key); }); });
  const parts = [low.length && [low.length === 1 ? '1 account is low' : low.length + ' accounts are low', 'attention'], unk.length && [unk.length + ' unknown', 'unknown']].filter(Boolean);
  return h('div', { class: 'ax-page' }, h('div', { class: 'view ax-view' },
    top('Usage', parts.length ? parts : [['Every account has room', 'ok']], 'How much of each account is left, read only from the existing usage reader. Archeus shows a number only when it can source it.'),
    h('div', { class: 'us-table' },
      h('div', { class: 'us-head', 'aria-hidden': 'true' }, h('span', null, 'Account'), h('span', null, '5 hour window'), h('span', null, 'Week'), h('span', null, 'Status'), h('span', null, 'Last hour')),
      h('div', { class: 'ax-dim' }, ...shown.map(accRow))),
    rows.length > USAGE_CAP ? h('button', { class: 'btn', type: 'button', 'data-key': 'us-all', onclick: () => { ctx.ui.usAll = !ctx.ui.usAll; ctx.render(); } }, ctx.ui.usAll ? 'Show fewer' : 'Show all ' + rows.length) : null,
    h('div', { class: 'ax-legend' }, h('span', { class: 'lg' }, h('b', { class: 'tk', 'aria-hidden': 'true' }), 'The tick is the 20% line'), h('span', { class: 'lg', 'data-tone': 'unknown' }, h('i', { 'aria-hidden': 'true' }), 'Unknown, never 0'), link('#/accounts', 'Failover rules', 'ax-link')),
    note('These are account percentages read about every 15 minutes, not the cost or tokens of one session.'),
    dnote('H03', 'Usage: a ring is what is left and empties as it is used; the tick is your 20% line. "20% weekly usage" is read here as 20% left (owner to confirm). Unknown stays unknown.')));
}

// ---------- Accounts and models ----------
const sel = (key, value, opts, on, label) => h('select', { class: 'ax-sel', 'aria-label': label, 'data-key': key, onchange: (e) => on(e.target.value) }, ...opts.map(([v, l]) => h('option', { value: v, selected: v === value ? true : null }, l)));
export function viewAccounts(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), st = S.accounts, rows = A.usage(), f = A.failover(), models = S.models, opened = (ctx.ui.lnOpen ||= {});
  const next = rows.find((r) => ['AVAILABLE', 'CONSTRAINED', 'UNVERIFIED'].includes(r.state) && !(f.pauseOn && r.week.left != null && r.week.left <= f.pauseAt));
  const fo = (key, label, sub, locked) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, label), h('span', { class: 'r-note' }, sub)), locked ? pill('ok', 'Always on') : sw({ on: f[key], label, key: 'fo-' + key, onclick: () => { A.setFailover(key, !f[key]); ctx.render(); } }));
  const accountRow = (r, i) => h('div', { class: 'ax-row ax-acct', 'data-key': 'ac-' + r.id },
    h('span', { class: 'n', 'aria-hidden': 'true' }, String(i + 1)),
    h('a', { class: 'a-main', href: hrefFor('account', r.id) }, h('span', { class: 'r-name' }, r.label), h('span', { class: 'r-note' }, harnessLabel(r.harness) + ' · ' + r.role + ' · ' + (r.session.left == null ? 'usage unknown' : r.session.left + '% of the session left'))),
    badge('account_health', r.state),
    h('span', { class: 'a-mv' }, h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' up', disabled: i === 0 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, -1), 'Moved up in the failover order.') }, '↑'), h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' down', disabled: i === rows.length - 1 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, 1), 'Moved down in the failover order.') }, '↓')));
  const launch = (id, name) => {
    const c = A.launch(id), pv = A.preview(id), har = S.harnesses.filter((x) => x.state !== 'MISSING');
    const set = (k) => (v) => { done(ctx, A.setLaunch(id, k, v), 'Launch setting saved (simulated).'); };
    return h('details', { class: 'ln-row', 'data-tone': pv.tone, 'data-key': 'ln-' + id, open: opened[id] ? true : null, ontoggle: toggler(opened, id, false) },
      h('summary', null, h('span', { class: 'ln-name' }, name), pill(pv.tone, pv.tone === 'ok' ? 'Can start' : pv.tone === 'blocked' ? 'Cannot start' : 'Waits'), chev(),
        h('span', { class: 'ln-prev' }, h('b', null, 'Next mission: '), harnessLabel(pv.harness) + ' · ' + pv.model + (pv.account ? ' · ' + pv.account : ''))),
      h('div', { class: 'ln-body' }, h('p', { class: 'ax-note' }, pv.note),
        h('div', { class: 'ax-form' },
          h('label', null, h('span', null, 'Harness'), sel('ln-h-' + id, c.harness, har.map((x) => [x.id, x.label]), set('harness'), 'Harness for ' + name)),
          h('label', null, h('span', null, 'Model'), sel('ln-m-' + id, c.model, models.filter((m) => m.harness === c.harness).map((m) => [m.id, m.label]), set('model'), 'Model for ' + name)),
          h('label', null, h('span', null, 'Account'), sel('ln-a-' + id, c.account, [['auto', 'Automatic, by failover order'], ...st.filter((a) => a.harness === c.harness).map((a) => [a.id, a.label])], set('account'), 'Account for ' + name)),
          h('label', null, h('span', null, 'Approvals'), sel('ln-d-' + id, c.mode, MODES, set('mode'), 'Approval mode for ' + name)),
          h('label', null, h('span', null, 'Runs at once'), sel('ln-p-' + id, String(c.parallel), [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']], set('parallel'), 'Runs at once for ' + name)),
          h('p', { class: 'ax-note' }, 'Isolation: required. It cannot be switched off here.')),
        id === 'default' ? null : h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', 'data-key': 'ln-reset-' + id, onclick: () => { delete opened[id]; done(ctx, A.resetLaunch(id), 'Back to the default (simulated).'); } }, 'Use the default'), h('a', { class: 'ax-link', href: hrefFor('project', 'prj-' + id) }, 'Open project'))));
  };
  const modelRow = (m) => { const d = A.defaultModel() === m.id; return h('div', { class: 'ax-model', 'data-default': d ? 'true' : 'false', 'data-key': 'md-' + m.id }, h('a', { class: 'm-main', href: hrefFor('model', 'mdl-' + m.id) }, h('span', { class: 'r-name' }, m.label), h('span', { class: 'r-note' }, harnessLabel(m.harness) + ' · tier ' + m.tier)), d ? pill('ok', 'Default') : h('button', { class: 'btn', type: 'button', onclick: () => done(ctx, A.setDefaultModel(m.id), m.label + ' is now the default (simulated).') }, 'Make default')); };
  const overrides = S.projects.filter((p) => A.isOverride(p.id)), inheriting = S.projects.filter((p) => !A.isOverride(p.id));
  return h('div', { class: 'ax-page' }, h('div', { class: 'view ax-view' },
    top('Accounts', [[next ? next.label + ' takes the next mission' : 'No account can take new work', next ? null : 'blocked']], 'Three accounts, four models, one default, and the rules that decide which account takes the next mission.'),
    h('div', { class: 'ac-layout' },
      h('div', { class: 'ac-col' },
        sect('Accounts', rows.length, 'In failover order. The first available account takes the next mission.', dim(...rows.map(accountRow)), h('p', { class: 'ax-note' }, 'A subscription login belongs to you. Archeus never reads, stores, copies, injects or relays the token.')),
        sect('Failover rules', null, 'What happens when an account runs low or out.', dim(
          fo('handoff', 'Hand off a run when its account is limited', 'The run writes a checkpoint and continues on the next account.'),
          h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, 'New work waits when the week is low'), h('span', { class: 'r-note' }, 'Your line. Running work finishes; nothing new starts on that account.')), h('span', { class: 'r-ctl' }, f.pauseOn ? sel('fo-at', String(f.pauseAt), [['10', '10% left'], ['20', '20% left'], ['30', '30% left']], (v) => { A.setFailover('pauseAt', Number(v)); ctx.render(); }, 'Line, percent left') : null, sw({ on: f.pauseOn, label: 'New work waits when the week is low', key: 'fo-pauseOn', onclick: () => { A.setFailover('pauseOn', !f.pauseOn); ctx.render(); } }))),
          fo('askHarness', 'Ask before switching to another harness', 'A move from Claude Code to Codex is a card you confirm.'),
          fo('never', 'Never run without isolation', 'There is no unisolated fallback, whatever else fails.', true)))),
      h('div', { class: 'ac-col' },
        sect('Models', models.length, 'The default is what a new mission asks for.', dim(...models.map(modelRow)), h('p', { class: 'ax-note' }, 'This is the model Archeus asks for, not proof of which model the provider served.')),
        sect('Launch settings per project', null, 'Every project starts with the default. Only a project that differs has its own row.',
          dim(launch('default', 'Default'), ...overrides.map((p) => launch(p.id, p.name))),
          inheriting.length ? sel('ln-add', '', [['', 'Give a project its own settings'], ...inheriting.map((p) => [p.id, p.name])], (v) => { if (v) { opened[v] = true; done(ctx, A.overrideLaunch(v), 'This project now has its own launch settings (simulated).'); } }, 'Project that gets its own settings') : null))),
    dnote('H10', 'Accounts and models: three accounts in a failover order, four models with one default, per-project launch settings. No token is shown or handled.')));
}

// ---------- Extensions: hooks, MCP servers, agents, automations, clients ----------
// One row per extension: name and what it does (the whole row opens its details), its last use inline, a status word only where the switch does not say it, the switch.
function xrow(ctx, o) {
  const last = o.lastLabel === null ? [o.last] : [h('span', { class: 'l' }, o.lastLabel || 'Last run'), ' ', o.last];
  return h('div', { class: 'ax-xrow', 'data-key': o.key, 'data-nost': o.status ? null : 'true' },
    h('a', { class: 'x-main', href: o.href }, h('span', { class: 'r-name' }, o.name), h('span', { class: 'r-note' }, o.meta, ' · ', ...last)),
    o.status ? h('span', { class: 'x-st' }, o.status) : null, h('span', { class: 'x-sw' }, o.control || null), o.below || null);
}
const needsYou = (n) => (n === 1 ? '1 needs you' : n + ' need you');
export function viewExtensions(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), clock = S.clock;
  const when = (t) => (t == null ? 'Never' : clockLabel(t));
  const hookList = A.hooks(), mcpList = A.mcp(), agentList = A.agents();
  const hooks = hookList.map((x) => {
    const key = 'row:' + x.id, flip = () => { const r = A.toggleHook(x.id); done(ctx, r, r.on ? 'Hook switched on (simulated).' : 'Hook switched off (simulated).'); };
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('hook', x.id), name: x.name, meta: x.event + ' · ' + x.matcher, last: when(x.last),
      control: x.locked ? pill('ok', 'Built in') : sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => (x.enabled && x.sensitive ? ask(ctx, { at: key, text: 'Switch off "' + x.name + '"? An execution can then do this without asking you.', label: 'Switch off', tone: 'danger', run: flip }) : flip()) }), below: inline(ctx, key) });
  });
  const mcps = mcpList.map((x) => {
    const st = A.mcpStatus(x, clock), t = MCP_TONE[st];
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('mcp', x.id), name: x.name, meta: x.transport + ' · ' + (x.tools.length ? x.tools.length + (x.tools.length === 1 ? ' tool' : ' tools') : 'tools not known') + (st === 'CONNECTED' ? ' · ' + x.calls + ' calls' : ''), status: pill(t[0], t[1]), lastLabel: 'Last call', last: when(x.last),
      control: x.unchecked ? h('span', { class: 'x-na' }, 'Not checked') : sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => { const r = A.toggleMcp(x.id); done(ctx, r, r.on ? 'Connecting (simulated).' : 'Switched off (simulated).'); } }) });
  });
  const agentState = agentList.map((x) => A.agentStatus(x));
  const agents = agentList.map((x, i) => {
    const s = agentState[i];
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('agent', x.id), name: x.name, meta: x.role, status: pill(s.key === 'working' ? 'active' : s.key === 'off' ? 'paused' : s.key === 'ready' ? 'attention' : 'ok', s.key === 'working' ? 'Working' : s.key === 'off' ? 'Off' : s.key === 'ready' ? 'Result waits' : 'Idle'), last: when(x.last), control: sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => { const r = A.toggleAgent(x.id); done(ctx, r, r.on ? 'Agent switched on (simulated).' : 'Agent switched off (simulated).'); } }), below: s.key === 'working' || s.key === 'ready' ? h('p', { class: 'x-below' }, s.text) : null });
  });
  const waits = (a) => a.state === 'SUSPENDED' || a.state === 'PENDING_APPROVAL';
  const autos = S.automations.map((a) => xrow(ctx, { key: 'x-' + a.id, href: hrefFor('automation', a.id), name: a.name, meta: a.trigger, status: badge('automation', a.state), last: a.next_run ? 'Next ' + a.next_run : 'Not scheduled', lastLabel: null, control: waits(a) ? h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('enable', a.id) }, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve') : null, below: a.note ? h('p', { class: 'x-below' }, a.note) : null }));
  const clients = S.devices.map((d) => xrow(ctx, { key: 'x-' + d.id, href: hrefFor('device', d.id), name: d.name, meta: 'Paired client', status: badge('device', d.state), last: d.state === 'ACTIVE' ? 'Now' : 'Revoked', lastLabel: 'Seen' }));
  const need = { agents: agentState.filter((s) => s.key === 'ready').length, autos: S.automations.filter(waits).length };
  const total = hooks.length + mcps.length + agents.length + autos.length + clients.length, off = [...hookList, ...mcpList, ...agentList].filter((x) => !x.enabled).length, needAll = need.agents + need.autos;
  const sum = h('p', { class: 'ext-sum', role: 'status' }, h('span', null, total + ' extensions'), off ? h('span', null, off + ' off') : null, needAll ? pill('attention', needsYou(needAll)) : null);
  const jump = (id, l, n) => h('button', { class: 'chip', type: 'button', onclick: () => { const el = document.getElementById(id); if (el) el.scrollIntoView({ block: 'start' }); } }, l, h('span', { class: 'n' }, String(n)));
  const group = (id, t, sub, rows, n) => h('section', { class: 'ax-card ax-ext', id }, h('div', { class: 'ax-card-h' }, h('h2', null, t, h('span', { class: 'n' }, String(rows.length)), n ? pill('attention', needsYou(n)) : null), h('p', null, sub)), h('div', { class: 'ax-xrows' }, ...rows));
  return h('div', { class: 'ax-page' }, head(ctx, 'Extensions', sum), h('div', { class: 'view' },
    h('div', { class: 'chips ax-jump' }, jump('x-hooks', 'Hooks', hooks.length), jump('x-mcp', 'MCP servers', mcps.length), jump('x-agents', 'Agents', agents.length), jump('x-autos', 'Automations', autos.length), jump('x-clients', 'Clients', clients.length)),
    cols([group('x-hooks', 'Hooks', 'Run before or after a tool. A hook that guards something asks you to confirm before it is switched off.', hooks), group('x-mcp', 'MCP servers', 'Tools a run can call. A server that writes asks first.', mcps)],
      [group('x-agents', 'Agents', 'The roles Core calls. None of them can decide for you.', agents, need.agents), group('x-autos', 'Automations', 'Work that starts on a schedule or an event.', autos, need.autos), group('x-clients', 'Clients', 'Paired devices that can read and decide.', clients)]),
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
    ideas.replaceWith(pinnedPanel(ctx, A), ideasPanel(ctx, A));
  }
  return content;
}
