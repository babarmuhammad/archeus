// S3 areas: Security, Health, Usage, Accounts and models, Hooks / MCP / agents (Extensions), plus what S3 adds to Now and Work
// (digest, pins, idea path) and the offline view. Everything is SIMULATED; each page says so in its header.
import { h } from './dom.js';
import { icon, glyph } from './icons.js';
import { illustration } from './illustrations.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { head, dnote, missionRow, badge, projName } from './views.js';
import { spineRow } from './spine.js';
import { ask, ideaPath } from './inspectors.js';
import { done, MCP_TONE } from './inspectors2.js';
import { areasOf, breakerView, waitLabel, keptSummary, harnessLabel } from './areas-model.js';
import { pill, note, link, entity, hrefFor, sw, ringNode, patchRing, spark, stat, eyebrow, TONE_OF_METER, TONE_OF_STATE } from './ax.js';

const card = (title, sub, ...kids) => h('section', { class: 'ax-card' }, title ? h('div', { class: 'ax-card-h' }, h('h2', null, title), sub ? h('p', null, sub) : null) : null, ...kids);
const toneCard = (tone, ...kids) => { const c = card(...kids); c.dataset.tone = tone; return c; };
function axHead(ctx, eyebrowText, title, lede) {
  const hd = head(ctx, title);
  hd.querySelector('h1').before(eyebrow(eyebrowText));
  hd.classList.add('ax-head');
  return h('div', { class: 'ax-hero' }, hd, lede ? h('p', { class: 'ax-lede' }, lede) : null);
}
export const onTick = (ctx, fn) => { (ctx.ticks = ctx.ticks || []).push(fn); };
const cols = (a, b) => h('div', { class: 'ax-cols' }, h('div', { class: 'ax-col' }, ...a), h('div', { class: 'ax-col' }, ...b));
function inline(ctx, key) {
  const c = ctx.ui.confirm; if (!c || c.at !== key) return null;
  return h('div', { class: 'ax-inline-confirm', role: 'group' }, h('p', null, c.text), h('div', { class: 'actions' },
    h('button', { class: 'btn ' + (c.tone === 'danger' ? 'danger' : 'primary'), type: 'button', onclick: () => { ctx.ui.confirm = null; c.run(); } }, c.label), h('button', { class: 'btn', type: 'button', onclick: () => { ctx.ui.confirm = null; ctx.render(); } }, 'Back')));
}

