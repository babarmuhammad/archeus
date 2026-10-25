// Screens. Each view takes ctx = { sim, nav(hash), act(kind, id), toast(text), route, ui } and returns the content node.
// Everything shown comes from the simulation (fixtures), and every screen says so in its header.
import { h, s } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel, REPLAY_CATEGORIES, SPEEDS } from '../sim.js';
import { missionGroups } from '../term.js';
import { spineRow, spineCard, spineInspector } from './spine.js';
import { drawMap } from './map.js';
import { THEMES, DEVICES } from './store.js';
import * as store from './store.js';

export const ROUTES = [
  { id: 'now', label: 'Now', icon: 'now' }, { id: 'work', label: 'Work', icon: 'work' }, { id: 'attention', label: 'Attention', icon: 'attention' },
  { id: 'map', label: 'Map', icon: 'map' }, { id: 'replay', label: 'Replay', icon: 'replay' }, { id: 'chat', label: 'Chat', icon: 'chat' },
  { id: 'security', label: 'Security', icon: 'security' }, { id: 'health', label: 'Health', icon: 'health' }, { id: 'accounts', label: 'Accounts', icon: 'accounts' },
  { id: 'settings', label: 'Settings', icon: 'settings' }
];
export const BOTTOM = ['now', 'work', 'attention', 'chat'];

export const projName = (sim, id) => (sim.state.projects.find((p) => p.id === id) || { name: '' }).name;
export const word = (machine, state) => present(machine, state).label;

export function badge(machine, state) {
  const p = present(machine, state);
  return h('span', { class: 'badge', 'data-role': p.cls }, h('span', { class: 'g', 'aria-hidden': 'true' }, p.glyph), h('span', { class: 'w' }, p.label));
}

export function head(ctx, title, extra) {
  const st = ctx.sim.state;
  return h('header', { class: 'page-head' },
    h('div', null, h('h1', null, title),
      h('p', { class: 'sub' }, h('span', { class: 'sim-tag' }, 'SIMULATED'), ' Fixture data, nothing is connected to a Core. Simulated time ', h('span', { 'data-live': 'clock' }, clockLabel(st.clock)), st.playing ? ' (running, x' + st.speed + ')' : ' (paused)')),
    extra || null);
}

export const panel = (title, n, ...kids) => h('section', { class: 'panel' }, h('h2', null, h('span', { class: 'gt' }, title), n != null ? h('span', { class: 'n' }, String(n)) : null), ...kids);
export const dnote = (id, text) => h('p', { class: 'dnote' }, h('b', null, 'Decision ' + id), ' \u00b7 ' + text);
export const empty = (t) => h('p', { class: 'empty' }, t);

export function missionRow(ctx, m, base) {
  const p = present('mission', m.state);
  const x = Object.values(ctx.sim.state.executions).find((e) => e.mission === m.id && (e.state === 'RUNNING' || e.state === 'LOST'));
  const meta = [projName(ctx.sim, m.project), m.branch, m.reason || (x ? ctx.sim.reading(x) : null)].filter(Boolean).join(' · ');
  return h('a', { class: 'mrow', href: '#/' + base + '/' + m.id, 'aria-current': ctx.route.id === m.id ? 'true' : null, 'data-key': 'm-' + m.id },
    h('span', { class: 't' }, badge('mission', m.state), h('span', { class: 'name' }, m.title)),
    h('span', { class: 'm' }, meta, x ? h('span', { class: 'vh' }, ' ') : null),
    h('span', { class: 'sp' }, spineRow(m.state, m.held_from)));
}

function attentionItem(ctx, a) {
  const sim = ctx.sim, m = a.mission_id ? sim.state.missions[a.mission_id] : null;
  const need = a.group === 'Decide' || a.group === 'Review';
  const open = a.kind === 'approval' ? '#/attention/' + a.ref : m ? '#/attention/' + m.id : null;
  const btns = [];
  if (a.kind === 'knowledge') btns.push(h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('confirm', a.ref) }, 'Remember'), h('button', { class: 'btn', type: 'button', onclick: () => ctx.act('retract', a.ref) }, 'Not this'));
  else if (a.kind === 'automation') btns.push(h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('enable', a.ref) }, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve'));
  else if (a.kind === 'account') btns.push(h('a', { class: 'btn', href: '#/settings' }, 'Open Settings'));
  else if (open) btns.push(h('a', { class: 'btn primary', href: open }, a.kind === 'approval' ? 'Open decision' : a.group === 'Review' ? 'Open review' : 'Open'));
  return h('article', { class: 'card' + (a.group === 'Decide' ? ' band' : ''), 'data-key': a.id },
    h('div', { class: 'top' }, a.kind === 'approval' || a.kind === 'verification' || a.kind === 'mission' ? badge('mission', m ? m.state : 'APPROVAL_REQUIRED') : h('span', { class: 'badge', 'data-role': need ? 'needs_you' : 'blocked' }, h('span', { class: 'g', 'aria-hidden': 'true' }, need ? '◆' : '■'), h('span', { class: 'w' }, a.kind === 'knowledge' ? 'Candidate' : a.kind === 'automation' ? 'Automation' : 'Account')),
      h('span', { class: 'why' }, [projName(sim, a.project_id), a.since ? 'since ' + clockLabel(a.since) : ''].filter(Boolean).join(' · '))),
    h('p', { class: 'ttl' }, a.reason),
    m ? spineCard(m.state, m.held_from) : null,
    btns.length ? h('div', { class: 'actions' }, ...btns) : null);
}

// ---------- Now ----------
export function coreMark(live, n) {
  return h('div', { class: 'core', 'data-core': 'idle', 'data-live': live ? 'true' : 'false', 'data-n': String(n) },
    s('svg', { class: 'core-mark', viewBox: '0 0 44 44', 'aria-hidden': 'true', focusable: 'false' }, s('circle', { class: 'o', cx: 22, cy: 22, r: 20 }), s('circle', { class: 'i', cx: 22, cy: 22, r: 8 })),
    h('span', { class: 'core-txt' }, n + ' running'));
}

function mapPanel(ctx, wide, title) {
  const sim = ctx.sim, st = sim.state;
  const live = sim.liveWork();
  const svg = s('svg', { class: 'map', role: 'img', 'aria-label': 'Live map of ' + st.projects.length + ' projects and ' + Object.keys(st.missions).length + ' missions. The list beside it has the same content.' });
  const box = h('div', { class: 'map-box' + (wide ? ' wide' : '') }, svg, coreMark(live.length > 0, live.length));
  ctx.mounts.push(() => drawMap(svg, box, sim, ctx.route.id));
  const legend = h('div', { class: 'legend' },
    h('span', { class: 'k' }, '○ Project'), h('span', { class: 'k' }, '● Mission'), h('span', { class: 'k' }, '▲ Execution'), h('span', { class: 'k' }, '◆ Decision'),
    h('span', { class: 'k' }, 'Centre: Core, ', live.length ? live.length + ' running' : 'nothing running'));
  return h('section', { class: 'panel' }, h('h2', null, title || 'Live map', h('span', { class: 'n' }, 'vector, redrawn at every size')), box, legend);
}