// ---------- Security ----------
const PRIV = { allowed: ['ok', 'Allowed'], asks: ['attention', 'Asks you'], denied: ['paused', 'Denied'], 'denied-policy': ['attention', 'Denied by policy only'], unguarded: ['blocked', 'Unguarded'], unconfined: ['blocked', 'Not confined'] };
const LAYER = (w) => (w === 'Built' ? 'ok' : w === 'Open' ? 'blocked' : w === 'Designed' || w === 'Partly' ? 'attention' : 'paused');

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
  const A = areasOf(ctx.sim), S = A.S(), sc = A.security();
  const closed = sc.breakers - sc.open;
  return h('div', { class: 'ax-page' }, axHead(ctx, 'Security', 'Security', 'Archeus stops what policy can stop. It does not yet confine a running process at the operating system level, and this page says so.'), h('div', { class: 'view' },
    dnote('H14', 'Isolation (PV-20) is shown as the board records it: designed and fixture tested, physical reach not built, switches off. It is stated, never simulated as working.'),
    h('div', { class: 'ax-stats' }, stat('ok', 'Built', 'Policy boundary', 'Five rules hold today'), stat('attention', 'Not built', 'Physical isolation', 'Designed, switches off'), stat(sc.open ? 'attention' : 'ok', closed + ' of ' + sc.breakers, 'Spawn breakers closed', sc.open ? sc.open + ' open: cannot start' : 'Every harness starts normally')),
    cols([
      card('Two boundaries', 'Neither stands in for the other.',
        h('div', { class: 'ax-two' },
          h('div', null, pill('ok', 'Built'), h('h3', null, 'Application policy'), h('p', null, 'What Archeus lets a run do: the workdir, the stripped environment, the fail-closed hook, approvals. This is V1 today.')),
          h('div', null, pill('attention', 'Designed, not built'), h('h3', null, 'Physical reach'), h('p', null, 'What a process can physically reach, whatever the agent tries: an isolated identity, AppContainer, job object, ACLs. Gated off.')))),
      card('What is isolated and what is not', 'Held by policy, and the gaps that policy cannot close.',
        h('div', { class: 'ax-lists' }, h('div', null, h('h3', { class: 'ok' }, 'Held by policy'), h('ul', { class: 'ax-ul' }, ...sc.policyList.map((t) => h('li', { 'data-t': 'ok' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph('ok')), h('span', null, t))))),
          h('div', null, h('h3', { class: 'gap' }, 'Not isolated'), h('ul', { class: 'ax-ul' }, ...sc.notList.map((t) => h('li', { 'data-t': 'gap' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph('blocked')), h('span', null, t))))))),
      card('Eight boundaries', 'Each with its policy layer and its physical layer.', h('div', { class: 'ax-ents' }, ...sc.boundaries.map((b) => h('a', { class: 'ax-ent', href: hrefFor('boundary', b.id), 'data-key': b.id }, h('span', { class: 'e-main' }, h('span', { class: 'e-name' }, b.n + ' · ' + b.name), h('span', { class: 'e-note' }, b.what)), h('span', { class: 'e-pills' }, h('span', { class: 'lay' }, h('span', { class: 'l' }, 'Policy'), pill(LAYER(b.policy), b.policy)), h('span', { class: 'lay' }, h('span', { class: 'l' }, 'Physical'), pill(LAYER(b.physical), b.physical)))))),
        h('p', { class: 'ax-note pad' }, 'Design acceptance rows closed: ' + sc.rows.acceptance.closed + ' of ' + sc.rows.acceptance.total + ', and ' + sc.rows.additions.closed + ' of ' + sc.rows.additions.total + ' additions. No row about physical reach can be closed in this build.')),
    ], [
      card('Spawn breakers', 'One per CLI. Trips at 3 failed starts in 10 minutes.', h('div', { class: 'ax-brs' }, ...S.harnesses.map((hs) => breakerRow(ctx, A, S, hs))),
        h('p', { class: 'ax-note pad' }, 'A waiting task backs off 15 s, 30 s, 1 min, 2 min, 4 min, then 5 min. After 5 minutes one trial start is allowed. It never falls back to an unisolated run.'), dnote('H04', 'One breaker per CLI; trip and reset are simulated here; a mission says "cannot start" while it is open.')),
      card('Switches', null, h('div', { class: 'ax-rows' }, ...sc.switches.map((x) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, x.label), h('span', { class: 'r-note' }, x.note)), pill(x.state === 'ok' ? 'ok' : 'paused', x.word))))),
      card('What an execution may do', 'Who stops each thing, and what is not stopped at all.', h('div', { class: 'ax-rows' }, ...A.privileges().map((p) => { const t = PRIV[p.state], r = h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, p.label), h('span', { class: 'r-note' }, p.by + '. ' + p.note)), pill(t[0], t[1])); return p.link ? h('a', { class: 'ax-row-link', href: hrefFor(p.link.startsWith('sec-') ? 'boundary' : 'hook', p.link) }, r) : r; }))),
      card('Security log', 'Breakers, hooks and what you changed.', h('div', { class: 'ax-rows' }, ...A.log().slice(0, 7).map((l) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-note' }, l.text)), h('span', { class: 'r-time' }, clockLabel(l.at)))))),
      card('Owner rules', null, h('div', { class: 'ax-rows' }, ...[['Never push, never touch credentials', 'Archeus does not read, store, copy, inject or relay subscription tokens.'], ['Decisions are the owner\'s', 'Chat proposes; only a card on screen with its hash is decided.'], ['No silent approval', 'A new mission from chat waits for a card here (V1 today starts it; flagged G1).']].map(([a, b]) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, a), h('span', { class: 'r-note' }, b))))))
    ])));
}