export function viewNow(ctx) {
  const sim = ctx.sim, st = sim.state, att = sim.attention();
  const decide = att.filter((a) => a.group === 'Decide').slice(0, 3);
  const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  const upcoming = Object.values(st.missions).filter((m) => ['planning', 'approved'].includes(present('mission', m.state).cls));
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-6).reverse();
  return h('div', { class: 'view' },
    h('div', { class: 'now-hero' }, h('p', { class: 'state-sentence', 'data-key': 'sentence' }, sim.sentence()), h('p', { class: 'sub2' }, 'The sentence is built only from Core state words and counts.'), dnote('A10', 'The serif display font is used for this one line only.'), dnote('A12', 'The core mark sits on the centre of the live map, with its static twin under reduced motion.')),
    h('div', { class: 'cols two now-cols' },
      mapPanel(ctx, false),
      h('div', { class: 'col', style: 'gap:var(--gut)' },
        panel('Needs you', att.filter((a) => a.group === 'Decide').length, decide.length ? h('div', { class: 'stack' }, ...decide.map((a) => attentionItem(ctx, a))) : empty('Nothing is waiting for a decision.'),
          att.filter((a) => a.group !== 'Decide').length ? h('div', { class: 'actions', style: 'padding:12px 16px 16px' }, h('a', { class: 'btn', href: '#/attention' }, att.filter((a) => a.group !== 'Decide').length + ' more in Attention')) : null),
        panel('Happening now', live.length, live.length ? h('div', { class: 'stack' }, ...live.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is running.')))),
    h('div', { class: 'cols eq' },
      panel('Upcoming', upcoming.length, upcoming.length ? h('div', { class: 'stack' }, ...upcoming.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is planned or approved.')),
      panel('Recent decisions and changes', recent.length, h('div', { class: 'body' }, ...recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))), recent.length ? null : empty('Nothing has changed yet.')))));
}

// ---------- Work ----------
export function viewWork(ctx) {
  const sim = ctx.sim, st = sim.state;
  const groups = missionGroups(sim);
  return h('div', null, head(ctx, 'Work'), h('div', { class: 'view' },
    dnote('E03', 'Missions grouped by what they wait on, as in V1; the spine shows where each one is (A13).'),
    ...groups.map((g) => panel(g.title, g.items.length, h('div', { class: 'stack' }, ...g.items.map((m) => missionRow(ctx, m, 'work'))))),
    panel('Ideas', st.ideas.length, h('div', { class: 'body' }, ...st.ideas.map((i) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, i.title), h('span', { class: 'b' }, projName(sim, i.project) + ' · ' + word('idea', i.state))))))));
}

// ---------- Attention ----------
export function viewAttention(ctx) {
  const att = ctx.sim.attention();
  const groups = ['Decide', 'Review', 'Unblock'].map((g) => [g, att.filter((a) => a.group === g)]).filter((x) => x[1].length);
  return h('div', null, head(ctx, 'Attention'), h('div', { class: 'view' },
    dnote('E20', 'Groups Decide, Review, Unblock; the band is a 12 % tint with the word in ink (B09). No acknowledge or snooze: that needs a Core record.'),
    groups.length ? groups.map(([g, items]) => h('section', { class: 'col', style: 'gap:8px' }, h('h2', { class: 'group-h' }, g, h('span', { class: 'n' }, items.length + (g === 'Decide' ? ' · asks you to decide' : g === 'Review' ? ' · results to accept' : ' · work that needs a person'))),
      h('div', { class: 'cols eq' }, ...items.map((a) => h('div', { class: 'panel' }, attentionItem(ctx, a)))))) : [panel('Attention', 0, empty('Nothing waits on you.'))]));
}

// ---------- Map ----------
export function viewMap(ctx) {
  const sim = ctx.sim, st = sim.state;
  return h('div', null, head(ctx, 'Map'), h('div', { class: 'view' },
    dnote('A03', 'A vector constellation redrawn at every size; the list beside it is the text mirror and where selection happens in slice 1.'),
    h('div', { class: 'cols two' }, mapPanel(ctx, true, 'Constellation'),
      h('div', { style: 'display:flex;flex-direction:column;gap:var(--gut)' },
        ...st.projects.map((p) => { const ms = Object.values(st.missions).filter((m) => m.project === p.id); return panel(p.name, ms.length, h('p', { class: 'lede' }, p.note), h('div', { class: 'stack' }, ...ms.map((m) => missionRow(ctx, m, 'map')))); })))));
}