// ---------- Health ----------
export function viewHealth(ctx) {
  const A = areasOf(ctx.sim), hl = A.health(), c = hl.counts;
  const word = { ok: 'OK', attention: 'Needs attention', unknown: 'Unknown' };
  return h('div', { class: 'ax-page' }, axHead(ctx, 'Health', 'Health', 'Six checks, each read from records. When one is not OK it says why and what to do. A missing reading is unknown, never 0.'), h('div', { class: 'view' },
    dnote('H15', 'Health is read from records, one live derivation (P21 D12). Each check has a cause and a fix when it is not OK.'),
    h('div', { class: 'ax-stats' }, stat('ok', String(c.ok), 'OK'), stat('attention', String(c.attention), 'Need attention'), stat('unknown', String(c.unknown), 'Unknown')),
    h('div', { class: 'ax-checks' }, ...hl.checks.map((k) => {
      const art = h('article', { class: 'ax-card ax-check', 'data-tone': TONE_OF_STATE[k.state], 'data-key': 'hl-' + k.id },
        h('div', { class: 'ck-top' }, h('h2', null, k.label), pill(TONE_OF_STATE[k.state], word[k.state])), h('p', { class: 'ck-sum' }, k.summary),
        k.cause ? h('div', { class: 'ck-blk' }, h('h3', null, 'Cause'), h('p', null, k.cause)) : null,
        k.fix ? h('div', { class: 'ck-blk' }, h('h3', null, 'Fix'), h('ol', { class: 'ax-steps' }, ...k.fix.map((s) => h('li', null, s)))) : h('p', { class: 'ck-none' }, 'Nothing to fix.'),
        h('div', { class: 'actions' }, k.action ? h('a', { class: 'btn' + (k.state === 'attention' ? ' primary' : ''), href: k.action.href }, k.action.label) : null, h('a', { class: 'btn quiet', href: hrefFor('check', k.id) }, 'Readings')));
      return art;
    }))));
}

// ---------- Usage ----------
export function viewUsage(ctx) {
  const A = areasOf(ctx.sim), rows = A.usage(), f = A.failover(), low = rows.filter((r) => ['low', 'critical', 'out'].includes(r.worst));
  const live = [];
  const accCard = (r) => {
    const s = ringNode({ left: r.session.left, key: r.session.key, label: r.label + ', 5 hour window', live: r.id + ':session' }), w = ringNode({ left: r.week.left, key: r.week.key, label: r.label + ', week', live: r.id + ':week' });
    live.push([r.id, s, w]);
    const msg = r.worst === 'unknown' ? 'No reading yet: Core has never started this account. Unknown is not zero.' : r.worst === 'out' ? 'Limit reached. New work uses another account.' : r.worst === 'critical' ? 'Almost out. New work prefers another account.' : r.worst === 'low' ? 'At or under your ' + f.pauseAt + '% line. New work prefers another account.' : 'On track.';
    const c = h('article', { class: 'ax-card ax-acc', 'data-tone': TONE_OF_METER[r.worst], 'data-key': 'us-' + r.id },
      h('div', { class: 'ac-top' }, h('div', null, h('h2', null, h('a', { href: hrefFor('account', r.id) }, r.label)), h('p', { class: 'ac-sub' }, harnessLabel(r.harness) + ' · ' + r.role)), badge('account_health', r.state)),
      h('div', { class: 'ax-rings' }, h('figure', null, s, h('figcaption', null, '5 hour window')), h('figure', null, w, h('figcaption', null, 'Week'))),
      h('p', { class: 'ac-msg', 'data-ax': 'umsg:' + r.id }, msg), r.resets ? h('p', { class: 'ac-reset' }, r.resets) : h('p', { class: 'ac-reset' }, 'Reset time unknown'),
      r.hist.length > 2 ? h('div', { class: 'ac-spark' }, h('span', { class: 'ac-sl' }, 'Session over the last hour'), spark(r.hist, 200, 40)) : null);
    return c;
  };
  onTick(ctx, () => { const now = A.usage(); live.forEach(([id, s, w]) => { const r = now.find((x) => x.id === id); patchRing(s, r.session.left, r.session.key); patchRing(w, r.week.left, r.week.key); }); });
  return h('div', { class: 'ax-page' }, axHead(ctx, 'Usage', 'Usage', 'How much of each account is left, read only from the existing usage reader. Archeus shows a number only when it can source it.'), h('div', { class: 'view' },
    dnote('H03', 'Usage: a ring is what is left and empties as it is used; the tick is your 20% line. "20% weekly usage" is read here as 20% left (owner to confirm). Unknown stays unknown.'),
    low.length ? h('div', { class: 'ax-banner', 'data-tone': 'attention', role: 'status' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph('attention')), h('p', null, low.map((r) => r.label).join(' and ') + (low.length === 1 ? ' is' : ' are') + ' at or under the ' + f.pauseAt + '% line.' + (f.pauseOn ? ' New work waits on a week that low.' : '')), link('#/accounts', 'Failover rules', 'btn')) : null,
    h('div', { class: 'ax-legend' }, ...[['active', 'On track, more than 20% left'], ['attention', 'Low, 20% or less left'], ['blocked', 'Almost out, 5% or less'], ['unknown', 'Unknown, never 0']].map(([t, w]) => h('span', { class: 'lg', 'data-tone': t }, h('i', { 'aria-hidden': 'true' }), w)), h('span', { class: 'lg' }, h('b', { class: 'tk', 'aria-hidden': 'true' }), 'The tick is the 20% line')),
    h('div', { class: 'ax-accs' }, ...rows.map(accCard)),
    note('These are account percentages read about every 15 minutes, not the cost or tokens of one session.')));
}