// ---------- Replay ----------
export function viewReplay(ctx) {
  const sim = ctx.sim, st = sim.state;
  const ms = Object.values(st.missions);
  const m = st.missions[ctx.route.id] || st.missions['m-date'];
  const r = sim.replay(m.id);
  const sel = Math.min(ctx.ui.replaySel == null ? r.rows.length - 1 : ctx.ui.replaySel, r.rows.length - 1);
  const row = r.rows[sel];
  const move = (d) => { ctx.ui.replaySel = Math.max(0, Math.min(r.rows.length - 1, sel + d)); ctx.render(); };
  return h('div', null, head(ctx, 'Replay'), h('div', { class: 'view' },
    dnote('A19', 'Replay answers from what Core recorded: nine categories, a reason when it cannot tell, nothing that can be re-run (G03, G11).'),
    h('div', { class: 'chips' }, ...ms.map((x) => h('a', { class: 'chip', href: '#/replay/' + x.id, 'aria-current': x.id === m.id ? 'true' : null }, x.title))),
    h('div', { class: 'cols two' },
      panel(m.title, r.rows.length, h('div', { class: 'lede' }, 'What Core recorded, in order. Each step carries a Replay category and who settled it. Nothing here can be re-run.'),
        r.rows.length ? h('div', { class: 'tl' }, ...r.rows.map((x, i) => h('button', { class: 'tl-row', type: 'button', 'aria-current': i === sel ? 'true' : null, onclick: () => { ctx.ui.replaySel = i; ctx.render(); }, 'data-key': 'tl-' + x.seq },
          h('span', { class: 'tm' }, x.time), h('span', { class: 'mn' }, h('b', null, x.title), h('span', { class: 'cat', 'data-cat': x.category }, x.category))))) : empty('No recorded steps for this mission.'),
        r.pruned ? h('p', { class: 'note' }, 'Older steps were pruned from the event log, so anything before them is UNKNOWN, not "nothing happened".') : null),
      h('div', { style: 'display:flex;flex-direction:column;gap:var(--gut)' },
        panel('Selected step', null, row ? h('div', { class: 'body' }, h('dl', { class: 'kv' },
          h('dt', null, 'Step'), h('dd', null, row.title), h('dt', null, 'Time'), h('dd', null, row.time),
          h('dt', null, 'Category'), h('dd', null, h('span', { class: 'cat', 'data-cat': row.category }, row.category)),
          h('dt', null, 'Trigger'), h('dd', null, row.trigger || 'none recorded'),
          h('dt', null, 'Settled by'), h('dd', null, row.settled_by), h('dt', null, 'Record'), h('dd', null, row.subject.kind + ' ' + row.subject.id)),
          h('div', { class: 'actions', style: 'margin-top:12px' }, h('button', { class: 'btn', type: 'button', disabled: sel <= 0, onclick: () => move(-1) }, 'Earlier'), h('button', { class: 'btn', type: 'button', disabled: sel >= r.rows.length - 1, onclick: () => move(1) }, 'Later'))) : empty('Nothing selected.')),
        panel('Categories', REPLAY_CATEGORIES.length, h('div', { class: 'body chips' }, ...REPLAY_CATEGORIES.map((c) => h('span', { class: 'chip static' }, h('span', { class: 'cat', 'data-cat': c }, c))))),
        panel('Not recorded', null, h('p', { class: 'note', style: 'padding-top:8px' }, r.gaps))))));
}

// ---------- Settings ----------
export function simControls(ctx) {
  const sim = ctx.sim, st = sim.state;
  const pr = (kind, label) => h('button', { class: 'btn', type: 'button', onclick: () => ctx.act(kind) }, label);
  return h('div', { class: 'col', style: 'gap:10px' },
    h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'button', 'aria-pressed': st.playing ? 'true' : 'false', onclick: () => ctx.act(st.playing ? 'pause-sim' : 'play-sim') }, st.playing ? 'Pause' : 'Play'),
      h('div', { class: 'sel-wrap', style: 'padding:0' }, h('label', { for: 'sim-speed-' + (ctx.where || 'a') }, 'Speed'), h('select', { id: 'sim-speed-' + (ctx.where || 'a'), onchange: (e) => ctx.act('speed', e.target.value) }, ...SPEEDS.map((x) => h('option', { value: String(x), selected: x === st.speed ? true : null }, 'x' + x))))),
    h('div', { class: 'actions' }, pr('trigger-approval', 'Trigger an approval'), pr('inject-failure', 'Inject a failure'), pr('inject-spawn', 'Break the harness'), pr('reset', 'Reset')),
    h('p', { class: 'note', style: 'padding:0' }, 'Simulated clock ', h('span', { 'data-live': 'clock' }, clockLabel(st.clock)), '. One real second is ten simulated seconds at x1. Same seed, same story.'));
}

export const meter = (label, v, cap) => h('div', { class: 'meter' }, h('div', { class: 'cap' }, h('span', null, label), h('span', null, v == null ? 'unknown' : Math.round(v) + '%')),
  h('div', { class: 'bar' + (v == null ? ' unk' : v >= 85 ? ' warn' : ''), role: 'img', 'aria-label': label + ' ' + (v == null ? 'unknown' : Math.round(v) + ' percent') }, v == null ? null : h('i', { style: 'width:' + Math.min(100, v) + '%' })), cap ? h('div', { class: 'cap' }, h('span', null, cap)) : null);

export function viewSettings(ctx) {
  const sim = ctx.sim, st = sim.state;
  const row = (a, b) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, a), h('span', { class: 'b' }, b));
  return h('div', null, head(ctx, 'Settings'), h('div', { class: 'view' },
    dnote('A04', 'Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05).'),
    h('div', { class: 'cols eq' },
      panel('Appearance', null, h('div', { class: 'body' }, h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap)' }, 'Theme'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Theme' }, ...THEMES.map((t) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('theme') === t.id ? 'true' : 'false', onclick: () => { store.set('theme', t.id); ctx.render(); } }, t.label))),
        h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap);margin-top:16px' }, 'Motion'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Motion' }, ...[['system', 'Follow the system'], ['full', 'Full'], ['reduced', 'Reduced (Quiet)']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('motion') === id ? 'true' : 'false', onclick: () => { store.set('motion', id); ctx.render(); } }, l))),
        h('p', { class: 'note', style: 'padding:8px 0 0' }, 'The core mark is the one thing that moves: a 6 second breath while a fresh read shows live work. Reduced motion shows it still, with a count.'))),
      panel('Device preview', null, h('div', { class: 'body' }, h('div', { class: 'chips', role: 'group', 'aria-label': 'Device preview' }, ...DEVICES.map((d) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('device') === d.id ? 'true' : 'false', onclick: () => ctx.setDevice(d.id) }, d.label + (d.w ? ' ' + d.w : ''))), h('a', { class: 'chip', href: '#/terminal' }, 'Open the terminal view')))),
      panel('Simulation', null, h('div', { class: 'body' }, simControls(Object.assign({}, ctx, { where: 'set' }))))),
    h('div', { class: 'cols eq' },
      panel('Language and notes', null, h('div', { class: 'body' }, h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap)' }, 'Language'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Language' }, ...[['en', 'English'], ['it', 'Italiano']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('lang') === id ? 'true' : 'false', onclick: () => ctx.setLang(id) }, l))),
        h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap);margin-top:16px' }, 'Decision notes'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Decision notes' }, ...[['on', 'Show'], ['off', 'Hide']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('notes') === id ? 'true' : 'false', onclick: () => ctx.setNotes(id) }, l))),
        dnote('A15', 'Everything on screen is simulated and says so; no Core is connected.'))),
      panel('About this prototype', null, h('div', { class: 'body' }, h('p', null, 'V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock.'),
        h('p', { style: 'margin-top:8px' }, 'Slice 1 of about 6: the shell, the simulation, the tokens and the layout probe. The map, mission views, chat and terminal are filled in by later slices.'))))));
}