// ---------- Accounts and models ----------
const sel = (key, value, opts, on, label) => h('select', { class: 'ax-sel', 'aria-label': label, 'data-key': key, onchange: (e) => on(e.target.value) }, ...opts.map(([v, l]) => h('option', { value: v, selected: v === value ? true : null }, l)));
const MODES = [['ask', 'Ask on risky actions'], ['plan', 'Plan only, never execute'], ['auto', 'Approve low risk automatically']];
export function viewAccounts(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), st = S.accounts, rows = A.usage(), f = A.failover(), models = S.models;
  const fo = (key, label, sub, locked) => h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, label), h('span', { class: 'r-note' }, sub)), locked ? pill('ok', 'Always on') : sw({ on: f[key], label, key: 'fo-' + key, onclick: () => { A.setFailover(key, !f[key]); ctx.render(); } }));
  const accountRow = (r, i) => h('div', { class: 'ax-acct', 'data-key': 'ac-' + r.id },
    h('span', { class: 'n', 'aria-hidden': 'true' }, String(i + 1)),
    h('a', { class: 'a-main', href: hrefFor('account', r.id) }, h('span', { class: 'r-name' }, r.label), h('span', { class: 'r-note' }, harnessLabel(r.harness) + ' · ' + r.role + ' · ' + (r.session.left == null ? 'usage unknown' : r.session.left + '% of the session left'))),
    badge('account_health', r.state),
    h('span', { class: 'a-mv' }, h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' up', disabled: i === 0 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, -1), 'Moved up in the failover order.') }, '↑'), h('button', { class: 'btn', type: 'button', 'aria-label': 'Move ' + r.label + ' down', disabled: i === rows.length - 1 ? true : null, onclick: () => done(ctx, A.moveAccount(r.id, 1), 'Moved down in the failover order.') }, '↓')));
  const launch = (p) => {
    const c = A.launch(p.id), pv = A.preview(p.id), har = S.harnesses.filter((x) => x.state !== 'MISSING');
    const set = (k) => (v) => { done(ctx, A.setLaunch(p.id, k, v), 'Launch setting saved (simulated).'); };
    return h('article', { class: 'ax-card ax-launch', 'data-tone': pv.tone === 'ok' ? 'active' : pv.tone, 'data-key': 'ln-' + p.id },
      h('div', { class: 'ck-top' }, h('h2', null, h('a', { href: hrefFor('project', 'prj-' + p.id) }, p.name)), pill(pv.tone === 'ok' ? 'ok' : pv.tone, pv.tone === 'ok' ? 'Can start' : pv.tone === 'blocked' ? 'Cannot start' : 'Waits')),
      h('p', { class: 'ln-prev' }, h('b', null, 'Next mission: '), harnessLabel(pv.harness) + ' · ' + pv.model + (pv.account ? ' · ' + pv.account : '')), h('p', { class: 'ax-note' }, pv.note),
      h('div', { class: 'ax-form' },
        h('label', null, h('span', null, 'Harness'), sel('ln-h-' + p.id, c.harness, har.map((x) => [x.id, x.label]), set('harness'), 'Harness for ' + p.name)),
        h('label', null, h('span', null, 'Model'), sel('ln-m-' + p.id, c.model, models.filter((m) => m.harness === c.harness).map((m) => [m.id, m.label]), set('model'), 'Model for ' + p.name)),
        h('label', null, h('span', null, 'Account'), sel('ln-a-' + p.id, c.account, [['auto', 'Automatic, by failover order'], ...st.filter((a) => a.harness === c.harness).map((a) => [a.id, a.label])], set('account'), 'Account for ' + p.name)),
        h('label', null, h('span', null, 'Approvals'), sel('ln-d-' + p.id, c.mode, MODES, set('mode'), 'Approval mode for ' + p.name)),
        h('label', null, h('span', null, 'Runs at once'), sel('ln-p-' + p.id, String(c.parallel), [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']], set('parallel'), 'Runs at once for ' + p.name)),
        h('p', { class: 'ax-note' }, 'Isolation: required. It cannot be switched off here.')));
  };
  return h('div', { class: 'ax-page' }, axHead(ctx, 'Accounts', 'Accounts and models', 'Three accounts, four models, one default, and the rules that decide which account takes the next mission.'), h('div', { class: 'view' },
    dnote('H10', 'Accounts and models: three accounts in a failover order, four models with one default, per-project launch settings. No token is shown or handled.'),
    cols([
      card('Accounts', 'In failover order. The first available account takes the next mission.', h('div', { class: 'ax-accts' }, ...rows.map(accountRow)), h('p', { class: 'ax-note pad' }, 'A subscription login belongs to you. Archeus never reads, stores, copies, injects or relays the token.')),
      card('Failover rules', 'What happens when an account runs low or out.', h('div', { class: 'ax-rows' },
        fo('handoff', 'Hand off a run when its account is limited', 'The run writes a checkpoint and continues on the next account.'),
        h('div', { class: 'ax-row' }, h('span', { class: 'r-main' }, h('span', { class: 'r-name' }, 'New work waits when the week is low'), h('span', { class: 'r-note' }, 'Your line. Running work finishes; nothing new starts on that account.')), h('span', { class: 'r-ctl' }, f.pauseOn ? sel('fo-at', String(f.pauseAt), [['10', '10% left'], ['20', '20% left'], ['30', '30% left']], (v) => { A.setFailover('pauseAt', Number(v)); ctx.render(); }, 'Line, percent left') : null, sw({ on: f.pauseOn, label: 'New work waits when the week is low', key: 'fo-pauseOn', onclick: () => { A.setFailover('pauseOn', !f.pauseOn); ctx.render(); } }))),
        fo('askHarness', 'Ask before switching to another harness', 'A move from Claude Code to Codex is a card you confirm.'),
        fo('never', 'Never run without isolation', 'There is no unisolated fallback, whatever else fails.', true))),
    ], [
      card('Models', 'The default is what a new mission asks for.', h('div', { class: 'ax-models' }, ...models.map((m) => { const d = A.defaultModel() === m.id; return h('div', { class: 'ax-model', 'data-default': d ? 'true' : 'false', 'data-key': 'md-' + m.id }, h('a', { class: 'm-main', href: hrefFor('model', 'mdl-' + m.id) }, h('span', { class: 'r-name' }, m.label), h('span', { class: 'r-note' }, harnessLabel(m.harness) + ' · tier ' + m.tier)), d ? pill('ok', 'Default') : h('button', { class: 'btn', type: 'button', onclick: () => done(ctx, A.setDefaultModel(m.id), m.label + ' is now the default (simulated).') }, 'Make default')); })),
        h('p', { class: 'ax-note pad' }, 'This is the model Archeus asks for, not proof of which model the provider served.')),
    ]),
    h('h2', { class: 'ax-sh' }, 'Launch settings per project', h('span', null, 'What a new mission starts with, and what would happen right now.')),
    h('div', { class: 'ax-launches' }, ...S.projects.map(launch))));
}

// ---------- Extensions: hooks, MCP servers, agents, automations, clients ----------
function xrow(ctx, o) {
  return h('div', { class: 'ax-xrow', 'data-key': o.key },
    h('a', { class: 'x-main', href: o.href }, h('span', { class: 'r-name' }, o.name), h('span', { class: 'r-note' }, o.meta)),
    h('span', { class: 'x-st' }, o.status), h('span', { class: 'x-last' }, h('span', { class: 'l' }, o.lastLabel || 'Last run'), h('span', null, o.last)), h('span', { class: 'x-sw' }, o.control || null), o.below || null);
}
export function viewExtensions(ctx) {
  const A = areasOf(ctx.sim), S = A.S(), clock = S.clock;
  const when = (t) => (t == null ? 'Never' : clockLabel(t));
  const hooks = A.hooks().map((x) => {
    const key = 'row:' + x.id, flip = () => { const r = A.toggleHook(x.id); done(ctx, r, r.on ? 'Hook switched on (simulated).' : 'Hook switched off (simulated).'); };
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('hook', x.id), name: x.name, meta: x.event + ' · ' + x.matcher, status: pill(x.enabled ? 'ok' : 'paused', x.enabled ? 'Enabled' : 'Disabled'), last: when(x.last),
      control: x.locked ? pill('ok', 'Built in') : sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => (x.enabled && x.sensitive ? ask(ctx, { at: key, text: 'Switch off "' + x.name + '"? An execution can then do this without asking you.', label: 'Switch off', tone: 'danger', run: flip }) : flip()) }), below: inline(ctx, key) });
  });
  const mcps = A.mcp().map((x) => {
    const st = A.mcpStatus(x, clock), t = MCP_TONE[st];
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('mcp', x.id), name: x.name, meta: x.transport + ' · ' + (x.tools.length ? x.tools.length + (x.tools.length === 1 ? ' tool' : ' tools') : 'tools not known') + (st === 'CONNECTED' ? ' · ' + x.calls + ' calls' : ''), status: pill(t[0], t[1]), lastLabel: 'Last call', last: when(x.last),
      control: x.unchecked ? h('span', { class: 'x-na' }, 'Not checked') : sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => { const r = A.toggleMcp(x.id); done(ctx, r, r.on ? 'Connecting (simulated).' : 'Switched off (simulated).'); } }) });
  });
  const agents = A.agents().map((x) => {
    const s = A.agentStatus(x);
    return xrow(ctx, { key: 'x-' + x.id, href: hrefFor('agent', x.id), name: x.name, meta: x.role, status: pill(s.key === 'working' ? 'active' : s.key === 'off' ? 'paused' : s.key === 'ready' ? 'attention' : 'ok', s.key === 'working' ? 'Working' : s.key === 'off' ? 'Off' : s.key === 'ready' ? 'Result waits' : 'Idle'), last: when(x.last), control: sw({ on: x.enabled, label: x.name, key: 'sw-' + x.id, onclick: () => { const r = A.toggleAgent(x.id); done(ctx, r, r.on ? 'Agent switched on (simulated).' : 'Agent switched off (simulated).'); } }), below: s.key === 'working' || s.key === 'ready' ? h('p', { class: 'x-below' }, s.text) : null });
  });
  const autos = S.automations.map((a) => xrow(ctx, { key: 'x-' + a.id, href: hrefFor('automation', a.id), name: a.name, meta: a.trigger, status: badge('automation', a.state), last: a.next_run ? 'Next ' + a.next_run : 'Not scheduled', lastLabel: 'Schedule', control: a.state === 'SUSPENDED' || a.state === 'PENDING_APPROVAL' ? h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('enable', a.id) }, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve') : null, below: a.note ? h('p', { class: 'x-below' }, a.note) : null }));
  const clients = S.devices.map((d) => xrow(ctx, { key: 'x-' + d.id, href: hrefFor('device', d.id), name: d.name, meta: 'Paired client', status: badge('device', d.state), last: d.state === 'ACTIVE' ? 'Now' : 'Revoked', lastLabel: 'Seen' }));
  const jump = (id, l, n) => h('button', { class: 'chip', type: 'button', onclick: () => { const el = document.getElementById(id); if (el) el.scrollIntoView({ block: 'start' }); } }, l, h('span', { class: 'n' }, String(n)));
  return h('div', { class: 'ax-page' }, axHead(ctx, 'Extensions', 'Hooks, MCP servers and agents', 'What can act before, after and beside a run. Each row says its status and when it last ran; a switch changes it for the next run.'), h('div', { class: 'view' },
    dnote('H09', 'Hooks, MCP servers and agents managers: status, last run, enable and disable, and a details sheet for each. Automations and clients are the other Control lists.'),
    h('div', { class: 'chips ax-jump' }, jump('x-hooks', 'Hooks', hooks.length), jump('x-mcp', 'MCP servers', mcps.length), jump('x-agents', 'Agents', agents.length), jump('x-autos', 'Automations', autos.length), jump('x-clients', 'Clients', clients.length)),
    ...[['x-hooks', 'Hooks', 'Run before or after a tool. A hook that guards something asks you to confirm before it is switched off.', hooks], ['x-mcp', 'MCP servers', 'Tools a run can call. A server that writes asks first.', mcps], ['x-agents', 'Agents', 'The roles Core calls. None of them can decide for you.', agents], ['x-autos', 'Automations', 'Work that starts on a schedule or an event.', autos], ['x-clients', 'Clients', 'Paired devices that can read and decide.', clients]]
      .map(([id, t, sub, rows]) => h('section', { class: 'ax-card ax-ext', id }, h('div', { class: 'ax-card-h' }, h('h2', null, t, h('span', { class: 'n' }, String(rows.length))), h('p', null, sub)), h('div', { class: 'ax-xrows' }, ...rows)))));
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
      d.items.length > shown.length ? note((d.items.length - shown.length) + ' more are in Replay and Attention.') : null,
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
    ...k.decide.map((a) => h('a', { class: 'card band ax-stale', href: '#/attention/' + a.id }, h('div', { class: 'top' }, badge('mission', 'APPROVAL_REQUIRED'), h('span', { class: 'why' }, projName(ctx.sim, a.project))), h('p', { class: 'ttl' }, a.presented.what), h('span', { class: 'ax-lock' }, 'Read only: decide when Core is back.'))),
    ...k.review.map((m) => h('a', { class: 'card band ax-stale', href: '#/work/' + m.id }, h('div', { class: 'top' }, badge('mission', m.state), h('span', { class: 'why' }, projName(ctx.sim, m.project))), h('p', { class: 'ttl' }, 'Verified, waiting for your review: ' + m.title), h('span', { class: 'ax-lock' }, 'Read only: accept when Core is back.')))));
}
function offlinePage(ctx, A, name) {
  const S = A.S(), k = keptSummary(S), title = { now: 'Now', work: 'Work', attention: 'Attention' }[name];
  return h('div', { class: 'view ax-offline-page' }, offlineBanner(ctx, A),
    name === 'now' ? h('div', { class: 'now-hero' }, h('p', { class: 'state-sentence ax-stale-sentence' }, 'As of ' + clockLabel(A.offlineAt()) + ': ' + k.sentence), h('p', { class: 'sub2' }, 'This is the last read. It is not live.'), dnote('E12', 'Offline Now: kept missions with their spine drawn outlined, the time it was last seen, and Decide rows read only (D11).')) : h('header', { class: 'page-head', style: 'padding:0' }, h('div', null, h('h1', null, title), h('p', { class: 'sub' }, 'Offline: last seen ' + clockLabel(A.offlineAt())))),
    offlineDecide(ctx, A, k), ...(name === 'attention' ? [] : offlineList(ctx, A)));
}

export function decorate(ctx, content) {
  const A = areasOf(ctx.sim), name = ctx.route.name;
  if (A.isOffline() && ['now', 'work', 'attention'].includes(name)) return offlinePage(ctx, A, name);
  if (A.isOffline() && !['terminal'].includes(name)) { const v = content.querySelector('.view') || content; v.prepend(offlineBanner(ctx, A)); return content; }
  if (name === 'now') { content.append(digestPanel(ctx, A)); return content; }
  if (name === 'work') {
    const view = content.querySelector('.view'), ideas = [...view.querySelectorAll('.panel')].find((p) => p.querySelector('h2') && /^Ideas/.test(p.querySelector('h2').textContent));
    if (ideas) ideas.replaceWith(ideasPanel(ctx, A));
    const first = view.querySelector('.panel'); if (first) first.before(pinnedPanel(ctx, A)); else view.append(pinnedPanel(ctx, A));
  }
  return content;
}