// ---------- inspector content ----------
export function inspectorMission(ctx, m) {
  const sim = ctx.sim, st = sim.state, p = present('mission', m.state);
  const tab = ctx.ui.tab || 'outcome';
  const tabs = [['outcome', 'Outcome'], ['plan', 'Plan'], ['now', 'Now'], ['evidence', 'Evidence'], ['timeline', 'Timeline']];
  const tasks = m.tasks.map((id) => st.tasks[id]);
  const execs = Object.values(st.executions).filter((x) => x.mission === m.id);
  let body;
  if (tab === 'outcome') body = h('div', { class: 'insp-body' }, h('div', null, h('h3', null, 'Where it is'), spineInspector(m.state, m.held_from), dnote('A13', 'Six stations named with Core\'s own state words; a hold with no held_from is drawn unknown, never guessed (D03).')),
    h('div', null, h('h3', null, 'Facts'), h('dl', { class: 'kv' }, h('dt', null, 'State'), h('dd', null, badge('mission', m.state)), h('dt', null, 'Project'), h('dd', null, projName(sim, m.project)), h('dt', null, 'Branch'), h('dd', null, m.branch), h('dt', null, 'Origin'), h('dd', null, m.origin), h('dt', null, 'Plan'), h('dd', null, m.plan_version ? 'version ' + m.plan_version : 'none yet'), h('dt', null, 'Tasks'), h('dd', null, tasks.filter((t) => t.state === 'SUCCEEDED').length + ' of ' + tasks.length + ' done'), m.reason ? [h('dt', null, 'Why'), h('dd', null, m.reason)] : null)));
  else if (tab === 'plan') body = h('div', { class: 'insp-body' }, h('div', null, h('h3', null, 'Tasks'), tasks.length ? tasks.map((t) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, t.title), badge('task', t.state))) : h('p', null, 'No plan yet.')),
    h('div', null, h('h3', null, 'Plan versions'), Object.values(st.plans).filter((x) => x.mission === m.id).map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, 'Version ' + x.version), badge('plan', x.state)))));
  else if (tab === 'now') body = h('div', { class: 'insp-body' }, h('h3', null, 'Executions'), execs.length ? execs.map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, x.id, h('span', { class: 'sp-text', style: 'display:block;padding:0' }, x.harness + ' · ' + x.model + (ctx.sim.reading(x) ? ' · ' + ctx.sim.reading(x) : ''))), badge('execution', x.state))) : h('p', null, 'No execution yet.'));
  else if (tab === 'evidence') { const vs = Object.values(st.verifications).filter((x) => x.mission === m.id); body = h('div', { class: 'insp-body' }, h('h3', null, 'Verification'), vs.length ? vs.map((v) => h('div', null, h('div', { class: 'row-line' }, h('span', { class: 'a' }, v.id + ' · base ' + v.base_revision), badge('verification', v.state)), ...v.checks.map((c) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, c.name), h('span', { class: 'b' }, c.result))))) : h('p', null, 'Nothing has been verified yet.')); }
  else { const r = sim.replay(m.id); body = h('div', { class: 'insp-body' }, h('h3', null, 'Last recorded steps'), ...r.rows.slice(-6).reverse().map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, x.title), h('span', { class: 'b' }, x.time + ' · ' + x.category))), h('a', { class: 'btn', href: '#/replay/' + m.id }, 'Open Replay')); }
  const actions = [];
  const A = (kind, label, primary) => h('button', { class: 'btn' + (primary ? ' primary' : ''), type: 'button', onclick: () => ctx.act(kind, m.id) }, label);
  if (m.state === 'BLOCKED') actions.push(A('unblock', 'Answer and unblock', true), A('cancel', 'Cancel mission'));
  else if (m.state === 'PAUSED') actions.push(A('resume', 'Resume', true), A('cancel', 'Cancel mission'));
  else if (m.state === 'FAILED') actions.push(A('replan', 'Replan', true), A('cancel', 'Cancel mission'));
  else if (m.state === 'REVIEWING') actions.push(A('accept', 'Accept', true), A('changes', 'Request changes'));
  else if (m.state === 'EXECUTING') actions.push(A('pause', 'Pause'));
  else if (m.state === 'APPROVAL_REQUIRED' && m.approval) actions.push(h('a', { class: 'btn primary', href: '#/attention/' + m.approval }, 'Open decision'));
  else if (m.state === 'CREATED') actions.push(A('cancel', 'Cancel mission'));
  return h('div', null,
    h('div', { class: 'grab', 'aria-hidden': 'true' }),
    h('div', { class: 'insp-head' }, h('div', null, h('h2', null, m.title), h('p', { class: 'm' }, projName(sim, m.project) + ' · ' + m.branch)), h('button', { class: 'btn quiet', type: 'button', 'aria-label': 'Close details', onclick: () => ctx.closeInsp() }, 'Close')),
    h('div', { class: 'tabs', role: 'tablist' }, ...tabs.map(([id, l]) => h('button', { class: 'tab', type: 'button', role: 'tab', 'aria-selected': tab === id ? 'true' : 'false', onclick: () => { ctx.ui.tab = id; ctx.render(); } }, l))),
    body, actions.length ? h('div', { class: 'insp-foot' }, ...actions) : null);
}

export function inspectorApproval(ctx, a) {
  const sim = ctx.sim, m = sim.state.missions[a.mission];
  const open = a.state === 'PENDING';
  return h('div', null,
    h('div', { class: 'grab', 'aria-hidden': 'true' }),
    h('div', { class: 'insp-head' }, h('div', null, h('h2', null, a.kind === 'plan' ? 'Approve this plan?' : 'Allow this action?'), h('p', { class: 'm' }, m.title + ' · ' + projName(sim, a.project))), h('button', { class: 'btn quiet', type: 'button', 'aria-label': 'Close decision', onclick: () => ctx.closeInsp() }, 'Close')),
    h('div', { class: 'insp-body' },
      h('div', null, h('h3', null, 'What'), h('p', null, a.presented.what)),
      h('div', null, h('h3', null, 'Why it asks'), h('p', null, a.presented.why)),
      h('div', null, h('h3', null, 'What Core does next'), h('p', null, a.presented.consequence)),
      h('div', null, h('h3', null, 'Where the mission is'), spineInspector(m.state, m.held_from)),
      h('p', { class: 'sp-text' }, open ? 'Expires ' + clockLabel(a.expires_at) + '. This is a simulated decision: nothing is run, sent or spent.' : 'Decided: ' + word('approval', a.state) + '.')),
    open ? h('div', { class: 'insp-foot' }, h('button', { class: 'btn primary decide', type: 'button', onclick: () => ctx.act('approve', a.id) }, 'Approve'), h('button', { class: 'btn danger decide', type: 'button', onclick: () => ctx.act('reject', a.id) }, 'Reject')) : null);
}

export function viewAccounts(ctx) {
  const sim = ctx.sim, st = sim.state;
  const row = (a, b) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, a), h('span', { class: 'b' }, b));
  return h('div', null, head(ctx, 'Accounts'), h('div', { class: 'view' },
    dnote('H03', 'Accounts, models and usage: unknown stays "unknown", never 0. Usage comes only from the existing usage reader; no token is shown.'),
    h('div', { class: 'cols eq' },
      panel('Accounts and usage', st.accounts.length, h('div', { class: 'body', style: 'display:flex;flex-direction:column;gap:14px' }, ...st.accounts.map((a) => h('div', null, h('div', { class: 'row-line', style: 'padding-top:0' }, h('span', { class: 'a' }, a.label), badge('account_health', a.state)),
        meter('5 hour window', st.usage[a.id].window5h, st.usage[a.id].resets), meter('Week', st.usage[a.id].week))))),
      panel('Models and harnesses', st.models.length, h('div', { class: 'body' }, ...st.models.map((m) => row(m.label, m.harness + ' · ' + m.tier)), h('div', { class: 'sep' }),
        ...st.harnesses.map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, x.label, x.breaker.state !== 'closed' ? ' · breaker ' + x.breaker.state.replace('_', ' ') : ''), h('span', { class: 'b' }, x.breaker.last_error && x.breaker.state !== 'closed' ? x.breaker.last_error : x.state.toLowerCase()))))),
      panel('Automations', st.automations.length, h('div', { class: 'body' }, ...st.automations.map((a) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, a.name, h('span', { class: 'sp-text', style: 'display:block;padding:0' }, a.trigger)), badge('automation', a.state))))),
      panel('Hooks, MCP servers and agents', st.hooks.length + st.mcp.length + st.agents.length, h('div', { class: 'body' }, ...st.hooks.map((x) => row('Hook · ' + x.name, x.event + ' · ' + x.state.toLowerCase())), ...st.mcp.map((x) => row('MCP · ' + x.name, x.state.toLowerCase())), ...st.agents.map((x) => row('Agent · ' + x.name, x.tier)))),
      panel('Clients', st.devices.length, h('div', { class: 'body' }, ...st.devices.map((d) => row(d.name, d.state.toLowerCase())))))));
}
